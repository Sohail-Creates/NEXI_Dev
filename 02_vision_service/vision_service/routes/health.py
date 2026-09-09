"""
Vision Service Health Check Routes
From Vision-Nexus
"""

import cv2
import asyncio
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
        features=["face_detection", "face_embeddings", "emotion_analysis", "video_streaming"],
        timestamp=datetime.utcnow().isoformat()
    )


@router.get("/health", response_model=HealthCheckResponse)
async def health_check_detailed(request: Request):
    """
    Detailed health check endpoint
    Report the model initialization result and actual camera availability.
    """
    if _resource_pool is None:
        raise HTTPException(status_code=503, detail="Resource pool not initialized")
    
    camera_available = await asyncio.to_thread(_resource_pool.is_camera_available)
    camera_status = "available" if camera_available else "unavailable"
    face_model_loaded = getattr(request.app.state, "face_model_loaded", False)
    emotion_status = "disabled"
    
    return HealthCheckResponse(
        status="healthy" if camera_available and face_model_loaded else "degraded",
        camera=camera_status,
        face_model="loaded" if face_model_loaded else "unavailable",
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
