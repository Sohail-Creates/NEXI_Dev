"""
Vision Service Routes
=====================

Orchestration routes for Vision Service microservice integration.
Handles face detection, embedding extraction, and mood analysis.
"""

import logging
from fastapi import APIRouter, UploadFile, File, HTTPException

# Import vision service client (shared module)
try:
    from shared.clients.vision_client import VisionServiceClient
    from shared.models.api_response import APIResponse, success_response, error_response, ErrorCode
    from shared.utils.circuit_breaker import CircuitBreaker
    from config.settings import get_settings
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
    from shared.clients.vision_client import VisionServiceClient
    from shared.models.api_response import APIResponse, success_response, error_response, ErrorCode
    from shared.utils.circuit_breaker import CircuitBreaker
    from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Create router with prefix
router = APIRouter(prefix="/vision", tags=["Vision Service"])

# Circuit breaker for vision service
vision_circuit_breaker = CircuitBreaker(
    name="vision_service",
    failure_threshold=settings.circuit_breaker_failure_threshold,
    recovery_timeout=settings.circuit_breaker_recovery_timeout
)

# Initialize vision service client
vision_client = VisionServiceClient()


@router.get("/health")
async def vision_health():
    """Vision service health check"""
    try:
        if not vision_circuit_breaker.is_healthy():
            raise HTTPException(status_code=503, detail="Vision service unavailable")
        
        logger.info("[VisionRoutes] Health check requested")
        result = await vision_client.health_check()
        vision_circuit_breaker.mark_success()
        
        if result.success:
            return success_response({"status": "healthy", "service": "vision"})
        else:
            vision_circuit_breaker.mark_failure()
            raise HTTPException(status_code=503, detail=result.error_message)
    except Exception as e:
        vision_circuit_breaker.mark_failure()
        logger.error(f"Vision health check failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/extract-face-embedding")
async def extract_face_embedding(image_file: UploadFile = File(...)):
    """
    Extract face embedding from image file.
    
    Returns 512D face embedding vector for enrollment or recognition.
    """
    try:
        if not vision_circuit_breaker.is_healthy():
            raise HTTPException(status_code=503, detail="Vision service unavailable")
        
        logger.info(f"[VisionRoutes] POST /extract-face-embedding: {image_file.filename}")
        image_bytes = await image_file.read()
        
        result = await vision_client.process_face(
            image_file_bytes=image_bytes,
            filename=image_file.filename
        )
        
        vision_circuit_breaker.mark_success()
        
        if result.success:
            logger.info("[VisionRoutes] extract_face_embedding SUCCESS")
            return {
                "status": "success",
                "data": result.data
            }
        else:
            logger.error(f"[VisionRoutes] extract_face_embedding FAILED: {result.error_message}")
            raise HTTPException(status_code=400, detail=result.error_message)
    
    except Exception as e:
        vision_circuit_breaker.mark_failure()
        logger.error(f"[VisionRoutes] extract_face_embedding ERROR: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))
