"""
Comprehensive validation and error handling utilities
Provides robust input validation, file validation, and secure error responses
"""

import os
import mimetypes
from typing import List, Optional, Dict, Any
from fastapi import HTTPException, UploadFile
from enum import Enum


class ValidationError(Exception):
    """Custom validation error with HTTP status codes"""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class FileType(str, Enum):
    """Allowed file types"""
    JPG = "image/jpeg"
    PNG = "image/png"
    WAV = "audio/wav"
    MP3 = "audio/mpeg"


class EnrollmentValidator:
    """Centralized validation logic for enrollment operations"""
    
    # Configuration
    REQUIRED_PHOTOS = 5
    REQUIRED_AUDIO = 5
    MAX_PHOTO_SIZE = 5 * 1024 * 1024  # 5 MB
    MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 10 MB
    ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png"}
    ALLOWED_AUDIO_TYPES = {"audio/wav", "audio/mpeg"}
    MAX_FILENAME_LENGTH = 255
    MAX_USERNAME_LENGTH = 255
    MIN_USERNAME_LENGTH = 1
    
    @classmethod
    def validate_username(cls, username: Optional[str]) -> str:
        """
        Validate user name format and length
        
        Args:
            username: User name to validate
            
        Returns:
            Validated username
            
        Raises:
            ValidationError: If username is invalid
        """
        if not username or not isinstance(username, str):
            raise ValidationError(
                "User name is required and must be a string",
                status_code=400
            )
        
        username = username.strip()
        
        if not username:
            raise ValidationError(
                "User name cannot be empty or whitespace only",
                status_code=400
            )
        
        if len(username) < cls.MIN_USERNAME_LENGTH:
            raise ValidationError(
                f"User name too short (minimum {cls.MIN_USERNAME_LENGTH} character)",
                status_code=400
            )
        
        if len(username) > cls.MAX_USERNAME_LENGTH:
            raise ValidationError(
                f"User name too long (maximum {cls.MAX_USERNAME_LENGTH} characters)",
                status_code=400
            )
        
        # Check for invalid characters
        invalid_chars = {'/', '\\', '\x00', '<', '>', ':', '"', '|', '?', '*'}
        if any(char in username for char in invalid_chars):
            raise ValidationError(
                "User name contains invalid characters",
                status_code=400
            )
        
        return username
    
    @classmethod
    def validate_optional_metadata(cls, age: Optional[int] = None, relation: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate optional metadata fields
        
        Args:
            age: User age (optional)
            relation: Relationship description (optional)
            
        Returns:
            Validated metadata dict
            
        Raises:
            ValidationError: If validation fails
        """
        metadata = {}
        
        if age is not None:
            if not isinstance(age, int):
                raise ValidationError(
                    "Age must be an integer",
                    status_code=400
                )
            if age < 0 or age > 150:
                raise ValidationError(
                    "Age must be between 0 and 150",
                    status_code=400
                )
            metadata['age'] = age
        
        if relation is not None:
            if not isinstance(relation, str):
                raise ValidationError(
                    "Relation must be a string",
                    status_code=400
                )
            relation = relation.strip()
            if len(relation) > 100:
                raise ValidationError(
                    "Relation description too long (max 100 characters)",
                    status_code=400
                )
            if relation:  # Only add if not empty after strip
                metadata['relation'] = relation
        
        return metadata
    
    @classmethod
    def validate_file_count(cls, photos: List[UploadFile], voice_samples: List[UploadFile]) -> None:
        """
        Validate that exactly required number of files are provided
        
        Args:
            photos: List of photo files
            voice_samples: List of audio files
            
        Raises:
            ValidationError: If file count doesn't match requirements
        """
        if not photos or len(photos) != cls.REQUIRED_PHOTOS:
            actual_count = len(photos) if photos else 0
            raise ValidationError(
                f"Exactly {cls.REQUIRED_PHOTOS} photos required. Received: {actual_count}",
                status_code=400
            )
        
        if not voice_samples or len(voice_samples) != cls.REQUIRED_AUDIO:
            actual_count = len(voice_samples) if voice_samples else 0
            raise ValidationError(
                f"Exactly {cls.REQUIRED_AUDIO} voice samples required. Received: {actual_count}",
                status_code=400
            )
    
    @classmethod
    async def validate_photo_file(cls, file: UploadFile, file_index: int) -> None:
        """
        Validate a single photo file
        
        Args:
            file: UploadFile to validate
            file_index: Index for error messages (1-based)
            
        Raises:
            ValidationError: If validation fails
        """
        if not file or not file.filename:
            raise ValidationError(
                f"Photo {file_index}: No file provided",
                status_code=400
            )
        
        # Check filename length
        if len(file.filename) > cls.MAX_FILENAME_LENGTH:
            raise ValidationError(
                f"Photo {file_index}: Filename too long",
                status_code=400
            )
        
        # Check file extension
        _, ext = os.path.splitext(file.filename.lower())
        if not ext:
            raise ValidationError(
                f"Photo {file_index}: File must have an extension",
                status_code=400
            )
        
        # Check MIME type
        if not file.content_type:
            raise ValidationError(
                f"Photo {file_index}: Content type not detected",
                status_code=400
            )
        
        if file.content_type not in cls.ALLOWED_IMAGE_TYPES:
            raise ValidationError(
                f"Photo {file_index}: Invalid format. Allowed: JPG, PNG. Got: {file.content_type}",
                status_code=415
            )
        
        # Check file size
        if file.size and file.size > cls.MAX_PHOTO_SIZE:
            size_mb = file.size / (1024 * 1024)
            max_mb = cls.MAX_PHOTO_SIZE / (1024 * 1024)
            raise ValidationError(
                f"Photo {file_index}: File too large ({size_mb:.2f}MB). Maximum: {max_mb}MB",
                status_code=413
            )
        
        # Attempt to read first bytes to verify it's actually an image
        try:
            content = await file.read(512)  # Read first 512 bytes
            await file.seek(0)  # Reset file pointer
            
            if not content:
                raise ValidationError(
                    f"Photo {file_index}: File is empty",
                    status_code=400
                )
            
            # Basic magic number check for JPEG/PNG
            is_jpeg = content[:2] == b'\xff\xd8'
            is_png = content[:4] == b'\x89PNG'
            
            if not (is_jpeg or is_png):
                raise ValidationError(
                    f"Photo {file_index}: File content doesn't match expected format",
                    status_code=400
                )
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(
                f"Photo {file_index}: Failed to read file: {str(e)}",
                status_code=400
            )
    
    @classmethod
    async def validate_audio_file(cls, file: UploadFile, file_index: int) -> None:
        """
        Validate a single audio file
        
        Args:
            file: UploadFile to validate
            file_index: Index for error messages (1-based)
            
        Raises:
            ValidationError: If validation fails
        """
        if not file or not file.filename:
            raise ValidationError(
                f"Audio {file_index}: No file provided",
                status_code=400
            )
        
        # Check filename length
        if len(file.filename) > cls.MAX_FILENAME_LENGTH:
            raise ValidationError(
                f"Audio {file_index}: Filename too long",
                status_code=400
            )
        
        # Check file extension
        _, ext = os.path.splitext(file.filename.lower())
        if not ext:
            raise ValidationError(
                f"Audio {file_index}: File must have an extension",
                status_code=400
            )
        
        # Check MIME type
        if not file.content_type:
            raise ValidationError(
                f"Audio {file_index}: Content type not detected",
                status_code=400
            )
        
        if file.content_type not in cls.ALLOWED_AUDIO_TYPES:
            raise ValidationError(
                f"Audio {file_index}: Invalid format. Allowed: WAV, MP3. Got: {file.content_type}",
                status_code=415
            )
        
        # Check file size
        if file.size and file.size > cls.MAX_AUDIO_SIZE:
            size_mb = file.size / (1024 * 1024)
            max_mb = cls.MAX_AUDIO_SIZE / (1024 * 1024)
            raise ValidationError(
                f"Audio {file_index}: File too large ({size_mb:.2f}MB). Maximum: {max_mb}MB",
                status_code=413
            )
        
        # Attempt to read first bytes to verify it's actually audio
        try:
            content = await file.read(512)
            await file.seek(0)
            
            if not content:
                raise ValidationError(
                    f"Audio {file_index}: File is empty",
                    status_code=400
                )
            
            # Basic magic number check for WAV/MP3
            is_wav = content[:4] == b'RIFF' and b'WAVE' in content[:12]
            is_mp3 = content[:2] == b'ID' or content[:2] == b'\xff\xfb'
            
            if not (is_wav or is_mp3):
                raise ValidationError(
                    f"Audio {file_index}: File content doesn't match expected audio format",
                    status_code=400
                )
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(
                f"Audio {file_index}: Failed to read file: {str(e)}",
                status_code=400
            )
    
    @classmethod
    async def validate_all_photos(cls, photos: List[UploadFile]) -> None:
        """Validate all photo files"""
        for idx, photo in enumerate(photos, 1):
            await cls.validate_photo_file(photo, idx)
    
    @classmethod
    async def validate_all_audio(cls, audio_files: List[UploadFile]) -> None:
        """Validate all audio files"""
        for idx, audio in enumerate(audio_files, 1):
            await cls.validate_audio_file(audio, idx)


class ErrorFormatter:
    """Format errors for safe external response"""
    
    @staticmethod
    def format_validation_error(error: Exception) -> Dict[str, Any]:
        """
        Format validation error for HTTP response
        Avoid exposing sensitive internal information
        
        Args:
            error: Exception to format
            
        Returns:
            Formatted error dict
        """
        if isinstance(error, ValidationError):
            return {
                "error": error.message,
                "type": "validation_error",
                "status": error.status_code
            }
        
        # Generic error response that doesn't expose internals
        return {
            "error": "An error occurred during processing. Please try again.",
            "type": "processing_error",
            "status": 500
        }
    
    @staticmethod
    def format_service_error(service_name: str, detail: str) -> Dict[str, Any]:
        """
        Format service integration error
        
        Args:
            service_name: Name of the service (Vision, Audio, Central)
            detail: Error detail
            
        Returns:
            Formatted error dict
        """
        return {
            "error": f"{service_name} service returned an error. Please try again.",
            "service": service_name,
            "type": "service_error",
            "status": 503
        }
    
    @staticmethod
    def format_file_error(file_index: int, file_type: str, detail: str) -> Dict[str, Any]:
        """
        Format file processing error
        
        Args:
            file_index: Index of the file (1-based)
            file_type: Type of file (photo/audio)
            detail: Error detail
            
        Returns:
            Formatted error dict
        """
        return {
            "error": f"Failed to process {file_type} {file_index}. Please ensure file is valid.",
            "file_index": file_index,
            "file_type": file_type,
            "type": "file_error",
            "status": 400
        }
