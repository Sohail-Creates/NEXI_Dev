"""
Wake word detection service using Porcupine.
Implements continuous listening for the activation phrase "Hey Nexi" (using Jarvis keyword).

Week 3 Enhancements:
- Voice Activity Detection (VAD) for power optimization
- Power mode switching (low_power/balanced/high_performance)
- error handling with auto-recovery
- Performance monitoring and statistics
"""

import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable
from collections import deque

import numpy as np
import pvporcupine
import sounddevice as sd
from scipy.io import wavfile

from audio_service.config import (
    WAKE_WORD_CONFIG,
    PORCUPINE_ACCESS_KEY,
    DATA_DIR,
    WAKE_WORD_FILE_PREFIX,
    TIMESTAMP_FORMAT,
    AUDIO_FILE_EXTENSION,
    VAD_CONFIG,
    POWER_CONFIG
)
from audio_service.services.keyboard_wake_word import KeyboardWakeWordListener
from audio_service.device_selection import resolve_sounddevice_input
from audio_service.utils.vad import VoiceActivityDetector
from audio_service.utils.errors import (
    WakeWordError,
    WakeWordAlreadyRunningError,
    WakeWordNotRunningError,
    MicrophoneError,
    MicrophoneNotFoundError,
    AudioBufferError,
    wrap_error
)

logger = logging.getLogger(__name__)


