"""
Vision Service Health Check Routes
From Vision-Nexus
"""

import cv2
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request

from ..models import HealthCheckResponse, ServiceHealthResponse, FaceDataResponse
from ..config import Config
from ..services.resource_pool import ResourcePool

logger = logging.getLogger(__name__)
router = APIRouter()

# Global resource pool reference (set by app.py)
_resource_pool: ResourcePool = None


def set_resource_pool(pool: ResourcePool):
    """Set the global resource pool reference"""
    global _resource_pool
    _resource_pool = pool


@router.get("/", response_model=ServiceHealthResponse)
async def health_check_root():
    """
    Root endpoint - service information
    From Vision-Nexus
    """
    return ServiceHealthResponse(
        service="Vision Service",
        version="4.0.0",
        status="operational",
        features=["face_detection", "face_embeddings", "video_streaming"],
        timestamp=datetime.utcnow().isoformat()
    )


@router.get("/health", response_model=HealthCheckResponse)
async def health_check_detailed(request: Request):
    """
    Detailed health check endpoint
    Return readiness without acquiring hardware; camera is intentionally not probed.
    """
    if _resource_pool is None:
        raise HTTPException(status_code=503, detail="Resource pool not initialized")
    
    face_model_loaded = getattr(request.app.state, "face_model_loaded", False)
    object_model_loaded = getattr(request.app.state, "object_model_loaded", False)
    object_status = (
        "disabled" if not Config.ENABLE_OBJECT_DETECTION
        else "loaded" if object_model_loaded
        else "unavailable"
    )
    models_ready = face_model_loaded and object_status in {"loaded", "disabled"}
    emotion_status = "disabled"
    
    return HealthCheckResponse(
        status="healthy" if models_ready else "degraded",
        camera="not_checked",
        face_model="loaded" if face_model_loaded else "unavailable",
        object_model=object_status,
        opencv_version=cv2.__version__,
        emotion_detection=emotion_status,
        timestamp=datetime.utcnow().isoformat()
    )


@router.get("/api/face-data", response_model=FaceDataResponse)
async def get_face_data():
    """
    Get current real-time face data
    Useful for web UI polling
    """
    if _resource_pool is None:
        raise HTTPException(status_code=500, detail="Resource pool not initialized")
    
    # This endpoint would be populated by concurrent face detection
    # For now, return empty data (will be updated by real-time processing)
    return FaceDataResponse(
        face_count=0,
        primary_emotion=None,
        confidence=None,
        timestamp=datetime.utcnow().isoformat()
    )
