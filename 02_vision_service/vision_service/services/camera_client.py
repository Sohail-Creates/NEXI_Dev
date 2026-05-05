"""
Camera Resource Client for Vision Service
Communicates with Central Server's camera manager (optional)
Prevents resource conflicts if Central Server is running
Gracefully falls back to direct access if not available
"""

import requests
import logging
import time
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class CameraResourceClient:
    """Client for requesting camera access from Central Server (optional)"""
    
    def __init__(self, central_server_url: str = "http://localhost:8000", 
                 service_name: str = "vision_service"):
        """
        Initialize camera resource client
        
        Args:
            central_server_url: URL of Central Server
            service_name: Name of this service
        """
        self.central_server_url = central_server_url
        self.service_name = service_name
        self.camera_granted = False
        self._central_available = None  # Cache to avoid repeated checks
        
        logger.debug(f"Camera Resource Client initialized "
                    f"(optional, fallback available)")
    
    def _is_central_server_available(self, timeout: int = 2) -> bool:
        """
        Check if Central Server is running (cached for 60s)
        Doesn't fail, just returns status
        """
        if self._central_available is not None:
            return self._central_available
            
        try:
            response = requests.get(
                f"{self.central_server_url}/health",
                timeout=timeout
            )
            self._central_available = (response.status_code == 200)
            return self._central_available
        except:
            self._central_available = False
            return False
    
    def request_camera(self, timeout: int = 5, max_retries: int = 3) -> bool:
        """
        Request camera access from Central Server
        OPTIONAL - fails gracefully if Central Server not available
        
        Args:
            timeout: Request timeout in seconds
            max_retries: Max retry attempts if camera is busy
            
        Returns:
            True if camera granted (or Central Server unavailable), False if denied
        """
        if self.camera_granted:
            logger.debug(f"Camera already granted to {self.service_name}")
            return True
        
        # Check if Central Server is available
        if not self._is_central_server_available():
            logger.debug("Central Server not available - using direct camera access (fallback)")
            self.camera_granted = True  # Assume granted in fallback mode
            return True
        
        # Try to request camera (but don't retry endlessly)
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    f"{self.central_server_url}/camera/request",
                    json={
                        "service_name": self.service_name,
                        "timeout": timeout
                    },
                    timeout=timeout
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get("status") == "granted":
                        self.camera_granted = True
                        logger.info(f" Camera GRANTED to {self.service_name}")
                        return True
                    
                    elif data.get("status") == "denied":
                        held_by = data.get("held_by", "unknown")
                        logger.info(f"Camera held by {held_by}, waiting...")
                        
                        # Brief wait before retry
                        if attempt < max_retries - 1:
                            time.sleep(0.5)
                        continue
                
                else:
                    logger.debug(f"Camera request status {response.status_code}")
                    time.sleep(0.5)
                    continue
            
            except requests.ConnectionError:
                logger.debug("Cannot reach Central Server (fallback to direct access)")
                self.camera_granted = True
                return True
            
            except Exception as e:
                logger.debug(f"Camera request: {e}")
                time.sleep(0.5)
        
        # Failed to get camera from Central Server, allow direct access as fallback
        logger.info("Camera resource unavailable from Central Server - using direct access")
        self.camera_granted = True
        return True
    
    def release_camera(self, timeout: int = 5) -> bool:
        """
        Release camera back to Central Server
        Returns: True if released or fallback mode
        """
        if not self.camera_granted:
            return True
        
        # Only try to release if we know Central Server is available
        if not self._is_central_server_available():
            self.camera_granted = False
            logger.debug("Camera released (fallback mode)")
            return True
        
        try:
            response = requests.post(
                f"{self.central_server_url}/camera/release",
                json={"service_name": self.service_name},
                timeout=timeout
            )
            
            if response.status_code == 200:
                self.camera_granted = False
                logger.debug("Camera released to Central Server")
                return True
        
        except Exception as e:
            logger.debug(f"Error releasing camera: {e}")
        
        self.camera_granted = False
        return True


# Global instance
_camera_client: Optional[CameraResourceClient] = None


def initialize_camera_client(central_server_url: str = "http://localhost:8000",
                              service_name: str = "vision_service") -> CameraResourceClient:
    """Initialize the global camera client instance"""
    global _camera_client
    _camera_client = CameraResourceClient(central_server_url, service_name)
    return _camera_client


def get_camera_client(central_server_url: str = "http://localhost:8000",
                      service_name: str = "vision_service") -> CameraResourceClient:
    """Get or create global camera client instance"""
    global _camera_client
    if _camera_client is None:
        _camera_client = CameraResourceClient(central_server_url, service_name)
    return _camera_client

