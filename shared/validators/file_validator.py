"""
Input Validation Utilities
Validates all file uploads and parameters before processing
"""

import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


class FileValidator:
    """Validate uploaded files (images, audio) before processing."""
    
    # File size limits
    MAX_IMAGE_SIZE_MB = 5
    MAX_AUDIO_SIZE_MB = 10
    
    # File size in bytes
    MAX_IMAGE_SIZE = MAX_IMAGE_SIZE_MB * 1024 * 1024
    MAX_AUDIO_SIZE = MAX_AUDIO_SIZE_MB * 1024 * 1024
    
    # File signatures (magic bytes)
    JPEG_SIGNATURE = b'\xff\xd8\xff'
    PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
    WAV_SIGNATURE = b'RIFF'
    MP3_SIGNATURE = b'ID3'  # MP3 v2
    
    @classmethod
    def validate_image(cls, file_bytes: bytes, filename: str) -> Tuple[bool, Optional[str]]:
        """
        Validate image file format and size.
        
        Returns:
            (is_valid, error_message)
        """
        if not file_bytes:
            return False, "Image file is empty"
        
        if len(file_bytes) == 0:
            return False, "Image file contains no data"
        
        if len(file_bytes) > cls.MAX_IMAGE_SIZE:
            size_mb = len(file_bytes) / 1024 / 1024
            return False, f"Image too large: {size_mb:.1f}MB (max {cls.MAX_IMAGE_SIZE_MB}MB)"
        
        # Check file signature
        if file_bytes[:3] == cls.JPEG_SIGNATURE:
            file_type = "JPEG"
        elif file_bytes[:8] == cls.PNG_SIGNATURE:
            file_type = "PNG"
        else:
            return False, "Invalid image format (must be JPEG or PNG)"
        
        # Check filename extension matches content
        ext = filename.lower().split('.')[-1] if '.' in filename else ''
        
        if file_type == "JPEG" and ext not in ['jpg', 'jpeg']:
            return False, f"File content is JPEG but extension is '.{ext}'"
        elif file_type == "PNG" and ext != 'png':
            return False, f"File content is PNG but extension is '.{ext}'"
        
        logger.debug(f" Valid {file_type} image: {filename} ({len(file_bytes)} bytes)")
        return True, None
    
    @classmethod
    def validate_audio(cls, file_bytes: bytes, filename: str) -> Tuple[bool, Optional[str]]:
        """
        Validate audio file format and size.
        
        Returns:
            (is_valid, error_message)
        """
        if not file_bytes:
            return False, "Audio file is empty"
        
        if len(file_bytes) == 0:
            return False, "Audio file contains no data"
        
        if len(file_bytes) > cls.MAX_AUDIO_SIZE:
            size_mb = len(file_bytes) / 1024 / 1024
            return False, f"Audio too large: {size_mb:.1f}MB (max {cls.MAX_AUDIO_SIZE_MB}MB)"
        
        # Check file signature
        is_wav = file_bytes[:4] == cls.WAV_SIGNATURE
        is_mp3 = file_bytes[:3] == cls.MP3_SIGNATURE
        
        if not (is_wav or is_mp3):
            return False, "Invalid audio format (must be WAV or MP3)"
        
        file_type = "WAV" if is_wav else "MP3"
        
        # Validate WAV header if applicable
        if is_wav:
            try:
                # WAV header structure:
                # Bytes 0-3: "RIFF"
                # Bytes 4-7: File size - 8
                # Bytes 8-11: "WAVE"
                # Check minimum size
                if len(file_bytes) < 44:  # Minimum WAV header
                    return False, "WAV file too small (corrupted header)"
                
                # Bytes 12-15: "fmt "
                if file_bytes[12:16] != b'fmt ':
                    logger.warning(f"WAV file {filename} missing fmt chunk")
                    # Continue anyway - might still be valid
                
                # Bytes 16-19: fmt chunk size
                # Bytes 20-21: Audio format (1 = PCM)
                # Bytes 22-23: Number of channels
                # Bytes 24-27: Sample rate
                
                if len(file_bytes) >= 24:
                    channels = int.from_bytes(file_bytes[22:24], 'little')
                    if channels < 1 or channels > 8:
                        return False, f"Invalid channel count: {channels} (must be 1-8)"
                    
                    sample_rate = int.from_bytes(file_bytes[24:28], 'little')
                    if sample_rate < 8000 or sample_rate > 48000:
                        return False, f"Invalid sample rate: {sample_rate} (must be 8000-48000 Hz)"
                
                logger.debug(f" Valid WAV audio: {filename} ({len(file_bytes)} bytes)")
                
            except Exception as e:
                logger.warning(f"Could not fully validate WAV header: {e}")
                # Still accept it if basic checks passed
        
        if is_mp3:
            logger.debug(f" Valid MP3 audio: {filename} ({len(file_bytes)} bytes)")
        
        return True, None


class ParameterValidator:
    """Validate request parameters."""
    
    @classmethod
    def validate_speaker_id(cls, speaker_id: str) -> Tuple[bool, Optional[str]]:
        """Validate speaker ID format."""
        if not speaker_id:
            return False, "speaker_id is required"
        
        if not isinstance(speaker_id, str):
            return False, "speaker_id must be a string"
        
        if len(speaker_id) > 256:
            return False, "speaker_id too long (max 256 chars)"
        
        # Allow alphanumeric, underscore, dash
        if not all(c.isalnum() or c in ['_', '-'] for c in speaker_id):
            return False, "speaker_id contains invalid characters (use letters, numbers, _, -)"
        
        return True, None
    
    @classmethod
    def validate_threshold(cls, threshold: float) -> Tuple[bool, Optional[str]]:
        """Validate similarity threshold (0.0-1.0)."""
        if threshold < 0.0 or threshold > 1.0:
            return False, f"threshold must be between 0.0 and 1.0, got {threshold}"
        
        return True, None
    
    @classmethod
    def validate_user_name(cls, user_name: str) -> Tuple[bool, Optional[str]]:
        """Validate user name."""
        if not user_name:
            return False, "user_name is required"
        
        if not isinstance(user_name, str):
            return False, "user_name must be a string"
        
        if len(user_name.strip()) == 0:
            return False, "user_name cannot be empty or whitespace"
        
        if len(user_name) > 256:
            return False, "user_name too long (max 256 chars)"
        
        return True, None


# Default instance for use in routes
file_validator = FileValidator()
param_validator = ParameterValidator()
