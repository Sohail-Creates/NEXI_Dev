"""
Timeout Handler for Service Calls
==================================

Ensures service calls complete within defined time windows:
- Configurable timeouts per service
- Async-aware timeout enforcement
- Graceful timeout error handling
- Distributed tracing
"""

import asyncio
import threading
from typing import Callable, Any, Optional, Dict
import logging


class TimeoutError(Exception):
    """Raised when operation exceeds timeout"""
    def __init__(self, service_name: str, timeout_seconds: float):
        self.service_name = service_name
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"[{service_name}] Operation exceeded timeout of {timeout_seconds}s"
        )


class TimeoutConfig:
    """Configuration for service call timeouts"""
    
    def __init__(self):
        self._timeouts: Dict[str, float] = {
            "default": 30.0,  # 30 seconds default
            "audio_service": 10.0,
            "vision_service": 5.0,
            "enrollment_service": 30.0,
            "central_server": 15.0,
            "llm_service": 90.0,  # CPU inference takes 20-30s, allow 90s buffer
        }
    
    def get(self, service_name: str) -> float:
        """Get timeout for service (returns default if not configured)"""
        return self._timeouts.get(service_name, self._timeouts["default"])
    
    def set(self, service_name: str, timeout_seconds: float):
        """Set timeout for service"""
        self._timeouts[service_name] = timeout_seconds
    
    def get_all(self) -> Dict[str, float]:
        """Get all configured timeouts"""
        return self._timeouts.copy()


class TimeoutHandler:
    """Execute function with timeout enforcement"""
    
    def __init__(
        self,
        config: Optional[TimeoutConfig] = None,
        logger: Optional[logging.Logger] = None
    ):
        self.config = config or TimeoutConfig()
        self.logger = logger or logging.getLogger(__name__)
    
    def execute(
        self,
        func: Callable,
        *args,
        service_name: str = "default",
        request_id: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Execute function with timeout enforcement
        
        Args:
            func: Callable to execute
            *args: Positional arguments
            service_name: Name of service (used for timeout lookup)
            request_id: For distributed tracing
            **kwargs: Keyword arguments
            
        Returns:
            Result of func(*args, **kwargs)
            
        Raises:
            TimeoutError: If function exceeds timeout
        """
        timeout_seconds = self.config.get(service_name)
        
        self.logger.debug(
            f"Executing {service_name} with {timeout_seconds}s timeout",
            extra={"request_id": request_id, "timeout_seconds": timeout_seconds}
        )
        
        # For synchronous code, use threading
        result = [None]
        exception = [None]
        
        def target():
            try:
                result[0] = func(*args, **kwargs)
            except Exception as e:
                exception[0] = e
        
        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout=timeout_seconds)
        
        if thread.is_alive():
            self.logger.error(
                f"{service_name} call exceeded timeout",
                extra={
                    "request_id": request_id,
                    "timeout_seconds": timeout_seconds
                }
            )
            raise TimeoutError(service_name, timeout_seconds)
        
        if exception[0]:
            raise exception[0]
        
        return result[0]
    
    async def execute_async(
        self,
        func: Callable,
        *args,
        service_name: str = "default",
        request_id: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Execute async function with timeout enforcement
        
        Args:
            func: Async callable to execute
            *args: Positional arguments
            service_name: Name of service (used for timeout lookup)
            request_id: For distributed tracing
            **kwargs: Keyword arguments
            
        Returns:
            Result of await func(*args, **kwargs)
            
        Raises:
            TimeoutError: If function exceeds timeout
            asyncio.TimeoutError: On timeout (converted to TimeoutError)
        """
        timeout_seconds = self.config.get(service_name)
        
        self.logger.debug(
            f"Executing async {service_name} with {timeout_seconds}s timeout",
            extra={"request_id": request_id, "timeout_seconds": timeout_seconds}
        )
        
        try:
            result = await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=timeout_seconds
            )
            return result
        except asyncio.TimeoutError:
            self.logger.error(
                f"Async {service_name} call exceeded timeout",
                extra={
                    "request_id": request_id,
                    "timeout_seconds": timeout_seconds
                }
            )
            raise TimeoutError(service_name, timeout_seconds)


# Global timeout configuration
_global_config = TimeoutConfig()


def get_timeout_config() -> TimeoutConfig:
    """Get global timeout configuration"""
    return _global_config


def set_service_timeout(service_name: str, timeout_seconds: float):
    """Set timeout for service globally"""
    _global_config.set(service_name, timeout_seconds)


def get_timeout_handler(config: Optional[TimeoutConfig] = None) -> TimeoutHandler:
    """Create a timeout handler"""
    return TimeoutHandler(config or _global_config)
