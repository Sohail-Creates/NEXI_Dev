"""
Unified API response models using Pydantic.
Ensures consistent response format across all services.
"""

from typing import Any, Optional, Generic, TypeVar
from pydantic import BaseModel, Field
from datetime import datetime


T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """Standard API response wrapper."""

    status: str = Field(..., description="Status: success, error, etc.")
    data: Optional[T] = Field(None, description="Response data")
    message: Optional[str] = Field(None, description="Additional message")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")
    request_id: Optional[str] = Field(None, description="Request tracking ID")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "data": {"key": "value"},
                "message": "Operation completed",
                "timestamp": "2024-01-01T00:00:00",
                "request_id": "req-123",
            }
        }


class ErrorResponse(BaseModel):
    """Standard error response format."""

    status: str = Field(default="error", description="Always 'error'")
    error: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    details: Optional[dict] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")
    request_id: Optional[str] = Field(None, description="Request tracking ID")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "error",
                "error": "VALIDATION_ERROR",
                "message": "Invalid request parameters",
                "details": {"field": "email", "reason": "invalid format"},
                "timestamp": "2024-01-01T00:00:00",
                "request_id": "req-123",
            }
        }


class HealthStatus(BaseModel):
    """Health check response model."""

    status: str = Field(..., description="healthy, degraded, unhealthy")
    service: str = Field(..., description="Service name")
    version: Optional[str] = Field(None, description="Service version")
    dependencies: Optional[dict[str, str]] = Field(None, description="Dependency statuses")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "service": "central_server",
                "version": "1.0.0",
                "dependencies": {"audio_service": "healthy", "database": "healthy"},
                "timestamp": "2024-01-01T00:00:00",
            }
        }
