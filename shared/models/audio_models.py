"""
Unified Audio Service Models for all services.
Single source of truth for audio-related data structures.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class AudioFile(BaseModel):
    """Represents an uploaded audio file."""

    id: str = Field(..., description="Unique file ID")
    filename: str = Field(..., description="Original filename")
    size_bytes: int = Field(..., ge=0, description="File size in bytes")
    duration_seconds: float = Field(..., ge=0)
    format: str = Field(..., description="Audio format (wav, mp3, etc.)")
    sample_rate: int = Field(default=16000, description="Sample rate in Hz")
    channels: int = Field(default=1, description="Number of audio channels")
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    uploader_id: Optional[str] = None
    purpose: str = Field(default="processing", description="Why file was uploaded")
    is_processed: bool = False
    metadata: Optional[Dict[str, Any]] = None


class Transcription(BaseModel):
    """Audio transcription result."""

    id: str = Field(..., description="Unique transcription ID")
    audio_file_id: str = Field(..., description="Source audio file ID")
    text: str = Field(..., description="Transcribed text")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    language: str = Field(default="en", description="Detected language")
    duration_seconds: float = Field(..., ge=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    model_used: Optional[str] = None


class SpeakerEmbedding(BaseModel):
    """Speaker embedding for voice verification."""

    id: str = Field(..., description="Unique embedding ID")
    speaker_id: str = Field(..., description="Speaker ID")
    audio_file_id: str = Field(..., description="Source audio file ID")
    embedding_vector: List[float] = Field(..., description="Embedding vector")
    model_version: str = Field(default="1.0")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    quality_score: Optional[float] = Field(None, ge=0.0, le=1.0)


class AudioQualityAnalysis(BaseModel):
    """Audio quality metrics and analysis."""

    file_id: str = Field(..., description="Audio file ID")
    signal_noise_ratio_db: Optional[float] = None
    loudness_lufs: Optional[float] = None
    clipping_detected: bool = False
    silence_percentage: float = Field(default=0.0, ge=0.0, le=100.0)
    noise_level: Optional[float] = None
    overall_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    recommendations: List[str] = Field(default_factory=list)
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)


class ProcessingJob(BaseModel):
    """Audio processing job tracker."""

    id: str = Field(..., description="Unique job ID")
    audio_file_id: str = Field(..., description="File being processed")
    job_type: str = Field(..., description="Type of processing: transcription, embedding, etc.")
    status: str = Field(..., description="queued, processing, completed, failed")
    progress_percentage: int = Field(default=0, ge=0, le=100)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


class WakeWordDetectionResult(BaseModel):
    """Wake word detection result."""

    file_id: str = Field(..., description="Audio file ID")
    wake_word: str = Field(..., description="Detected wake word")
    confidence: float = Field(..., ge=0.0, le=1.0)
    timestamp_seconds: float = Field(..., ge=0)
    audio_segment: Optional[tuple[float, float]] = None
    detected_at: datetime = Field(default_factory=datetime.utcnow)


class VADSegment(BaseModel):
    """Voice Activity Detection segment."""

    start_time_seconds: float = Field(..., ge=0)
    end_time_seconds: float = Field(..., gt=0)
    is_speech: bool = Field(..., description="True if segment contains speech")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class AudioFeatures(BaseModel):
    """Extracted audio features."""

    file_id: str = Field(..., description="Audio file ID")
    mfcc: Optional[List[List[float]]] = None
    spectral_centroid: Optional[List[float]] = None
    zero_crossing_rate: Optional[List[float]] = None
    rms_energy: Optional[List[float]] = None
    chroma_features: Optional[List[List[float]]] = None
    extracted_at: datetime = Field(default_factory=datetime.utcnow)


class LanguageDetectionResult(BaseModel):
    """Language detection result."""

    file_id: str = Field(..., description="Audio file ID")
    detected_language: str = Field(..., description="ISO 639-1 language code")
    confidence: float = Field(..., ge=0.0, le=1.0)
    alternatives: List[Dict[str, float]] = Field(default_factory=list)
    detected_at: datetime = Field(default_factory=datetime.utcnow)
