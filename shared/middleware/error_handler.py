"""
Global error handler middleware for FastAPI.
Provides consistent error response format across all endpoints.
"""

import logging
from typing import Union

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from shared.utils.error_handling import APIError
from shared.models.api_models import ErrorResponse

logger = logging.getLogger(__name__)


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle exceptions and return consistent error response."""

    # Handle APIError (our custom exceptions)
    if isinstance(exc, APIError):
        error_response = ErrorResponse(
            error=exc.error_code.value,
            message=exc.message,
            details=exc.details,
            request_id=getattr(request.state, "request_id", None),
        )
        logger.warning(
            f"API Error: {exc.error_code.value} - {exc.message}",
            extra={"details": exc.details},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response.model_dump(),
        )

    # Handle generic exceptions
    logger.error(
        f"Unhandled exception: {type(exc).__name__}: {str(exc)}",
        exc_info=True,
    )

    error_response = ErrorResponse(
        error="INTERNAL_ERROR",
        message="An internal server error occurred",
        details={"type": type(exc).__name__} if logger.level == logging.DEBUG else None,
        request_id=getattr(request.state, "request_id", None),
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.model_dump(),
    )


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Middleware for global error handling."""

    async def dispatch(self, request: Request, call_next):
        """Process request and handle errors."""
        try:
            return await call_next(request)
        except Exception as exc:
            return await global_exception_handler(request, exc)
