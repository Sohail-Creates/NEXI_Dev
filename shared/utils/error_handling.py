"""
Unified error handling for all services.
Provides consistent exception hierarchy and HTTP status codes.
"""

from typing import Any, Optional
from enum import Enum


class ErrorCode(str, Enum):
    """Standard error codes for all services."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    SERVICE_TIMEOUT = "SERVICE_TIMEOUT"
    CIRCUIT_BREAKER_OPEN = "CIRCUIT_BREAKER_OPEN"
    DATABASE_ERROR = "DATABASE_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class APIError(Exception):
    """Base exception for all API errors."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        status_code: int = 500,
        details: Optional[dict] = None,
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict:
        """Convert error to dictionary."""
        return {
            "error": self.error_code.value,
            "message": self.message,
            "details": self.details,
        }


class ValidationError(APIError):
    """Raised when request validation fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=422,
            details=details,
        )


class ServiceUnavailableError(APIError):
    """Raised when a dependent service is unavailable."""

    def __init__(
        self,
        service_name: str,
        message: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        msg = message or f"{service_name} service is currently unavailable"
        super().__init__(
            message=msg,
            error_code=ErrorCode.SERVICE_UNAVAILABLE,
            status_code=503,
            details={**(details or {}), "service": service_name},
        )


class ServiceTimeoutError(APIError):
    """Raised when a service request times out."""

    def __init__(
        self,
        service_name: str,
        timeout_seconds: int,
        details: Optional[dict] = None,
    ):
        super().__init__(
            message=f"{service_name} request timed out after {timeout_seconds}s",
            error_code=ErrorCode.SERVICE_TIMEOUT,
            status_code=504,
            details={**(details or {}), "service": service_name, "timeout_seconds": timeout_seconds},
        )


class CircuitBreakerOpenError(APIError):
    """Raised when circuit breaker is open."""

    def __init__(
        self,
        service_name: str,
        recovery_time: Optional[int] = None,
        details: Optional[dict] = None,
    ):
        msg = f"Circuit breaker open for {service_name}"
        if recovery_time:
            msg += f" - will retry in {recovery_time}s"
        super().__init__(
            message=msg,
            error_code=ErrorCode.CIRCUIT_BREAKER_OPEN,
            status_code=429,
            details={
                **(details or {}),
                "service": service_name,
                "recovery_time_seconds": recovery_time,
            },
        )


class DataPersistenceError(APIError):
    """Raised when database/persistence operations fail."""

    def __init__(
        self,
        message: str,
        operation: str = "unknown",
        details: Optional[dict] = None,
    ):
        super().__init__(
            message=message,
            error_code=ErrorCode.DATABASE_ERROR,
            status_code=500,
            details={**(details or {}), "operation": operation},
        )


class ConfigurationError(APIError):
    """Raised when configuration is invalid."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.CONFIGURATION_ERROR,
            status_code=500,
            details=details,
        )


class NotFoundError(APIError):
    """Raised when resource is not found."""

    def __init__(
        self,
        resource_type: str,
        resource_id: Any,
        details: Optional[dict] = None,
    ):
        super().__init__(
            message=f"{resource_type} with ID {resource_id} not found",
            error_code=ErrorCode.NOT_FOUND,
            status_code=404,
            details={**(details or {}), "resource_type": resource_type, "resource_id": str(resource_id)},
        )


class AuthenticationError(APIError):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Authentication failed", details: Optional[dict] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.AUTHENTICATION_ERROR,
            status_code=401,
            details=details,
        )


class AuthorizationError(APIError):
    """Raised when user lacks authorization."""

    def __init__(self, message: str = "Insufficient permissions", details: Optional[dict] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.AUTHORIZATION_ERROR,
            status_code=403,
            details=details,
        )
