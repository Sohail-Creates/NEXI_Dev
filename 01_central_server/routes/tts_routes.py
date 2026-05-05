"""
TTS Service Routes
==================

Orchestration routes for Text-to-Speech Service microservice integration.
Handles speech synthesis in multiple voices and languages.
"""

import logging
from fastapi import APIRouter, HTTPException

# Import TTS service client (shared module)
try:
    from shared.clients.tts_client import TTSServiceClient
    from shared.models.api_response import APIResponse, success_response, error_response, ErrorCode
    from shared.utils.circuit_breaker import CircuitBreaker
    from config.settings import get_settings
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
    from shared.clients.tts_client import TTSServiceClient
    from shared.models.api_response import APIResponse, success_response, error_response, ErrorCode
    from shared.utils.circuit_breaker import CircuitBreaker
    from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Create router with prefix
router = APIRouter(prefix="/tts", tags=["TTS Service"])

# Circuit breaker for TTS service
tts_circuit_breaker = CircuitBreaker(
    name="tts_service",
    failure_threshold=settings.circuit_breaker_failure_threshold,
    recovery_timeout=settings.circuit_breaker_recovery_timeout
)

# Initialize TTS service client
tts_client = TTSServiceClient()


@router.get("/health")
async def tts_health():
    """TTS service health check"""
    try:
        if not tts_circuit_breaker.is_healthy():
            raise HTTPException(status_code=503, detail="TTS service unavailable")
        
        logger.info("[TTSRoutes] Health check requested")
        result = await tts_client.health_check()
        tts_circuit_breaker.mark_success()
        
        if result.success:
            return success_response({"status": "healthy", "service": "tts"})
        else:
            tts_circuit_breaker.mark_failure()
            raise HTTPException(status_code=503, detail=result.error_message)
    except Exception as e:
        tts_circuit_breaker.mark_failure()
        logger.error(f"TTS health check failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/synthesize")
async def synthesize_speech(
    text: str,
    voice: str = "default",
    language: str = "en"
):
    """
    Synthesize text to speech.
    
    Args:
        text: Text to synthesize
        voice: Voice to use (default: "default")
        language: Language code (en, ur)
        
    Returns:
        Audio file URL and metadata
    """
    try:
        if not tts_circuit_breaker.is_healthy():
            raise HTTPException(status_code=503, detail="TTS service unavailable")
        
        logger.info(f"[TTSRoutes] POST /synthesize: text='{text[:50]}...', voice={voice}, language={language}")
        
        result = await tts_client.synthesize(
            text=text,
            voice=voice,
            language=language
        )
        
        tts_circuit_breaker.mark_success()
        
        if result.success:
            logger.info("[TTSRoutes] synthesize SUCCESS")
            return {
                "status": "success",
                "data": result.data
            }
        else:
            logger.error(f"[TTSRoutes] synthesize FAILED: {result.error_message}")
            raise HTTPException(status_code=400, detail=result.error_message)
    
    except Exception as e:
        tts_circuit_breaker.mark_failure()
        logger.error(f"[TTSRoutes] synthesize ERROR: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/voices/list")
async def list_voices():
    """
    Get list of available voices.
    
    Returns:
        List of available voices with metadata
    """
    try:
        logger.info("[TTSRoutes] GET /voices/list")
        
        result = await tts_client.list_voices()
        
        if result.success:
            logger.info("[TTSRoutes] list_voices SUCCESS")
            return {
                "status": "success",
                "data": result.data
            }
        else:
            logger.error(f"[TTSRoutes] list_voices FAILED: {result.error_message}")
            raise HTTPException(status_code=400, detail=result.error_message)
    
    except Exception as e:
        logger.error(f"[TTSRoutes] list_voices ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
