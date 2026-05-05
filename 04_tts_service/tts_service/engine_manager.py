"""
Engine Manager
Intelligently routes text to unified model cache (Piper English + Urdu).
Handles language detection and lazy loading/unloading for optimal resource usage.
NOW: Accepts cache as dependency injection (per-worker cache support).
PHASE 2.3: Integrated circuit breaker for fault tolerance.
"""

import logging
import time
from typing import Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .unified_model_cache import UnifiedModelCache
    from .language_detector import LanguageDetector

logger = logging.getLogger(__name__)


class EngineManager:
    """
    Manages routing between Piper and Urdu engines.
    Automatically detects language and routes appropriately.
    CHANGE: Now accepts UnifiedModelCache as dependency (not singleton).
    This allows per-worker cache instances to eliminate lock contention.
    """
    
    def __init__(self, model_cache: "UnifiedModelCache", language_detector: Optional["LanguageDetector"] = None):
        """
        Initialize the engine manager with injected dependencies.
        
        Args:
            model_cache: UnifiedModelCache instance (injected, not singleton)
            language_detector: Optional language detector (uses default if None)
        """
        if language_detector is None:
            from .language_detector import get_language_detector
            language_detector = get_language_detector()
        
        self.language_detector = language_detector
        self.model_cache = model_cache  # Injected cache (per-worker)
        self.current_engine = None
        self.current_language = None
        
        logger.info(f"EngineManager initialized with injected cache (id: {id(model_cache)})")
    
    def detect_language_and_route(self, text: str) -> Tuple[str, str]:
        """
        Detect language and return appropriate engine.
        
        Args:
            text: Input text
            
        Returns:
            Tuple of (language, engine_name)
            language: 'ur' or 'en'
            engine_name: 'urdu' or 'piper'
        """
        try:
            language, confidence = self.language_detector.detect_language(text)
            
            if language == "ur":
                engine = "urdu"
                logger.debug(f"Detected Urdu text (confidence: {confidence:.2f})")
            else:
                engine = "piper"
                language = "en"
                logger.debug(f"Detected English text (confidence: {confidence:.2f})")
            
            return language, engine
        
        except Exception as e:
            logger.error(f"Error detecting language: {str(e)}")
            return "en", "piper"  # Default to English on error
    
    def synthesize(
        self,
        text: str,
        voice_id: str,
        language: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> Optional[bytes]:
        """
        Synthesize text using appropriate engine.
        Automatically detects language unless explicitly provided.
        
        Args:
            text: Text to synthesize
            voice_id: Voice ID (Piper voice for English, Urdu voice for Urdu)
            language: Optional language hint ('en', 'ur', 'english', 'urdu')
            request_id: Request ID for logging
            
        Returns:
            WAV audio bytes or None if failed
        """
        if not text:
            logger.warning(f"[{request_id}] Empty text provided")
            return None
        
        start_time = time.time()
        
        try:
            # OPTIMIZATION: Skip detection if language explicitly provided
            if language:
                # Normalize language parameter
                if language.lower() in ["en", "english"]:
                    detected_language = "en"
                    engine_name = "piper"
                elif language.lower() in ["ur", "urdu"]:
                    detected_language = "ur"
                    engine_name = "urdu"
                else:
                    # Unknown language, fallback to detection
                    detected_language, engine_name = self.detect_language_and_route(text)
                logger.debug(f"[{request_id}] Using provided language: {language}")
            else:
                # Slow path: must detect language
                detected_language, engine_name = self.detect_language_and_route(text)
            
            logger.debug(f"[{request_id}] Routing to {engine_name} engine for {detected_language} text")
            
            # Route to appropriate engine
            if engine_name == "urdu":
                result = self._synthesize_urdu(text, voice_id, request_id)
            else:
                result = self._synthesize_piper(text, voice_id, request_id)
            
            return result
        
        except Exception as e:
            logger.error(f"[{request_id}] Synthesis error: {str(e)}", exc_info=True)
            return None
    
    def _synthesize_urdu(
        self,
        text: str,
        voice_id: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> Optional[bytes]:
        """
        Synthesize using unified cache (Urdu path).
        PHASE 2.3: Protected by circuit breaker for fault tolerance.
        
        Args:
            text: Urdu text
            voice_id: Urdu voice (e.g., 'shahid')
            request_id: Request ID for logging
            
        Returns:
            WAV audio bytes or None
        """
        try:
            # Default to shahid if no voice specified
            voice = voice_id if voice_id else "shahid"
            
            logger.info(f"[{request_id}] Synthesizing Urdu with voice '{voice}'")
            
            # PHASE 2.3: Wrap with circuit breaker
            from .circuit_breaker import get_breaker, CircuitBreakerOpenError
            
            breaker = get_breaker(voice)
            
            try:
                # Call with circuit breaker protection
                audio = breaker.call(
                    self.model_cache.synthesize,
                    voice,
                    text
                )
            except CircuitBreakerOpenError as e:
                logger.error(f"[{request_id}] Circuit breaker OPEN for {voice}: {e}")
                # Fallback to English
                return self._synthesize_piper(text, voice_id=None, request_id=request_id)
            
            if audio:
                logger.info(f"[{request_id}] Urdu synthesis successful ({len(audio)} bytes)")
                return audio
            else:
                logger.warning(f"[{request_id}] Urdu synthesis returned None - falling back to English/Piper")
                return self._synthesize_piper(text, voice_id=None, request_id=request_id)
        
        except Exception as e:
            logger.warning(f"[{request_id}] Urdu synthesis error: {str(e)} - falling back to English/Piper")
            try:
                return self._synthesize_piper(text, voice_id=None, request_id=request_id)
            except Exception as fallback_error:
                logger.error(f"[{request_id}] Fallback to English also failed: {str(fallback_error)}")
                return None
    
    def _synthesize_piper(
        self,
        text: str,
        voice_id: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> Optional[bytes]:
        """
        Synthesize using unified cache (English/Piper path).
        PHASE 2.3: Protected by circuit breaker for fault tolerance.
        
        Args:
            text: English text
            voice_id: Piper voice ID
            request_id: Request ID for logging
            
        Returns:
            WAV audio bytes or None
        """
        try:
            # Default Piper voice
            if not voice_id:
                voice_id = "ryan"
            
            logger.debug(f"[{request_id}] Using injected cache with voice '{voice_id}'")
            
            # PHASE 2.3: Wrap with circuit breaker
            from .circuit_breaker import get_breaker, CircuitBreakerOpenError
            
            breaker = get_breaker(voice_id)
            
            try:
                # Call with circuit breaker protection
                audio = breaker.call(
                    self.model_cache.synthesize,
                    voice_id,
                    text
                )
            except CircuitBreakerOpenError as e:
                logger.error(f"[{request_id}] Circuit breaker OPEN for {voice_id}: {e}")
                return None
            
            if audio:
                logger.info(f"[{request_id}] Piper synthesis successful ({len(audio)} bytes)")
                return audio
            else:
                logger.error(f"[{request_id}] Piper synthesis returned None")
                return None
        
        except Exception as e:
            logger.error(f"[{request_id}] Piper synthesis error: {str(e)}", exc_info=True)
            return None
    
    def get_all_voices(self) -> dict:
        """
        Get all available voices (English + Urdu) from unified cache.
        
        Returns:
            Dictionary with voices grouped by language
        """
        try:
            voices = self.model_cache.get_available_voices()
            return {
                "english": voices.get("english", []),
                "urdu": voices.get("urdu", []),
                "all": voices.get("english", []) + voices.get("urdu", [])
            }
        except Exception as e:
            logger.error(f"Error getting voices: {str(e)}")
            return {"english": [], "urdu": [], "all": []}


# Dependency-injected EngineManager (no global singleton)
# Each worker creates its own instance with its own cache

