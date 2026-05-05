"""
Vision Service Camera Control Routes
"""

import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException

from ..models import CameraStateResponse
from ..config import Config
from ..services.resource_pool import ResourcePool

logger = logging.getLogger(__name__)
router = APIRouter()

# Global resource pool reference and state
_resource_pool: ResourcePool = None
_camera_paused: bool = False


def set_resource_pool(pool: ResourcePool):
    """Set the global resource pool reference"""
    global _resource_pool
    _resource_pool = pool


@router.post("/camera/pause", response_model=CameraStateResponse)
async def pause_camera():
    """Pause camera - stop capturing frames"""
    global _camera_paused
    
    if _resource_pool is None:
        raise HTTPException(status_code=500, detail="Resource pool not initialized")
    
    try:
        _camera_paused = True
        logger.info("Camera paused")
        
        return CameraStateResponse(
            status="paused"
        )
    except Exception as e:
        logger.error(f"Error pausing camera: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to pause camera: {str(e)}")


@router.post("/camera/resume", response_model=CameraStateResponse)
async def resume_camera():
    """Resume camera - start capturing frames"""
    global _camera_paused
    
    if _resource_pool is None:
        raise HTTPException(status_code=500, detail="Resource pool not initialized")
    
    try:
        _camera_paused = False
        logger.info("Camera resumed")
        
        return CameraStateResponse(
            status="active"
        )
    except Exception as e:
        logger.error(f"Error resuming camera: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to resume camera: {str(e)}")


def is_camera_paused() -> bool:
    """Check if camera is paused"""
    return _camera_paused
