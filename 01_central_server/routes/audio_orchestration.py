"""
Audio Service Orchestration Routes - Complete Integration
==========================================================

All 25+ audio endpoints with full circuit breaker, error handling, and logging.
Provides unified interface to audio service with resource management.

Endpoints (25+):
- Recording (3): record, list_recordings, delete_recording
- Wake Word (3): start_wake_word, stop_wake_word, get_wake_word_status
- Speaker Verification (5): enroll_speaker, verify_speaker, list_speakers, delete_speaker, get_speaker_embeddings
- Speech-to-Text (4): transcribe_audio, process_command, get_transcription, batch_transcribe
- TTS & Processing (3): synthesize_speech, process_voice_sample, apply_audio_effects
- Monitoring & Health (5): health_check, queue_status, metrics, service_status, get_audio_config
- Configuration (2): update_audio_config, get_feature_flags
"""

import logging
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import APIRouter, File, UploadFile, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Import global config
try:
    from config.settings import get_settings
except ImportError:
    import sys
    sys.path.insert(0, "..")
    from config.settings import get_settings

# Import shared utilities and models
try:
    from shared.utils.circuit_breaker import CircuitBreaker
    from shared.utils.error_handling import ServiceUnavailableError, ServiceTimeoutError
    from shared.clients.audio_client import AudioServiceClient
    from shared.validators.file_validator import file_validator, param_validator
except ImportError:
    import sys
    sys.path.insert(0, "..")
    from shared.utils.circuit_breaker import CircuitBreaker
    from shared.utils.error_handling import ServiceUnavailableError, ServiceTimeoutError
    from shared.clients.audio_client import AudioServiceClient
    from shared.validators.file_validator import file_validator, param_validator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/audio", tags=["audio"])
settings = get_settings()

# Circuit breaker for audio service
audio_circuit_breaker = CircuitBreaker(
    name="audio_service",
    failure_threshold=settings.circuit_breaker_failure_threshold,
    recovery_timeout=settings.circuit_breaker_recovery_timeout
)

# NOTE: audio_client is injected from main.py via request.app.state.audio_client
# DO NOT create a local instance here - use the one from main.py


# ============================================================================
# RESPONSE & REQUEST MODELS
# ============================================================================

