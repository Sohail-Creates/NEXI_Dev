"""
Audio preprocessing utility module.
Handles noise reduction, normalization, and audio format conversion for optimal processing.
"""

import logging
from pathlib import Path
from typing import Tuple, Optional

import numpy as np
try:
    import librosa
except Exception:
    librosa = None
    logging.getLogger(__name__).warning(
        "librosa not available at import time; some preprocessing functions will be disabled"
    )

# Note: do not import `noisereduce` at module import time to avoid issues with
# heavy optional dependencies and import-time failures (pkg_resources / pyparsing
# incompatibilities). Import `noisereduce` lazily inside `reduce_noise` where
# it's used; that allows the application to start even if the optional package
# is problematic in the environment.

from scipy.io import wavfile

from audio_service.config import PREPROCESSING_CONFIG

logger = logging.getLogger(__name__)


class AudioPreprocessingError(Exception):
    """Custom exception for audio preprocessing errors."""
    pass


def load_audio_file(file_path: str) -> Tuple[np.ndarray, int]:
    """
    Load audio file and return audio data with sample rate.
    
    Function to handles various audio formats and converts them to a consistent
    format for further processing. It supports WAV, MP3, FLAC, and other common formats.
    
    Args:
        file_path: Path to the audio file to load
        
    Returns:
        Tuple containing:
            - audio_data: NumPy array of audio samples
            - sample_rate: Sample rate of the audio in Hz
            
    Raises:
        AudioPreprocessingError: If file cannot be loaded or is invalid
    """
    try:
        file_path_obj = Path(file_path)

        if not file_path_obj.exists():
            raise AudioPreprocessingError(f"Audio file not found: {file_path}")

        # Try loading with scipy first for WAV files as it is faster
        if file_path_obj.suffix.lower() == '.wav':
            try:
                sample_rate, raw_data = wavfile.read(str(file_path_obj))

                # Preserve original dtype for correct scaling
                original_dtype = raw_data.dtype

                # Convert integer PCM to float32 in range [-1.0, 1.0]
                if np.issubdtype(original_dtype, np.integer):
                    if original_dtype == np.int16:
                        audio_data = raw_data.astype(np.float32) / 32768.0
                    elif original_dtype == np.int32:
                        audio_data = raw_data.astype(np.float32) / 2147483648.0
                    else:
                        # Generic integer scaling
                        max_val = float(np.iinfo(original_dtype).max)
                        audio_data = raw_data.astype(np.float32) / max_val
                else:
                    # Already float - cast to float32
                    audio_data = raw_data.astype(np.float32)

            except Exception:
                # Fall back to librosa if scipy fails
                audio_data, sample_rate = librosa.load(str(file_path_obj), sr=None)
        else:
            # Use librosa for non-WAV formats if available
            if librosa is None:
                raise AudioPreprocessingError(
                    "librosa is required to load non-WAV audio formats but is not available"
                )
            audio_data, sample_rate = librosa.load(str(file_path_obj), sr=None)

        # Convert stereo to mono if necessary
        if getattr(audio_data, 'ndim', 1) > 1:
            audio_data = np.mean(audio_data, axis=1)

        logger.info(f"Loaded audio file: {file_path} (duration: {len(audio_data)/sample_rate:.2f}s, sr: {sample_rate}Hz)")

        return audio_data, sample_rate
        
    except AudioPreprocessingError:
        raise
    except Exception as e:
        error_msg = f"Failed to load audio file {file_path}: {str(e)}"
        logger.error(error_msg)
        raise AudioPreprocessingError(error_msg) from e


def normalize_audio(audio_data: np.ndarray) -> np.ndarray:
    """
    Normalize audio amplitude to standard range.
    
    This ensures consistent volume levels across different recordings, which is
    important for wake word detection and speaker verification accuracy.
    
    Args:
        audio_data: Input audio data as NumPy array
        
    Returns:
        Normalized audio data in range [-1.0, 1.0]
    """
    try:
        if len(audio_data) == 0:
            logger.warning("Received empty audio data for normalization")
            return audio_data
        
        # Find the maximum absolute value
        max_val = np.max(np.abs(audio_data))
        
        # Avoid division by zero
        if max_val == 0:
            logger.warning("Audio data is completely silent, cannot normalize")
            return audio_data
        
        # Normalize to range [-1.0, 1.0]
        normalized = audio_data / max_val
        
        logger.debug(f"Normalized audio: max_val={max_val:.4f}")
        
        return normalized
        
    except Exception as e:
        logger.error(f"Failed to normalize audio: {str(e)}")
        # Return original audio if normalization fails
        return audio_data


