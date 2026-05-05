"""
Shared Utilities - Retry Handler
Exponential backoff retry logic for transient failures
"""

import asyncio
import logging
from typing import Callable, TypeVar, Any

logger = logging.getLogger(__name__)

T = TypeVar('T')


async def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    *args,
    **kwargs
) -> Any:
    """
    Retry a function with exponential backoff.
    
    Implements exponential backoff: 1s, 2s, 4s, 8s, etc.
    
    Args:
        func: Async function to retry
        max_retries: Maximum number of attempts (default: 3)
        initial_delay: Initial delay in seconds (default: 1.0)
        backoff_factor: Multiplier for delay (default: 2.0)
        *args: Positional arguments for func
        **kwargs: Keyword arguments for func
    
    Returns:
        Result from func if successful
    
    Raises:
        Exception: Last exception if all retries fail
    """
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            result = await func(*args, **kwargs)
            if attempt > 0:
                logger.info(f"Retry successful on attempt {attempt + 1}/{max_retries}")
            return result
        
        except Exception as e:
            last_exception = e
            
            if attempt < max_retries - 1:
                delay = initial_delay * (backoff_factor ** attempt)
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries} failed: {str(e)}. "
                    f"Retrying in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    f"All {max_retries} retry attempts failed. Last error: {str(e)}"
                )
    
    if last_exception is not None:
        raise last_exception
    else:
        raise RuntimeError(f"Failed after {max_retries} attempts")


def retry_sync(
    func: Callable,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    *args,
    **kwargs
) -> Any:
    """
    Retry a synchronous function with exponential backoff.
    
    Args:
        func: Synchronous function to retry
        max_retries: Maximum number of attempts (default: 3)
        initial_delay: Initial delay in seconds (default: 1.0)
        backoff_factor: Multiplier for delay (default: 2.0)
        *args: Positional arguments for func
        **kwargs: Keyword arguments for func
    
    Returns:
        Result from func if successful
    
    Raises:
        Exception: Last exception if all retries fail
    """
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            result = func(*args, **kwargs)
            if attempt > 0:
                logger.info(f"Retry successful on attempt {attempt + 1}/{max_retries}")
            return result
        
        except Exception as e:
            last_exception = e
            
            if attempt < max_retries - 1:
                delay = initial_delay * (backoff_factor ** attempt)
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries} failed: {str(e)}. "
                    f"Retrying in {delay:.1f}s..."
                )
                import time
                time.sleep(delay)
            else:
                logger.error(
                    f"All {max_retries} retry attempts failed. Last error: {str(e)}"
                )
    
    if last_exception is not None:
        raise last_exception
    else:
        raise RuntimeError(f"Failed after {max_retries} attempts")
