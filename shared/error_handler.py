"""
Centralized Error Handling & Structured Logging
Purpose: No silent failures, all errors visible and testable

This is the FOUNDATION for Phase 1: System Truth & Observability
"""
# type: ignore

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from enum import Enum
from typing_extensions import Unpack
from typing_extensions import TypedDict  # For better Pylance support

# ==============================================================================
# ERROR CODES - Explicit, testable error states
# ==============================================================================

class ErrorCode(str, Enum):
    """Explicit error codes for all failure scenarios"""
    
    # Audio Service
    AUDIO_EMPTY = "AUDIO_001_EMPTY"
    AUDIO_INVALID_FORMAT = "AUDIO_002_INVALID_FORMAT"
    AUDIO_INVALID_SAMPLE_RATE = "AUDIO_003_INVALID_SAMPLE_RATE"
    AUDIO_PROCESSING_FAILED = "AUDIO_004_PROCESSING_FAILED"
    AUDIO_EMBEDDING_INVALID = "AUDIO_005_EMBEDDING_INVALID"  # Zero vector or wrong shape
    AUDIO_SERVICE_UNAVAILABLE = "AUDIO_006_SERVICE_UNAVAILABLE"
    
    # Vision Service
    VISION_NO_IMAGE = "VISION_001_NO_IMAGE"
    VISION_INVALID_FORMAT = "VISION_002_INVALID_FORMAT"
    VISION_PROCESSING_FAILED = "VISION_003_PROCESSING_FAILED"
    VISION_EMBEDDING_INVALID = "VISION_004_EMBEDDING_INVALID"
    VISION_SERVICE_UNAVAILABLE = "VISION_005_SERVICE_UNAVAILABLE"
    
    # Enrollment
    ENROLLMENT_DUPLICATE_USER = "ENROLLMENT_001_DUPLICATE_USER"
    ENROLLMENT_INVALID_INPUT = "ENROLLMENT_002_INVALID_INPUT"
    ENROLLMENT_INCOMPLETE = "ENROLLMENT_003_INCOMPLETE"
    ENROLLMENT_DATABASE_ERROR = "ENROLLMENT_004_DATABASE_ERROR"
    ENROLLMENT_RACE_CONDITION = "ENROLLMENT_005_RACE_CONDITION"
    
    # Database
    DB_CONNECTION_FAILED = "DB_001_CONNECTION_FAILED"
    DB_WRITE_FAILED = "DB_002_WRITE_FAILED"
    DB_READ_FAILED = "DB_003_READ_FAILED"
    DB_CORRUPT_DATA = "DB_004_CORRUPT_DATA"
    
    # Service Integration
    SERVICE_TIMEOUT = "SERVICE_001_TIMEOUT"
    SERVICE_UNAVAILABLE = "SERVICE_002_UNAVAILABLE"
    SERVICE_INVALID_RESPONSE = "SERVICE_003_INVALID_RESPONSE"
    
    # General
    INTERNAL_ERROR = "INTERNAL_001_INTERNAL_ERROR"


# ==============================================================================
# STRUCTURED ERROR OBJECT - What every error should look like
# ==============================================================================

class AppError(Exception):
    """
    Structured error that can be:
    - Logged
    - Returned as JSON
    - Tested programmatically
    """
    
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = 500,
        request_id: Optional[str] = None
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        self.status_code = status_code
        self.request_id = request_id or str(uuid.uuid4())
        self.timestamp = datetime.utcnow().isoformat()
        
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        return {
            "success": False,
            "error": {
                "code": self.code.value,
                "message": self.message,
                "details": self.details,
                "timestamp": self.timestamp,
                "request_id": self.request_id
            }
        }
    
    def to_http_response(self) -> tuple[Dict[str, Any], int]:
        """Convert to (JSON response, HTTP status code) for FastAPI"""
        return self.to_dict(), self.status_code


# ==============================================================================
# SUCCESS RESPONSE - Consistent format for all success cases
# ==============================================================================

class SuccessResponse:
    """Structured success response - consistent with error format"""
    
    def __init__(
        self,
        data: Any,
        message: str = "OK",
        request_id: Optional[str] = None
    ):
        self.data = data
        self.message = message
        self.request_id = request_id or str(uuid.uuid4())
        self.timestamp = datetime.utcnow().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        return {
            "success": True,
            "data": self.data,
            "message": self.message,
            "timestamp": self.timestamp,
            "request_id": self.request_id
        }


# ==============================================================================
# STRUCTURED LOGGER - All logs are machine-parseable
# ==============================================================================