def reduce_noise(audio_data: np.ndarray, sample_rate: int) -> np.ndarray:
    """
    Apply noise reduction to audio data.
    
    This removes background noise while preserving speech quality. Uses stationary
    noise reduction which is effective for constant background sounds like fans,
    air conditioning, or electrical hum.
    
    Args:
        audio_data: Input audio data as NumPy array
        sample_rate: Sample rate of the audio in Hz
        
    Returns:
        Noise-reduced audio data
    """
    try:
        if len(audio_data) == 0:
            logger.warning("Received empty audio data for noise reduction")
            return audio_data

        # Try to (re)import noisereduce at call time for robustness
        try:
            import noisereduce as nr_local
        except Exception:
            nr_local = None

        if nr_local is not None:
            # Use noisereduce if available
            try:
                reduced = nr_local.reduce_noise(
                    y=audio_data,
                    sr=sample_rate,
                    stationary=PREPROCESSING_CONFIG.get("noise_reduce_stationary", True),
                    prop_decrease=PREPROCESSING_CONFIG.get("noise_prop_decrease", 0.95)
                )
                logger.debug("Applied noise reduction via noisereduce")
                return reduced
            except Exception as e:
                logger.debug(f"noisereduce call failed: {e}; falling back to local method")

        # Fallback: simple spectral gating using librosa if available
        if librosa is not None:
            try:
                S = librosa.stft(audio_data, n_fft=2048, hop_length=512)
                mag, phase = np.abs(S), np.angle(S)

                # Estimate noise from minimum (quiet) frames across time
                noise_est = np.median(mag, axis=1, keepdims=True)

                prop_decrease = PREPROCESSING_CONFIG.get("noise_prop_decrease", 0.95)
                # Subtract scaled noise estimate and floor to tiny epsilon
                mag_denoised = np.maximum(mag - noise_est * prop_decrease, 1e-8)

                S_denoised = mag_denoised * np.exp(1j * phase)
                recovered = librosa.istft(S_denoised, hop_length=512)
                logger.debug("Applied fallback spectral gating via librosa")
                return recovered
            except Exception as e:
                logger.debug(f"Librosa-based fallback noise reduction failed: {e}")

        # Final fallback: simple high-pass filter using scipy.signal to remove low-frequency hum
        try:
            from scipy.signal import butter, filtfilt

            # Design a 2nd-order Butterworth high-pass filter at 100 Hz
            nyq = 0.5 * sample_rate
            cutoff = PREPROCESSING_CONFIG.get("hp_cutoff_hz", 100.0)
            normal_cutoff = min(cutoff / nyq, 0.99)
            b, a = butter(2, normal_cutoff, btype='high', analog=False)
            filtered = filtfilt(b, a, audio_data)
            logger.debug("Applied high-pass filter fallback for noise reduction")
            return filtered
        except Exception as e:
            logger.debug(f"High-pass filter fallback failed: {e}")

        # If all fallbacks fail, return original audio
        logger.debug("No noise reduction applied; returning original audio")
        return audio_data

    except Exception as e:
        logger.error(f"Failed to reduce noise: {str(e)}")
        # Return original audio if noise reduction fails
        return audio_data


def resample_audio(audio_data: np.ndarray, original_sr: int, target_sr: int) -> np.ndarray:
    """
    Resample audio to target sample rate.
    
    Different models expect different sample rates. Function to converts audio
    to the required sample rate while maintaining audio quality.
    
    Args:
        audio_data: Input audio data as NumPy array
        original_sr: Original sample rate in Hz
        target_sr: Target sample rate in Hz
        
    Returns:
        Resampled audio data
    """
    try:
        if original_sr == target_sr:
            # No resampling needed
            return audio_data
        
        if len(audio_data) == 0:
            logger.warning("Received empty audio data for resampling")
            return audio_data
        
        # Use librosa for high-quality resampling if available
        if librosa is None:
            logger.debug("librosa not available; skipping resampling")
            return audio_data

        resampled = librosa.resample(
            y=audio_data,
            orig_sr=original_sr,
            target_sr=target_sr
        )
        
        logger.debug(f"Resampled audio from {original_sr}Hz to {target_sr}Hz")
        
        return resampled
        
    except Exception as e:
        logger.error(f"Failed to resample audio: {str(e)}")
        # Return original audio if resampling fails
        return audio_data


