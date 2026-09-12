"""
Trace Context - Propagate trace IDs across services for request tracking.

This module provides contextvars-based trace ID tracking that works across
async boundaries, allowing requests to be tracked from Central Server
through Vision/Audio/Enrollment services.

FEATURE #8: TRACE PROPAGATION
- Creates unique trace_id per request
- Propagates via asyncio.contextvars (async-safe)
- Added to all log records automatically
- Passed to downstream services via HTTP headers
"""

import contextvars
import logging
import uuid
from typing import Optional
from contextlib import contextmanager
import asyncio


# Context variable for trace ID (async-safe)
trace_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'trace_id', default=None
)


def generate_trace_id() -> str:
    """Generate unique trace ID for request tracking."""
    return f"trace-{uuid.uuid4().hex[:16]}"


def get_trace_id() -> Optional[str]:
    """Get current trace ID from context."""
    return trace_id_context.get()


def set_trace_id(trace_id: str) -> None:
    """Set trace ID in context."""
    trace_id_context.set(trace_id)


@contextmanager
def trace_scope(trace_id: Optional[str] = None):
    """
    Context manager for trace ID scope.
    
    Usage:
        with trace_scope("trace-abc123"):
            logger.info("This log includes trace ID")
    
    Args:
        trace_id: Optional trace ID to set. If None, generates new one.
    
    Yields:
        The trace ID being used
    """
    if trace_id is None:
        trace_id = generate_trace_id()
    
    # Save previous trace ID (for nested contexts)
    token = trace_id_context.set(trace_id)
    
    try:
        yield trace_id
    finally:
        # Restore previous trace ID
        trace_id_context.reset(token)


class TraceLoggingFilter(logging.Filter):
    """
    Logging filter that adds trace_id to log records.
    
    Must be added to handlers:
        filter = TraceLoggingFilter()
        handler.addFilter(filter)
    """
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Add trace_id to log record."""
        trace_id = get_trace_id()
        record.trace_id = trace_id or "no-trace"
        return True


def setup_trace_logging() -> None:
    """
    Configure logging to include trace IDs in all output.
    
    Call this during application startup to enable trace logging.
    """
    root_logger = logging.getLogger()
    trace_filter = TraceLoggingFilter()
    
    for handler in root_logger.handlers:
        handler.addFilter(trace_filter)
    
    # Update formatting to include trace_id
    for handler in root_logger.handlers:
        if hasattr(handler, 'formatter') and handler.formatter:
            current_format = handler.formatter._fmt
            # Add trace_id if not already present
            if '%(trace_id)s' not in current_format:
                new_format = current_format.replace(
                    '%(name)s',
                    '%(trace_id)s:%(name)s'
                )
                handler.formatter._fmt = new_format


async def async_trace_scope(trace_id: Optional[str] = None):
    """
    Async context manager for trace ID scope.
    
    Usage:
        async with async_trace_scope("trace-abc123"):
            await some_async_operation()  # Has trace context
    
    Args:
        trace_id: Optional trace ID. If None, generates new one.
    
    Yields:
        The trace ID being used
    """
    if trace_id is None:
        trace_id = generate_trace_id()
    
    token = trace_id_context.set(trace_id)
    
    try:
        yield trace_id
    finally:
        trace_id_context.reset(token)


class TraceContextMiddleware:
    """
    FastAPI middleware that:
    1. Extracts trace ID from request headers (X-Trace-ID)
    2. Generates new trace ID if not present
    3. Sets it in context for duration of request
    4. Returns trace ID in response headers
    """
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # Get or generate trace ID
        headers = dict(scope.get("headers", []))
        trace_id = None
        
        # Look for trace ID in various header formats
        if b"x-trace-id" in headers:
            trace_id = headers[b"x-trace-id"].decode()
        elif b"trace-id" in headers:
            trace_id = headers[b"trace-id"].decode()
        
        # Generate if not found
        if not trace_id:
            trace_id = generate_trace_id()
        
        # Set in context for this request
        token = trace_id_context.set(trace_id)
        
        async def send_with_trace(message):
            """Wrapper to add trace ID to response headers."""
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                # Add trace ID to response
                headers.append((b"x-trace-id", trace_id.encode()))
                message["headers"] = headers
            
            await send(message)
        
        try:
            await self.app(scope, receive, send_with_trace)
        finally:
            # Clear trace context
            trace_id_context.reset(token)


def get_trace_headers() -> dict:
    """
    Get headers dict with current trace ID for downstream requests.
    
    Usage:
        headers = get_trace_headers()
        async with session.get(url, headers=headers) as resp:
            ...
    
    Returns:
        Dictionary with the shared X-Correlation-ID header
    """
    trace_id = get_trace_id()
    if trace_id:
        return {"X-Correlation-ID": trace_id}
    return {}


# Version info
__version__ = "1.0.0"
__trace_feature__ = "FEATURE #8: Trace Propagation"
