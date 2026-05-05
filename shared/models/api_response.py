"""
Unified API Response Contract

All services must return responses conforming to this contract.
This ensures predictable, observable, auditable behavior.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from enum import Enum


class ErrorCode(str, Enum):
    """Standardized error codes across all services"""
    
    # Validation errors (4xx)
    INVALID_INPUT = "INVALID_INPUT"
    INVALID_AUDIO = "INVALID_AUDIO"
    INVALID_IMAGE = "INVALID_IMAGE"
    MISSING_FIELD = "MISSING_FIELD"
    
    # Resource errors (4xx)
    USER_NOT_FOUND = "USER_NOT_FOUND"
    USER_ALREADY_EXISTS = "USER_ALREADY_EXISTS"
    ENROLLMENT_NOT_FOUND = "ENROLLMENT_NOT_FOUND"
    
    # Rate limiting (4xx)
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    
    # Processing errors (5xx)
    PROCESSING_FAILED = "PROCESSING_FAILED"
    MODEL_LOADING_FAILED = "MODEL_LOADING_FAILED"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    
    # Service errors (5xx)
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    SERVICE_TIMEOUT = "SERVICE_TIMEOUT"
    SERVICE_ERROR = "SERVICE_ERROR"
    
    # Storage errors (5xx)
    STORAGE_ERROR = "STORAGE_ERROR"
    PERSISTENCE_FAILED = "PERSISTENCE_FAILED"


class ErrorDetail(BaseModel):
    """Error information with context"""
    code: ErrorCode
    message: str
    details: Optional[Dict[str, Any]] = None
    trace_id: Optional[str] = None


class SuccessData(BaseModel):
    """Wrapper for successful response data"""
    pass


class APIResponse(BaseModel):
    """
    Unified response contract.
    
    RULE: Either `data` is set (success=True) OR `error` is set (success=False).
    Never both. Never neither.
    """
    
    success: bool = Field(..., description="True if operation succeeded")
    data: Optional[Any] = Field(None, description="Response data (only if success=True)")
    error: Optional[ErrorDetail] = Field(None, description="Error detail (only if success=False)")
    
    def __init__(self, **data):
        super().__init__(**data)
        # Enforce contract
        if self.success:
            if self.error is not None:
                raise ValueError("success=True but error is not None")
            if self.data is None:
                raise ValueError("success=True but data is None")
        else:
            if self.error is None:
                raise ValueError("success=False but error is None")
            if self.data is not None:
                raise ValueError("success=False but data is not None")


def success_response(data: Any, trace_id: Optional[str] = None) -> APIResponse:
    """Create a successful response"""
    return APIResponse(
        success=True,
        data=data,
        error=None
    )


def error_response(
    code: ErrorCode,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    trace_id: Optional[str] = None
) -> APIResponse:
    """Create an error response"""
    return APIResponse(
        success=False,
        data=None,
        error=ErrorDetail(
            code=code,
            message=message,
            details=details,
            trace_id=trace_id
        )
    )
