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


class _CameraView:
    """Serialize frame reads with physical release during cooperative revocation."""
    def __init__(self, pool):
        self.pool = pool

    def read(self):
        with self.pool._frame_lock:
            if self.pool._camera is None:
                return False, None
            return self.pool._camera.read()


class ResourcePool:
    """Thread-safe resource pool for camera and YOLO object detector"""
    
    def __init__(self, camera_timeout: int = 10,
                 central_server_url: str = "https://localhost:8000",
                 enable_object_detection: bool = True, object_model_name: str = "yolov8n",
                 release_watchdog_timeout: float = 3.0):
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
        self._frame_lock = threading.Lock()
        self._object_detector = None
        self._object_detector_lock = threading.RLock()
        self._is_shutting_down = False
        self._camera_timeout = camera_timeout
        if release_watchdog_timeout <= 0:
            raise ValueError("Release watchdog timeout must be positive")
        self._release_watchdog_timeout = release_watchdog_timeout
        self.enable_object_detection = enable_object_detection
        self.object_model_name = object_model_name
        
        # Initialize camera resource client
        self._camera_client = get_camera_client(central_server_url, "vision_service")
        
    @contextmanager
    def get_camera(self, timeout: Optional[int] = None, delegated_lease_id: Optional[str] = None):
        """Open only after an acknowledged grant; close before acknowledging release."""
        timeout = timeout or self._camera_timeout
        if not self._camera_lock.acquire(timeout=timeout):
            raise RuntimeError(f"Camera lock timeout ({timeout}s) - resource busy")
        try:
            if self._is_shutting_down or self._camera is not None:
                raise RuntimeError("Camera is shutting down or previous closure failed")
            owns_lease = delegated_lease_id is None
            if owns_lease:
                if not self._camera_client.request_camera(timeout=timeout):
                    raise RuntimeError("Camera access denied or authority unreachable")
            elif not self._camera_client.validate_delegated_video_lease(
                delegated_lease_id, timeout=min(timeout, 2)
            ):
                raise RuntimeError("Delegated VIDEO_CALL camera lease is not active")
            stop = threading.Event()
            watcher = None
            try:
                self._camera = cv2.VideoCapture(0)
                if not self._camera.isOpened():
                    raise RuntimeError("Cannot access camera - verify device connection")
                if owns_lease:
                    watcher = threading.Thread(target=self._watch_lease,
                        args=(self._camera_client.lease_id, stop, self._camera), daemon=True)
                    watcher.start()
                yield _CameraView(self)
            finally:
                stop.set()
                if watcher is not None:
                    watcher.join(timeout=3)
                # A closure exception intentionally prevents release acknowledgement.
                self._close_camera()
                if owns_lease:
                    self._camera_client.release_camera()
        finally:
            self._camera_lock.release()

    def _close_camera(self, camera=None, forced=False):
        camera = self._camera if camera is None else camera
        acquired = False if forced else self._frame_lock.acquire(timeout=1)
        if not forced and not acquired:
            raise RuntimeError("Camera frame read did not yield for physical release")
        try:
            if camera is not None:
                camera.release()
                if camera.isOpened():
                    raise RuntimeError("Camera driver did not confirm physical closure")
                if self._camera is camera:
                    self._camera = None
        finally:
            if acquired:
                self._frame_lock.release()

    def _force_release(self, camera, lease_id, acknowledged):
        if acknowledged.is_set():
            return
        try:
            # This runs inside the holder process, independently of a stuck read
            # or graceful-release lock. Never acknowledge an unconfirmed close.
            self._close_camera(camera, forced=True)
            if self._camera_client.release_camera(timeout=1, lease_id=lease_id, forced=True):
                acknowledged.set()
                logger.warning("Camera watchdog confirmed forced release for lease %s", lease_id)
                return
        except Exception as exc:
            logger.error("Camera watchdog could not confirm release: %s", exc)
        timer = threading.Timer(1.0, self._force_release, args=(camera, lease_id, acknowledged))
        timer.daemon = True
        timer.start()

    def _watch_lease(self, lease_id, stop, camera):
        while not stop.wait(0.25):
            if not self._camera_client.lease_active(lease_id):
                acknowledged = threading.Event()
                timer = threading.Timer(self._release_watchdog_timeout, self._force_release,
                                        args=(camera, lease_id, acknowledged))
                timer.daemon = True
                timer.start()
                try:
                    self._close_camera(camera)
                    if self._camera_client.release_camera(timeout=1, lease_id=lease_id):
                        acknowledged.set()
                        timer.cancel()
                except Exception as exc:
                    logger.error("Physical camera release failed: %s", exc)
                return
    
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

