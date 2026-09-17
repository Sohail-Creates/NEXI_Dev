"""
Stop Word Detection Module for NEXI Audio Service.
Detects stop words for conversation termination using Porcupine library.

Features:
- Porcupine-based stop word detection (reuses PorcupineDetectorBase)
- Background detection with thread-aware CPU optimization
- Callback support for stop word events
- Dedicated audio stream for frame processing
- Event queue for async polling
"""

import logging
import threading
import asyncio
import struct
from typing import Optional, Callable, List
from datetime import datetime

import pyaudio

from audio_service.services.base_detector import PorcupineDetectorBase
from audio_service.device_selection import resolve_pyaudio_input

logger = logging.getLogger(__name__)


class StopWordDetector(PorcupineDetectorBase):
    """
    Detects stop words (e.g., "stop", "exit") for conversation termination.
    Inherits from PorcupineDetectorBase to avoid duplication with wake word detector.
    
    Example:
        detector = StopWordDetector(
            model_path="/path/to/stop.ppn",
            access_key="...",
            sensitivity=0.7,
            callback=lambda: print("Stop word detected!")
        )
        detector.start()
        detector.activate()  # When entering conversation mode
        detector.process_audio_frame(audio_data)  # Call from audio processing
        detector.deactivate()  # When exiting conversation mode
        detector.stop()
    """
    
    def __init__(
        self,
        model_path: str,
        access_key: str,
        sensitivity: float = 0.7,
        callback: Optional[Callable] = None
    ):
        """
        Initialize stop word detector.
        
        Args:
            model_path: Path to stop word Porcupine model file
            access_key: Porcupine API access key
            sensitivity: Detection sensitivity (0.0-1.0, default 0.7)
            callback: Optional callback when stop word detected
            
        Raises:
            ModelNotFoundError: If model file doesn't exist
            PorcupineInitializationError: If initialization fails
        """
        super().__init__(
            model_path=model_path,
            access_key=access_key,
            sensitivity=sensitivity,
            callback=callback,
            detector_name="StopWordDetector"
        )
        
        # Audio stream for dedicated microphone input
        self.audio_stream = None
        self.pyaudio_instance = None
        
        # Event queue for async polling
        self.event_queue = asyncio.Queue(maxsize=10)
        
        logger.info("StopWordDetector initialized with event queue")
    
    def get_keywords(self) -> List[str]:
        """Return stop words to detect."""
        return ["stop"]
    
    def _initialize_audio_stream(self):
        """
        Initialize PyAudio stream for stop word detection.
        
        Creates a dedicated audio input stream that feeds frames to the detector.
        Gracefully handles audio device unavailability.
        """
        try:
            if not self.porcupine_instance:
                logger.warning("Porcupine not initialized, cannot set up audio stream")
                return
            
            self.pyaudio_instance = pyaudio.PyAudio()
            input_device_index = resolve_pyaudio_input(self.pyaudio_instance)
            
            logger.debug(
                f"Opening audio stream: "
                f"sr={self.porcupine_instance.sample_rate}, "
                f"frame_length={self.porcupine_instance.frame_length}"
            )
            
            self.audio_stream = self.pyaudio_instance.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.porcupine_instance.sample_rate,
                input=True,
                input_device_index=input_device_index,
                frames_per_buffer=self.porcupine_instance.frame_length,
                exception_on_overflow=False
            )
            
            logger.info("Stop word detector audio stream initialized successfully")
        
        except OSError as e:
            logger.warning(f"Audio device unavailable for stop word detector: {e}")
            logger.info("Stop word detector will continue without audio (degraded mode)")
            self.audio_stream = None
            if self.pyaudio_instance:
                self.pyaudio_instance.terminate()
                self.pyaudio_instance = None
        
        except Exception as e:
            logger.error(f"Failed to initialize audio stream: {e}")
            self.audio_stream = None
            if self.pyaudio_instance:
                try:
                    self.pyaudio_instance.terminate()
                except:
                    pass
                self.pyaudio_instance = None
    
    def _cleanup_audio_stream(self):
        """
        Properly close audio stream and clean up PyAudio instance.
        """
        try:
            if self.audio_stream:
                self.audio_stream.close()
                self.audio_stream = None
                logger.debug("Stop word detector audio stream closed")
            
            if self.pyaudio_instance:
                self.pyaudio_instance.terminate()
                self.pyaudio_instance = None
                logger.debug("PyAudio instance terminated")
        
        except Exception as e:
            logger.warning(f"Error cleaning up audio stream: {e}")
    
    def _detection_tick(self):
        """
        Single detection iteration - read audio frame and process for stop word.
        
        Runs repeatedly in background thread when is_active=True.
        Handles graceful degradation if audio stream unavailable.
        """
        # If detection not active, sleep to save CPU
        if not self.is_active:
            threading.Event().wait(0.01)
            return
        
        # If no audio stream, sleep (graceful degradation)
        if not self.audio_stream:
            threading.Event().wait(0.01)
            return
        
        try:
            # Read audio frame from stream
            audio_chunk = self.audio_stream.read(
                self.porcupine_instance.frame_length,
                exception_on_overflow=False
            )
            
            # Convert bytes to format expected by Porcupine
            audio_data = struct.unpack_from(
                "h" * self.porcupine_instance.frame_length,
                audio_chunk
            )
            
            # Process frame for stop word detection
            self.process_audio_frame(audio_data)
        
        except KeyboardInterrupt:
            raise
        
        except OSError as e:
            # Audio device error (disconnected, etc)
            logger.warning(f"Audio stream error in stop word detector: {e}")
            logger.info("Stop word detector will continue without audio")
            self.audio_stream = None
        
        except Exception as e:
            logger.warning(f"Error in stop word detection loop: {e}")
    
    def process_audio_frame(self, frame) -> bool:
        """
        Process an audio frame for stop word detection.
        
        Args:
            frame: Audio frame (bytes or tuple of PCM samples)
            
        Returns:
            True if stop word detected, False otherwise
        """
        if not self.is_active or not self.porcupine_instance:
            return False
        
        try:
            # Porcupine.process() expects a sequence (tuple/list) of PCM samples
            # If frame is bytes, convert to tuple via struct.unpack (already done in _detection_tick)
            # If frame is already a tuple, use directly
            
            result = self.porcupine_instance.process(frame)
            
            if result >= 0:  # Detection result >= 0 means match
                logger.info(f"Stop word detected (keyword index: {result})")
                self._trigger_detection(keyword_index=result)
                return True
        
        except Exception as e:
            logger.warning(f"Error processing audio frame: {e}")
        
        return False
    
    def _trigger_detection(self, keyword_index: int = 0):
        """
        Handle detection event - call callback and queue event.
        Overrides base class to add event queue functionality.
        
        Args:
            keyword_index: Index of detected keyword
        """
        # Call parent implementation (handles callback)
        try:
            if self.callback:
                self.callback(keyword_index=keyword_index)
        except Exception as e:
            logger.error(f"Error in stop word detector callback: {e}")
        
        # Queue detection event for async polling
        try:
            event = {
                "event": "stop_word_detected",
                "keyword": "stop",
                "keyword_index": keyword_index,
                "timestamp": datetime.now().isoformat(),
                "confidence": 1.0
            }
            
            self.event_queue.put_nowait(event)
            logger.info("Stop word event queued for polling")
        
        except asyncio.QueueFull:
            logger.warning("Stop word event queue full, removing oldest event")
            try:
                self.event_queue.get_nowait()  # Remove oldest
                self.event_queue.put_nowait(event)  # Add new
            except:
                logger.warning("Failed to queue stop word event")
    
    async def get_next_event(self, timeout: float = 1.0) -> Optional[dict]:
        """
        Wait for next stop word detection event with timeout.
        
        Args:
            timeout: Maximum seconds to wait for event (0.1 to 60.0)
            
        Returns:
            dict: Event data if detected, None if timeout
        """
        try:
            event = await asyncio.wait_for(
                self.event_queue.get(),
                timeout=timeout
            )
            return event
        
        except asyncio.TimeoutError:
            return None
        
        except Exception as e:
            logger.error(f"Error getting detection event: {e}")
            return None
    
    def has_pending_events(self) -> bool:
        """Check if any detection events waiting in queue."""
        return not self.event_queue.empty()
    
    def get_event_count(self) -> int:
        """Get number of pending detection events."""
        return self.event_queue.qsize()
    
    def start(self):
        """
        Start stop word detection with dedicated audio stream.
        
        Overrides base class to initialize audio stream after Porcupine setup.
        """
        with self.state_lock:
            if self.is_running:
                logger.warning("Stop word detector already running")
                return
            
            try:
                # Initialize Porcupine
                self._initialize_porcupine()
                
                # Initialize audio stream
                self._initialize_audio_stream()
                
                # Start detection thread
                self.is_running = True
                self.detection_thread = threading.Thread(
                    target=self._detection_loop,
                    daemon=False,
                    name="StopWordDetector-DetectionThread"
                )
                self.detection_thread.start()
                
                if self.audio_stream:
                    logger.info("Stop word detector started with audio stream")
                else:
                    logger.warning("Stop word detector started without audio (degraded mode)")
            
            except Exception as e:
                logger.error(f"Failed to start stop word detector: {e}")
                self._cleanup_audio_stream()
                raise
    
    def stop(self):
        """
        Stop stop word detection and clean up resources.
        
        Overrides base class to clean up audio stream.
        """
        with self.state_lock:
            if not self.is_running:
                logger.debug("Stop word detector not running")
                return
            
            try:
                logger.info("Stopping stop word detector...")
                self.is_running = False
                
                # Wait for detection thread
                if self.detection_thread and self.detection_thread.is_alive():
                    logger.debug("Waiting for detection thread to finish...")
                    self.detection_thread.join(timeout=5)
                
                # Clean up Porcupine
                self._cleanup_porcupine()
                
                # Clean up audio stream
                self._cleanup_audio_stream()
                
                # Clear any pending events
                while not self.event_queue.empty():
                    try:
                        self.event_queue.get_nowait()
                    except:
                        break
                
                logger.info("Stop word detector stopped")
            
            except Exception as e:
                logger.error(f"Error stopping stop word detector: {e}")
                raise
