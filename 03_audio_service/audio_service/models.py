"""
Pydantic models for request validation and response serialization.
"""

from typing import Optional
from pydantic import BaseModel, Field, validator


class RecordRequest(BaseModel):
    """Request model for audio recording endpoint."""
    
    duration: Optional[float] = Field(
        default=5.0,
        description="Recording duration in seconds",
        gt=0,
        le=300
    )
    sample_rate: Optional[int] = Field(
        default=16000,
        description="Audio sample rate in Hz",
        ge=8000,
        le=48000
    )
    channels: Optional[int] = Field(
        default=1,
        description="Number of audio channels (1=mono, 2=stereo)",
        ge=1,
        le=2
    )
    
    @validator("duration")
    def validate_duration(cls, v):
        """Validate duration is within acceptable range."""
        if v <= 0:
            raise ValueError("Duration must be greater than 0")
        if v > 300:
            raise ValueError("Duration cannot exceed 300 seconds")
        return v
    
    @validator("sample_rate")
    def validate_sample_rate(cls, v):
        """Validate sample rate is within acceptable range."""
        if v < 8000 or v > 48000:
            raise ValueError("Sample rate must be between 8000 and 48000 Hz")
        return v


class RecordResponse(BaseModel):
    """Response model for successful audio recording."""
    
    status: str = Field(description="Status of the operation")
    message: str = Field(description="Human-readable message")
    file_name: str = Field(description="Name of the saved audio file")
    filepath: str = Field(description="Complete path to the audio file")
    duration: float = Field(description="Recording duration in seconds")
    sample_rate: int = Field(description="Audio sample rate in Hz")
    channels: int = Field(description="Number of audio channels")
    file_size: int = Field(description="File size in bytes")
    timestamp: str = Field(description="ISO format timestamp of recording")


class ErrorResponse(BaseModel):
    """Response model for error cases."""
    
    status: str = Field(default="error", description="Status of the operation")
    message: str = Field(description="Error message")
    error_type: Optional[str] = Field(default=None, description="Type of error")


class AudioFileInfo(BaseModel):
    """Model for audio file information."""
    
    filename: str = Field(description="Name of the audio file")
    relative_path: Optional[str] = Field(default=None, description="Relative path inside data directory")
    file_size: int = Field(description="File size in bytes")
    created_at: str = Field(description="File creation timestamp")
    modified_at: str = Field(description="File modification timestamp")


class ListAudioResponse(BaseModel):
    """Response model for listing audio files."""
    
    status: str = Field(description="Status of the operation")
    count: int = Field(description="Number of audio files found")
    files: list[AudioFileInfo] = Field(description="List of audio files")


class DeleteResponse(BaseModel):
    """Response model for file deletion."""
    
    status: str = Field(description="Status of the operation")
    message: str = Field(description="Human-readable message")
    filename: str = Field(description="Name of the deleted file")


# Week 2: Wake Word Detection Models

class WakeWordStatusResponse(BaseModel):
    """Response model for wake word detection status."""
    
    status: str = Field(description="Current status of wake word detection")
    is_listening: bool = Field(description="Whether the system is actively listening")
    message: str = Field(description="Human-readable status message")


class WakeWordDetectionEvent(BaseModel):
    """Model for wake word detection event data."""
    
    detected_at: str = Field(description="ISO format timestamp when wake word was detected")
    confidence: float = Field(description="Detection confidence score")
    audio_file: str = Field(description="Path to recorded command audio file")
    duration: float = Field(description="Duration of recorded command in seconds")


class WakeWordDetectResponse(BaseModel):
    """Response model for wake word detection and recording endpoint."""
    
    status: str = Field(description="Detection status: 'success' or 'error'")
    keyword: str = Field(description="Wake word that was detected")
    detection_time: float = Field(description="Time in seconds to detect wake word")
    frames_processed: int = Field(description="Total audio frames processed during detection")
    speech_frames: int = Field(description="Frames containing detected speech")
    audio_file: str = Field(description="Path to recorded command audio file")
    confidence: float = Field(description="Detection confidence score (0.0-1.0)")


# Week 2: Speaker Verification Models

class EnrollSpeakerRequest(BaseModel):
    """Request model for speaker enrollment."""
    
    user_id: str = Field(description="Unique identifier for the speaker")
    duration: Optional[float] = Field(
        default=5.0,
        description="Duration in seconds for voice sample recording",
        ge=3.0,
        le=15.0
    )
    
    @validator("user_id")
    def validate_user_id(cls, v):
        """Validate user ID format."""
        if not v or len(v.strip()) == 0:
            raise ValueError("User ID cannot be empty")
        if len(v) > 50:
            raise ValueError("User ID cannot exceed 50 characters")
        # Only allow alphanumeric characters, underscores, and hyphens
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("User ID can only contain letters, numbers, underscores, and hyphens")
        return v.strip()


