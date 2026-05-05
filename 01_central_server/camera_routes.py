"""
Camera Management Routes for Central Server
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from camera_manager import get_camera_manager

router = APIRouter(prefix="/camera", tags=["camera"])


class CameraRequest(BaseModel):
    """Camera request payload"""
    service_name: str
    timeout: int = 30


@router.post("/request")
def request_camera(request: CameraRequest):
    """
    Request camera access from Central Server
    
    Body:
    {
        "service_name": "vision_service",
        "timeout": 30
    }
    
    Response:
    {
        "status": "granted|denied",
        "message": "...",
        "held_by": "...",
        "timestamp": "..."
    }
    """
    manager = get_camera_manager()
    result = manager.request_camera(request.service_name, request.timeout)
    return result


@router.post("/release")
def release_camera(request: CameraRequest):
    """
    Release camera access
    
    Body:
    {
        "service_name": "vision_service"
    }
    
    Response:
    {
        "status": "released|error",
        "message": "...",
        "timestamp": "..."
    }
    """
    manager = get_camera_manager()
    result = manager.release_camera(request.service_name)
    return result


@router.get("/status")
def get_camera_status():
    """
    Get current camera status
    
    Response:
    {
        "status": "available|in_use",
        "held_by": "service_name or null",
        "held_duration_seconds": 5.3,
        "timestamp": "..."
    }
    """
    manager = get_camera_manager()
    result = manager.get_camera_status()
    return result


@router.post("/force-release")
def force_release_camera():
    """
    Force release camera (admin only - use with caution)
    
    Response:
    {
        "status": "released|error",
        "message": "...",
        "timestamp": "..."
    }
    """
    manager = get_camera_manager()
    result = manager.force_release_camera()
    return result
