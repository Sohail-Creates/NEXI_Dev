"""
Central Server Data Models

All Pydantic models for request/response validation.
"""

from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class WakewordRecord(BaseModel):
    """Wake word configuration for a user."""
    phrase: str
    wake_word_id: Optional[str] = None
    stage: Optional[int] = None
    last_trained_at: Optional[str] = None


class User(BaseModel):
    """User profile with biometric data."""
    user_id: Optional[str] = None
    name: str
    face_embeddings: List[List[float]]
    voice_embeddings: List[List[float]]
    age: Optional[int] = None
    relation: Optional[str] = None
    avg_face_confidence: Optional[float] = None
    avg_voice_quality: Optional[float] = None
    enrollment_timestamp: Optional[str] = None
    voice_preference: Optional[str] = None
    wake_word: Optional[WakewordRecord] = None


class LearnedObject(BaseModel):
    """Learned object in the environment."""
    name: str


class KnownFace(BaseModel):
    """Face embedding record."""
    name: str
    embedding: List[float]


class KnowledgeItem(BaseModel):
    """Knowledge base entry."""
    question: str
    answer: str
    tags: List[str] = []


class VisionEvent(BaseModel):
    """Vision service event (frame capture)."""
    frame_b64: str


class VisionAction(BaseModel):
    """Action to take based on vision analysis."""
    action: str
    payload: Dict[str, Any] = {}


class AudioEvent(BaseModel):
    """Audio service event (transcribed text)."""
    text: str


class AdminLoginRequest(BaseModel):
    """Admin login credentials."""
    username: str
    password: str


class AdminLoginResponse(BaseModel):
    """Admin login response with token."""
    token: str
    username: str
    expires_at: str


class WakewordUpdatePayload(BaseModel):
    """Request to update user wake word."""
    name: str
    wake_word: Optional[WakewordRecord] = None


class VoicePreferenceUpdate(BaseModel):
    """Request to update user voice preference."""
    name: str
    voice_id: Optional[str] = None


class VoicePreferencePayload(BaseModel):
    """Voice preference update payload."""
    voice_id: Optional[str] = None


class VoicePreviewRequest(BaseModel):
    """Request to preview voice."""
    voice_id: str
    text: Optional[str] = None


class HealthCheckResponse(BaseModel):
    """Health check response."""
    status: str
    service: Optional[str] = None
    version: Optional[str] = None


class SystemStatusResponse(BaseModel):
    """System status response."""
    status: str
    timestamp: str
    uptime_seconds: float
    services: Dict[str, Any] = {}
    users_count: int = 0
    objects_count: int = 0


class ServiceStatusResponse(BaseModel):
    """Individual service status."""
    service: str
    status: str
    last_check: str
    response_time_ms: float = 0