class StructuredLogger:
    """
    Logging that captures context, request_id, severity
    Every log can be queried/analyzed programmatically
    """
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self._setup_logging()
    
    def _setup_logging(self):
        """Configure structured logging format"""
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s | %(name)s | %(levelname)s | %(message)s'
        )
        handler.setFormatter(formatter)
        if not self.logger.handlers:
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG)
    
    def info(
        self,
        message: str,
        request_id: Optional[str] = None,
        **context: Any
    ) -> None:
        """Log info with context"""
        ctx = f"[{request_id}]" if request_id else ""
        extra = f" | {json.dumps(context)}" if context else ""
        self.logger.info(f"{ctx} {message}{extra}")
    
    def error(
        self,
        message: str,
        error_code: Optional[ErrorCode] = None,
        request_id: Optional[str] = None,
        **context: Any
    ) -> None:
        """Log error with code and context"""
        ctx = f"[{request_id}]" if request_id else ""
        code = f"[{error_code.value}]" if error_code else ""
        extra = f" | {json.dumps(context)}" if context else ""
        self.logger.error(f"{ctx} {code} {message}{extra}")
    
    def warning(
        self,
        message: str,
        request_id: Optional[str] = None,
        **context: Any
    ) -> None:
        """Log warning with context"""
        ctx = f"[{request_id}]" if request_id else ""
        extra = f" | {json.dumps(context)}" if context else ""
        self.logger.warning(f"{ctx} {message}{extra}")
    
    def debug(
        self,
        message: str,
        request_id: Optional[str] = None,
        **context: Any
    ) -> None:
        """Log debug info"""
        ctx = f"[{request_id}]" if request_id else ""
        extra = f" | {json.dumps(context)}" if context else ""
        self.logger.debug(f"{ctx} {message}{extra}")


# ==============================================================================
# GLOBAL LOGGER INSTANCE
# ==============================================================================

logger = StructuredLogger("NeXiRobo")


# ==============================================================================
# VALIDATION HELPERS - Prevent silent failures from bad data
# ==============================================================================

class Validator:
    """Validation utilities that raise AppError (never silent)"""
    
    @staticmethod
    def require_non_empty(value: Any, field_name: str, request_id: str = None):
        """Raise if value is empty"""
        if not value:
            error = AppError(
                code=ErrorCode.ENROLLMENT_INVALID_INPUT,
                message=f"{field_name} cannot be empty",
                details={"field": field_name},
                status_code=400,
                request_id=request_id
            )
            logger.error(  # type: ignore
                f"Validation failed: {field_name} is empty",
                error_code=ErrorCode.ENROLLMENT_INVALID_INPUT,
                request_id=request_id
            )
            raise error
    
    @staticmethod
    def require_non_zero_embedding(
        embedding: list,
        embedding_name: str,
        request_id: str = None
    ):
        """Raise if embedding is all zeros or invalid"""
        if not embedding or len(embedding) == 0:
            error = AppError(
                code=ErrorCode.AUDIO_EMBEDDING_INVALID,
                message=f"{embedding_name} is empty",
                status_code=400,
                request_id=request_id
            )
            logger.error(  # type: ignore
                f"Embedding validation failed: {embedding_name} is empty",
                error_code=ErrorCode.AUDIO_EMBEDDING_INVALID,
                request_id=request_id
            )
            raise error
        
        # Check if all zeros (very unlikely for real embeddings)
        if all(x == 0.0 or x == 0 for x in embedding):
            error = AppError(
                code=ErrorCode.AUDIO_EMBEDDING_INVALID,
                message=f"{embedding_name} is all zeros (invalid embedding)",
                details={"embedding_length": len(embedding)},
                status_code=400,
                request_id=request_id
            )
            logger.error(  # type: ignore
                f"Embedding validation failed: {embedding_name} is all zeros",
                error_code=ErrorCode.AUDIO_EMBEDDING_INVALID,
                request_id=request_id,
                embedding_length=len(embedding)
            )
            raise error
    
    @staticmethod
    def require_valid_shape(
        data: list,
        expected_length: int,
        data_name: str,
        request_id: str = None
    ):
        """Raise if shape doesn't match"""
        if len(data) != expected_length:
            error = AppError(
                code=ErrorCode.SERVICE_INVALID_RESPONSE,
                message=f"{data_name} has invalid shape",
                details={
                    "expected": expected_length,
                    "actual": len(data)
                },
                status_code=400,
                request_id=request_id
            )
            logger.error(  # type: ignore
                f"{data_name} shape mismatch",
                error_code=ErrorCode.SERVICE_INVALID_RESPONSE,
                request_id=request_id,
                expected=expected_length,
                actual=len(data)
            )
            raise error


# ==============================================================================
# REQUEST ID CONTEXT - For correlation across services
# ==============================================================================

import threading

_request_id_context = threading.local()

def set_request_id(request_id: str):
    """Store request ID in thread-local context"""
    _request_id_context.value = request_id

def get_request_id() -> str:
    """Get current request ID (or generate new one)"""
    if not hasattr(_request_id_context, 'value') or not _request_id_context.value:
        _request_id_context.value = str(uuid.uuid4())
    return _request_id_context.value

def clear_request_id():
    """Clear request ID after request completes"""
    if hasattr(_request_id_context, 'value'):
        _request_id_context.value = None
