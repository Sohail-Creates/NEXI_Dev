"""
Voice Activity Detection (VAD) utilities.
Implements energy-based and WebRTC-based voice activity detection to reduce power consumption.
"""

import logging
import numpy as np
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


class VADError(Exception):
    """Custom exception for VAD errors."""
    pass


class VoiceActivityDetector:
    """
    Voice Activity Detection using energy-based and WebRTC VAD.
    
    Class for provides fast, lightweight speech detection to avoid
    processing silence through expensive wake word detection.
    
    Strategy:
    1. Use simple energy threshold for quick silence filtering (99% of cases)
    2. Optionally use WebRTC VAD for more accurate detection
    3. Use adaptive thresholds to handle different environments
    """
    
    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        energy_threshold: float = 0.01,
        adaptive_threshold: bool = True,
        webrtc_mode: int = 3  # 0=Quality, 1=Low Bitrate, 2=Aggressive, 3=Very Aggressive
    ):
        """
        Initialize Voice Activity Detector.
        
        Args:
            sample_rate: Audio sample rate in Hz
            frame_duration_ms: Frame duration in milliseconds (10, 20, or 30)
            energy_threshold: Initial energy threshold for voice detection
            adaptive_threshold: Whether to adapt threshold to environment
            webrtc_mode: WebRTC VAD aggressiveness (0-3, higher = more aggressive)
        """
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.energy_threshold = energy_threshold
        self.adaptive_threshold = adaptive_threshold
        self.webrtc_mode = webrtc_mode
        
        # Adaptive threshold parameters
        self.energy_history = []
        self.history_size = 50  # Keep last 50 energy measurements
        
        # WebRTC VAD (optional, may not be available)
        self.webrtc_vad = None
        try:
            import webrtcvad
            self.webrtc_vad = webrtcvad.Vad(webrtc_mode)
            logger.info(f"WebRTC VAD initialized (mode={webrtc_mode})")
        except ImportError:
            logger.warning("WebRTC VAD not available, using energy-based detection only")
        except Exception as e:
            logger.warning(f"Failed to initialize WebRTC VAD: {e}")
        
        logger.info(
            f"VAD initialized: sr={sample_rate}Hz, frame={frame_duration_ms}ms, "
            f"threshold={energy_threshold}, adaptive={adaptive_threshold}"
        )
    
    def calculate_energy(self, audio_frame: np.ndarray) -> float:
        """
        Calculate normalized energy of audio frame.
        
        Args:
            audio_frame: Audio data as numpy array
        
        Returns:
            Normalized energy value (0.0 to 1.0)
        """
        # Calculate RMS (Root Mean Square) energy
        if len(audio_frame) == 0:
            return 0.0
        
        # Normalize to float (-1.0 to 1.0)
        if audio_frame.dtype == np.int16:
            audio_float = audio_frame.astype(np.float32) / 32768.0
        else:
            audio_float = audio_frame.astype(np.float32)
        
        # Calculate RMS energy
        energy = np.sqrt(np.mean(audio_float ** 2))
        
        return float(energy)
    
    def update_adaptive_threshold(self, energy: float):
        """
        Update adaptive energy threshold based on recent history.
        
        This helps the system adapt to different noise environments:
        - Quiet room: Lower threshold for better sensitivity
        - Noisy environment: Higher threshold to ignore background noise
        
        Args:
            energy: Current frame energy
        """
        if not self.adaptive_threshold:
            return
        
        # Add to history
        self.energy_history.append(energy)
        
        # Keep only recent history
        if len(self.energy_history) > self.history_size:
            self.energy_history.pop(0)
        
        # Update threshold if we have enough samples
        if len(self.energy_history) >= 10:
            # Use median of recent energies as baseline noise level
            baseline_noise = np.median(self.energy_history)
            
            # Set threshold slightly above baseline noise
            # Add 0.01 to ensure we detect speech above noise floor
            self.energy_threshold = baseline_noise + 0.01
            
            # Clamp to reasonable range
            self.energy_threshold = max(0.005, min(0.05, self.energy_threshold))
    
    def is_speech_energy_based(self, audio_frame: np.ndarray) -> Tuple[bool, float]:
        """
        Fast energy-based speech detection.
        
        This is VERY fast (< 1ms) and filters out 99% of silence.
        Only frames passing this check need further processing.
        
        Args:
            audio_frame: Audio data as numpy array (int16)
        
        Returns:
            Tuple of (is_speech, energy_level)
        """
        energy = self.calculate_energy(audio_frame)
        
        # Update adaptive threshold
        self.update_adaptive_threshold(energy)
        
        # Simple threshold comparison
        is_speech = energy > self.energy_threshold
        
        return is_speech, energy
    
    def is_speech_webrtc(self, audio_frame: np.ndarray) -> bool:
        """
        WebRTC VAD-based speech detection (more accurate but slower).
        
        WebRTC VAD uses more sophisticated algorithms than simple energy,
        including spectral analysis and statistical models.
        
        Args:
            audio_frame: Audio data as numpy array (int16)
        
        Returns:
            True if speech detected, False otherwise
        """
        if self.webrtc_vad is None:
            # Fall back to energy-based if WebRTC not available
            is_speech, _ = self.is_speech_energy_based(audio_frame)
            return is_speech
        
        try:
            # WebRTC VAD expects raw bytes in int16 format
            if audio_frame.dtype != np.int16:
                audio_frame = audio_frame.astype(np.int16)
            
            audio_bytes = audio_frame.tobytes()
            
            # Call WebRTC VAD
            is_speech = self.webrtc_vad.is_speech(
                audio_bytes,
                self.sample_rate
            )
            
            return is_speech
            
        except Exception as e:
            logger.warning(f"WebRTC VAD error: {e}, falling back to energy-based")
            is_speech, _ = self.is_speech_energy_based(audio_frame)
            return is_speech
    
    def is_speech(
        self,
        audio_frame: np.ndarray,
        use_webrtc: bool = False
    ) -> Tuple[bool, dict]:
        """
        Determine if audio frame contains speech.
        
        Two-stage detection:
        1. Fast energy check (filters 99% of silence in <1ms)
        2. Optional WebRTC VAD for higher accuracy
        
        Args:
            audio_frame: Audio data as numpy array
            use_webrtc: Whether to use WebRTC VAD (slower but more accurate)
        
        Returns:
            Tuple of (is_speech, metadata_dict)
            metadata_dict contains: energy, threshold, method
        """
        # Stage 1: Fast energy check
        is_speech_energy, energy = self.is_speech_energy_based(audio_frame)
        
        metadata = {
            "energy": energy,
            "threshold": self.energy_threshold,
            "method": "energy"
        }
        
        # If energy check fails, no need for WebRTC
        if not is_speech_energy:
            return False, metadata
        
        # Stage 2: Optional WebRTC check
        if use_webrtc and self.webrtc_vad is not None:
            is_speech_webrtc = self.is_speech_webrtc(audio_frame)
            metadata["method"] = "webrtc"
            return is_speech_webrtc, metadata
        
        return is_speech_energy, metadata
    
    def get_threshold(self) -> float:
        """Get current energy threshold."""
        return self.energy_threshold
    
    def set_threshold(self, threshold: float):
        """
        Manually set energy threshold.
        
        Args:
            threshold: New threshold value (0.0 to 1.0)
        """
        self.energy_threshold = max(0.0, min(1.0, threshold))
        logger.info(f"VAD threshold manually set to {self.energy_threshold}")
    
    def get_stats(self) -> dict:
        """
        Get VAD statistics.
        
        Returns:
            Dictionary with current state and statistics
        """
        stats = {
            "sample_rate": self.sample_rate,
            "frame_duration_ms": self.frame_duration_ms,
            "energy_threshold": self.energy_threshold,
            "adaptive_threshold": self.adaptive_threshold,
            "webrtc_available": self.webrtc_vad is not None,
            "webrtc_mode": self.webrtc_mode if self.webrtc_vad else None,
            "history_size": len(self.energy_history)
        }
        
        if len(self.energy_history) > 0:
            stats["recent_energy_mean"] = float(np.mean(self.energy_history))
            stats["recent_energy_median"] = float(np.median(self.energy_history))
            stats["recent_energy_std"] = float(np.std(self.energy_history))
        
        return stats


