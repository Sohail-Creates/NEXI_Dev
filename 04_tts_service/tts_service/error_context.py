"""
PHASE 3.2: Enhanced Error Context Logging
Track, log, and analyze errors with full context for debugging and monitoring.
"""

import logging
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum


class ErrorSeverity(Enum):
    """Error severity levels for classification."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Categorized error types."""
    VALIDATION = "validation"           # Input validation errors
    SYNTHESIS = "synthesis"             # TTS synthesis failures
    TIMEOUT = "timeout"                 # Request timeouts
    RESOURCE = "resource"               # Resource exhaustion
    CONFIGURATION = "configuration"     # Config errors
    WORKER = "worker"                   # Worker pool errors
    UNKNOWN = "unknown"                 # Uncategorized errors


@dataclass
class ErrorContext:
    """Structured error context for detailed logging."""
    request_id: str
    timestamp: float
    error_type: str
    error_message: str
    error_severity: ErrorSeverity = ErrorSeverity.ERROR
    category: ErrorCategory = ErrorCategory.UNKNOWN
    
    # Request context
    voice_id: Optional[str] = None
    text_length: Optional[int] = None
    language_hint: Optional[str] = None
    
    # Error context
    traceback: Optional[str] = None
    status_code: Optional[int] = None
    response_time_ms: Optional[float] = None
    
    # Recovery context
    retry_count: int = 0
    can_retry: bool = True
    recovery_action: Optional[str] = None
    
    # Metadata
    worker_id: Optional[str] = None
    cache_hit: Optional[bool] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON logging."""
        return {
            "request_id": self.request_id,
            "timestamp": self.timestamp,
            "datetime": datetime.fromtimestamp(self.timestamp).isoformat(),
            "error_type": self.error_type,
            "error_message": self.error_message,
            "severity": self.error_severity.value,
            "category": self.category.value,
            "voice_id": self.voice_id,
            "text_length": self.text_length,
            "language_hint": self.language_hint,
            "traceback": self.traceback,
            "status_code": self.status_code,
            "response_time_ms": self.response_time_ms,
            "retry_count": self.retry_count,
            "can_retry": self.can_retry,
            "recovery_action": self.recovery_action,
            "worker_id": self.worker_id,
            "cache_hit": self.cache_hit,
        }


class ErrorContextLogger:
    """
    High-performance error context logger with persistent history.
    PHASE 3.2: Tracks errors for debugging and observability.
    """
    
    def __init__(self, max_history: int = 1000):
        """
        Initialize error context logger.
        Args:
            max_history: Maximum error records to keep in memory
        """
        self.max_history = max_history
        self.error_history: List[ErrorContext] = []
        self.error_counts: Dict[str, int] = {}
        self.category_counts: Dict[ErrorCategory, int] = {}
        self.lock = threading.RLock()
        self.logger = logging.getLogger("nexi.tts.errors")
    
    def log_error(self, context: ErrorContext) -> None:
        """Log error with full context."""
        with self.lock:
            # Add to history
            self.error_history.append(context)
            if len(self.error_history) > self.max_history:
                self.error_history.pop(0)  # Remove oldest
            
            # Update counters
            self.error_counts[context.error_type] = \
                self.error_counts.get(context.error_type, 0) + 1
            self.category_counts[context.category] = \
                self.category_counts.get(context.category, 0) + 1
        
        # Log with appropriate level
        level_map = {
            ErrorSeverity.INFO: logging.INFO,
            ErrorSeverity.WARNING: logging.WARNING,
            ErrorSeverity.ERROR: logging.ERROR,
            ErrorSeverity.CRITICAL: logging.CRITICAL,
        }
        
        log_level = level_map.get(context.error_severity, logging.ERROR)
        
        self.logger.log(
            log_level,
            "[%(request_id)s] %(category)s error: %(error_type)s - %(error_message)s "
            "(voice=%(voice_id)s, text_len=%(text_length)s, retry_count=%(retry_count)d, "
            "response_time=%(response_time_ms)s ms)",
            context.to_dict()
        )
        
        # Log traceback if available
        if context.traceback:
            self.logger.debug("[%s] Traceback:\n%s", context.request_id, context.traceback)
    
    def log_validation_error(self, request_id: str, message: str, 
                            voice_id: Optional[str] = None, 
                            text_length: Optional[int] = None) -> None:
        """Log input validation error."""
        context = ErrorContext(
            request_id=request_id,
            timestamp=time.time(),
            error_type="ValidationError",
            error_message=message,
            error_severity=ErrorSeverity.WARNING,
            category=ErrorCategory.VALIDATION,
            voice_id=voice_id,
            text_length=text_length,
            status_code=400,
            can_retry=False,  # Validation errors shouldn't be retried
        )
        self.log_error(context)
    
    def log_synthesis_error(self, request_id: str, message: str, traceback: str,
                           voice_id: Optional[str] = None, 
                           text_length: Optional[int] = None,
                           response_time_ms: Optional[float] = None,
                           retry_count: int = 0) -> None:
        """Log synthesis error with traceback."""
        context = ErrorContext(
            request_id=request_id,
            timestamp=time.time(),
            error_type="SynthesisError",
            error_message=message,
            error_severity=ErrorSeverity.ERROR,
            category=ErrorCategory.SYNTHESIS,
            voice_id=voice_id,
            text_length=text_length,
            traceback=traceback,
            status_code=500,
            response_time_ms=response_time_ms,
            retry_count=retry_count,
            can_retry=True,
        )
        self.log_error(context)
    
    def log_timeout_error(self, request_id: str, timeout_seconds: float,
                         voice_id: Optional[str] = None,
                         text_length: Optional[int] = None) -> None:
        """Log timeout error."""
        context = ErrorContext(
            request_id=request_id,
            timestamp=time.time(),
            error_type="TimeoutError",
            error_message=f"Request timeout after {timeout_seconds}s",
            error_severity=ErrorSeverity.WARNING,
            category=ErrorCategory.TIMEOUT,
            voice_id=voice_id,
            text_length=text_length,
            status_code=504,
            can_retry=True,
            recovery_action="retry with increased timeout",
        )
        self.log_error(context)
    
    def log_worker_error(self, request_id: str, message: str, worker_id: str,
                        traceback: Optional[str] = None) -> None:
        """Log worker pool error."""
        context = ErrorContext(
            request_id=request_id,
            timestamp=time.time(),
            error_type="WorkerError",
            error_message=message,
            error_severity=ErrorSeverity.ERROR,
            category=ErrorCategory.WORKER,
            traceback=traceback,
            status_code=503,
            worker_id=worker_id,
            can_retry=True,
            recovery_action="fallback to primary worker",
        )
        self.log_error(context)
    
    def get_recent_errors(self, limit: int = 20) -> List[Dict]:
        """Get recent errors."""
        with self.lock:
            return [e.to_dict() for e in self.error_history[-limit:]]
    
    def get_errors_by_category(self, category: ErrorCategory) -> List[Dict]:
        """Get all errors of a specific category."""
        with self.lock:
            return [e.to_dict() for e in self.error_history 
                   if e.category == category]
    
    def get_error_stats(self) -> Dict:
        """Get error statistics and summary."""
        with self.lock:
            total_errors = len(self.error_history)
            critical_count = sum(1 for e in self.error_history 
                               if e.error_severity == ErrorSeverity.CRITICAL)
            retryable_count = sum(1 for e in self.error_history if e.can_retry)
            
            return {
                "total_errors": total_errors,
                "errors_by_type": dict(self.error_counts),
                "errors_by_category": {k.value: v for k, v in self.category_counts.items()},
                "critical_errors": critical_count,
                "retryable_errors": retryable_count,
                "most_common_error": max(self.error_counts.items(), key=lambda x: x[1])[0] 
                                     if self.error_counts else None,
            }
    
    def get_error_rate(self, window_seconds: int = 60) -> float:
        """
        Calculate error rate over time window (errors per second).
        """
        with self.lock:
            now = time.time()
            recent = [e for e in self.error_history 
                     if now - e.timestamp <= window_seconds]
            
            if window_seconds > 0:
                return len(recent) / window_seconds
            return 0.0
    
    def clear_history(self) -> None:
        """Clear error history (for testing or reset)."""
        with self.lock:
            self.error_history.clear()
            self.error_counts.clear()
            self.category_counts.clear()


# Global instance
ERROR_LOGGER = ErrorContextLogger()


# ==========================
# Error Recovery Patterns
# ==========================
class ErrorRecoveryStrategy:
    """Strategies for error recovery and handling."""
    
    @staticmethod
    def should_retry(context: ErrorContext) -> bool:
        """Determine if error should be retried."""
        return context.can_retry and context.retry_count < 3
    
    @staticmethod
    def get_backoff_delay(retry_count: int) -> float:
        """
        Exponential backoff delay for retries.
        retry_count 0 -> 0.1s, 1 -> 0.2s, 2 -> 0.4s
        """
        return 0.1 * (2 ** retry_count)


# Export
__all__ = [
    "ErrorContext",
    "ErrorContextLogger",
    "ErrorSeverity",
    "ErrorCategory",
    "ERROR_LOGGER",
    "ErrorRecoveryStrategy",
]
