"""
Integration Bridge for Service Clients

This module provides refactored route handlers that use the new service clients.
It bridges the existing Central Server with the circuit-breaker-protected clients.

Usage:
  Import the router and mount it in the FastAPI app:
  app.include_router(integration_router)
"""

from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from fastapi.responses import Response
from typing import Optional, List
import logging
import sys
import os

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

# Import service clients
from shared.clients import (
    AudioServiceClient,
    VisionServiceClient,
    TTSServiceClient,
    TeachMeServiceClient,
    ServiceCallResult
)
from shared.models.api_response import APIResponse

logger = logging.getLogger(__name__)

# Initialize clients (will be instantiated once)
audio_client = AudioServiceClient()
vision_client = VisionServiceClient()
tts_client = TTSServiceClient()
teachme_client = TeachMeServiceClient()

# Create router
router = APIRouter()


# ============================================================================
# AUDIO SERVICE INTEGRATION
# ============================================================================

@router.post("/audio/process-voice")
async def audio_process_voice(file: UploadFile = File(...)):
    """
    Accept an audio file, forward to Audio Service, return voice embeddings.
    This endpoint does NOT process audio itself. It delegates entirely.
    """
    audio_bytes = await file.read()

    result = await audio_client.process_voice(
        audio_file_bytes=audio_bytes,
        filename=file.filename or "audio.wav"
    )

    if result.success:
        return APIResponse(
            status="success",
            data=result.data,
            message="Voice embeddings extracted successfully"
        )
    else:
        return APIResponse(
            status="error",
            error_code=result.error_code,
            message=result.error_message
        )


@router.post("/audio/verify-speaker")
async def audio_verify_speaker(
    file: UploadFile = File(...),
    user_id: str = Form(...)
):
    """
    Accept audio + user_id, forward to Audio Service for speaker verification.
    """
    if not user_id:
        return APIResponse(
            status="error",
            error_code="MISSING_USER_ID",
            message="user_id is required for speaker verification"
        )

    audio_bytes = await file.read()

    result = await audio_client.verify_speaker(
        audio_file_bytes=audio_bytes,
        filename=file.filename or "audio.wav",
        user_id=user_id
    )

    if result.success:
        return APIResponse(status="success", data=result.data)
    else:
        return APIResponse(
            status="error",
            error_code=result.error_code,
            message=result.error_message
        )


@router.post("/audio/transcribe")
async def audio_transcribe(
    file: UploadFile = File(...),
    language: str = Form(default="auto")
):
    """
    Accept audio, forward to Audio Service for speech-to-text.
    """
    audio_bytes = await file.read()

    result = await audio_client.transcribe(
        audio_file_bytes=audio_bytes,
        filename=file.filename or "audio.wav",
        language=language
    )

    if result.success:
        return APIResponse(status="success", data=result.data)
    else:
        return APIResponse(
            status="error",
            error_code=result.error_code,
            message=result.error_message
        )


@router.post("/audio/wake-word/start")
async def audio_start_wake_word():
    """Forward wake word start command to Audio Service."""
    result = await audio_client.start_wake_word()
    if result.success:
        return APIResponse(
            status="success",
            data=result.data,
            message="Wake word detection started"
        )
    else:
        return APIResponse(
            status="error",
            error_code=result.error_code,
            message=result.error_message
        )


@router.post("/audio/wake-word/stop")
async def audio_stop_wake_word():
    """Forward wake word stop command to Audio Service."""
    result = await audio_client.stop_wake_word()
    if result.success:
        return APIResponse(
            status="success",
            data=result.data,
            message="Wake word detection stopped"
        )
    else:
        return APIResponse(
            status="error",
            error_code=result.error_code,
            message=result.error_message
        )


@router.get("/audio/wake-word/status")
async def audio_get_wake_word_status():
    """Forward wake word status query to Audio Service."""
    result = await audio_client.get_wake_word_status()
    if result.success:
        return APIResponse(status="success", data=result.data)
    else:
        return APIResponse(
            status="error",
            error_code=result.error_code,
            message=result.error_message
        )


@router.get("/audio/health")
async def audio_health():
    """
    Check Audio Service health. This does NOT go through circuit breaker.
    Returns the downstream service's health status directly.
    """
    result = await audio_client.health_check()
    if result.success:
        return APIResponse(
            status="success",
            data=result.data,
            message="Audio Service is healthy"
        )
    else:
        return APIResponse(
            status="error",
            error_code=result.error_code,
            message="Audio Service is unreachable or unhealthy"
        )


# ============================================================================
# VISION SERVICE INTEGRATION
# ============================================================================

@router.post("/vision/process-face")
async def vision_process_face(file: UploadFile = File(...)):
    """
    Accept an image, forward to Vision Service, return face data.
    Response includes: face embeddings, bounding boxes, age, gender, mood if detected.
    """
    image_bytes = await file.read()

    result = await vision_client.process_face(
        image_file_bytes=image_bytes,
        filename=file.filename or "image.jpg"
    )

    if result.success:
        return APIResponse(
            status="success",
            data=result.data,
            message="Face processed successfully"
        )
    else:
        return APIResponse(
            status="error",
            error_code=result.error_code,
            message=result.error_message
        )