class SilenceTrimmer:
    """
    Utility to trim silence from beginning and end of audio.
    Useful for preprocessing before transcription.
    """
    
    def __init__(self, energy_threshold: float = 0.01):
        """
        Initialize silence trimmer.
        
        Args:
            energy_threshold: Energy threshold for silence detection
        """
        self.energy_threshold = energy_threshold
    
    def trim_silence(
        self,
        audio: np.ndarray,
        sample_rate: int,
        frame_size: int = 512
    ) -> Tuple[np.ndarray, dict]:
        """
        Trim silence from audio.
        
        Args:
            audio: Audio data as numpy array
            sample_rate: Sample rate in Hz
            frame_size: Frame size for analysis
        
        Returns:
            Tuple of (trimmed_audio, metadata)
        """
        if len(audio) == 0:
            return audio, {"trimmed": False, "original_duration": 0, "trimmed_duration": 0}
        
        # Calculate energy for each frame
        num_frames = len(audio) // frame_size
        energy_values = []
        
        for i in range(num_frames):
            start = i * frame_size
            end = start + frame_size
            frame = audio[start:end]
            
            # Calculate energy
            if frame.dtype == np.int16:
                frame_float = frame.astype(np.float32) / 32768.0
            else:
                frame_float = frame.astype(np.float32)
            
            energy = np.sqrt(np.mean(frame_float ** 2))
            energy_values.append(energy)
        
        # Find first and last non-silent frames
        speech_frames = [i for i, e in enumerate(energy_values) if e > self.energy_threshold]
        
        if len(speech_frames) == 0:
            # All silence
            return audio, {
                "trimmed": False,
                "original_duration": len(audio) / sample_rate,
                "trimmed_duration": len(audio) / sample_rate,
                "reason": "all_silence"
            }
        
        # Trim audio
        start_frame = speech_frames[0]
        end_frame = speech_frames[-1] + 1
        
        start_sample = start_frame * frame_size
        end_sample = min(end_frame * frame_size, len(audio))
        
        trimmed_audio = audio[start_sample:end_sample]
        
        metadata = {
            "trimmed": True,
            "original_duration": len(audio) / sample_rate,
            "trimmed_duration": len(trimmed_audio) / sample_rate,
            "trimmed_start_seconds": start_sample / sample_rate,
            "trimmed_end_seconds": (len(audio) - end_sample) / sample_rate
        }
        
        return trimmed_audio, metadata