def preprocess_audio(
    audio_data: np.ndarray,
    sample_rate: int,
    target_sr: Optional[int] = None,
    normalize: Optional[bool] = None,
    noise_reduction: Optional[bool] = None
) -> Tuple[np.ndarray, int]:
    """
    Complete audio preprocessing pipeline.
    
    This applies all necessary preprocessing steps in the correct order:
    1. Noise reduction (if enabled)
    2. Normalization (if enabled)
    3. Resampling (if target sample rate differs)
    
    Args:
        audio_data: Input audio data as NumPy array
        sample_rate: Original sample rate of the audio
        target_sr: Target sample rate for output (uses config default if None)
        normalize: Whether to normalize audio (uses config default if None)
        noise_reduction: Whether to apply noise reduction (uses config default if None)
        
    Returns:
        Tuple containing:
            - preprocessed_data: Processed audio data
            - output_sr: Sample rate of the output audio
            
    Raises:
        AudioPreprocessingError: If preprocessing fails critically
    """
    try:
        processed_data = audio_data.copy()
        
        # Use configuration defaults if not specified
        if normalize is None:
            normalize = PREPROCESSING_CONFIG["normalize_audio"]
        if noise_reduction is None:
            noise_reduction = PREPROCESSING_CONFIG["noise_reduction"]
        if target_sr is None:
            target_sr = PREPROCESSING_CONFIG["target_sr"]
        
        # Step 1: Apply noise reduction first to clean the signal
        if noise_reduction:
            processed_data = reduce_noise(processed_data, sample_rate)
        
        # Step 2: Normalize audio levels for consistent amplitude
        if normalize:
            processed_data = normalize_audio(processed_data)
        
        # Step 3: Resample to target sample rate if needed
        if target_sr != sample_rate:
            processed_data = resample_audio(processed_data, sample_rate, target_sr)
            output_sr = target_sr
        else:
            output_sr = sample_rate
        
        logger.info(
            f"Preprocessed audio: noise_reduction={noise_reduction}, "
            f"normalize={normalize}, sr={sample_rate}->{output_sr}Hz"
        )
        
        return processed_data, output_sr
        
    except Exception as e:
        error_msg = f"Audio preprocessing failed: {str(e)}"
        logger.error(error_msg)
        raise AudioPreprocessingError(error_msg) from e


def preprocess_audio_file(
    file_path: str,
    target_sr: Optional[int] = None,
    normalize: Optional[bool] = None,
    noise_reduction: Optional[bool] = None
) -> Tuple[np.ndarray, int]:
    """
    Load and preprocess audio file in one step.
    
    This is a convenience function that combines file loading and preprocessing
    into a single operation. Use this when you need to prepare an audio file
    for model inference or further processing.
    
    Args:
        file_path: Path to the audio file
        target_sr: Target sample rate (uses config default if None)
        normalize: Whether to normalize (uses config default if None)
        noise_reduction: Whether to reduce noise (uses config default if None)
        
    Returns:
        Tuple containing:
            - processed_data: Preprocessed audio data
            - sample_rate: Sample rate of the output
            
    Raises:
        AudioPreprocessingError: If loading or preprocessing fails
    """
    try:
        # Load the audio file
        audio_data, sample_rate = load_audio_file(file_path)
        
        # Apply preprocessing pipeline
        processed_data, output_sr = preprocess_audio(
            audio_data=audio_data,
            sample_rate=sample_rate,
            target_sr=target_sr,
            normalize=normalize,
            noise_reduction=noise_reduction
        )
        
        return processed_data, output_sr
        
    except Exception as e:
        error_msg = f"Failed to preprocess audio file {file_path}: {str(e)}"
        logger.error(error_msg)
        raise AudioPreprocessingError(error_msg) from e


def validate_audio_duration(
    audio_data: np.ndarray,
    sample_rate: int,
    min_duration: float = 0.5,
    max_duration: float = 300.0
) -> bool:
    """
    Validate that audio duration is within acceptable range.
    
    This prevents processing of audio files that are too short (likely noise)
    or too long (possibly errors or very large files).
    
    Args:
        audio_data: Audio data to validate
        sample_rate: Sample rate of the audio
        min_duration: Minimum acceptable duration in seconds
        max_duration: Maximum acceptable duration in seconds
        
    Returns:
        True if duration is valid, False otherwise
    """
    try:
        duration = len(audio_data) / sample_rate
        
        if duration < min_duration:
            logger.warning(f"Audio duration {duration:.2f}s is below minimum {min_duration}s")
            return False
        
        if duration > max_duration:
            logger.warning(f"Audio duration {duration:.2f}s exceeds maximum {max_duration}s")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to validate audio duration: {str(e)}")
        return False


def convert_to_int16(audio_data: np.ndarray) -> np.ndarray:
    """
    Convert float audio data to int16 format for WAV file saving.
    
    Many audio processing functions use float32, but WAV files typically use
    int16. Function to converts between formats safely.
    
    Args:
        audio_data: Audio data as float32 in range [-1.0, 1.0]
        
    Returns:
        Audio data as int16
    """
    try:
        # Ensure data is in float format and in range [-1.0, 1.0]
        audio_float = np.clip(audio_data, -1.0, 1.0)
        
        # Convert to int16 range
        audio_int16 = (audio_float * 32767).astype(np.int16)
        
        return audio_int16
        
    except Exception as e:
        logger.error(f"Failed to convert audio to int16: {str(e)}")
        # Return original data if conversion fails
        return audio_data.astype(np.int16)
