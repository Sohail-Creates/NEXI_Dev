"""
TTS Audio Playback Manager with Stop Word Interrupt Support.

Handles playback of TTS audio with ability to interrupt when stop word detected.
Features:
- Audio playback via PyAudio or sounddevice
- Interrupt flag for stop word detection
- Playback state tracking
- Error handling and recovery
"""

import logging
import threading
import sounddevice as sd
import numpy as np
import wave
import io
from pathlib import Path
from typing import Optional, Dict, Callable
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class PlaybackState(Enum):
    """Playback state enumeration."""
    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class PlaybackManager:
    """
    Manages audio playback from TTS service with interrupt support.
    
    Attributes:
        sample_rate: Audio playback sample rate (default 22050 Hz, matches TTS)
        channels: Number of audio channels (1 = mono, default)
        device_id: PyAudio device ID (None = default device)
        interrupt_flag: threading.Event for stop word interrupt signal
        current_state: Current playback state
        playback_lock: RLock for thread-safe operations
    """
    
    def __init__(self, sample_rate: int = 22050, device_id: Optional[int] = None):
        """
        Initialize playback manager.
        
        Args:
            sample_rate: Audio playback sample rate in Hz (default 22050 Hz to match TTS)
            device_id: Audio device ID (None = use default)
        """
        self.sample_rate = sample_rate
        self.channels = 1  # Mono
        self.device_id = device_id
        self.interrupt_flag = threading.Event()
        self.current_state = PlaybackState.IDLE
        self.playback_lock = threading.RLock()
        self.playback_thread = None
        self.current_audio = None
        self.playback_position = 0
        self.interrupt_callback = None
        
        logger.info(
            f"PlaybackManager initialized: sr={sample_rate}Hz, "
            f"channels={self.channels}, device={device_id}"
        )
    
    def set_interrupt_callback(self, callback: Callable):
        """
        Register callback to be called when playback is interrupted.
        
        Args:
            callback: Function to call with interrupt event info
        """
        with self.playback_lock:
            self.interrupt_callback = callback
            logger.debug("Interrupt callback registered")
    
    def activate_interrupt(self):
        """Signal interrupt (stop word detected) to current playback."""
        logger.info("Playback interrupt signal activated")
        self.interrupt_flag.set()
    
    def reset_interrupt(self):
        """Reset interrupt flag for next playback."""
        with self.playback_lock:
            self.interrupt_flag.clear()
            logger.debug("Interrupt flag reset")
    
    def play_audio_bytes(self, audio_bytes: bytes) -> Dict:
        """
        Play audio from bytes (typically WAV format from TTS service).
        
        Args:
            audio_bytes: Audio data in bytes (WAV format expected)
            
        Returns:
            Dict with playback results:
            {
                "success": bool,
                "state": str (final playback state),
                "duration": float (seconds),
                "interrupted": bool,
                "error": str (if error occurred)
            }
        """
        with self.playback_lock:
            if self.current_state == PlaybackState.PLAYING:
                logger.warning("Playback already in progress, stopping current playback")
                self.stop_playback_internal()
            
            # Parse WAV file from bytes
            try:
                logger.debug(f"Parsing WAV data ({len(audio_bytes)} bytes)...")
                self.current_audio = self._parse_wav_bytes(audio_bytes)
                
                if self.current_audio is None:
                    return {
                        "success": False,
                        "state": PlaybackState.ERROR.value,
                        "duration": 0,
                        "interrupted": False,
                        "error": "Failed to parse WAV data"
                    }
                
                logger.info(
                    f"Audio parsed: {self.current_audio['frames'].shape[0]} frames, "
                    f"sr={self.current_audio['sample_rate']}Hz"
                )
                
                # Reset playback state
                self.playback_position = 0
                self.interrupt_flag.clear()
                self.playback_error = None
                
                # Set state to playing
                self._set_state(PlaybackState.PLAYING)
                
                # Start playback in background thread
                logger.debug("Starting playback thread...")
                self.playback_thread = threading.Thread(
                    target=self._playback_loop,
                    daemon=False
                )
                self.playback_thread.start()
                
                # Wait for playback to complete or be interrupted
                logger.debug("Waiting for playback to complete...")
                self.playback_thread.join(timeout=300)  # 5 minute max timeout
                if self.playback_thread.is_alive():
                    self.interrupt_flag.set()
                    self._set_state(PlaybackState.ERROR)
                    return {"success": False, "state": PlaybackState.ERROR.value,
                            "duration": 0, "interrupted": False, "error": "Playback timed out"}
                if self.playback_error:
                    self._set_state(PlaybackState.ERROR)
                    return {"success": False, "state": PlaybackState.ERROR.value,
                            "duration": 0, "interrupted": False, "error": self.playback_error}
                
                # Check if interrupted
                interrupted = self.interrupt_flag.is_set()
                
                # Determine final state
                if interrupted:
                    self._set_state(PlaybackState.STOPPED)
                    logger.info("● Playback interrupted by stop word")
                    
                    # Call interrupt callback
                    if self.interrupt_callback:
                        try:
                            self.interrupt_callback({
                                "timestamp": datetime.now().isoformat(),
                                "playback_position": self.playback_position,
                                "total_frames": self.current_audio['frames'].shape[0]
                            })
                        except Exception as e:
                            logger.error(f"Error in interrupt callback: {e}")
                else:
                    self._set_state(PlaybackState.IDLE)
                    logger.info("✓ Playback completed")
                
                # Calculate actual duration
                actual_duration = self.playback_position / self.current_audio['sample_rate']
                total_duration = self.current_audio['frames'].shape[0] / self.current_audio['sample_rate']
                
                return {
                    "success": True,
                    "state": self.current_state.value,
                    "duration": total_duration,
                    "actual_duration": actual_duration,
                    "interrupted": interrupted
                }
                
            except Exception as e:
                logger.error(f"Playback error: {e}")
                self._set_state(PlaybackState.ERROR)
                return {
                    "success": False,
                    "state": PlaybackState.ERROR.value,
                    "duration": 0,
                    "interrupted": False,
                    "error": str(e)
                }
    
    def _playback_loop(self):
        """Internal playback loop running in background thread."""
        try:
            if not self.current_audio:
                logger.error("No audio data available for playback")
                return
            
            audio_frames = self.current_audio['frames']
            sr = self.current_audio['sample_rate']
            channels = self.current_audio['channels']
            
            logger.debug(f"Playback loop started: {audio_frames.shape[0]} frames, sr={sr}Hz")
            
            # Play through sounddevice
            with sd.OutputStream(
                samplerate=sr,
                channels=channels,
                device=self.device_id,
                dtype='float32'
            ) as stream:
                # Play audio in chunks, checking for interrupt flag
                chunk_size = sr // 10  # 100ms chunks
                total_frames = audio_frames.shape[0]
                
                while self.playback_position < total_frames:
                    # Check for interrupt signal
                    if self.interrupt_flag.is_set():
                        logger.info("Interrupt signal detected in playback loop")
                        break
                    
                    # Calculate chunk to play
                    chunk_end = min(self.playback_position + chunk_size, total_frames)
                    chunk = audio_frames[self.playback_position:chunk_end]
                    
                    # Play chunk
                    stream.write(chunk)
                    self.playback_position = chunk_end
                    
                    # Debug: Log every 1 second
                    if self.playback_position % (sr * 1) == 0:
                        elapsed = self.playback_position / sr
                        total = total_frames / sr
                        logger.debug(f"Playback progress: {elapsed:.1f}s / {total:.1f}s")
                
                logger.info(f"Playback loop ended at {self.playback_position}/{total_frames}")
        
        except Exception as e:
            logger.error(f"Playback loop error: {e}")
            self.playback_error = str(e)
    
    def stop_playback_internal(self):
        """
        Internal: Stop playback (must be called with lock held).
        """
        logger.info("Stopping playback...")
        self.interrupt_flag.set()
        
        if self.playback_thread and self.playback_thread.is_alive():
            logger.debug("Waiting for playback thread to finish...")
            self.playback_thread.join(timeout=5)
        
        self._set_state(PlaybackState.STOPPED)
        logger.info("Playback stopped")
    
    def stop_playback(self):
        """Public: Stop playback immediately."""
        with self.playback_lock:
            self.stop_playback_internal()
    
    def _parse_wav_bytes(self, audio_bytes: bytes) -> Optional[Dict]:
        """
        Parse WAV audio from bytes.
        
        Args:
            audio_bytes: WAV audio data in bytes
            
        Returns:
            Dict with parsed audio data:
            {
                "frames": np.ndarray (audio samples),
                "sample_rate": int,
                "channels": int,
                "duration": float (seconds)
            }
            Or None if parsing fails
        """
        try:
            # Read WAV file from bytes
            wav_file = wave.open(io.BytesIO(audio_bytes), 'rb')
            
            # Get WAV parameters
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            num_frames = wav_file.getnframes()
            
            logger.debug(
                f"WAV parsed: ch={channels}, sw={sample_width}, "
                f"sr={sample_rate}, frames={num_frames}"
            )
            
            # Read audio frames
            audio_data = wav_file.readframes(num_frames)
            wav_file.close()
            
            # Convert to numpy array
            # Determine dtype based on sample width
            if sample_width == 1:
                dtype = np.uint8
            elif sample_width == 2:
                dtype = np.int16
            elif sample_width == 4:
                dtype = np.int32
            else:
                logger.error(f"Unsupported sample width: {sample_width}")
                return None
            
            # Reshape and convert to float32
            audio_array = np.frombuffer(audio_data, dtype=dtype).astype(np.float32)
            
            # Normalize to -1.0 to 1.0 range
            if dtype == np.uint8:
                audio_array = (audio_array - 128) / 128.0
            else:
                audio_array = audio_array / (1 << (sample_width * 8 - 1))
            
            # Reshape if stereo
            if channels > 1:
                audio_array = audio_array.reshape(-1, channels)
            else:
                audio_array = audio_array.reshape(-1, 1)
            
            duration = num_frames / sample_rate
            
            logger.debug(
                f"Audio converted: shape={audio_array.shape}, "
                f"duration={duration:.2f}s, range=[{audio_array.min():.3f}, {audio_array.max():.3f}]"
            )
            
            return {
                "frames": audio_array,
                "sample_rate": sample_rate,
                "channels": channels,
                "duration": duration
            }
        
        except Exception as e:
            logger.error(f"Failed to parse WAV: {e}")
            return None
    
    def _set_state(self, new_state: PlaybackState):
        """Set playback state with logging."""
        if self.current_state != new_state:
            logger.debug(f"Playback state: {self.current_state.value} → {new_state.value}")
            self.current_state = new_state
    
    def get_state(self) -> Dict:
        """
        Get current playback state.
        
        Returns:
            Dict with state info:
            {
                "state": str (current state),
                "playing": bool,
                "position_frames": int (current playback position),
                "total_frames": int (total audio frames),
                "interrupted": bool
            }
        """
        with self.playback_lock:
            total_frames = 0
            if self.current_audio:
                total_frames = self.current_audio['frames'].shape[0]
            
            return {
                "state": self.current_state.value,
                "playing": self.current_state == PlaybackState.PLAYING,
                "position_frames": self.playback_position,
                "total_frames": total_frames,
                "interrupted": self.interrupt_flag.is_set()
            }
