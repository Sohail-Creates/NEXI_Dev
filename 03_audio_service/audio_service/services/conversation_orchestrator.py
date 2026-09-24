"""
Conversation Orchestrator for NEXI Audio Service.
Manages complete conversation pipeline: Audio Input → STT → LLM → TTS → Playback.

Phases 5-9 Implementation:
- Phase 5: Async orchestration with proper service communication
- Phase 6: Integration with test suite and UI
- Phase 7: Comprehensive error handling and recovery
- Phase 8: Resource lifecycle management
- Phase 9: Performance optimization and monitoring
"""

import logging
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import aiohttp
from shared.security import merge_internal_headers
from config.ssl_config import client_ssl_context

try:
    from shared.focus_mode import FocusModeClient
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parents[3]))
    from shared.focus_mode import FocusModeClient

from audio_service.config import CONVERSATION_CONFIG
from audio_service.services.conversation_state import ConversationStateManager, ConversationState

logger = logging.getLogger(__name__)


class OrchestrationError(Exception):
    """Base exception for orchestration errors."""
    pass


class ServiceCommunicationError(OrchestrationError):
    """Raised when service communication fails."""
    pass


@dataclass
class ConversationTurn:
    """Single conversation turn with all context."""
    user_id: str
    user_text: str
    transcript_language: str = "en"
    mood: Optional[str] = None
    objects_detected: list = field(default_factory=list)
    knowledge_context: Optional[str] = None
    llm_response_text: Optional[str] = None
    tts_audio_bytes: Optional[bytes] = None
    timestamp: datetime= field(default_factory=datetime.now)
    duration_ms: int = 0
    error: Optional[str] = None


