"""
Error handler utilities for consistent error tracking and decoration.
Provides decorator and singleton error handler across all services.
"""

import logging
import functools
import asyncio
from typing import Optional, Callable, Any, TypeVar
from datetime import datetime


logger = logging.getLogger(__name__)


class ErrorHandler:
    """Centralized error tracking and logging."""

    def __init__(self):
        self.errors: list = []
        self.logger = logging.getLogger("ErrorHandler")

    def log_error(
        self,
        exception: Exception,
        context: str,
        level: str = "ERROR",
        **kwargs
    ) -> None:
        """Log an error with context."""
        error_record = {
            "timestamp": datetime.now().isoformat(),
            "exception_type": type(exception).__name__,
            "message": str(exception),
            "context": context,
            "level": level,
            "details": kwargs
        }
        self.errors.append(error_record)
        
        log_method = getattr(self.logger, level.lower(), self.logger.error)
        log_method(
            f"[{context}] {type(exception).__name__}: {str(exception)}",
            extra=kwargs
        )

    def get_recent_errors(self, count: int = 10) -> list:
        """Get recent errors."""
        return self.errors[-count:]

    def clear_errors(self) -> None:
        """Clear error history."""
        self.errors.clear()


# Singleton instance
_error_handler_instance: Optional[ErrorHandler] = None


def get_error_handler() -> ErrorHandler:
    """Get or create the singleton error handler instance."""
    global _error_handler_instance
    if _error_handler_instance is None:
        _error_handler_instance = ErrorHandler()
    return _error_handler_instance


def handle_errors(
    default_return: Any = None,
    service_name: str = "unknown",
    log_level: str = "ERROR"
) -> Callable:
    """
    Decorator for async functions that handles errors consistently.
    
    Usage:
        @handle_errors(service_name="audio_service")
        async def process_audio():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                error_handler = get_error_handler()
                error_handler.log_error(
                    e,
                    f"{service_name}.{func.__name__}",
                    level=log_level
                )
                return default_return

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_handler = get_error_handler()
                error_handler.log_error(
                    e,
                    f"{service_name}.{func.__name__}",
                    level=log_level
                )
                return default_return

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
