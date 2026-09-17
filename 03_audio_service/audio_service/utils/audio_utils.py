"""
Audio utility module for recording and saving audio files.
Handles microphone input capture and WAV file generation.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple, Optional

import numpy as np
import sounddevice as sd
from scipy.io import wavfile

from audio_service.config import (
    AUDIO_CONFIG,
    AUDIO_FILE_EXTENSION,
    AUDIO_FILE_PREFIX,
    DATA_DIR,
    TIMESTAMP_FORMAT
)
from audio_service.device_selection import resolve_sounddevice_input

logger = logging.getLogger(__name__)


class AudioRecorderError(Exception):
    """Custom exception for audio recording errors."""
    pass


def get_audio_filename() -> str:
    """
    Generate a unique filename for audio recordings based on timestamp.
    
    Returns:
        str: Formatted filename with timestamp
    """
    timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
    filename = f"{AUDIO_FILE_PREFIX}_{timestamp}{AUDIO_FILE_EXTENSION}"
    return filename


def get_audio_filepath(filename: str) -> Path:
    """
    Get the complete file path for an audio file.
    
    Args:
        filename: Name of the audio file
        
    Returns:
        Path: Complete path object for the audio file
    """
    # Organize audio files into subfolders by prefix to keep `data/` tidy.
    # Expected filename format: "prefix_timestamp.ext" (e.g., enrollment_20231101_120000.wav)
    try:
        prefix = filename.split('_', 1)[0]
    except Exception:
        prefix = "misc"

    subdir = DATA_DIR / prefix
    # Ensure category directory exists
    subdir.mkdir(parents=True, exist_ok=True)

    return subdir / filename


def validate_recording_parameters(duration: float, sample_rate: int) -> None:
    """
    Validate recording parameters to ensure they are within acceptable ranges.
    
    Args:
        duration: Recording duration in seconds
        sample_rate: Audio sample rate in Hz
        
    Raises:
        ValueError: If parameters are invalid
    """
    if duration <= 0:
        raise ValueError("Duration must be greater than 0 seconds")
    
    if duration > 300:
        raise ValueError("Duration cannot exceed 300 seconds (5 minutes)")
    
    if sample_rate < 8000 or sample_rate > 48000:
        raise ValueError("Sample rate must be between 8000 and 48000 Hz")


def record_audio(
    duration: float = None,
    sample_rate: int = None,
    channels: int = None
) -> Tuple[np.ndarray, int]:
    """
    Record audio from the default microphone.
    
    Args:
        duration: Recording duration in seconds (default from config)
        sample_rate: Sample rate in Hz (default from config)
        channels: Number of audio channels (default from config)
        
    Returns:
        Tuple[np.ndarray, int]: Recorded audio data and sample rate
        
    Raises:
        AudioRecorderError: If recording fails
    """
    # Use default values from config if not provided
    duration = duration or AUDIO_CONFIG["default_duration"]
    sample_rate = sample_rate or AUDIO_CONFIG["sample_rate"]
    channels = channels or AUDIO_CONFIG["channels"]
    
    # Validate parameters
    validate_recording_parameters(duration, sample_rate)
    
    try:
        logger.info(
            f"Starting audio recording: duration={duration}s, "
            f"sample_rate={sample_rate}Hz, channels={channels}"
        )
        input_device = resolve_sounddevice_input()
        logger.info(
            "Using audio input index=%s name=%s hostapi=%s",
            input_device.index,
            input_device.name,
            input_device.hostapi,
        )
        
        # Record audio from microphone
        audio_data = sd.rec(
            int(duration * sample_rate),
            samplerate=sample_rate,
            channels=channels,
            dtype=AUDIO_CONFIG["dtype"],
            device=input_device.index,
        )
        
        # Wait for recording to complete
        sd.wait()
        
        logger.info("Audio recording completed successfully")
        return audio_data, sample_rate
        
    except Exception as e:
        error_msg = f"Failed to record audio: {str(e)}"
        logger.error(error_msg)
        raise AudioRecorderError(error_msg) from e


def save_audio_file(
    audio_data: np.ndarray,
    sample_rate: int,
    filename: str = None
) -> Dict[str, any]:
    """
    Save recorded audio data to a WAV file.
    
    Args:
        audio_data: NumPy array containing audio data
        sample_rate: Sample rate of the audio
        filename: Optional custom filename (will generate if not provided)
        
    Returns:
        Dict: Metadata about the saved file
        
    Raises:
        AudioRecorderError: If file save fails
    """
    try:
        # Generate filename if not provided
        if filename is None:
            filename = get_audio_filename()
        
        # Get complete file path
        filepath = get_audio_filepath(filename)
        
        # Save audio as WAV file
        wavfile.write(str(filepath), sample_rate, audio_data)
        
        # Get file metadata
        file_size = filepath.stat().st_size
        duration = len(audio_data) / sample_rate
        
        logger.info(f"Audio file saved successfully: {filename}")
        
        return {
            "filename": filename,
            "filepath": str(filepath),
            "file_size": file_size,
            "duration": round(duration, 2),
            "sample_rate": sample_rate,
            "channels": audio_data.shape[1] if len(audio_data.shape) > 1 else 1,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        error_msg = f"Failed to save audio file: {str(e)}"
        logger.error(error_msg)
        raise AudioRecorderError(error_msg) from e


def record_and_save_audio(
    duration: Optional[float] = None,
    sample_rate: Optional[int] = None,
    channels: Optional[int] = None,
    filename: Optional[str] = None
) -> Dict[str, any]:
    """
    Complete workflow to record audio and save to file.
    
    Args:
        duration: Recording duration in seconds
        sample_rate: Sample rate in Hz
        channels: Number of audio channels
        filename: Optional custom filename
        
    Returns:
        Dict: Complete metadata about the recording and saved file
        
    Raises:
        AudioRecorderError: If recording or saving fails
    """
    try:
        # Record audio
        audio_data, actual_sample_rate = record_audio(
            duration=duration,
            sample_rate=sample_rate,
            channels=channels
        )
        
        # Save to file
        file_metadata = save_audio_file(
            audio_data=audio_data,
            sample_rate=actual_sample_rate,
            filename=filename
        )
        
        return file_metadata
        
    except Exception as e:
        logger.error(f"Audio recording workflow failed: {str(e)}")
        raise


def list_audio_files() -> list:
    """
    List all audio files in the data directory.
    
    Returns:
        list: List of dictionaries containing file information
    """
    try:
        audio_files = []

        # Search recursively so files stored in category subfolders are included
        for filepath in DATA_DIR.rglob(f"*{AUDIO_FILE_EXTENSION}"):
            file_stat = filepath.stat()
            # Include relative path within data directory so consumers can see category
            rel_path = filepath.relative_to(DATA_DIR)
            audio_files.append({
                "filename": filepath.name,
                "relative_path": str(rel_path),
                "file_size": file_stat.st_size,
                "created_at": datetime.fromtimestamp(file_stat.st_ctime).isoformat(),
                "modified_at": datetime.fromtimestamp(file_stat.st_mtime).isoformat()
            })
        
        logger.info(f"Found {len(audio_files)} audio files")
        return audio_files
        
    except Exception as e:
        error_msg = f"Failed to list audio files: {str(e)}"
        logger.error(error_msg)
        raise AudioRecorderError(error_msg) from e


def delete_audio_file(filename: str) -> bool:
    """
    Delete a specific audio file.
    
    Args:
        filename: Name of the file to delete
        
    Returns:
        bool: True if file was deleted successfully
        
    Raises:
        AudioRecorderError: If file deletion fails
        FileNotFoundError: If file does not exist
    """
    try:
        filepath = get_audio_filepath(filename)
        
        if not filepath.exists():
            raise FileNotFoundError(f"Audio file not found: {filename}")
        
        filepath.unlink()
        logger.info(f"Audio file deleted successfully: {filename}")
        return True
        
    except FileNotFoundError:
        raise
    except Exception as e:
        error_msg = f"Failed to delete audio file: {str(e)}"
        logger.error(error_msg)
        raise AudioRecorderError(error_msg) from e
