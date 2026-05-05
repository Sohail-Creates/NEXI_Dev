"""
Central Server Camera Resource Manager
Manages camera allocation across all services to prevent resource conflicts
"""

from _thread import RLock
import threading
import time
from typing import Optional, Dict
from datetime import datetime
import logging

logger: logging.Logger = logging.getLogger(__name__)


class CameraManager:
    """Centralized camera resource manager for NEXI services"""
    
    def __init__(self) -> None:
        """Initialize camera manager with resource tracking"""
        self._lock: RLock = threading.RLock()
        self._camera_holder: Optional[str] = None  # Service holding camera
        self._request_time: Optional[float] = None  # When camera was acquired
        self._timeout = 60  # Max time one service can hold camera (seconds)
        self._request_queue: Dict[str, float] = {}  # Services waiting for camera
        
        logger.info("Camera Resource Manager initialized")
    
    def request_camera(self, service_name: str, timeout: int = 30) -> Dict:
        """
        Request camera access from Central Server
        
        Args:
            service_name: Name of requesting service (e.g., "vision_service")
            timeout: How long to wait for camera if busy (seconds)
            
        Returns:
            {
                "status": "granted|denied|waiting",
                "message": "Camera access description",
                "held_by": "service_name or None",
                "timestamp": "ISO timestamp"
            }
        """
        with self._lock:
            current_time: float = time.time()
            
            # Check if camera is held
            if self._camera_holder is None:
                # Camera is free - grant access
                self._camera_holder = service_name
                self._request_time = current_time
                logger.info(f"✓ Camera GRANTED to {service_name}")
                
                return {
                    "status": "granted",
                    "message": f"Camera allocated to {service_name}",
                    "held_by": service_name,
                    "timestamp": datetime.now().isoformat()
                }
            
            # Camera is held by another service
            elif self._camera_holder == service_name:
                # Same service requesting again - allow renewal
                logger.info(f"✓ Camera time RENEWED for {service_name}")
                self._request_time = current_time
                
                return {
                    "status": "granted",
                    "message": f"Camera access renewed for {service_name}",
                    "held_by": service_name,
                    "timestamp": datetime.now().isoformat()
                }
            
            else:
                # Different service holding camera
                current_holder: str = self._camera_holder
                held_duration = current_time - self._request_time
                
                logger.warning(
                    f"✗ Camera DENIED to {service_name} - "
                    f"held by {current_holder} ({held_duration:.1f}s)"
                )
                
                return {
                    "status": "denied",
                    "message": f"Camera is in use by '{current_holder}'. "
                              f"Please wait ({held_duration:.1f}s elapsed)",
                    "held_by": current_holder,
                    "held_duration_seconds": held_duration,
                    "timestamp": datetime.now().isoformat()
                }
    
    def release_camera(self, service_name: str) -> Dict:
        """
        Release camera access
        
        Args:
            service_name: Name of service releasing camera
            
        Returns:
            {
                "status": "released|error",
                "message": "Description",
                "timestamp": "ISO timestamp"
            }
        """
        with self._lock:
            if self._camera_holder == service_name:
                held_duration = time.time() - self._request_time
                self._camera_holder = None
                self._request_time = None
                
                logger.info(f"✓ Camera RELEASED by {service_name} "
                           f"(held for {held_duration:.1f}s)")
                
                return {
                    "status": "released",
                    "message": f"Camera released by {service_name}",
                    "held_duration_seconds": held_duration,
                    "timestamp": datetime.now().isoformat()
                }
            
            elif self._camera_holder is None:
                logger.warning(f"⚠ {service_name} tried to release camera (not held)")
                
                return {
                    "status": "error",
                    "message": f"Camera is not currently held by any service",
                    "timestamp": datetime.now().isoformat()
                }
            
            else:
                logger.warning(
                    f"✗ {service_name} tried to release camera "
                    f"(held by {self._camera_holder})"
                )
                
                return {
                    "status": "error",
                    "message": f"Camera is held by '{self._camera_holder}', "
                              f"not by '{service_name}'",
                    "held_by": self._camera_holder,
                    "timestamp": datetime.now().isoformat()
                }
    
    def get_camera_status(self) -> Dict:
        """Get current camera status"""
        with self._lock:
            if self._camera_holder is None:
                return {
                    "status": "available",
                    "held_by": None,
                    "timestamp": datetime.now().isoformat()
                }
            
            else:
                held_duration = time.time() - self._request_time
                return {
                    "status": "in_use",
                    "held_by": self._camera_holder,
                    "held_duration_seconds": held_duration,
                    "timestamp": datetime.now().isoformat()
                }
    
    def force_release_camera(self) -> Dict:
        """Force release camera (admin only)"""
        with self._lock:
            if self._camera_holder is None:
                return {
                    "status": "error",
                    "message": "Camera is not currently held",
                    "timestamp": datetime.now().isoformat()
                }
            
            previous_holder: str = self._camera_holder
            self._camera_holder = None
            self._request_time = None
            
            logger.warning(f"⚠ Camera forcefully released (was held by {previous_holder})")
            
            return {
                "status": "released",
                "message": f"Camera forcefully released (was held by {previous_holder})",
                "timestamp": datetime.now().isoformat()
            }


# Global camera manager instance
_camera_manager: Optional[CameraManager] = None


def get_camera_manager() -> CameraManager:
    """Get or create global camera manager"""
    global _camera_manager
    if _camera_manager is None:
        _camera_manager = CameraManager()
    return _camera_manager
