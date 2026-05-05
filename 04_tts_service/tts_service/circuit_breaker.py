"""
Circuit Breaker for TTS Synthesis
Provides fault tolerance and automatic recovery from transient failures.
PHASE 2.3: Prevents cascading failures and service degradation.
"""

import logging
from typing import Callable, Any, Optional
import threading
from enum import Enum
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing, reject requests
    HALF_OPEN = "half_open" # Testing if recovered


class SynthesisCircuitBreaker:
    """
    Circuit breaker for synthesis failures.
    Protects against cascading failures from ONNX runtime crashes.
    """
    
    def __init__(
        self,
        name: str,
        fail_max: int = 5,
        reset_timeout: int = 60,
        expected_exception: type = Exception
    ):
        """
        Initialize circuit breaker.
        
        Args:
            name: Circuit breaker name (for logging)
            fail_max: Failure count before opening circuit
            reset_timeout: Seconds to wait before trying recovery
            expected_exception: Exception type to catch
        """
        self.name = name
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self.expected_exception = expected_exception
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.lock = threading.RLock()
        
        logger.info(
            f"CircuitBreaker '{name}' initialized "
            f"(fail_max={fail_max}, reset_timeout={reset_timeout}s)"
        )
    
    def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Args:
            func: Function to call
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function
            
        Returns:
            Function result if successful
            
        Raises:
            CircuitBreakerOpenError: If circuit is OPEN
            Exception: If function raises wrapped exception
        """
        with self.lock:
            # Check if circuit should be closed after timeout
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    logger.info(f"CircuitBreaker '{self.name}' attempting HALF_OPEN")
                    self.state = CircuitState.HALF_OPEN
                    self.failure_count = 0
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is OPEN"
                    )
        
        try:
            result = func(*args, **kwargs)
            
            with self.lock:
                # Success - reset circuit
                if self.state == CircuitState.HALF_OPEN:
                    logger.info(f"CircuitBreaker '{self.name}' recovered to CLOSED")
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                elif self.state == CircuitState.CLOSED:
                    self.failure_count = max(0, self.failure_count - 1)
            
            return result
        
        except self.expected_exception as e:
            with self.lock:
                self.failure_count += 1
                self.last_failure_time = datetime.now()
                
                logger.warning(
                    f"CircuitBreaker '{self.name}' failure {self.failure_count}/{self.fail_max}: {e}"
                )
                
                # Open circuit if threshold exceeded
                if self.failure_count >= self.fail_max:
                    logger.error(f"CircuitBreaker '{self.name}' OPENED after {self.fail_max} failures")
                    self.state = CircuitState.OPEN
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' opened after {self.fail_max} failures"
                    )
            
            raise
    
    def _should_attempt_reset(self) -> bool:
        """
        Check if enough time has passed to attempt recovery.
        
        Returns:
            True if reset timeout has elapsed
        """
        if not self.last_failure_time:
            return True
        
        elapsed = (datetime.now() - self.last_failure_time).total_seconds()
        return elapsed >= self.reset_timeout
    
    def get_state(self) -> str:
        """
        Get current circuit breaker state.
        
        Returns:
            Current state name
        """
        with self.lock:
            return self.state.value
    
    def reset(self) -> None:
        """Manually reset circuit breaker to CLOSED."""
        with self.lock:
            logger.info(f"CircuitBreaker '{self.name}' manually reset")
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.last_failure_time = None


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is OPEN."""
    pass


# Global circuit breakers for each voice (granular protection)
_breakers = {}


def get_breaker(voice_id: str) -> SynthesisCircuitBreaker:
    """
    Get or create circuit breaker for voice.
    
    Args:
        voice_id: Voice identifier
        
    Returns:
        SynthesisCircuitBreaker for voice
    """
    if voice_id not in _breakers:
        _breakers[voice_id] = SynthesisCircuitBreaker(
            name=f"synthesis_{voice_id}",
            fail_max=5,
            reset_timeout=60
        )
    return _breakers[voice_id]


def get_all_breakers() -> dict:
    """
    Get all circuit breakers and their states.
    
    Returns:
        Dictionary mapping voice_id to (breaker, state)
    """
    return {
        voice_id: {
            "name": breaker.name,
            "state": breaker.get_state(),
            "failure_count": breaker.failure_count,
        }
        for voice_id, breaker in _breakers.items()
    }
