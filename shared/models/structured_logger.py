"""
Structured Logging with Correlation IDs

Every request gets a unique trace ID.
Every error is correlated to a request.
Every log message includes context.
"""

import logging
import uuid
from typing import Any, Dict, Optional
from contextvars import ContextVar

# Context variable to store trace ID per request
trace_context: ContextVar[str] = ContextVar('trace_id', default='')


class CorrelationIDFilter(logging.Filter):
    """Add trace ID to all log records"""
    
    def filter(self, record: logging.LogRecord) -> bool:
        trace_id = trace_context.get()
        record.trace_id = trace_id or 'no-trace'
        return True


class StructuredLogger:
    """Logger with correlation ID and structured context"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.addFilter(CorrelationIDFilter())
    
    def set_trace_id(self, trace_id: str):
        """Set the current trace ID"""
        trace_context.set(trace_id)
    
    def get_trace_id(self) -> str:
        """Get the current trace ID"""
        return trace_context.get()
    
    def generate_trace_id(self) -> str:
        """Generate and set a new trace ID"""
        trace_id = str(uuid.uuid4())[:8]
        self.set_trace_id(trace_id)
        return trace_id
    
    def info(self, message: str, **context):
        """Log info with context"""
        self.logger.info(f"{message} | context={context}")
    
    def error(self, message: str, error_code: Optional[str] = None, **context):
        """Log error with code and context"""
        trace_id = self.get_trace_id()
        self.logger.error(
            f"{message} | error_code={error_code} | trace_id={trace_id} | context={context}"
        )
    
    def debug(self, message: str, **context):
        """Log debug with context"""
        self.logger.debug(f"{message} | context={context}")
    
    def warning(self, message: str, **context):
        """Log warning with context"""
        self.logger.warning(f"{message} | context={context}")


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger"""
    return StructuredLogger(name)


def setup_logging(level: str = 'INFO'):
    """Setup structured logging for all services"""
    
    formatter = logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)s | %(trace_id)s | %(message)s'
    )
    
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    
    root = logging.getLogger()
    root.setLevel(getattr(logging, level))
    root.addHandler(handler)
