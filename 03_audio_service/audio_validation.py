"""
Audio Validation Module

Validates audio inputs before processing.
No silent failures - explicit checks for every requirement.
"""

import os
from typing import Tuple
import numpy as np
import librosa

# Audio requirements
SUPPORTED_FORMATS = {'wav', 'mp3', 'ogg'}
MIN_DURATION_SECONDS = 1.0
MAX_DURATION_SECONDS = 30.0
TARGET_SAMPLE_RATE = 16000
MONO_CHANNELS = 1


class AudioValidationError(Exception):
    """Audio validation failed"""
    pass


class AudioValidator:
    """Comprehensive audio validation"""
    
    @staticmethod
    def validate_file_exists(file_path: str) -> bool:
        """Check file exists and is readable"""
        if not os.path.exists(file_path):
            raise AudioValidationError(f"Audio file not found: {file_path}")
        
        if not os.path.isfile(file_path):
            raise AudioValidationError(f"Path is not a file: {file_path}")
        
        if not os.access(file_path, os.R_OK):
            raise AudioValidationError(f"Audio file not readable: {file_path}")
        
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            raise AudioValidationError("Audio file is empty")
        
        return True
    
    @staticmethod
    def validate_format(file_path: str) -> str:
        """Check file format is supported"""
        ext = os.path.splitext(file_path)[1].lower().lstrip('.')
        
        if not ext:
            raise AudioValidationError("No file extension provided")
        
        if ext not in SUPPORTED_FORMATS:
            raise AudioValidationError(
                f"Unsupported audio format: {ext}. "
                f"Supported formats: {', '.join(SUPPORTED_FORMATS)}"
            )
        
        return ext
    
    @staticmethod
    def validate_audio_content(audio: np.ndarray, sr: int) -> Tuple[np.ndarray, int]:
        """
        Validate audio array has proper content
        
        Returns:
            (audio_array, sample_rate)
        """
        
        # Check array is not empty
        if audio.size == 0:
            raise AudioValidationError("Audio array is empty")
        
        # Check for NaN or Inf
        if not np.isfinite(audio).all():
            raise AudioValidationError("Audio contains NaN or Inf values")
        
        # Check sample rate
        if sr <= 0:
            raise AudioValidationError(f"Invalid sample rate: {sr}")
        
        # Check duration
        duration = len(audio) / sr
        if duration < MIN_DURATION_SECONDS:
            raise AudioValidationError(
                f"Audio too short: {duration:.2f}s < {MIN_DURATION_SECONDS}s"
            )
        
        if duration > MAX_DURATION_SECONDS:
            raise AudioValidationError(
                f"Audio too long: {duration:.2f}s > {MAX_DURATION_SECONDS}s"
            )
        
        # Check for all zeros (silent audio)
        rms = np.sqrt(np.mean(audio ** 2))
        if rms < 1e-6:
            raise AudioValidationError(
                f"Audio is silent (RMS < 1e-6, got {rms:.2e})"
            )
        
        return audio, sr
    
    @classmethod
    def validate_and_load(cls, file_path: str) -> Tuple[np.ndarray, int]:
        """
        Complete validation and loading pipeline
        
        Returns:
            (audio_array, sample_rate)
            
        Raises:
            AudioValidationError: If any validation fails
        """
        
        # Step 1: File exists
        cls.validate_file_exists(file_path)
        
        # Step 2: Format valid
        cls.validate_format(file_path)
        
        # Step 3: Load audio
        try:
            audio, sr = librosa.load(file_path, sr=None, mono=False)
        except Exception as e:
            raise AudioValidationError(f"Failed to load audio file: {str(e)}")
        
        # Step 4: Handle stereo/mono
        if len(audio.shape) > 1:
            # Stereo - convert to mono by averaging
            audio = np.mean(audio, axis=0)
        
        # Step 5: Resample to 16kHz
        if sr != TARGET_SAMPLE_RATE:
            try:
                audio = librosa.resample(audio, orig_sr=sr, target_sr=TARGET_SAMPLE_RATE)
                sr = TARGET_SAMPLE_RATE
            except Exception as e:
                raise AudioValidationError(f"Failed to resample audio: {str(e)}")
        
        # Step 6: Validate content
        audio, sr = cls.validate_audio_content(audio, sr)
        
        return audio, sr


class AudioNormalizer:
    """Normalize audio for processing"""
    
    @staticmethod
    def normalize(audio: np.ndarray) -> np.ndarray:
        """
        Normalize audio to [-1, 1] range
        """
        max_val = np.max(np.abs(audio))
        
        if max_val == 0:
            return audio
        
        return audio / max_val
    
    @staticmethod
    def apply_pre_emphasis(audio: np.ndarray, coef: float = 0.97) -> np.ndarray:
        """Apply pre-emphasis filter"""
        return np.append(audio[0], audio[1:] - coef * audio[:-1])
