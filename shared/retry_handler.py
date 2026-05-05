"""
Retry Handler with Exponential Backoff
=======================================

Enterprise-grade retry logic:
- Exponential backoff to avoid overwhelming services
- Jitter to prevent thundering herd
- Configurable retry policies per exception type
- Request tracing through retry attempts
"""

import asyncio
import time
import random
from typing import Callable, Any, Optional, Type, List, Dict
import logging


class RetryPolicy:
    """Policy for retry behavior"""
    
    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay_ms: int = 100,
        max_delay_ms: int = 5000,
        backoff_multiplier: float = 2.0,
        jitter: bool = True
    ):
        """
        Args:
            max_attempts: Maximum retry attempts (including initial)
            initial_delay_ms: Initial delay in milliseconds
            max_delay_ms: Maximum delay in milliseconds
            backoff_multiplier: Multiplier for exponential backoff
            jitter: Whether to add random jitter
        """
        self.max_attempts = max_attempts
        self.initial_delay_ms = initial_delay_ms
        self.max_delay_ms = max_delay_ms
        self.backoff_multiplier = backoff_multiplier
        self.jitter = jitter
        self.retryable_exceptions: List[Type[Exception]] = []
    
    def add_retryable_exception(self, exc_type: Type[Exception]):
        """Mark exception type as retryable"""
        self.retryable_exceptions.append(exc_type)
        return self
    
    def is_retryable(self, exception: Exception) -> bool:
        """Check if exception should trigger retry"""
        if not self.retryable_exceptions:
            return True  # Retry all exceptions by default
        return any(isinstance(exception, exc_type) for exc_type in self.retryable_exceptions)
    
    def get_delay_ms(self, attempt: int) -> int:
        """Calculate delay for given attempt number (0-indexed)"""
        delay = self.initial_delay_ms * (self.backoff_multiplier ** attempt)
        delay = min(delay, self.max_delay_ms)  # Cap at max
        
        if self.jitter:
            # Add random jitter (0-25% variation)
            jitter_amount = delay * 0.25 * random.random()
            delay += jitter_amount
        
        return int(delay)


class RetryHandler:
    """Execute function with automatic retries"""
    
    def __init__(
        self,
        policy: Optional[RetryPolicy] = None,
        logger: Optional[logging.Logger] = None
    ):
        self.policy = policy or RetryPolicy()
        self.logger = logger or logging.getLogger(__name__)
    
    def execute(
        self,
        func: Callable,
        *args,
        request_id: Optional[str] = None,
        operation_name: str = "operation",
        **kwargs
    ) -> Any:
        """
        Execute function with retries
        
        Args:
            func: Callable to execute
            *args: Positional arguments
            request_id: For distributed tracing
            operation_name: Human-readable operation name
            **kwargs: Keyword arguments
            
        Returns:
            Result of func(*args, **kwargs)
            
        Raises:
            Original exception on final failure
        """
        last_exception = None
        
        for attempt in range(self.policy.max_attempts):
            try:
                self.logger.debug(
                    f"Executing {operation_name} (attempt {attempt + 1}/{self.policy.max_attempts})",
                    extra={"request_id": request_id, "attempt": attempt + 1}
                )
                
                result = func(*args, **kwargs)
                
                if attempt > 0:
                    self.logger.info(
                        f"{operation_name} succeeded after {attempt} retries",
                        extra={"request_id": request_id, "attempts": attempt + 1}
                    )
                
                return result
            
            except Exception as e:
                last_exception = e
                
                # Check if this exception is retryable
                if not self.policy.is_retryable(e):
                    self.logger.error(
                        f"{operation_name} failed with non-retryable exception",
                        extra={
                            "request_id": request_id,
                            "exception_type": type(e).__name__,
                            "message": str(e)
                        }
                    )
                    raise
                
                # Check if we have more attempts
                if attempt < self.policy.max_attempts - 1:
                    delay_ms = self.policy.get_delay_ms(attempt)
                    self.logger.warning(
                        f"{operation_name} failed, retrying in {delay_ms}ms",
                        extra={
                            "request_id": request_id,
                            "attempt": attempt + 1,
                            "delay_ms": delay_ms,
                            "exception": str(e)
                        }
                    )
                    time.sleep(delay_ms / 1000.0)
                else:
                    self.logger.error(
                        f"{operation_name} failed after {self.policy.max_attempts} attempts",
                        extra={
                            "request_id": request_id,
                            "final_exception": str(e)
                        }
                    )
        
        # All retries exhausted
        raise last_exception or Exception(f"{operation_name} failed")
    
    async def execute_async(
        self,
        func: Callable,
        *args,
        request_id: Optional[str] = None,
        operation_name: str = "operation",
        **kwargs
    ) -> Any:
        """Async version of execute()"""
        last_exception = None
        
        for attempt in range(self.policy.max_attempts):
            try:
                self.logger.debug(
                    f"Executing {operation_name} (attempt {attempt + 1}/{self.policy.max_attempts})",
                    extra={"request_id": request_id, "attempt": attempt + 1}
                )
                
                result = await func(*args, **kwargs)
                
                if attempt > 0:
                    self.logger.info(
                        f"{operation_name} succeeded after {attempt} retries",
                        extra={"request_id": request_id, "attempts": attempt + 1}
                    )
                
                return result
            
            except Exception as e:
                last_exception = e
                
                if not self.policy.is_retryable(e):
                    self.logger.error(
                        f"{operation_name} failed with non-retryable exception",
                        extra={
                            "request_id": request_id,
                            "exception_type": type(e).__name__
                        }
                    )
                    raise
                
                if attempt < self.policy.max_attempts - 1:
                    delay_ms = self.policy.get_delay_ms(attempt)
                    self.logger.warning(
                        f"{operation_name} failed, retrying in {delay_ms}ms",
                        extra={
                            "request_id": request_id,
                            "attempt": attempt + 1,
                            "delay_ms": delay_ms
                        }
                    )
                    await asyncio.sleep(delay_ms / 1000.0)
                else:
                    self.logger.error(
                        f"{operation_name} failed after {self.policy.max_attempts} attempts",
                        extra={"request_id": request_id}
                    )
        
        raise last_exception or Exception(f"{operation_name} failed")


# Default retry policies
DEFAULT_POLICY = RetryPolicy(
    max_attempts=3,
    initial_delay_ms=100,
    max_delay_ms=5000,
    backoff_multiplier=2.0,
    jitter=True
)

AGGRESSIVE_POLICY = RetryPolicy(
    max_attempts=5,
    initial_delay_ms=50,
    max_delay_ms=10000,
    backoff_multiplier=2.0,
    jitter=True
)

CONSERVATIVE_POLICY = RetryPolicy(
    max_attempts=2,
    initial_delay_ms=500,
    max_delay_ms=2000,
    backoff_multiplier=1.5,
    jitter=True
)


def create_retry_handler(policy: Optional[RetryPolicy] = None) -> RetryHandler:
    """Create a retry handler with given policy"""
    return RetryHandler(policy or DEFAULT_POLICY)
