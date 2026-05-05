"""
Circuit Breaker pattern implementation for external API calls.
Prevents cascading failures and provides graceful degradation.
Used across all services for resilient inter-service communication.
"""

import logging
import time
from enum import Enum
from typing import Callable, Any, Optional, Union
from datetime import datetime, timedelta
import threading

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is OPEN."""
    pass


# Alias for backward compatibility
CircuitBreakerException = CircuitBreakerError


class CircuitBreaker:
    """
    Circuit Breaker pattern to prevent cascading failures.
    
    State Transitions:
    - CLOSED -> OPEN: When failure threshold exceeded
    - OPEN -> HALF_OPEN: After timeout period
    - HALF_OPEN -> CLOSED: When test request succeeds
    - HALF_OPEN -> OPEN: When test request fails
    
    Features:
    - Thread-safe state management
    - Comprehensive statistics and monitoring
    - Proper recovery thresholds
    - Half-open rate limiting (prevents thundering herd)
    
    Example:
        ```python
        breaker = CircuitBreaker(
            failure_threshold=5,
            timeout_seconds=60
        )
        
        try:
            result = breaker.call(lambda: api.transcribe(audio))
        except CircuitBreakerError:
            # Circuit is open, use fallback logic
            result = fallback_transcription(audio)
        ```
    """
    
    def __init__(
        self,
        name: str = "CircuitBreaker",
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout_seconds: Optional[float] = None,
        recovery_timeout: Optional[float] = None,
        recovery_threshold: Optional[int] = None,
        half_open_max_calls: int = 3
    ):
        """
        Initialize circuit breaker.
        
        Args:
            name: Name for logging purposes
            failure_threshold: Number of failures before opening circuit
            success_threshold: Number of successes needed to close circuit from half-open
            timeout_seconds: (DEPRECATED) Seconds to wait before trying again
            recovery_timeout: Seconds to wait before trying again (OPEN -> HALF_OPEN)
            recovery_threshold: (alias for success_threshold) Number of successes to close
            half_open_max_calls: Max concurrent calls allowed in HALF_OPEN state
        """
        self.name = name
        self.failure_threshold = failure_threshold
        
        # Support both old and new parameter names
        if recovery_threshold is not None:
            self.success_threshold = recovery_threshold
        else:
            self.success_threshold = success_threshold
        
        if recovery_timeout is not None:
            self.timeout_seconds = recovery_timeout
        elif timeout_seconds is not None:
            self.timeout_seconds = timeout_seconds
        else:
            self.timeout_seconds = 60.0  # Default
        
        self.half_open_max_calls = half_open_max_calls
        
        # State
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.opened_at: Optional[datetime] = None
        self.half_open_calls = 0
        
        # Statistics
        self.total_calls = 0
        self.total_successes = 0
        self.total_failures = 0
        self.total_rejections = 0
        
        # Thread safety
        self.lock = threading.Lock()
        
        logger.info(
            f"Circuit breaker '{name}' initialized: "
            f"failure_threshold={failure_threshold}, timeout={self.timeout_seconds}s"
        )
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function through circuit breaker.
        
        Args:
            func: Function to execute
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function
        
        Returns:
            Result from function
        
        Raises:
            CircuitBreakerError: If circuit is OPEN
            Exception: Any exception raised by the function
        """
        with self.lock:
            self.total_calls += 1
            
            # Check if circuit should transition from OPEN to HALF_OPEN
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    logger.info(f"Circuit breaker '{self.name}': OPEN -> HALF_OPEN (attempting recovery)")
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    self.half_open_calls = 0
                else:
                    # Circuit is still OPEN, reject the call
                    self.total_rejections += 1
                    if self.opened_at is not None:
                        time_since_open = (datetime.now() - self.opened_at).total_seconds()
                        time_remaining = max(0, self.timeout_seconds - time_since_open)
                    else:
                        time_remaining = 0
                    
                    logger.warning(
                        f"Circuit breaker '{self.name}' is OPEN. "
                        f"Rejecting call. Retry in {time_remaining:.1f}s"
                    )
                    raise CircuitBreakerError(
                        f"Circuit breaker '{self.name}' is OPEN. "
                        f"Service is temporarily unavailable. "
                        f"Retry after {time_remaining:.1f} seconds."
                    )
            
            # Check if we can make calls in HALF_OPEN state
            if self.state == CircuitState.HALF_OPEN:
                if self.half_open_calls >= self.half_open_max_calls:
                    self.total_rejections += 1
                    raise CircuitBreakerError(
                        f"Circuit breaker '{self.name}' is in HALF_OPEN state "
                        f"and max concurrent calls ({self.half_open_max_calls}) reached. "
                        f"Please try again shortly."
                    )
                self.half_open_calls += 1
        
        # Execute the function (outside lock to avoid blocking)
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
        finally:
            if self.state == CircuitState.HALF_OPEN:
                with self.lock:
                    self.half_open_calls -= 1
    
    def _on_success(self):
        """Handle successful call."""
        with self.lock:
            self.total_successes += 1
            self.failure_count = 0
            self.last_failure_time = None
            
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                logger.debug(
                    f"Circuit breaker '{self.name}': Success in HALF_OPEN "
                    f"({self.success_count}/{self.success_threshold})"
                )
                
                if self.success_count >= self.success_threshold:
                    logger.info(f"Circuit breaker '{self.name}': HALF_OPEN -> CLOSED (service recovered)")
                    self.state = CircuitState.CLOSED
                    self.success_count = 0
    
    def _on_failure(self):
        """Handle failed call."""
        with self.lock:
            self.total_failures += 1
            self.failure_count += 1
            self.last_failure_time = datetime.now()
            
            if self.state == CircuitState.HALF_OPEN:
                logger.warning(f"Circuit breaker '{self.name}': HALF_OPEN -> OPEN (service still failing)")
                self.state = CircuitState.OPEN
                self.opened_at = datetime.now()
                self.failure_count = 0
            elif self.state == CircuitState.CLOSED:
                if self.failure_count >= self.failure_threshold:
                    logger.error(
                        f"Circuit breaker '{self.name}': CLOSED -> OPEN "
                        f"(failure threshold {self.failure_threshold} exceeded)"
                    )
                    self.state = CircuitState.OPEN
                    self.opened_at = datetime.now()
                    self.failure_count = 0
                else:
                    logger.debug(
                        f"Circuit breaker '{self.name}': Failure {self.failure_count}/{self.failure_threshold}"
                    )
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset from OPEN to HALF_OPEN."""
        if self.opened_at is None:
            return True
        
        time_since_open = (datetime.now() - self.opened_at).total_seconds()
        return time_since_open >= self.timeout_seconds
    
    def reset(self):
        """Manually reset circuit breaker to CLOSED state."""
        with self.lock:
            logger.info(f"Circuit breaker '{self.name}': Manually reset to CLOSED")
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_time = None
            self.opened_at = None
    
    def get_state(self) -> CircuitState:
        """Get current circuit state."""
        with self.lock:
            return self.state
    
    def is_available(self) -> bool:
        """Check if circuit is available for calls (not OPEN)."""
        with self.lock:
            if self.state == CircuitState.OPEN:
                return self._should_attempt_reset()
            return True
    
    def get_stats(self) -> dict:
        """Get circuit breaker statistics."""
        with self.lock:
            stats = {
                "name": self.name,
                "state": self.state.value,
                "total_calls": self.total_calls,
                "total_successes": self.total_successes,
                "total_failures": self.total_failures,
                "total_rejections": self.total_rejections,
                "current_failure_count": self.failure_count,
                "failure_threshold": self.failure_threshold,
                "timeout_seconds": self.timeout_seconds
            }
            
            if self.total_calls > 0:
                stats["success_rate"] = self.total_successes / self.total_calls
                stats["failure_rate"] = self.total_failures / self.total_calls
                stats["rejection_rate"] = self.total_rejections / self.total_calls
            
            if self.opened_at:
                stats["opened_at"] = self.opened_at.isoformat()
                stats["open_duration_seconds"] = (datetime.now() - self.opened_at).total_seconds()
            
            if self.last_failure_time:
                stats["last_failure"] = self.last_failure_time.isoformat()
            
            return stats
    
    def record_success(self):
        """
        Manually record a successful operation.
        Useful for external API monitoring without using call().
        """
        with self.lock:
            self.total_calls += 1
            self.total_successes += 1
            self.failure_count = 0  # Reset failure count on success
            
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    self.state = CircuitState.CLOSED
                    logger.info(f"[{self.name}] Circuit CLOSED after {self.success_count} successes")
    
    def record_failure(self, error: Optional[Exception] = None):
        """
        Manually record a failed operation.
        Useful for external API monitoring without using call().
        
        Args:
            error: Optional exception that caused the failure
        """
        with self.lock:
            self.total_calls += 1
            self.total_failures += 1
            self.failure_count += 1
            self.last_failure_time = datetime.now()
            
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                logger.warning(f"[{self.name}] Circuit reopened after failure in HALF_OPEN state")
            elif self.state == CircuitState.CLOSED:
                if self.failure_count >= self.failure_threshold:
                    self.state = CircuitState.OPEN
                    self.opened_at = datetime.now()
                    logger.error(
                        f"[{self.name}] Circuit OPEN after {self.failure_count} failures. "
                        f"Last error: {str(error) if error else 'Unknown'}"
                    )


class RetryStrategy:
    """
    Retry strategy with exponential backoff.
    
    Complements CircuitBreaker for transient failures.
    Use CircuitBreaker for permanent failures, RetryStrategy for temporary glitches.
    """
    
    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        """
        Initialize retry strategy.
        
        Args:
            max_attempts: Maximum number of retry attempts
            initial_delay: Initial delay in seconds
            max_delay: Maximum delay in seconds
            exponential_base: Base for exponential backoff
            jitter: Add random jitter to prevent thundering herd
        """
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
    
    def execute(
        self,
        func: Callable,
        *args,
        retryable_exceptions: tuple = (Exception,),
        **kwargs
    ) -> Any:
        """
        Execute function with retry logic.
        
        Args:
            func: Function to execute
            *args: Positional arguments
            retryable_exceptions: Tuple of exceptions to retry on
            **kwargs: Keyword arguments
        
        Returns:
            Result from function
        
        Raises:
            Last exception if all retries exhausted
        """
        last_exception = None
        
        for attempt in range(1, self.max_attempts + 1):
            try:
                return func(*args, **kwargs)
            except retryable_exceptions as e:
                last_exception = e
                
                if attempt == self.max_attempts:
                    logger.error(f"All {self.max_attempts} retry attempts exhausted")
                    raise
                
                delay = self._calculate_delay(attempt)
                logger.warning(
                    f"Attempt {attempt}/{self.max_attempts} failed: {e}. "
                    f"Retrying in {delay:.2f}s..."
                )
                time.sleep(delay)
        
        # This should never be reached, but just in case
        if last_exception:
            raise last_exception
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number."""
        import random
        
        # Exponential backoff
        delay = min(
            self.initial_delay * (self.exponential_base ** (attempt - 1)),
            self.max_delay
        )
        
        # Add jitter (±25%)
        if self.jitter:
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)
        
        return max(0, delay)


# ============================================================================
# CONVENIENCE DECORATORS
# ============================================================================

def with_circuit_breaker(
    name: str = "default",
    failure_threshold: int = 5,
    timeout_seconds: float = 60.0
):
    """
    Decorator to wrap function with circuit breaker.
    
    Example:
        ```python
        @with_circuit_breaker(name="groq_api", failure_threshold=3)
        def call_groq_api(audio):
            return groq_client.transcribe(audio)
        ```
    """
    breaker = CircuitBreaker(
        name=name,
        failure_threshold=failure_threshold,
        timeout_seconds=timeout_seconds
    )
    
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            return breaker.call(func, *args, **kwargs)
        return wrapper
    return decorator


def with_retry(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    retryable_exceptions: tuple = (Exception,)
):
    """
    Decorator to add retry logic to function.
    
    Example:
        ```python
        @with_retry(max_attempts=3, initial_delay=2.0)
        def flaky_network_call():
            return requests.get("https://api.example.com")
        ```
    """
    strategy = RetryStrategy(
        max_attempts=max_attempts,
        initial_delay=initial_delay
    )
    
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            return strategy.execute(
                func,
                *args,
                retryable_exceptions=retryable_exceptions,
                **kwargs
            )
        return wrapper
    return decorator
