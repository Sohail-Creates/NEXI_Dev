"""
Unified User and Enrollment Models for all services.
Single source of truth for user-related data structures.
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr


class VoiceProfile(BaseModel):
    """User's voice profile for speaker verification."""

    speaker_id: str = Field(..., description="Unique speaker ID")
    enrollment_phrase: str = Field(..., description="Phrase used for enrollment")
    num_samples_collected: int = Field(default=0, ge=0)
    embedding_vector: Optional[List[float]] = Field(
        None, description="Voice embedding vector"
    )
    quality_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_verified_at: Optional[datetime] = None
    is_active: bool = True


class EnrollmentStatus(BaseModel):
    """Enrollment status for a user."""

    user_id: str = Field(..., description="User ID")
    status: str = Field(..., description="not_started, in_progress, completed, failed")
    completion_percentage: int = Field(default=0, ge=0, le=100)
    samples_collected: int = Field(default=0)
    required_samples: int = Field(default=3)
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None


class User(BaseModel):
    """Core user model."""

    id: str = Field(..., description="Unique user ID")
    username: str = Field(..., description="Username")
    email: EmailStr = Field(..., description="User email")
    full_name: Optional[str] = None
    is_active: bool = True
    voice_profile: Optional[VoiceProfile] = None
    enrollment_status: Optional[EnrollmentStatus] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "id": "user-123",
                "username": "john_doe",
                "email": "john@example.com",
                "full_name": "John Doe",
                "is_active": True,
            }
        }


class UserCreate(BaseModel):
    """Request model for user creation."""

    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: Optional[str] = None
    password: Optional[str] = None


class UserUpdate(BaseModel):
    """Request model for user update."""

    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None


class UserListResponse(BaseModel):
    """Response model for listing users."""

    users: List[User]
    total_count: int
    page: int = 1
    page_size: int = 50


class EnrollmentRequest(BaseModel):
    """Request model for user enrollment with voice."""

    user_id: str = Field(..., description="User to enroll")
    audio_file_ids: List[str] = Field(..., description="List of audio file IDs")
    enrollment_phrase: str = Field(
        default="my voice is my password",
        description="Phrase to speak for enrollment",
    )


class EnrollmentResponse(BaseModel):
    """Response model for enrollment result."""

    user_id: str
    status: str
    message: str
    embedding_vector: Optional[List[float]] = None
    quality_score: Optional[float] = None
