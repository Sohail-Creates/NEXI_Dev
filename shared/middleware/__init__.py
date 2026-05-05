"""Middleware and request handlers."""

from shared.middleware.error_handler import global_exception_handler

__all__ = ["global_exception_handler"]
