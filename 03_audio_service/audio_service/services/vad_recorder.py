"""
VAD-Controlled Recording Module for NEXI Audio Service.
Records audio until silence is detected instead of fixed duration.

Features:
- Voice Activity Detection (VAD) for dynamic recording
- Automatic stop on silence detection
- Maximum duration safety limit
- WAV file output with proper formatting
"""

import logging
import math
import numpy as np
import pyaudio
import wave
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict

from audio_service.utils.vad import VoiceActivityDetector
from audio_service.config import VAD_RECORDER_CONFIG
from audio_service.device_selection import resolve_pyaudio_input

logger = logging.getLogger(__name__)


class VADRecorder:
    """
    Records audio until silence is detected using Voice Activity Detection.
    
    Attributes:
        vad_instance: VAD object for speech detection
        sample_rate: Audio sample rate (16000 Hz default)
        chunk_size: Audio chunk size in samples (512 default)
        channels: Number of audio channels (1 = mono)
        silence_threshold_ms: Duration of silence to stop recording (500ms default)
        max_recording_seconds: Maximum recording safety backstop
        audio_buffer: List to store recorded audio chunks
        output_directory: Directory for saving WAV files
    """
    
    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_size: int = 512,
        silence_threshold_ms: int = 500,
        max_duration_seconds: int = 30
    ):
        """
        Initialize VAD recorder.
        
        Args:
            sample_rate: Audio sample rate in Hz (default 16000)
            chunk_size: Samples per chunk (default 512)
            silence_threshold_ms: Duration of silence to trigger stop (default 500ms)
            max_duration_seconds: Maximum recording duration safety backstop (default 30s)
        """
        self.sample_rate = sample_rate
        # WebRTC VAD accepts exact 10/20/30 ms PCM frames. Normalize legacy
        # 512-sample (32 ms) configuration to a supported 30 ms frame.
        requested_ms = round(chunk_size * 1000 / sample_rate)
        self.chunk_size = chunk_size if requested_ms in {10, 20, 30} else sample_rate * 30 // 1000
        self.channels = 1  # Mono
        self.silence_threshold_ms = silence_threshold_ms
        self.max_recording_seconds = max(1, max_duration_seconds)
        self.start_speech_frames = 3  # 90 ms at the 30 ms frame cadence rejects isolated blips.
        self.minimum_speech_seconds = 1.0  # Existing speaker verification minimum.
        self.audio_buffer = []
        self.output_directory = VAD_RECORDER_CONFIG["output_directory"]
        
        # Initialize VAD detector
        try:
            self.vad_instance = VoiceActivityDetector(sample_rate=sample_rate)
            logger.info(
                f"VADRecorder initialized: "
                f"sr={sample_rate}, chunk={chunk_size}, "
                f"silence={silence_threshold_ms}ms, "
                f"max={max_duration_seconds}s"
            )
        except Exception as e:
            logger.error(f"Failed to initialize VAD detector: {e}")
            raise
    
    def record_until_silence(self, output_path: Optional[str] = None, stop_event=None) -> Dict:
        """
        Record audio until silence is detected.
        
        Args:
            output_path: Path to save WAV file (generated if None)
            
        Returns:
            Dict with recording results:
            {
                "audio_file": str (path to saved WAV file),
                "duration": float (recording duration in seconds),
                "chunks_recorded": int (number of audio chunks),
        "stopped_by": str ("speech_end", "no_speech", "safety_timeout", or "cancelled"),
                "sample_rate": int,
                "success": bool
            }
            
        Raises:
            Exception: If recording fails
        """
        logger.info("Starting VAD-controlled recording...")
        
        # Generate output path if not provided
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S%f")[:-3]  # Include milliseconds
            output_path = str(self.output_directory / f"vad_recording_{timestamp}.wav")
        
        # Ensure output directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        audio_stream = None
        p = None  # PyAudio instance - ensure cleanup in error cases
        
        try:
            # Create PyAudio instance
            p = pyaudio.PyAudio()
            input_device_index = resolve_pyaudio_input(p)
            
            # Open audio stream
            logger.debug(f"Opening audio stream: sr={self.sample_rate}, chunk={self.chunk_size}")
            audio_stream = p.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=input_device_index,
                frames_per_buffer=self.chunk_size
            )
            
            # Initialize recording variables
            self.audio_buffer = []
            consecutive_silence_chunks = 0
            consecutive_speech_chunks = 0
            speech_chunks = 0
            chunks_recorded = 0
            stopped_by = "safety_timeout"
            pending_speech = []
            
            # Calculate silence threshold in chunks
            # silence_threshold_ms / (chunk_size_ms) = silence_threshold_chunks
            # chunk_size_ms = (chunk_size / sample_rate) * 1000
            chunk_duration_ms = (self.chunk_size / self.sample_rate) * 1000
            silence_threshold_chunks = max(1, math.ceil(self.silence_threshold_ms / chunk_duration_ms))
            
            # Calculate maximum chunks for safety
            max_chunks = int(self.max_recording_seconds * (self.sample_rate / self.chunk_size))
            
            logger.debug(
                f"Recording parameters: "
                f"chunk_duration={chunk_duration_ms:.1f}ms, "
                f"silence_threshold_chunks={silence_threshold_chunks}, "
                f"max_chunks={max_chunks}"
            )
            
            logger.info("Recording... (waiting for speech)")
            inside_speech_region = False
            
            # Recording loop
            while chunks_recorded < max_chunks:
                try:
                    if stop_event is not None and stop_event.is_set():
                        stopped_by = "manual_stop"
                        break

                    # Read audio chunk
                    audio_chunk = audio_stream.read(self.chunk_size, exception_on_overflow=False)
                    
                    # Convert to numpy array
                    audio_array = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32)
                    
                    chunks_recorded += 1
                    
                    # Check for speech using VAD
                    # CRITICAL FIX: VAD returns (is_speech: bool, metadata: dict) tuple
                    try:
                        vad_result = self.vad_instance.is_speech(audio_array, use_webrtc=True)
                        # Properly unpack the tuple returned by VAD method
                        if isinstance(vad_result, tuple):
                            is_speech, vad_metadata = vad_result
                        else:
                            # Fallback if VAD returns just bool (shouldn't happen but safety check)
                            is_speech = bool(vad_result)
                    except Exception as e:
                        logger.warning(f"VAD processing error (treating as non-speech): {e}")
                        is_speech = False
                    
                    if is_speech:
                        consecutive_speech_chunks += 1
                        consecutive_silence_chunks = 0
                        if not inside_speech_region:
                            pending_speech.append(audio_chunk)
                            if consecutive_speech_chunks >= self.start_speech_frames:
                                inside_speech_region = True
                                self.audio_buffer.extend(pending_speech)
                                speech_chunks += len(pending_speech)
                                pending_speech.clear()
                        else:
                            self.audio_buffer.append(audio_chunk)
                            speech_chunks += 1
                    
                    else:
                        consecutive_speech_chunks = 0
                        if inside_speech_region:
                            consecutive_silence_chunks += 1
                            self.audio_buffer.append(audio_chunk)
                            
                            if consecutive_silence_chunks <= 3:  # Log first few silence chunks only
                                logger.debug(
                                    f"Silence chunk {consecutive_silence_chunks}/{silence_threshold_chunks} "
                                    f"(chunk {chunks_recorded})"
                                )
                            
                            # Check if silence threshold reached
                            if consecutive_silence_chunks >= silence_threshold_chunks:
                                logger.info(
                                    f"Silence threshold reached after {chunks_recorded} chunks "
                                    f"({consecutive_silence_chunks} silent chunks)"
                                )
                                stopped_by = (
                                    "speech_end"
                                    if speech_chunks * self.chunk_size / self.sample_rate >= self.minimum_speech_seconds
                                    else "no_speech"
                                )
                                break
                        elif not inside_speech_region:
                            pending_speech.clear()
                
                except IOError as e:
                    logger.error(f"Audio stream error: {e}")
                    raise
            
            # Check if reached max duration
            if stop_event is not None and stop_event.is_set():
                stopped_by = "cancelled"
            elif chunks_recorded >= max_chunks and not inside_speech_region:
                stopped_by = "no_speech"
            elif chunks_recorded >= max_chunks and inside_speech_region:
                stopped_by = "safety_timeout"
                logger.info(f"Maximum recording duration ({self.max_recording_seconds}s) reached")
            
            # Close audio stream
            audio_stream.close()
            p.terminate()
            logger.info(f"Audio stream closed (recorded {chunks_recorded} chunks)")
            
            # Save WAV file
            logger.info(f"Saving recording to: {output_path}")
            if self.audio_buffer:
                self._save_wav_file(output_path)
            
            # Calculate actual duration
            actual_duration = len(self.audio_buffer) * self.chunk_size / self.sample_rate
            
            result = {
                "audio_file": output_path if self.audio_buffer else None,
                "duration": actual_duration,
                "chunks_recorded": chunks_recorded,
                "stopped_by": stopped_by,
                "end_reason": stopped_by,
                "sample_rate": self.sample_rate,
                "success": True
            }
            
            logger.info(
                f"✓ Recording complete: {actual_duration:.2f}s, "
                f"{chunks_recorded} chunks, stopped by: {stopped_by}"
            )
            
            return result
        
        except Exception as e:
            logger.error(f"Recording failed: {e}")
            
            # Clean up audio stream
            if audio_stream:
                try:
                    audio_stream.close()
                except Exception as cleanup_error:
                    logger.warning(f"Error closing audio stream: {cleanup_error}")
            
            # Clean up PyAudio
            if p:
                try:
                    p.terminate()
                except Exception as cleanup_error:
                    logger.warning(f"Error terminating PyAudio: {cleanup_error}")
            
            # Clean up partial file
            try:
                if Path(output_path).exists():
                    Path(output_path).unlink()
                    logger.debug(f"Cleaned up partial file: {output_path}")
            except Exception as cleanup_error:
                logger.warning(f"Error cleaning partial file: {cleanup_error}")
            
            return {
                "audio_file": None,
                "duration": 0,
                "chunks_recorded": len(self.audio_buffer),
                "stopped_by": "error",
                "sample_rate": self.sample_rate,
                "success": False,
                "error": str(e)
            }
    
    def _save_wav_file(self, output_path: str):
        """
        Save recorded audio buffer to WAV file.
        
        Args:
            output_path: Path to save WAV file
            
        Raises:
            Exception: If file save fails
        """
        try:
            with wave.open(output_path, 'wb') as wav_file:
                # Set WAV file parameters
                wav_file.setnchannels(self.channels)
                wav_file.setsampwidth(2)  # 16-bit = 2 bytes
                wav_file.setframerate(self.sample_rate)
                
                # Write all frames
                for chunk in self.audio_buffer:
                    wav_file.writeframes(chunk)
            
            logger.info(f"✓ WAV file saved: {output_path} ({len(self.audio_buffer)} chunks)")
        
        except Exception as e:
            logger.error(f"Failed to save WAV file: {e}")
            raise
