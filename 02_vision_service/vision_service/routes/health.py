"""
Vision Service Health Check Routes
From Vision-Nexus
"""

import cv2
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException

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
async def health_check_detailed():
    """
    Detailed health check endpoint
    Returns status of camera, emotion detection, and other resources
    From Vision-Nexus
    
    NOTE: This is a QUICK status check - does NOT attempt to acquire resources
    to avoid blocking on camera/model access. Use /detect/faces for actual capability check.
    """
    if _resource_pool is None:
        raise HTTPException(status_code=500, detail="Resource pool not initialized")
    
    # Quick status - don't try to access camera (that blocks!)
    # Camera is checked on first request when needed
    camera_status = "available"  # Assume available, will fail gracefully if not
    emotion_status = "disabled"
    
    return HealthCheckResponse(
        status="healthy",  # Service is running and ready
        camera=camera_status,
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