class EnrollSpeakerResponse(BaseModel):
    """Response model for speaker enrollment."""
    
    status: str = Field(description="Status of the enrollment operation")
    message: str = Field(description="Human-readable message")
    user_id: str = Field(description="Enrolled user identifier")
    audio_file: str = Field(description="Path to enrollment audio file")
    embedding_size: int = Field(description="Size of generated voice embedding vector")
    voice_embedding: Optional[list[float]] = Field(
        default=None,
        description="The actual voice embedding as a list of floats (256D vector)"
    )
    timestamp: str = Field(description="ISO format timestamp of enrollment")


class ListSpeakersResponse(BaseModel):
    """Response model for listing enrolled speakers."""
    
    status: str = Field(description="Status of the operation")
    count: int = Field(description="Number of enrolled speakers")
    speakers: list[str] = Field(description="List of enrolled speaker user IDs")


class VerifySpeakerRequest(BaseModel):
    """Request model for speaker verification."""
    
    audio_file: str = Field(description="Path to audio file for verification")
    
    @validator("audio_file")
    def validate_audio_file(cls, v):
        """Validate audio file path."""
        if not v or len(v.strip()) == 0:
            raise ValueError("Audio file path cannot be empty")
        return v.strip()


class VerifySpeakerResponse(BaseModel):
    """Response model for speaker verification."""
    
    status: str = Field(description="Status of the verification operation")
    user_id: str = Field(description="Identified user ID or 'unknown' if not recognized")
    confidence: float = Field(description="Confidence score of the match")
    is_verified: bool = Field(description="Whether speaker was successfully verified")
    threshold: float = Field(description="Verification threshold used")
    timestamp: str = Field(description="ISO format timestamp of verification")
    access_token: Optional[str] = Field(default=None, description="Signed user session token")
    token_type: Optional[str] = None
    expires_in: Optional[int] = None


# Week 2: Speech-to-Text Models

class TranscribeRequest(BaseModel):
    """Request model for speech-to-text transcription."""
    
    audio_file: str = Field(description="Path to audio file for transcription")
    language: Optional[str] = Field(
        default="auto",
        description="Language code ('auto', 'en', 'ur') for transcription"
    )
    
    @validator("audio_file")
    def validate_audio_file(cls, v):
        """Validate audio file path."""
        if not v or len(v.strip()) == 0:
            raise ValueError("Audio file path cannot be empty")
        return v.strip()
    
    @validator("language")
    def validate_language(cls, v):
        """Validate language code."""
        allowed_languages = ["auto", "en", "ur"]
        if v not in allowed_languages:
            raise ValueError(f"Language must be one of {allowed_languages}")
        return v


class TranscribeResponse(BaseModel):
    """Response model for speech-to-text transcription."""
    
    status: str = Field(description="Status of the transcription operation")
    text: str = Field(description="Transcribed text from audio")
    language: str = Field(description="Detected or specified language code")
    duration: float = Field(description="Duration of audio file in seconds")
    success: bool = Field(description="Whether transcription was successful")
    confidence: Optional[float] = Field(default=None, description="Transcription confidence if available")
    timestamp: str = Field(description="ISO format timestamp of transcription")


# Week 2: Complete Processing Pipeline Model

class ProcessCommandRequest(BaseModel):
    """Request model for complete command processing pipeline."""
    
    audio_file: str = Field(description="Path to command audio file")
    verify_speaker: Optional[bool] = Field(
        default=True,
        description="Whether to perform speaker verification"
    )
    language: Optional[str] = Field(
        default="auto",
        description="Language for transcription"
    )


class ProcessCommandResponse(BaseModel):
    """Response model for complete command processing pipeline."""
    
    status: str = Field(description="Overall status of the operation")
    text: str = Field(description="Transcribed command text")
    language: str = Field(description="Detected language")
    user_id: Optional[str] = Field(default="unknown", description="Identified speaker user ID")
    speaker_confidence: Optional[float] = Field(default=0.0, description="Speaker verification confidence")
    is_verified: bool = Field(description="Whether speaker was verified")
    audio_file: str = Field(description="Path to processed audio file")
    duration: float = Field(description="Audio duration in seconds")
    timestamp: str = Field(description="ISO format timestamp of processing")
    success: bool = Field(description="Whether complete pipeline succeeded")