class WakeWordService:
    """
    Service for continuous wake word detection with power optimization.
    
    Week 3 Enhancements:
    - Two-stage detection: VAD (fast) → Porcupine (expensive)
    - Power mode management for battery optimization
    - Auto-recovery from microphone errors
    - Performance statistics tracking
    
    This service runs in a background thread and continuously monitors audio input
    for the wake word. When detected, it records the subsequent command and triggers
    a callback function for further processing.
    """
    
    def __init__(self, power_mode: str = None):
        """
        Initialize the wake word detection service.
        
        Args:
            power_mode: Power mode ('low_power', 'balanced', 'high_performance')
                       If None, uses default from config
        """
        self.porcupine: Optional[pvporcupine.Porcupine] = None
        self.is_listening: bool = False
        self.detection_thread: Optional[threading.Thread] = None
        self.audio_stream: Optional[sd.InputStream] = None
        self.detection_callback: Optional[Callable] = None
        self.keyboard_listener: Optional[KeyboardWakeWordListener] = None
        self.using_keyboard: bool = False
        
        # Audio buffer for pre-wake word context
        # This stores audio before wake word is detected so we can include it
        self.pre_buffer: deque = deque(
            maxlen=int(WAKE_WORD_CONFIG["buffer_duration"] * 16000 / WAKE_WORD_CONFIG["frame_length"])
        )
        
        # Power optimization
        self.power_mode = power_mode or POWER_CONFIG["default_mode"]
        self.power_settings = POWER_CONFIG[self.power_mode]
        
        # VAD for power saving
        self.vad: Optional[VoiceActivityDetector] = None
        if self.power_settings.get("vad_enabled", False):
            self.vad = VoiceActivityDetector(
                sample_rate=16000,
                frame_duration_ms=VAD_CONFIG["frame_duration_ms"],
                energy_threshold=VAD_CONFIG["energy_threshold"],
                adaptive_threshold=VAD_CONFIG["adaptive_threshold"],
                webrtc_mode=VAD_CONFIG["webrtc_mode"]
            )
            logger.info(f"VAD initialized for power mode: {self.power_mode}")
        
        # Performance statistics
        self.stats = {
            "total_frames": 0,
            "speech_frames": 0,
            "silence_frames": 0,
            "wake_word_detections": 0,
            "false_positives": 0,
            "errors": 0,
            "start_time": None
        }
        
        # Microphone reconnection
        self.mic_reconnect_attempts = 0
        self.max_reconnect_attempts = 3
        
        logger.info(f"Wake word service initialized (power_mode={self.power_mode})")

    def _input_device_index(self) -> int:
        device = resolve_sounddevice_input()
        logger.info(
            "Using audio input index=%s name=%s hostapi=%s",
            device.index,
            device.name,
            device.hostapi,
        )
        return device.index
    
    def set_power_mode(self, mode: str):
        """
        Change power mode dynamically.
        
        Args:
            mode: Power mode ('low_power', 'balanced', 'high_performance')
        
        Raises:
            ValueError: If mode is invalid
        """
        if mode not in ["low_power", "balanced", "high_performance"]:
            raise ValueError(f"Invalid power mode: {mode}")
        
        self.power_mode = mode
        self.power_settings = POWER_CONFIG[mode]
        
        # Update VAD if needed
        if self.power_settings.get("vad_enabled", False) and self.vad is None:
            self.vad = VoiceActivityDetector(
                sample_rate=16000,
                frame_duration_ms=VAD_CONFIG["frame_duration_ms"],
                energy_threshold=VAD_CONFIG["energy_threshold"],
                adaptive_threshold=VAD_CONFIG["adaptive_threshold"]
            )
            logger.info(f"VAD enabled for power mode: {mode}")
        elif not self.power_settings.get("vad_enabled", False):
            self.vad = None
            logger.info(f"VAD disabled for power mode: {mode}")
        
        logger.info(f"Power mode changed to: {mode}")
    
    def initialize_porcupine(self):
        """Initialize Porcupine, falling back to direct voice on failure."""
        try:
            self.porcupine = pvporcupine.create(
                access_key=PORCUPINE_ACCESS_KEY,
                keyword_paths=[str(WAKE_WORD_CONFIG["keyword_path"])],
                sensitivities=[WAKE_WORD_CONFIG["sensitivity"]]
            )
            self.using_keyboard = False
            logger.info("Porcupine initialized")
        except Exception as e:
            self._activate_direct_voice_fallback(e)

    def _activate_direct_voice_fallback(self, error):
        """Use the same direct-voice path for every wake-detection failure."""
        logger.error("Wake-word detection failed: %s. Switching to direct voice.", error)
        self.cleanup_porcupine()
        self.using_keyboard = True
        if self.keyboard_listener is None:
            self.keyboard_listener = KeyboardWakeWordListener(
                callback=self._handle_wake_word_detected
            )

    def _run_direct_voice_fallback(self):
        listener = self.keyboard_listener
        listener.start()
        try:
            while self.is_listening:
                if listener.error is not None:
                    self.stats["errors"] += 1
                    self.is_listening = False
                    break
                time.sleep(0.05)
        finally:
            listener.stop()

    def _handle_wake_word_detected(self, audio_file, confidence):
        """Forward the actual recording captured by the direct voice fallback."""
        if self.detection_callback:
            logger.info(f"Direct voice recording received: {audio_file}")
            self.detection_callback(audio_file, confidence)

    def cleanup_porcupine(self):
        """Release Porcupine resources."""
        if self.porcupine is not None:
            self.porcupine.delete()
            self.porcupine = None
            logger.info("Porcupine resources released")
        if self.keyboard_listener is not None:
            self.keyboard_listener.stop()
            self.keyboard_listener = None
    
    def start_listening(self, detection_callback: Optional[Callable] = None):
        """
        Start continuous wake word detection.
        
        This begins the background listening loop that monitors for the wake word.
        When detected, it records the command and calls the callback function.
        
        Args:
            detection_callback: Optional callback function to call when wake word is detected.
                               Function signature: callback(audio_file_path: str, confidence: float)
        
        Raises:
            WakeWordAlreadyRunningError: If service is already running
            WakeWordError: If initialization fails
        """
        try:
            if self.is_listening:
                raise WakeWordAlreadyRunningError()
            
            # Initialize Porcupine if not already done
            if self.porcupine is None:
                self.initialize_porcupine()
            
            # Store the callback function
            self.detection_callback = detection_callback
            
            # Set listening flag
            self.is_listening = True
            
            # Reset statistics
            self.stats["start_time"] = datetime.now()
            self.stats["total_frames"] = 0
            self.stats["speech_frames"] = 0
            self.stats["silence_frames"] = 0
            
            # Start detection thread
            self.detection_thread = threading.Thread(
                target=self._detection_loop,
                daemon=True,
                name="WakeWordDetectionThread"
            )
            self.detection_thread.start()
            
            logger.info(f"Wake word detection started successfully (power_mode={self.power_mode})")
            
        except WakeWordAlreadyRunningError:
            raise
        except Exception as e:
            self.is_listening = False
            error_msg = f"Failed to start wake word detection: {str(e)}"
            logger.error(error_msg)
            raise WakeWordError(error_msg, technical_details=str(e)) from e
    
    def stop_listening(self):
        """
        Stop wake word detection.
        
        This gracefully stops the listening loop and releases resources.
        """
        try:
            if not self.is_listening:
                logger.warning("Wake word detection is not running")
                return
            
            # Set flag to stop the loop
            self.is_listening = False

            # Manual stop must interrupt the active direct-voice session first.
            if self.keyboard_listener is not None:
                self.keyboard_listener.stop()
            
            # Wait for thread to finish with timeout
            if self.detection_thread is not None:
                self.detection_thread.join(timeout=2.0)
                if self.detection_thread.is_alive():
                    logger.warning("Detection thread did not stop gracefully")
            
            # Close audio stream if open
            if self.audio_stream is not None:
                self.audio_stream.close()
                self.audio_stream = None
            
            # Cleanup Porcupine
            self.cleanup_porcupine()
            
            # Log statistics
            self._log_statistics()
            
            logger.info("Wake word detection stopped successfully")
            
        except Exception as e:
            error_msg = f"Error stopping wake word detection: {str(e)}"
            logger.error(error_msg)
            raise WakeWordError(error_msg, technical_details=str(e)) from e
    
    def _detection_loop(self):
        """
        Main detection loop with VAD-based power optimization.
        
        Two-stage detection
        - Stage 1: Fast VAD check (<1ms) filters 99% of silence  
        - Stage 2: Expensive Porcupine only runs when speech detected
        - Dynamic sleep during silence periods saves 70-80% CPU
        
        This continuously captures audio and processes it intelligently.
        When a wake word is detected, it records the command and triggers the callback.
        """
        logger.info(f"Detection loop started - power_mode={self.power_mode}, VAD={'enabled' if self.vad else 'disabled'}")
        
        # The fallback listener owns microphone recording when Porcupine is unavailable.
        if self.using_keyboard or self.porcupine is None:
            logger.info("Direct voice fallback active")
            self._run_direct_voice_fallback()
            return
        
        try:
            # Porcupine requires specific frame length
            frame_length = self.porcupine.frame_length
            sample_rate = self.porcupine.sample_rate
            
            # Heartbeat counter for diagnostic logging
            frame_count = 0
            heartbeat_frames = int(WAKE_WORD_CONFIG["heartbeat_interval"] * sample_rate / frame_length)
            
            # VAD state tracking
            consecutive_speech_frames = 0
            consecutive_silence_frames = 0
            speech_threshold = VAD_CONFIG.get("speech_frames_threshold", 2)
            silence_threshold = VAD_CONFIG.get("silence_frames_threshold", 10)
            
            # Create audio stream for continuous recording
            try:
                with sd.InputStream(
                    samplerate=sample_rate,
                    channels=1,
                    dtype=np.int16,
                    blocksize=frame_length,
                    device=self._input_device_index(),
                ) as stream:
                    
                    self.audio_stream = stream
                    logger.info(f"Audio stream opened (sr={sample_rate}Hz, frame_length={frame_length})")
                    logger.info(f"Listening for keyword '{WAKE_WORD_CONFIG['keyword']}' with sensitivity {WAKE_WORD_CONFIG['sensitivity']}")
                    
                    while self.is_listening:
                        try:
                            # Read audio frame from microphone
                            audio_frame, overflowed = stream.read(frame_length)
                            
                            if overflowed:
                                logger.warning("Audio buffer overflow detected")
                                self.stats["errors"] += 1
                            
                            # Convert to 1D array of int16
                            audio_frame = audio_frame.flatten().astype(np.int16)
                            
                            # Store in pre-buffer for context
                            self.pre_buffer.append(audio_frame)
                            
                            # Update statistics
                            self.stats["total_frames"] += 1
                            frame_count += 1
                            
                            # WEEK 3: STAGE 1 - Fast VAD Check (Power Optimization)
                            is_speech = True  # Default: process everything
                            
                            if self.vad is not None:
                                # Run VAD (< 1ms processing time)
                                is_speech, vad_meta = self.vad.is_speech(
                                    audio_frame,
                                    use_webrtc=VAD_CONFIG.get("use_webrtc", False)
                                )
                                
                                # Track speech/silence streaks
                                if is_speech:
                                    consecutive_speech_frames += 1
                                    consecutive_silence_frames = 0
                                    self.stats["speech_frames"] += 1
                                else:
                                    consecutive_silence_frames += 1
                                    consecutive_speech_frames = 0
                                    self.stats["silence_frames"] += 1
                                
                                # Only process through Porcupine if confirmed speech
                                # (reduces false triggers from transient noise)
                                if consecutive_speech_frames < speech_threshold:
                                    is_speech = False
                                    
                            # WEEK 3: STAGE 2 - Porcupine (Only if Speech Detected)
                            if is_speech:
                                # Process frame through Porcupine (expensive operation)
                                keyword_index = self.porcupine.process(audio_frame)
                                
                                if keyword_index >= 0:
                                    # Wake word detected!
                                    self.stats["wake_word_detections"] += 1
                                    detection_time = datetime.now()
                                    print("\n  Wake word detected! Recording 5 seconds of audio...")
                                    logger.info(f"[OK] Wake word detected at {detection_time.isoformat()}")
                                    
                                    # Record command audio immediately
                                    try:
                                        audio_file = self._record_command(stream, sample_rate, frame_length)
                                        
                                        # Calculate confidence (Porcupine doesn't provide this, use fixed value)
                                        confidence = 0.85
                                        
                                        print("[OK]  Command recorded and saved successfully.")
                                        logger.info(f"[OK] Command recorded successfully: {audio_file}")
                                        
                                        # Call detection callback if provided
                                        if self.detection_callback is not None:
                                            try:
                                                self.detection_callback(audio_file, confidence)
                                            except Exception as callback_error:
                                                logger.error(f"Detection callback failed: {str(callback_error)}")
                                                self.stats["errors"] += 1
                                        
                                    except Exception as record_error:
                                        logger.error(f"Failed to record command: {str(record_error)}")
                                        self.stats["errors"] += 1
                            else:
                                # WEEK 3: Power Saving - Sleep during silence
                                if self.power_settings.get("sleep_during_silence", False):
                                    # Only sleep if we have consecutive silence
                                    if consecutive_silence_frames >= silence_threshold:
                                        sleep_ms = self.power_settings.get("sleep_duration_ms", 50)
                                        time.sleep(sleep_ms / 1000.0)
                            
                            # Heartbeat logging for diagnostics
                            if frame_count % heartbeat_frames == 0:
                                speech_ratio = (self.stats["speech_frames"] / self.stats["total_frames"] * 100) if self.stats["total_frames"] > 0 else 0
                                logger.info(
                                    f"Still listening... "
                                    f"(frames={self.stats['total_frames']}, "
                                    f"speech={speech_ratio:.1f}%, "
                                    f"detections={self.stats['wake_word_detections']})"
                                )
                            
                        except Exception as loop_error:
                            self.stats["errors"] += 1
                            raise WakeWordError(
                                "Wake-word detection iteration failed",
                                technical_details=str(loop_error),
                            ) from loop_error
                            
            except sd.PortAudioError as e:
                if "No audio input device" in str(e):
                    raise MicrophoneNotFoundError() from e
                else:
                    raise MicrophoneError(str(e), technical_details=str(e)) from e
        
        except Exception as e:
            self.stats["errors"] += 1
            if self.is_listening:
                self._activate_direct_voice_fallback(e)
                self._run_direct_voice_fallback()
        finally:
            logger.info("Detection loop ended")
    
    def _record_command(self, stream: sd.InputStream, sample_rate: int, frame_length: int) -> str:
        """
        Record command audio after wake word detection.
        
        This captures the audio following the wake word for a configured duration.
        It also includes buffered audio from before the wake word for context.
        
        Args:
            stream: Active audio input stream
            sample_rate: Sample rate of the audio
            frame_length: Frame length for reading
        
        Returns:
            Path to the saved audio file
        
        Raises:
            WakeWordError: If recording fails
        """
        try:
            # Calculate number of frames to record
            command_duration = WAKE_WORD_CONFIG["command_duration"]
            num_frames = int((command_duration * sample_rate) / frame_length)
            
            # Start with pre-buffered audio for context
            command_audio = list(self.pre_buffer)
            
            # Record command audio
            logger.info(f"Recording command for {command_duration} seconds...")
            
            for _ in range(num_frames):
                if not self.is_listening:
                    # Service was stopped during recording
                    break
                
                audio_frame, overflowed = stream.read(frame_length)
                if overflowed:
                    logger.warning("Audio overflow during command recording")
                
                audio_frame = audio_frame.flatten().astype(np.int16)
                command_audio.append(audio_frame)
            
            # Concatenate all frames
            command_audio_array = np.concatenate(command_audio)
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
            filename = f"{WAKE_WORD_FILE_PREFIX}_{timestamp}{AUDIO_FILE_EXTENSION}"
            filepath = DATA_DIR / filename
            
            # Save audio file
            wavfile.write(str(filepath), sample_rate, command_audio_array)
            
            logger.info(f"Command audio saved: {filepath}")
            
            return str(filepath)
            
        except Exception as e:
            error_msg = f"Failed to record command: {str(e)}"
            logger.error(error_msg)
            raise WakeWordError(error_msg, technical_details=str(e)) from e
    
    def _log_statistics(self):
        """Log performance statistics."""
        if self.stats["start_time"] is None:
            return
        
        duration = (datetime.now() - self.stats["start_time"]).total_seconds()
        total = self.stats["total_frames"]
        
        if total > 0:
            speech_ratio = (self.stats["speech_frames"] / total) * 100
            silence_ratio = (self.stats["silence_frames"] / total) * 100
            
            logger.info("=" * 70)
            logger.info("WAKE WORD SERVICE - SESSION STATISTICS")
            logger.info("=" * 70)
            logger.info(f"Power Mode: {self.power_mode}")
            logger.info(f"Duration: {duration:.1f} seconds")
            logger.info(f"Total Frames: {total}")
            logger.info(f"Speech Frames: {self.stats['speech_frames']} ({speech_ratio:.1f}%)")
            logger.info(f"Silence Frames: {self.stats['silence_frames']} ({silence_ratio:.1f}%)")
            logger.info(f"Wake Word Detections: {self.stats['wake_word_detections']}")
            logger.info(f"Errors: {self.stats['errors']}")
            logger.info("=" * 70)
    
    def get_status(self) -> dict:
        """
        Get current status of the wake word service.
        
        Returns:
            Dictionary containing service status information
        """
        return {
            "is_listening": self.is_listening,
            "keyword": "Hi Nexi",
            "sensitivity": WAKE_WORD_CONFIG["sensitivity"],
            "command_duration": WAKE_WORD_CONFIG["command_duration"],
            "porcupine_initialized": self.porcupine is not None
        }
    
    def get_statistics(self) -> dict:
        """
        Get current statistics from wake word detection (Week 3 feature).
        
        Returns:
            Dictionary containing detection statistics
        """
        total = self.stats['total_frames']
        return {
            "total_frames": total,
            "speech_frames": self.stats['speech_frames'],
            "silence_frames": self.stats['silence_frames'],
            "detections": self.stats['wake_word_detections'],
            "errors": self.stats['errors'],
            "power_mode": self.power_mode,
            "vad_enabled": self.vad is not None,
            "current_power_mode": self.current_power_mode,
            "sleep_duration_ms": self.sleep_duration_ms
        }
    
    async def detect_wake_word_once(self) -> dict:
        """
        Detect wake word once (blocking call for API endpoint).
        
        Returns:
            Dictionary with detection result
        """
        import asyncio
        import time
        
        if not self.porcupine:
            self.initialize_porcupine()

        if self.using_keyboard:
            return await asyncio.to_thread(self.keyboard_listener.record_once)
        
        sample_rate = self.porcupine.sample_rate
        frame_length = self.porcupine.frame_length
        
        start_time = time.time()
        frames_processed = 0
        speech_frames = 0
        
        try:
            with sd.InputStream(samplerate=sample_rate, channels=1, dtype='int16', blocksize=frame_length, device=self._input_device_index()) as stream:
                logger.info(" Listening for wake word...")
                
                while True:
                    # Allow other async tasks to run
                    await asyncio.sleep(0.001)
                    
                    audio_chunk, overflowed = stream.read(frame_length)
                    
                    if overflowed:
                        logger.warning("Audio buffer overflow detected")
                    
                    pcm = audio_chunk.flatten().astype('int16')
                    frames_processed += 1
                    
                    # VAD check if enabled
                    if self.vad:
                        is_speech = self.vad.is_speech(pcm)
                        if is_speech:
                            speech_frames += 1
                        else:
                            # Sleep during silence
                            if self.sleep_duration_ms > 0:
                                await asyncio.sleep(self.sleep_duration_ms / 1000.0)
                            continue
                    
                    # Process with Porcupine
                    keyword_index = self.porcupine.process(pcm)
                    
                    if keyword_index >= 0:
                        detection_time = time.time() - start_time
                        logger.info(f" Wake word detected! (took {detection_time:.2f}s)")
                        
                        return {
                            "keyword": "Hi Nexi",
                            "detection_time": detection_time,
                            "frames_processed": frames_processed,
                            "speech_frames": speech_frames
                        }
                    
                    # Safety timeout (30 seconds)
                    if (time.time() - start_time) > 30:
                        raise TimeoutError("Wake word detection timed out")
                        
        except Exception as e:
            logger.error(f"Error in wake word detection: {str(e)}")
            raise
    
    async def detect_and_record_once(self) -> dict:
        """
        Detect wake word once and automatically record the subsequent command audio.
        
        This is a blocking call suitable for API endpoints. It listens for the wake word,
        and when detected, automatically records the command audio and returns both results.
        
        Returns:
            Dictionary with detection result and audio file path:
            {
                "status": "success",
                "keyword": "Hi Nexi",
                "detection_time": float,  # seconds to detect
                "frames_processed": int,
                "speech_frames": int,
                "audio_file": str,  # path to recorded command
                "confidence": float  # detection confidence
            }
        
        Raises:
            TimeoutError: If detection takes longer than 30 seconds
            Exception: If audio processing fails
        """
        import asyncio
        import time
        
        if not self.porcupine:
            self.initialize_porcupine()

        if self.using_keyboard:
            return await asyncio.to_thread(self.keyboard_listener.record_once)
        
        sample_rate = self.porcupine.sample_rate
        frame_length = self.porcupine.frame_length
        
        start_time = time.time()
        frames_processed = 0
        speech_frames = 0
        
        try:
            with sd.InputStream(samplerate=sample_rate, channels=1, dtype='int16', blocksize=frame_length, device=self._input_device_index()) as stream:
                logger.info(" Listening for wake word...")
                
                while True:
                    # Allow other async tasks to run
                    await asyncio.sleep(0.001)
                    
                    audio_chunk, overflowed = stream.read(frame_length)
                    
                    if overflowed:
                        logger.warning("Audio buffer overflow detected")
                    
                    pcm = audio_chunk.flatten().astype('int16')
                    frames_processed += 1
                    
                    # VAD check if enabled
                    if self.vad:
                        is_speech = self.vad.is_speech(pcm)
                        if is_speech:
                            speech_frames += 1
                        else:
                            # Sleep during silence
                            if self.sleep_duration_ms > 0:
                                await asyncio.sleep(self.sleep_duration_ms / 1000.0)
                            continue
                    
                    # Store frame in pre-buffer for recording context
                    self.pre_buffer.append(pcm)
                    
                    # Process with Porcupine
                    keyword_index = self.porcupine.process(pcm)
                    
                    if keyword_index >= 0:
                        detection_time = time.time() - start_time
                        logger.info(f" Wake word detected! (took {detection_time:.2f}s)")
                        
                        # Immediately record command audio
                        logger.info(" Recording command audio...")
                        try:
                            audio_file = self._record_command(stream, sample_rate, frame_length)
                            logger.info(f" Command recorded: {audio_file}")
                            
                            return {
                                "status": "success",
                                "keyword": "Hi Nexi",
                                "detection_time": detection_time,
                                "frames_processed": frames_processed,
                                "speech_frames": speech_frames,
                                "audio_file": audio_file,
                                "confidence": 0.85  # Porcupine doesn't provide confidence
                            }
                        except Exception as e:
                            logger.error(f" Failed to record command: {str(e)}")
                            raise
                    
                    # Safety timeout (30 seconds)
                    if (time.time() - start_time) > 30:
                        raise TimeoutError("Wake word detection timed out after 30 seconds")
                        
        except Exception as e:
            logger.error(f" Error in wake word detection and recording: {str(e)}")
            raise
    
    @property
    def current_power_mode(self) -> str:
        """Get current power mode"""
        return self.power_mode
    
    @property
    def vad_enabled(self) -> bool:
        """Check if VAD is enabled"""
        return self.vad is not None
    
    @property
    def sleep_duration_ms(self) -> int:
        """Get current sleep duration"""
        return self.power_settings.get("sleep_duration_ms", 0)
    
    def record_command_with_silence_detection(
        self,
        max_duration: float = 10.0,
        silence_threshold: float = 0.5,
        min_duration: float = 0.5
    ) -> str:
        """
        Record audio command with automatic silence-based stopping.
        
        Records audio after wake word detection and automatically stops when
        silence is detected, providing a natural user experience.
        
        Args:
            max_duration: Maximum recording duration in seconds
            silence_threshold: Seconds of silence before stopping
            min_duration: Minimum recording duration in seconds
        
        Returns:
            str: Path to saved audio file
        
        Raises:
            MicrophoneError: If recording fails
        """
        try:
            import sounddevice as sd
            from scipy.io import wavfile
            import time
            from datetime import datetime
            
            sample_rate = 16000
            silence_frames = int(silence_threshold * sample_rate)
            min_frames = int(min_duration * sample_rate)
            max_frames = int(max_duration * sample_rate)
            
            logger.info(
                f"Starting silence-based recording: max={max_duration}s, "
                f"silence_threshold={silence_threshold}s"
            )
            
            # Initialize VAD if not already done
            if not self.vad:
                self.vad = VoiceActivityDetector(
                    sample_rate=sample_rate,
                    frame_duration_ms=30,
                    energy_threshold=VAD_CONFIG.get("energy_threshold", 0.01),
                    adaptive_threshold=VAD_CONFIG.get("adaptive_threshold", True)
                )
            
            recorded_frames = []
            consecutive_silence = 0
            total_frames = 0
            recording_started = time.time()
            
            # Start recording
            with sd.InputStream(
                samplerate=sample_rate,
                channels=1,
                dtype='int16',
                blocksize=512,
                device=self._input_device_index(),
            ) as stream:
                
                logger.info("Recording started (will stop on silence)...")
                
                while total_frames < max_frames:
                    # Read audio chunk
                    audio_chunk, overflowed = stream.read(512)
                    
                    if overflowed:
                        logger.warning("Audio buffer overflow during recording")
                    
                    pcm = audio_chunk.flatten().astype('int16')
                    recorded_frames.append(pcm)
                    total_frames += len(pcm)
                    
                    # Check for silence (after minimum duration met)
                    if total_frames >= min_frames:
                        is_speech = self.vad.is_speech(pcm)
                        
                        if not is_speech:
                            consecutive_silence += len(pcm)
                            
                            # Stop if silence threshold reached
                            if consecutive_silence >= silence_frames:
                                logger.info(
                                    f"Silence detected after {total_frames/sample_rate:.2f}s, "
                                    "stopping recording"
                                )
                                break
                        else:
                            # Reset silence counter on speech
                            consecutive_silence = 0
            
            # Combine all recorded frames
            audio_data = np.concatenate(recorded_frames)
            duration = len(audio_data) / sample_rate
            
            # Save to file
            timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
            filename = f"command_{timestamp}.wav"
            filepath = DATA_DIR / filename
            
            # Ensure data directory exists
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            
            wavfile.write(str(filepath), sample_rate, audio_data)
            
            logger.info(
                f"Silence-based recording complete: duration={duration:.2f}s, "
                f"file={filename}"
            )
            
            # Update statistics
            self.stats["commands_recorded"] += 1
            
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Failed to record command with silence detection: {e}")
            raise MicrophoneError(f"Silence-based recording failed: {e}")