class ConversationOrchestrator:
    """
    Orchestrates complete conversation workflow across NEXI services.
    
    Features:
    - Async/await for non-blocking operations
    - Service communication with retries
    - State machine integration
    - Error recovery with fallbacks
    - Resource pooling
    - Performance tracking
    
    Architecture:
        Client Application
            ↓
        ConversationOrchestrator
            ├─ Audio Service (recording, STT, verification)
            ├─ Vision Service (object detection, mood)
            ├─ TeachMe Service (knowledge retrieval)
            ├─ LLM Service (text generation)
            ├─ TTS Service (speech synthesis)
            └─ PlaybackManager (audio playback)
    """
    
    def __init__(
        self,
        conversation_state_manager: ConversationStateManager,
        audio_service_url: str = "https://localhost:8002",
        vision_service_url: str = "https://localhost:8001",
        teachme_service_url: str = "https://localhost:8004",
        central_service_url: str = "https://localhost:8000",
        tts_service_url: str = "https://localhost:8003",
        timeout: int = 30,
        max_retries: int = 3,
        focus_mode_client=None,
    ):
        """
        Initialize orchestrator with service URLs.
        
        Args:
            conversation_state_manager: Shared state manager
            audio_service_url: Audio service endpoint
            vision_service_url: Vision service endpoint
            teachme_service_url: Knowledge service endpoint
            central_service_url: Central restricted-RAG endpoint
            tts_service_url: TTS service endpoint
            timeout: Request timeout in seconds
            max_retries: Number of retry attempts for failed requests
        """
        self.state_manager = conversation_state_manager
        self.audio_url = audio_service_url
        self.vision_url = vision_service_url
        self.teachme_url = teachme_service_url
        self.central_url = central_service_url
        self.tts_url = tts_service_url
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.focus_mode_client = focus_mode_client or FocusModeClient()
        
        # Session pool
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Metrics
        self.turns_processed = 0
        self.total_latency_ms = 0
        
        logger.info(
            f"ConversationOrchestrator initialized: "
            f"audio={audio_service_url}, rag={central_service_url}, tts={tts_service_url}"
        )
    
    async def start(self):
        """Start orchestrator (create session pool)."""
        if self.session is None:
            self.session = aiohttp.ClientSession(
                timeout=self.timeout,
                connector=aiohttp.TCPConnector(ssl=client_ssl_context(self.central_url)),
            )
            logger.info("Orchestrator session pool started")
    
    async def stop(self):
        """Stop orchestrator (close session pool)."""
        if self.session:
            await self.session.close()
            self.session = None
            logger.info("Orchestrator session pool closed")
    
    async def _get_with_retry(self, url: str, **kwargs) -> Optional[Dict]:
        """
        Make GET request with retries.
        
        Args:
            url: Endpoint URL
            **kwargs: Additional aiohttp arguments
            
        Returns:
            Response JSON or None if all retries failed
        """
        if not self.session:
            raise OrchestrationError("Session not started. Call start() first.")
        
        kwargs["headers"] = merge_internal_headers(kwargs.get("headers"))
        for attempt in range(self.max_retries):
            try:
                async with self.session.get(url, **kwargs) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        logger.warning(f"GET {url}: status {resp.status}")
            except Exception as e:
                logger.warning(f"GET retry {attempt + 1}/{self.max_retries}: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
        
        return None
    
    async def _post_with_retry(
        self, url: str, json_data: Dict = None, data=None,
        audio_file: tuple[str, bytes] | None = None, expect_audio: bool = False, **kwargs
    ) -> Optional[Dict | bytes]:
        """
        Make POST request with retries.
        
        Args:
            url: Endpoint URL
            json_data: JSON payload
            data: Raw data payload
            **kwargs: Additional aiohttp arguments
            
        Returns:
            Response JSON or None if all retries failed
        """
        if not self.session:
            raise OrchestrationError("Session not started. Call start() first.")
        
        kwargs["headers"] = merge_internal_headers(kwargs.get("headers"))
        for attempt in range(self.max_retries):
            try:
                request_data = data
                if audio_file is not None:
                    request_data = aiohttp.FormData()
                    request_data.add_field(
                        "file", audio_file[1], filename=audio_file[0], content_type="audio/wav"
                    )
                async with self.session.post(
                    url,
                    json=json_data,
                    data=request_data,
                    **kwargs
                ) as resp:
                    if resp.status in [200, 201]:
                        if expect_audio:
                            if not resp.content_type.startswith("audio/"):
                                logger.error("Expected audio from %s, received %s", url, resp.content_type)
                                return None
                            return await resp.read()
                        return await resp.json()
                    else:
                        logger.warning(f"POST {url}: status {resp.status}")
            except Exception as e:
                logger.warning(f"POST retry {attempt + 1}/{self.max_retries}: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
        
        return None
    
    async def transcribe_audio(
        self,
        audio_file_path: str,
        language: str = "en"
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Transcribe audio file using Audio Service STT.
        
        Args:
            audio_file_path: Path to WAV file from VAD recording
            language: Language hint ('en' or 'ur')
            
        Returns:
            Tuple of (transcribed_text, detected_language)
        """
        try:
            logger.info(f"Transcribing audio: {audio_file_path}")
            
            with open(audio_file_path, 'rb') as f:
                audio_data = f.read()
            
            result = await self._post_with_retry(
                f"{self.audio_url}/api/v1/transcribe",
                audio_file=(Path(audio_file_path).name, audio_data),
            )
            
            if result and result.get("success"):
                text = result.get("text", "")
                detected_lang = result.get("language", language)
                logger.info(f"Transcribed ({detected_lang}): {text[:50]}...")
                return text, detected_lang
            else:
                logger.error(f"Transcription failed: {result}")
                return None, None
        
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return None, None

    async def verify_speaker(self, audio_file_path: str) -> tuple[str, float] | None:
        """Use Audio's existing speaker matcher before any user-scoped RAG call."""
        from audio_service.routes.advanced_routes import get_speaker_service

        speaker_service = get_speaker_service()
        user_id, confidence = await asyncio.to_thread(
            speaker_service.verify_speaker, audio_file_path
        )
        threshold = speaker_service.get_verification_threshold()
        if user_id == "unknown" or confidence < threshold:
            logger.warning("Speaker verification rejected: confidence=%.4f", confidence)
            return None
        return user_id, confidence
    
    async def generate_llm_response(
        self,
        user_text: str,
        user_id: str,
        language: str = "en",
        context: Optional[Dict] = None
    ) -> Optional[str]:
        """
        Generate LLM response for user text.
        
        Args:
            user_text: User's input text
            user_id: User identifier for context window
            language: Language ('en' or 'ur')
            context: Additional context (mood, objects, knowledge)
            
        Returns:
            Generated response text or None if failed
        """
        try:
            await self.focus_mode_client.async_defer_if_needed("conversation")
            logger.info(f"Calling LLM for user {user_id}: {user_text[:50]}...")
            
            payload = {"query": user_text}
            
            result = await self._post_with_retry(
                f"{self.central_url}/api/v1/rag/query",
                json_data=payload,
                headers=merge_internal_headers(user_id=user_id),
            )
            
            if result and result.get("success"):
                response_text = result.get("response", "")
                logger.info(f"LLM response: {response_text[:50]}...")
                return response_text
            else:
                logger.error(f"LLM failed: {result}")
                return None
        
        except Exception as e:
            logger.error(f"LLM error: {e}")
            return None
    
    async def synthesize_speech(
        self,
        text: str,
        language: str = "en",
        speaker_id: str = "jenny"
    ) -> Optional[bytes]:
        """
        Synthesize speech from text using TTS Service.
        
        Args:
            text: Text to synthesize
            language: Language ('en' or 'ur')
            speaker_id: Speaker voice ID
            
        Returns:
            WAV audio bytes or None if failed
        """
        try:
            await self.focus_mode_client.async_defer_if_needed("conversation")
            logger.info(f"Synthesizing speech ({speaker_id}): {text[:50]}...")
            
            payload = {
                "text": text,
                "language": language,
                "voice_id": speaker_id
            }
            
            result = await self._post_with_retry(
                f"{self.tts_url}/speak", json_data=payload, expect_audio=True
            )
            
            if result:
                if isinstance(result, bytes):
                    logger.info(f"Received {len(result)} bytes of audio")
                    return result
                else:
                    logger.error(f"TTS response format error: {result}")
                    return None
            else:
                logger.error("No response from TTS")
                return None
        
        except Exception as e:
            logger.error(f"TTS error: {e}")
            return None
    
    async def process_conversation_turn(
        self,
        user_id: str | None,
        audio_file_path: str,
        speaker_id: str = "jenny"
    ) -> Optional[ConversationTurn]:
        """
        Process complete conversation turn: transcribe → LLM → TTS.
        
        Args:
            user_id: User identifier
            audio_file_path: Path to VAV-recorded audio file
            speaker_id: TTS speaker voice
            
        Returns:
            ConversationTurn with results or None if critical errors
        """
        start_time = datetime.now()
        turn = ConversationTurn(user_id=user_id or "", user_text="")
        
        try:
            # Update state
            self.state_manager.transition_to(ConversationState.PROCESSING_QUERY)
            
            # Verify before transcription or any user-scoped downstream request.
            verified = await self.verify_speaker(audio_file_path)
            if verified is None:
                turn.error = "Speaker verification failed"
                return turn
            verified_user_id, confidence = verified
            if user_id is not None and user_id != verified_user_id:
                turn.error = "Speaker does not match requested user"
                return turn
            turn.user_id = verified_user_id
            logger.info("Speaker verified: user_id=%s confidence=%.4f", verified_user_id, confidence)

            logger.info("Transcribing verified speech...")
            user_text, language = await self.transcribe_audio(audio_file_path)
            
            if not user_text:
                turn.error = "Transcription failed"
                logger.warning("Transcription returned empty")
                return turn
            
            turn.user_text = user_text
            turn.transcript_language = language
            
            # Step 2: Get LLM response (parallel with Vision/TeachMe if possible)
            logger.info("Step 2/4: Generating LLM response...")
            context = {
                "objects": turn.objects_detected,
                "knowledge": turn.knowledge_context
            }
            
            llm_response = await self.generate_llm_response(
                user_text=user_text,
                user_id=verified_user_id,
                language=language,
                context=context
            )
            
            if not llm_response:
                turn.error = "LLM generation failed"
                logger.warning("LLM returned empty")
                # Use fallback response
                llm_response = "I'm sorry, I couldn't understand that. Could you please repeat?"
            
            turn.llm_response_text = llm_response
            
            # Step 3: TTS synthesis
            logger.info("Step 3/4: Synthesizing speech...")
            audio_bytes = await self.synthesize_speech(
                text=llm_response,
                language=language,
                speaker_id=speaker_id
            )
            
            if not audio_bytes:
                turn.error = "TTS synthesis failed"
                logger.warning("TTS returned no audio")
                return turn
            
            turn.tts_audio_bytes = audio_bytes
            
            # Audio owns speaker playback; keep hardware work off the event loop.
            from main import playback_manager
            if playback_manager is None:
                turn.error = "Playback manager unavailable"
                return turn
            playback = await asyncio.to_thread(playback_manager.play_audio_bytes, audio_bytes)
            if not playback.get("success"):
                turn.error = playback.get("error") or "Playback failed"
                return turn
            self.state_manager.transition_to(ConversationState.CONVERSATION_ACTIVE)
            
            # Record metrics
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            turn.duration_ms = int(duration_ms)
            self.turns_processed += 1
            self.total_latency_ms += turn.duration_ms
            
            avg_latency = self.total_latency_ms / self.turns_processed
            logger.info(
                f"Turn complete: {turn.duration_ms}ms "
                f"(avg: {avg_latency:.0f}ms, count: {self.turns_processed})"
            )
            
            return turn
        
        except Exception as e:
            logger.error(f"Conversation turn error: {e}")
            turn.error = str(e)
            return turn
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get orchestration metrics."""
        avg_latency = (
            self.total_latency_ms / self.turns_processed
            if self.turns_processed > 0
            else 0
        )
        
        return {
            "turns_processed": self.turns_processed,
            "total_latency_ms": self.total_latency_ms,
            "average_latency_ms": avg_latency
        }