@router.get("/vision/health")
async def vision_health():
    """Check Vision Service health."""
    result = await vision_client.health_check()
    if result.success:
        return APIResponse(
            status="success",
            data=result.data,
            message="Vision Service is healthy"
        )
    else:
        return APIResponse(
            status="error",
            error_code=result.error_code,
            message="Vision Service is unreachable or unhealthy"
        )


# ============================================================================
# TTS SERVICE INTEGRATION
# ============================================================================

@router.post("/tts/synthesize")
async def tts_synthesize(
    text: str = Form(...),
    voice: str = Form(default="default"),
    language: str = Form(default="en")
):
    """
    Accept text, forward to TTS Service, return audio stream.
    """
    if not text or text.strip() == "":
        return APIResponse(
            status="error",
            error_code="EMPTY_TEXT",
            message="Cannot synthesize empty text"
        )

    result = await tts_client.synthesize(
        text=text,
        voice=voice,
        language=language
    )

    if result.success:
        return Response(
            content=result.data["audio_bytes"],
            media_type=result.data["content_type"]
        )
    else:
        return APIResponse(
            status="error",
            error_code=result.error_code,
            message=result.error_message
        )


@router.get("/tts/health")
async def tts_health():
    """Check TTS Service health."""
    result = await tts_client.health_check()
    if result.success:
        return APIResponse(
            status="success",
            data=result.data,
            message="TTS Service is healthy"
        )
    else:
        return APIResponse(
            status="error",
            error_code=result.error_code,
            message="TTS Service is unreachable or unhealthy"
        )


# ============================================================================
# TEACHME SERVICE INTEGRATION
# ============================================================================

@router.post("/teachme/learn/object")
async def teachme_learn_object(
    object_name: str = Form(...),
    description: str = Form(...),
    image_embedding: Optional[List[float]] = Form(default=None)
):
    """
    Receive a new object to learn. Forward to TeachMe Service.
    """
    result = await teachme_client.learn_object(
        object_name=object_name,
        description=description,
        image_embedding=image_embedding
    )

    if result.success:
        return APIResponse(
            status="success",
            data=result.data,
            message=f"Learned object: {object_name}"
        )
    else:
        return APIResponse(
            status="error",
            error_code=result.error_code,
            message=result.error_message
        )


@router.post("/teachme/learn/fact")
async def teachme_learn_fact(
    topic: str = Form(...),
    content: str = Form(...),
    user_id: Optional[str] = Form(default=None)
):
    """Receive a new fact to learn. Forward to TeachMe Service."""
    result = await teachme_client.learn_fact(
        fact_topic=topic,
        fact_content=content,
        user_id=user_id
    )

    if result.success:
        return APIResponse(
            status="success",
            data=result.data,
            message=f"Learned fact about: {topic}"
        )
    else:
        return APIResponse(
            status="error",
            error_code=result.error_code,
            message=result.error_message
        )


@router.get("/teachme/knowledge")
async def teachme_retrieve_knowledge(
    query: str,
    user_id: Optional[str] = None
):
    """Query the knowledge base. Forward to TeachMe Service."""
    result = await teachme_client.retrieve_knowledge(
        query=query,
        user_id=user_id
    )

    if result.success:
        return APIResponse(status="success", data=result.data)
    else:
        return APIResponse(
            status="error",
            error_code=result.error_code,
            message=result.error_message
        )


@router.delete("/teachme/forget/{item_type}/{item_id}")
async def teachme_forget_item(item_type: str, item_id: str):
    """Remove a learned item. Forward to TeachMe Service."""
    if item_type not in ("object", "fact"):
        return APIResponse(
            status="error",
            error_code="INVALID_ITEM_TYPE",
            message="item_type must be 'object' or 'fact'"
        )

    result = await teachme_client.forget(
        item_type=item_type,
        item_id=item_id
    )

    if result.success:
        return APIResponse(
            status="success",
            data=result.data,
            message=f"Forgot {item_type}: {item_id}"
        )
    else:
        return APIResponse(
            status="error",
            error_code=result.error_code,
            message=result.error_message
        )


@router.get("/teachme/health")
async def teachme_health():
    """Check TeachMe Service health."""
    result = await teachme_client.health_check()
    if result.success:
        return APIResponse(
            status="success",
            data=result.data,
            message="TeachMe Service is healthy"
        )
    else:
        return APIResponse(
            status="error",
            error_code=result.error_code,
            message="TeachMe Service is unreachable or unhealthy"
        )


# ============================================================================
# SYSTEM HEALTH ENDPOINT
# ============================================================================

import asyncio

@router.get("/health")
async def system_health():
    """
    Consolidated health check of all downstream services.
    Checks all services in parallel and returns unified status.
    """
    results = await asyncio.gather(
        audio_client.health_check(),
        vision_client.health_check(),
        tts_client.health_check(),
        teachme_client.health_check(),
        return_exceptions=True
    )

    service_names = ["audio_service", "vision_service", "tts_service", "teachme_service"]
    health_map = {}
    all_healthy = True

    for name, result in zip(service_names, results):
        if isinstance(result, Exception):
            health_map[name] = {"status": "error", "message": str(result)}
            all_healthy = False
        elif result.success:
            health_map[name] = {"status": "healthy", "data": result.data}
        else:
            health_map[name] = {"status": "unhealthy", "error_code": result.error_code}
            all_healthy = False

    from shared.models.api_response import success_response
    return success_response({
        "central_server": "healthy",
        "services": health_map,
        "all_services_healthy": all_healthy
    })