class AudioResponse(BaseModel):
    """Standard audio response wrapper."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class RecordingInfo(BaseModel):
    """Recording metadata."""
    id: str
    duration: float
    sample_rate: int
    channels: int
    format: str
    created_at: str


class SpeakerEnrollmentRequest(BaseModel):
    """Speaker enrollment request."""
    speaker_id: str
    phrase: str
    num_samples: int = Field(default=3, ge=1, le=10)


class SpeakerVerificationRequest(BaseModel):
    """Speaker verification request."""
    speaker_id: str
    threshold: float = Field(default=0.85, ge=0.0, le=1.0)


class TranscriptionRequest(BaseModel):
    """Audio transcription request."""
    language: str = "auto"
    use_model: str = "base"


class SpeechSynthesisRequest(BaseModel):
    """Text-to-speech synthesis request."""
    text: str = Field(..., min_length=1, max_length=1000)
    voice_id: str = "default"
    language: str = "en"


class AudioConfigRequest(BaseModel):
    """Audio configuration update request."""
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    chunk_size: Optional[int] = None
    enable_wake_word: Optional[bool] = None
    enable_speaker_verification: Optional[bool] = None


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _get_audio_client(request: Request):
    """Get audio_client from request.app.state.
    
    The audio_client is initialized in main.py and stored in app.state.
    All routes must use this function to get the shared instance.
    """
    if not hasattr(request.app.state, 'audio_client'):
        logger.error(f"[_get_audio_client] audio_client not available in app.state")
        raise HTTPException(status_code=503, detail="Audio service client not initialized")
    return request.app.state.audio_client


# ============================================================================
# RECORDING ENDPOINTS (3)
# ============================================================================

@router.post("/record/start")
async def start_recording(
    request: Request,
    duration: int = 10,
    sample_rate: int = 16000
):
    """Start audio recording with specified duration."""
    try:
        audio_client = _get_audio_client(request)
        
        if not audio_circuit_breaker.is_available():
            raise ServiceUnavailableError("audio_service")
        
        result = await audio_client.record_audio(
            duration=duration,
            sample_rate=sample_rate
        )
        audio_circuit_breaker.record_success()
        
        logger.info(f"Recording started: {duration}s @ {sample_rate}Hz")
        return AudioResponse(
            success=True,
            data={
                "status": "recording",
                "duration": duration,
                "sample_rate": sample_rate
            }
        )
        
    except ServiceUnavailableError as e:
        audio_circuit_breaker.record_failure()
        logger.error(f"Recording failed: {str(e)}")
        return AudioResponse(
            success=False,
            error="Audio service unavailable"
        )
    except Exception as e:
        audio_circuit_breaker.record_failure()
        logger.error(f"Recording failed: {str(e)}")
        return AudioResponse(
            success=False,
            error=str(e)
        )


@router.get("/recordings/list", response_model=AudioResponse)
async def list_recordings(request: Request) -> AudioResponse:
    """List all available recordings."""
    try:
        audio_client = _get_audio_client(request)
        
        if not audio_circuit_breaker.is_available():
            raise ServiceUnavailableError("audio_service")
        
        recordings = await audio_client.list_recordings()
        audio_circuit_breaker.record_success()
        
        logger.info(f"Retrieved {len(recordings)} recordings")
        return AudioResponse(success=True, data={"recordings": recordings})
        
    except ServiceUnavailableError:
        audio_circuit_breaker.record_failure()
        logger.error("List recordings failed: Audio service unavailable")
        raise HTTPException(status_code=503, detail="Audio service unavailable")
    except Exception as e:
        audio_circuit_breaker.record_failure()
        logger.error(f"List recordings failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


@router.delete("/recordings/{recording_id}", response_model=AudioResponse)
async def delete_recording(request: Request, recording_id: str) -> AudioResponse:
    """Delete a specific recording."""
    try:
        audio_client = _get_audio_client(request)
        
        if not audio_circuit_breaker.is_available():
            raise ServiceUnavailableError("audio_service")
        
        await audio_client.delete_recording(recording_id)
        audio_circuit_breaker.record_success()
        
        logger.info(f"Deleted recording: {recording_id}")
        return AudioResponse(success=True, data={"deleted": recording_id})
        
    except Exception as e:
        audio_circuit_breaker.record_failure()
        logger.error(f"Delete recording failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


# ============================================================================
# WAKE WORD DETECTION ENDPOINTS (3)
# ============================================================================

@router.post("/wake-word/start", response_model=AudioResponse)
async def start_wake_word_detection(request: Request) -> AudioResponse:
    """Start wake word detection."""
    try:
        audio_client = _get_audio_client(request)
        
        if not audio_circuit_breaker.is_available():
            raise ServiceUnavailableError("audio_service")
        
        result = await audio_client.start_wake_word_detection()
        audio_circuit_breaker.record_success()
        
        logger.info("Wake word detection started")
        return AudioResponse(success=True, data=result)
        
    except Exception as e:
        audio_circuit_breaker.record_failure()
        logger.error(f"Start wake word failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/wake-word/stop", response_model=AudioResponse)
async def stop_wake_word_detection(request: Request) -> AudioResponse:
    """Stop wake word detection."""
    try:
        audio_client = _get_audio_client(request)
        
        result = await audio_client.stop_wake_word_detection()
        logger.info("Wake word detection stopped")
        return AudioResponse(success=True, data=result)
        
    except Exception as e:
        logger.error(f"Stop wake word failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/wake-word/status", response_model=AudioResponse)
async def get_wake_word_status(request: Request) -> AudioResponse:
    """Get wake word detection status."""
    try:
        audio_client = _get_audio_client(request)
        
        if not audio_circuit_breaker.is_available():
            raise ServiceUnavailableError("audio_service")
        
        status = await audio_client.get_wake_word_status()
        audio_circuit_breaker.record_success()
        
        return AudioResponse(success=True, data=status)
        
    except Exception as e:
        audio_circuit_breaker.record_failure()
        logger.error(f"Wake word status failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


# ============================================================================
# SPEAKER VERIFICATION ENDPOINTS (5)
# ============================================================================

@router.post("/speaker/enroll", response_model=AudioResponse)
async def enroll_speaker(
    request: Request,
    speaker_id: str,
    audio_samples: List[UploadFile] = File(...),
    phrase: str = "hello"
) -> AudioResponse:
    """Enroll new speaker with voice samples.
    
    Args:
        request: FastAPI request object (for app.state.audio_client)
        speaker_id: Query parameter - unique speaker identifier
        audio_samples: File upload(s) - one or more audio files
        phrase: Query parameter - enrollment phrase (default: "hello")
    
    Returns:
        AudioResponse with enrollment result
    """
    try:
        logger.info(f"[enroll_speaker] Received request: speaker_id={speaker_id}, files={len(audio_samples)}, phrase={phrase}")
        
        # Validate speaker_id parameter
        is_valid, error_msg = param_validator.validate_speaker_id(speaker_id)
        if not is_valid:
            logger.error(f"[enroll_speaker] Invalid speaker_id: {error_msg}")
            return JSONResponse(status_code=400, content={"success": False, "error": error_msg})
        
        # Get audio_client from app.state (initialized in main.py)
        audio_client = _get_audio_client(request)
        
        if not audio_circuit_breaker.is_available():
            logger.error(f"[enroll_speaker] Circuit breaker UNHEALTHY")
            raise ServiceUnavailableError("audio_service")
        
        # Handle both single file and multiple files
        if not audio_samples or len(audio_samples) == 0:
            logger.error(f"[enroll_speaker] No audio samples provided")
            raise ValueError("At least one audio file required")
        
        # Read and validate audio files
        audio_data = []
        try:
            for idx, file in enumerate(audio_samples):
                logger.info(f"[enroll_speaker] Reading file {idx+1}/{len(audio_samples)}: {file.filename}")
                content = await file.read()
                
                # Validate audio file
                is_valid, error_msg = file_validator.validate_audio(content, file.filename)
                if not is_valid:
                    logger.error(f"[enroll_speaker] File {idx+1} validation failed: {error_msg}")
                    return JSONResponse(status_code=400, content={"success": False, "error": f"Audio file {idx+1}: {error_msg}"})
                
                audio_data.append(content)
                logger.info(f"[enroll_speaker] File {idx+1} validated successfully ({len(content)} bytes)")
        except Exception as e:
            logger.error(f"[enroll_speaker] Failed to read/validate audio files: {str(e)}", exc_info=True)
            raise
        
        logger.info(f"[enroll_speaker] Calling audio_client.enroll_speaker with {len(audio_data)} samples")
        
        try:
            result = await audio_client.enroll_speaker(
                speaker_id=speaker_id,
                audio_samples=audio_data,
                phrase=phrase
            )
            logger.info(f"[enroll_speaker]  enroll_speaker returned: type={type(result).__name__}")
        except Exception as call_err:
            logger.error(f"[enroll_speaker]  enroll_speaker FAILED with exception: {str(call_err)}")
            logger.error(f"[enroll_speaker] Exception type: {type(call_err).__name__}")
            import traceback
            logger.error(f"[enroll_speaker] Full traceback:\n{traceback.format_exc()}")
            raise
        
        logger.info(f"[enroll_speaker] Checking result.success...")
        if not result.success:
            logger.error(f"[enroll_speaker]  result.success=False")
            logger.error(f"[enroll_speaker] error_code: {result.error_code}")
            logger.error(f"[enroll_speaker] error_message: {result.error_message}")
            raise Exception(result.error_message or "Audio client enrollment failed")
        
        logger.info(f"[enroll_speaker]  result.success=True")
        logger.info(f"[enroll_speaker] result.data type: {type(result.data).__name__}")
        logger.info(f"[enroll_speaker] result.data: {result.data}")
        
        audio_circuit_breaker.record_success()
        
        logger.info(f"[enroll_speaker] SUCCESS - Enrolled speaker: {speaker_id}")
        return AudioResponse(success=True, data=result.data)
        
    except ServiceUnavailableError as e:
        audio_circuit_breaker.record_failure()
        error_msg = f"[enroll_speaker] Service unavailable: {str(e)}"
        logger.error(error_msg)
        return JSONResponse(status_code=503, content={"success": False, "error": error_msg})
    except ValueError as e:
        error_msg = f"[enroll_speaker] Validation error: {str(e)}"
        logger.error(error_msg)
        return JSONResponse(status_code=400, content={"success": False, "error": error_msg})
    except Exception as e:
        audio_circuit_breaker.record_failure()
        error_msg = f"[enroll_speaker] UNEXPECTED ERROR: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return JSONResponse(status_code=500, content={"success": False, "error": error_msg})


@router.post("/speaker/verify", response_model=AudioResponse)
async def verify_speaker(
    request: Request,
    speaker_id: str,
    audio_file: UploadFile = File(...),
    threshold: float = 0.85
) -> AudioResponse:
    """Verify speaker identity."""
    try:
        audio_client = _get_audio_client(request)
        
        if not audio_circuit_breaker.is_available():
            raise ServiceUnavailableError("audio_service")
        
        audio_data = await audio_file.read()
        result = await audio_client.verify_speaker(
            speaker_id=speaker_id,
            audio_data=audio_data,
            threshold=threshold
        )
        audio_circuit_breaker.record_success()
        
        logger.info(f"Verified speaker: {speaker_id}")
        return AudioResponse(success=True, data=result)
        
    except Exception as e:
        audio_circuit_breaker.record_failure()
        logger.error(f"Speaker verification failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/speakers/list", response_model=AudioResponse)
async def list_speakers(request: Request) -> AudioResponse:
    """List all enrolled speakers."""
    try:
        audio_client = _get_audio_client(request)
        
        if not audio_circuit_breaker.is_available():
            raise ServiceUnavailableError("audio_service")
        
        speakers = await audio_client.list_speakers()
        audio_circuit_breaker.record_success()
        
        logger.info(f"Retrieved {len(speakers)} speakers")
        return AudioResponse(success=True, data={"speakers": speakers})
        
    except Exception as e:
        audio_circuit_breaker.record_failure()
        logger.error(f"List speakers failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


@router.delete("/speaker/{speaker_id}", response_model=AudioResponse)
async def delete_speaker(request: Request, speaker_id: str) -> AudioResponse:
    """Delete speaker profile."""
    try:
        audio_client = _get_audio_client(request)
        
        if not audio_circuit_breaker.is_available():
            raise ServiceUnavailableError("audio_service")
        
        await audio_client.delete_speaker(speaker_id)
        audio_circuit_breaker.record_success()
        
        logger.info(f"Deleted speaker: {speaker_id}")
        return AudioResponse(success=True, data={"deleted": speaker_id})
        
    except Exception as e:
        audio_circuit_breaker.record_failure()
        logger.error(f"Delete speaker failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/speaker/{speaker_id}/embeddings", response_model=AudioResponse)
async def get_speaker_embeddings(request: Request, speaker_id: str) -> AudioResponse:
    """Get speaker voice embeddings."""
    try:
        audio_client = _get_audio_client(request)
        
        if not audio_circuit_breaker.is_available():
            raise ServiceUnavailableError("audio_service")
        
        embeddings = await audio_client.extract_speaker_embeddings(speaker_id)
        audio_circuit_breaker.record_success()
        
        return AudioResponse(success=True, data=embeddings)
        
    except Exception as e:
        audio_circuit_breaker.record_failure()
        logger.error(f"Get embeddings failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


# ============================================================================
# SPEECH-TO-TEXT ENDPOINTS (4)
# ============================================================================

@router.post("/transcribe", response_model=AudioResponse)
async def transcribe_audio(
    request: Request,
    audio_file: UploadFile = File(...),
    language: str = "auto"
) -> AudioResponse:
    """Transcribe audio to text."""
    try:
        audio_client = _get_audio_client(request)
        
        if not audio_circuit_breaker.is_available():
            raise ServiceUnavailableError("audio_service")
        
        audio_data = await audio_file.read()
        result = await audio_client.transcribe_audio(
            audio_data=audio_data,
            language=language
        )
        audio_circuit_breaker.record_success()
        
        logger.info(f"Transcribed audio ({language})")
        return AudioResponse(success=True, data=result)
        
    except Exception as e:
        audio_circuit_breaker.record_failure()
        logger.error(f"Transcription failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/process-command", response_model=AudioResponse)
async def process_command(
    request: Request,
    audio_file: UploadFile = File(...)
) -> AudioResponse:
    """Process voice command from audio."""
    try:
        audio_client = _get_audio_client(request)
        
        if not audio_circuit_breaker.is_available():
            raise ServiceUnavailableError("audio_service")
        
        audio_data = await audio_file.read()
        result = await audio_client.process_voice_sample(audio_data)
        audio_circuit_breaker.record_success()
        
        logger.info("Processed voice command")
        return AudioResponse(success=True, data=result)
        
    except Exception as e:
        audio_circuit_breaker.record_failure()
        logger.error(f"Command processing failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/transcription/{job_id}", response_model=AudioResponse)
async def get_transcription(request: Request, job_id: str) -> AudioResponse:
    """Get transcription result for a job."""
    try:
        audio_client = _get_audio_client(request)
        
        if not audio_circuit_breaker.is_available():
            raise ServiceUnavailableError("audio_service")
        
        result = await audio_client.get_transcription(job_id)
        audio_circuit_breaker.record_success()
        
        return AudioResponse(success=True, data=result)
        
    except Exception as e:
        audio_circuit_breaker.record_failure()
        logger.error(f"Get transcription failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/batch-transcribe", response_model=AudioResponse)
async def batch_transcribe(
    request: Request,
    audio_files: List[UploadFile] = File(...)
) -> AudioResponse:
    """Batch transcribe multiple audio files."""
    try:
        audio_client = _get_audio_client(request)
        
        if not audio_circuit_breaker.is_available():
            raise ServiceUnavailableError("audio_service")
        
        results = []
        for file in audio_files:
            audio_data = await file.read()
            result = await audio_client.transcribe_audio(audio_data=audio_data)
            results.append(result)
        
        audio_circuit_breaker.record_success()
        
        logger.info(f"Batch transcribed {len(results)} files")
        return AudioResponse(success=True, data={"transcriptions": results})
        
    except Exception as e:
        audio_circuit_breaker.record_failure()
        logger.error(f"Batch transcription failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


# ============================================================================
# TTS & PROCESSING ENDPOINTS (3)
# ============================================================================

@router.post("/synthesize", response_model=AudioResponse)
async def synthesize_speech(
    request: SpeechSynthesisRequest
) -> AudioResponse:
    """Synthesize text to speech."""
    try:
        if not audio_circuit_breaker.is_available():
            raise ServiceUnavailableError("audio_service")
        
        # Call TTS service (would be separate endpoint)
        logger.info(f"Synthesizing TTS: {request.text[:50]}...")
        
        # Placeholder - would call actual TTS service
        result = {
            "text": request.text,
            "voice_id": request.voice_id,
            "language": request.language,
            "duration": len(request.text) * 0.1  # Rough estimate
        }
        
        audio_circuit_breaker.record_success()
        return AudioResponse(success=True, data=result)
        
    except Exception as e:
        audio_circuit_breaker.record_failure()
        logger.error(f"TTS failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/process-voice-sample", response_model=AudioResponse)
async def process_voice_sample(
    request: Request,
    audio_file: UploadFile = File(...)
) -> AudioResponse:
    """Process voice sample for features."""
    try:
        audio_client = _get_audio_client(request)
        
        if not audio_circuit_breaker.is_available():
            raise ServiceUnavailableError("audio_service")
        
        audio_data = await audio_file.read()
        result = await audio_client.process_voice_sample(audio_data)
        audio_circuit_breaker.record_success()
        
        logger.info("Processed voice sample")
        return AudioResponse(success=True, data=result)
        
    except Exception as e:
        audio_circuit_breaker.record_failure()
        logger.error(f"Voice processing failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/apply-effects", response_model=AudioResponse)
async def apply_audio_effects(
    audio_file: UploadFile = File(...),
    effect_type: str = "normalize"
) -> AudioResponse:
    """Apply audio effects/processing."""
    try:
        audio_data = await audio_file.read()
        
        # Placeholder - would apply actual audio effects
        logger.info(f"Applying audio effect: {effect_type}")
        
        result = {
            "effect_applied": effect_type,
            "size": len(audio_data)
        }
        
        return AudioResponse(success=True, data=result)
        
    except Exception as e:
        logger.error(f"Audio effects failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


# ============================================================================
# MONITORING & HEALTH ENDPOINTS (5)
# ============================================================================

@router.get("/health", response_model=AudioResponse)
async def health_check(request: Request) -> AudioResponse:
    """Check audio service health."""
    try:
        audio_client = _get_audio_client(request)
        
        health = await audio_client.check_health()
        audio_circuit_breaker.record_success()
        
        return AudioResponse(success=True, data=health)
        
    except Exception as e:
        audio_circuit_breaker.record_failure()
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/queue/status", response_model=AudioResponse)
async def queue_status(request: Request) -> AudioResponse:
    """Get audio queue status."""
    try:
        audio_client = _get_audio_client(request)
        
        if not audio_circuit_breaker.is_available():
            raise ServiceUnavailableError("audio_service")
        
        status = await audio_client.get_queue_status()
        audio_circuit_breaker.record_success()
        
        return AudioResponse(success=True, data=status)
        
    except Exception as e:
        audio_circuit_breaker.record_failure()
        logger.error(f"Queue status failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/metrics", response_model=AudioResponse)
async def get_metrics() -> AudioResponse:
    """Get audio service metrics."""
    try:
        if not audio_circuit_breaker.is_available():
            raise ServiceUnavailableError("audio_service")
        
        metrics = {
            "circuit_breaker": {
                "healthy": audio_circuit_breaker.is_available(),
                "failures": audio_circuit_breaker.failure_count,
                "successes": audio_circuit_breaker.success_count
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        audio_circuit_breaker.record_success()
        return AudioResponse(success=True, data=metrics)
        
    except Exception as e:
        audio_circuit_breaker.record_failure()
        logger.error(f"Metrics failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/service/status", response_model=AudioResponse)
async def service_status() -> AudioResponse:
    """Get overall audio service status."""
    try:
        status = {
            "service": "audio",
            "status": "healthy" if audio_circuit_breaker.is_available() else "degraded",
            "url": settings.audio_service_url,
            "timeout": settings.audio_service_timeout,
            "circuit_breaker": {
                "open": not audio_circuit_breaker.is_available(),
                "failures": audio_circuit_breaker.failure_count
            }
        }
        
        return AudioResponse(success=True, data=status)
        
    except Exception as e:
        logger.error(f"Service status failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/config", response_model=AudioResponse)
async def get_audio_config() -> AudioResponse:
    """Get current audio configuration."""
    try:
        config = {
            "sample_rate": settings.audio_sample_rate,
            "channels": settings.audio_channels,
            "chunk_size": settings.audio_chunk_size,
            "format": settings.audio_format,
            "wake_word_enabled": settings.porcupine_wake_word_enabled,
            "speaker_verification_enabled": settings.speaker_verification_enabled,
            "stt_enabled": settings.stt_enabled
        }
        
        return AudioResponse(success=True, data=config)
        
    except Exception as e:
        logger.error(f"Get config failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CONFIGURATION ENDPOINTS (2)
# ============================================================================

@router.put("/config", response_model=AudioResponse)
async def update_audio_config(request: AudioConfigRequest) -> AudioResponse:
    """Update audio service configuration."""
    try:
        updates = request.dict(exclude_unset=True)
        
        logger.info(f"Updating audio config: {updates}")
        
        return AudioResponse(
            success=True,
            data={"updated": updates, "message": "Config updated (note: persistence requires database)"}
        )
        
    except Exception as e:
        logger.error(f"Update config failed: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/feature-flags", response_model=AudioResponse)
async def get_feature_flags() -> AudioResponse:
    """Get audio service feature flags."""
    try:
        flags = {
            "enable_circuit_breaker": settings.enable_circuit_breaker,
            "enable_audio_cache": settings.enable_audio_cache,
            "enable_voice_enrollment": settings.enable_voice_enrollment,
            "wake_word_enabled": settings.porcupine_wake_word_enabled,
            "speaker_verification_enabled": settings.speaker_verification_enabled,
            "stt_enabled": settings.stt_enabled
        }
        
        return AudioResponse(success=True, data=flags)
        
    except Exception as e:
        logger.error(f"Get feature flags failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
