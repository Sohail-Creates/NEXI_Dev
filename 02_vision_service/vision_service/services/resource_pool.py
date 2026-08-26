"""
Vision Service Resource Pool
Thread-safe management of camera and object detection resources
Production implementation from Vision-Nexus
"""

import cv2
import threading
import logging
import sys
from typing import Optional
from contextlib import contextmanager

from .camera_client import get_camera_client

logger = logging.getLogger(__name__)


class ResourcePool:
    """Thread-safe resource pool for camera and YOLO object detector"""
    
    def __init__(self, camera_timeout: int = 10,
                 central_server_url: str = "http://localhost:8000",
                 enable_object_detection: bool = True, object_model_name: str = "yolov8n"):
        """
        Initialize resource pool
        
        Args:
            camera_timeout: Timeout for camera access in seconds
            central_server_url: URL of Central Server for camera resource management
            enable_object_detection: Whether to enable YOLO object detection
            object_model_name: YOLO model to use (yolov8n, yolov8s, etc)
        """
        self._camera = None
        self._camera_lock = threading.RLock()
        self._object_detector = None
        self._object_detector_lock = threading.RLock()
        self._is_shutting_down = False
        self._camera_timeout = camera_timeout
        self.enable_object_detection = enable_object_detection
        self.object_model_name = object_model_name
        
        # Initialize camera resource client
        self._camera_client = get_camera_client(central_server_url, "vision_service")
        
    @contextmanager
    def get_camera(self, timeout: Optional[int] = None):
        """
        Get camera with automatic lock and cleanup
        Thread-safe camera access pattern from Vision-Nexus
        
        Args:
            timeout: Lock timeout in seconds
            
        Yields:
            cv2.VideoCapture instance
            
        Raises:
            RuntimeError: If camera not available or lock timeout
        """
        timeout = timeout or self._camera_timeout
        
        # REQUEST CAMERA FROM CENTRAL SERVER
        if not self._camera_client.request_camera(timeout=timeout):
            raise RuntimeError(
                "Camera access denied - another service is using the camera. "
                "Please try again later or check Central Server camera status."
            )
        
        acquired = self._camera_lock.acquire(timeout=timeout)
        
        if not acquired:
            self._camera_client.release_camera()
            raise RuntimeError(f"Camera lock timeout ({timeout}s) - resource busy")
        
        try:
            if self._camera is None or not self._camera.isOpened():
                self._camera = cv2.VideoCapture(0)
                if not self._camera.isOpened():
                    raise RuntimeError("Cannot access camera - verify device connection")
                logger.info(" Camera initialized successfully")
            
            yield self._camera
        
        except Exception as e:
            logger.error(f"Camera access error: {e}")
            if self._camera:
                try:
                    self._camera.release()
                except:
                    pass
                self._camera = None
            raise
        finally:
            self._camera_lock.release()
            # RELEASE CAMERA BACK TO CENTRAL SERVER
            self._camera_client.release_camera()
    
    def is_camera_available(self) -> bool:
        """Check if camera is available and working"""
        try:
            with self.get_camera(timeout=2):
                return True
        except Exception as e:
            logger.warning(f"Camera availability check failed: {e}")
            return False
    
    def get_object_detector(self):
        """
        Get YOLO object detector instance
        Lazy initialization with thread safety
        
        Returns:
            ObjectDetector instance or None if object detection disabled
        """
        if not self.enable_object_detection:
            return None
            
        acquired = self._object_detector_lock.acquire(timeout=120)  # Model loading timeout
        if not acquired:
            raise RuntimeError("Object detector lock timeout - model loading in progress")
        
        try:
            if self._object_detector is None:
                from .object_detector import ObjectDetector
                from pathlib import Path
                
                # Try to load from models directory first
                models_dir = Path(__file__).parent.parent.parent / "models"
                model_path = models_dir / f"{self.object_model_name}.pt"
                
                logger.info(f"Initializing YOLO object detector ({self.object_model_name})...")
                self._object_detector = ObjectDetector(
                    model_name=self.object_model_name,
                    model_path=str(model_path) if model_path.exists() else None
                )
                
                if not self._object_detector.load_model():
                    logger.error(f"Failed to load YOLO model: {self.object_model_name}")
                    self._object_detector = None
                    return None
                
                logger.info("YOLO object detector initialized successfully")
            return self._object_detector
        finally:
            self._object_detector_lock.release()
    
    def is_object_detector_available(self) -> bool:
        """Check if YOLO object detector is available"""
        if not self.enable_object_detection:
            return False
        try:
            detector = self.get_object_detector()
            return detector is not None and detector.available
        except Exception as e:
            logger.warning(f"Object detector availability check failed: {e}")
            return False
    
    def shutdown(self):
        """Clean shutdown of all resources (Vision-Nexus pattern)"""
        self._is_shutting_down = True
        
        with self._camera_lock:
            if self._camera:
                try:
                    self._camera.release()
                    logger.info("Camera resources released")
                except Exception as e:
                    logger.error(f"Error releasing camera: {e}")
                finally:
                    self._camera = None
        
        with self._object_detector_lock:
            self._object_detector = None
            logger.info("YOLO object detector resources released")
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.shutdown()

