"""
Base Porcupine Detector Class for NEXI Audio Service.
Provides common initialization, error handling, and lifecycle management
for all Porcupine-based detectors (wake word, stop word, etc.).

This eliminates duplication between WakeWordDetector and StopWordDetector.
"""

import logging
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Callable, List
from datetime import datetime

import pvporcupine

logger = logging.getLogger(__name__)


class DetectionError(Exception):
    """Base exception for detection-related errors."""
    pass


class PorcupineInitializationError(DetectionError):
    """Raised when Porcupine initialization fails."""
    pass


class ModelNotFoundError(DetectionError):
    """Raised when detection model file is not found."""
    pass


class PorcupineDetectorBase(ABC):
    """
    Abstract base class for Porcupine-based detectors.
    Provides common initialization, error handling, and lifecycle management.
    
    Subclasses implement detection logic via process_audio_frame().
    
    Attributes:
        model_path: Path to Porcupine model file
        access_key: Porcupine API key
        sensitivity: Detection sensitivity (0.0-1.0)
        porcupine_instance: Initialized Porcupine object
        is_running: Whether detection loop is active
        is_active: Whether detection is enabled (can be toggled)
        detection_thread: Background detection thread
    """
    
    def __init__(
        self,
        model_path: str,
        access_key: str,
        sensitivity: float = 0.7,
        callback: Optional[Callable] = None,
        detector_name: str = "PorcupineDetector"
    ):
        """
        Initialize base Porcupine detector.
        
        Args:
            model_path: Path to Porcupine model file
            access_key: Porcupine API access key
            sensitivity: Detection sensitivity (0.0-1.0, default 0.7)
            callback: Optional callback when keyword detected
            detector_name: Name for logging (e.g., "WakeWordDetector")
            
        Raises:
            ModelNotFoundError: If model file doesn't exist
        """
        if not model_path:
            raise ModelNotFoundError(f"{detector_name}: Model path is None or empty")
        
        self.model_path = Path(model_path)
        self.access_key = access_key
        self.sensitivity = sensitivity
        self.callback = callback
        self.detector_name = detector_name
        
        # Validate model file
        if not self.model_path.exists():
            raise ModelNotFoundError(f"Model not found: {self.model_path}")
        
        logger.info(f"{detector_name}: Model validated at {self.model_path}")
        
        # State
        self.porcupine_instance = None
        self.is_running = False
        self.is_active = False
        self.detection_thread = None
        self.state_lock = threading.RLock()
        
        logger.info(f"{detector_name}: Initialized (sensitivity={sensitivity})")
    
    @abstractmethod
    def get_keywords(self) -> List[str]:
        """
        Return list of keywords to detect.
        Must be implemented by subclass.
        
        Returns:
            List of keyword strings (e.g., ["hey nexi"] or ["stop"])
        """
        pass
    
    def _initialize_porcupine(self):
        """
        Initialize Porcupine instance with configured keywords or custom model.
        Supports both default keywords and custom model files.
        
        Raises:
            PorcupineInitializationError: If initialization fails
        """
        try:
            # Check if model file exists and is valid
            has_model = self.model_path and isinstance(self.model_path, Path) and self.model_path.exists()
            
            if has_model:
                # Use custom model via keyword_paths
                logger.info(
                    f"{self.detector_name}: Using custom Porcupine model at {self.model_path}"
                )
                
                self.porcupine_instance = pvporcupine.create(
                    access_key=self.access_key,
                    keyword_paths=[str(self.model_path)],
                    sensitivities=[self.sensitivity]
                )
            else:
                # Fall back to default keywords (for wake word only)
                keywords = self.get_keywords()
                sensitivities = [self.sensitivity] * len(keywords)
                
                logger.info(
                    f"{self.detector_name}: Using default Porcupine keywords: {keywords}"
                )
                
                self.porcupine_instance = pvporcupine.create(
                    access_key=self.access_key,
                    keywords=keywords,
                    sensitivities=sensitivities
                )
            
            logger.info(
                f"{self.detector_name}: Porcupine initialized "
                f"(frame_length={self.porcupine_instance.frame_length})"
            )
        
        except Exception as e:
            logger.error(f"{self.detector_name}: Porcupine initialization failed: {e}")
            raise PorcupineInitializationError(str(e))
    
    def _cleanup_porcupine(self):
        """Clean up Porcupine instance gracefully."""
        try:
            if self.porcupine_instance:
                self.porcupine_instance.delete()
                self.porcupine_instance = None
                logger.info(f"{self.detector_name}: Porcupine cleaned up")
        except Exception as e:
            logger.warning(f"{self.detector_name}: Error cleaning up Porcupine: {e}")
    
    def start(self):
        """
        Start detection in background thread.
        
        Raises:
            PorcupineInitializationError: If Porcupine initialization fails
        """
        with self.state_lock:
            if self.is_running:
                logger.warning(f"{self.detector_name}: Already running")
                return
            
            try:
                self._initialize_porcupine()
                self.is_running = True
                
                # Start background thread
                self.detection_thread = threading.Thread(
                    target=self._detection_loop,
                    daemon=False,
                    name=f"{self.detector_name}-DetectionThread"
                )
                self.detection_thread.start()
                logger.info(f"{self.detector_name}: Started (thread={self.detection_thread.name})")
            
            except Exception as e:
                logger.error(f"{self.detector_name}: Failed to start: {e}")
                raise
    
    def stop(self):
        """Stop detection and clean up resources."""
        with self.state_lock:
            if not self.is_running:
                logger.debug(f"{self.detector_name}: Not running")
                return
            
            try:
                logger.info(f"{self.detector_name}: Stopping...")
                self.is_running = False
                
                # Wait for thread
                if self.detection_thread and self.detection_thread.is_alive():
                    logger.debug(f"{self.detector_name}: Waiting for thread to finish...")
                    self.detection_thread.join(timeout=5)
                
                # Cleanup
                self._cleanup_porcupine()
                logger.info(f"{self.detector_name}: Stopped")
            
            except Exception as e:
                logger.error(f"{self.detector_name}: Error stopping: {e}")
                raise
    
    def activate(self):
        """Enable detection (but keep thread running)."""
        with self.state_lock:
            if not self.is_active:
                self.is_active = True
                logger.info(f"{self.detector_name}: Activated")
    
    def deactivate(self):
        """Disable detection to save CPU (thread keeps running)."""
        with self.state_lock:
            if self.is_active:
                self.is_active = False
                logger.info(f"{self.detector_name}: Deactivated (thread still running)")
    
    def _detection_loop(self):
        """
        Background detection loop. Checks if detection is active before processing.
        Designed to be minimal - actual processing done by subclass.
        """
        logger.debug(f"{self.detector_name}: Detection loop started")
        
        while self.is_running:
            # Detection disabled - just idle
            if not self.is_active:
                threading.Event().wait(0.1)  # Sleep 100ms to avoid CPU spin
                continue
            
            try:
                # Subclass implements actual detection
                self._detection_tick()
            
            except Exception as e:
                logger.error(f"{self.detector_name}: Error in detection loop: {e}")
                # Continue running even on errors
        
        logger.debug(f"{self.detector_name}: Detection loop ended")
    
    @abstractmethod
    def _detection_tick(self):
        """
        Single detection iteration. Must be implemented by subclass.
        Called repeatedly by _detection_loop() when is_active=True.
        
        Subclass should read audio frame and call _trigger_detection() if keyword found.
        """
        pass
    
    def _trigger_detection(self, keyword_index: int = 0):
        """
        Call this when keyword is detected. Invokes callback if registered.
        
        Args:
            keyword_index: Index of which keyword was detected (for multi-keyword)
        """
        try:
            if self.callback:
                self.callback(keyword_index=keyword_index)
        except Exception as e:
            logger.error(f"{self.detector_name}: Error in callback: {e}")
    
    def get_state(self) -> dict:
        """
        Get current detector state.
        
        Returns:
            Dict with state information
        """
        with self.state_lock:
            return {
                "is_running": self.is_running,
                "is_active": self.is_active,
                "detector_name": self.detector_name,
                "model_path": str(self.model_path),
                "sensitivity": self.sensitivity
            }
