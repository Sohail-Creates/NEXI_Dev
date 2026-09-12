"""
Vision Service Connector with Circuit Breaker
Resilient connector for Vision Service integration with:
- Circuit breaker pattern (CLOSED -> OPEN -> HALF_OPEN)
- Exponential backoff retry logic
- Timeout management
- Graceful degradation (continues without Vision if unavailable)
- Comprehensive logging and metrics
"""

import asyncio
import logging
import aiohttp
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from .config import vision_config
from shared.security import internal_service_headers
from config.ssl_config import client_ssl_context

logger = logging.getLogger(__name__)


class VisionCircuitState(Enum):
    """Vision Service circuit breaker states"""
    CLOSED = "closed"           # Normal operation
    OPEN = "open"               # Service failing, reject requests
    HALF_OPEN = "half_open"     # Testing if service recovered


class VisionServiceConnector:
    """
    Resilient connector for Vision Service
    Prevents cascading failures when Vision Service is slow or unavailable
    """
    
    def __init__(self):
        self.base_url = vision_config.get_base_url()
        self.timeout = vision_config.TIMEOUT
        self.health_timeout = vision_config.HEALTH_CHECK_TIMEOUT
        
        # Circuit breaker state
        self.circuit_state = VisionCircuitState.CLOSED
        self.failure_count = 0
        self.failure_threshold = 3  # Open circuit after 3 failures
        self.circuit_open_time: Optional[datetime] = None
        self.circuit_timeout = 30  # Try recovery after 30 seconds
        
        # Metrics
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.skipped_requests = 0  # Circuit open
        self.response_time_sum = 0.0
        
        logger.info(f"VisionServiceConnector initialized: {self.base_url}")
    
    async def get_vision_attributes(
        self, 
        object_name: str,
        timeout_override: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get object attributes from Vision Service with circuit breaker.
        
        Args:
            object_name: Name of the object to analyze
            timeout_override: Override default timeout
            
        Returns:
            Dict with vision attributes or None if unavailable
        """
        # Check circuit breaker state
        if not self._check_circuit():
            self.skipped_requests += 1
            logger.warning(f"Vision Service circuit {self.circuit_state.value}, skipping request")
            return None
        
        self.total_requests += 1
        timeout = timeout_override or self.timeout
        
        # Exponential backoff retry logic
        retry_delays = [0.5, 1.0, 2.0]  # seconds
        last_error = None
        
        for attempt, delay in enumerate(retry_delays, 1):
            try:
                start_time = datetime.utcnow()
                
                async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=client_ssl_context(self.base_url))) as session:
                    url = f"{self.base_url}{vision_config.ANALYZE_ENDPOINT}"
                    payload = {"object_name": object_name}
                    
                    async with session.post(
                        url,
                        json=payload,
                        headers=internal_service_headers(),
                        timeout=aiohttp.ClientTimeout(total=timeout)
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            # Record success
                            elapsed = (datetime.utcnow() - start_time).total_seconds()
                            self._record_success(elapsed)
                            
                            logger.info(f"Vision attributes retrieved for '{object_name}' (attempt {attempt})")
                            return data
                        else:
                            logger.warning(f"Vision Service returned {response.status} for '{object_name}'")
                            last_error = f"HTTP {response.status}"
                            
            except asyncio.TimeoutError:
                last_error = "Timeout"
                logger.warning(f"Vision Service timeout on attempt {attempt}/{len(retry_delays)}")
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Vision Service error on attempt {attempt}: {type(e).__name__}: {e}")
            
            # Wait before retrying (except on last attempt)
            if attempt < len(retry_delays):
                await asyncio.sleep(delay)
        
        # All retries failed
        self._record_failure()
        logger.error(f"Vision Service failed after {len(retry_delays)} retries: {last_error}")
        return None
    
    async def health_check(self) -> bool:
        """
        Check Vision Service health
        
        Returns:
            True if service is healthy, False otherwise
        """
        try:
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=client_ssl_context(self.base_url))) as session:
                url = f"{self.base_url}{vision_config.HEALTH_ENDPOINT}"
                
                async with session.get(
                    url,
                    headers=internal_service_headers(),
                    timeout=aiohttp.ClientTimeout(total=self.health_timeout)
                ) as response:
                    is_healthy = response.status == 200
                    
                    if is_healthy:
                        self._record_success(0.1)  # Health check is fast
                    else:
                        self._record_failure()
                    
                    return is_healthy
                    
        except Exception as e:
            logger.warning(f"Vision health check failed: {e}")
            self._record_failure()
            return False
    
    def _check_circuit(self) -> bool:
        """
        Check circuit breaker state and handle transitions
        
        Returns:
            True if request should proceed, False if circuit is open
        """
        if self.circuit_state == VisionCircuitState.CLOSED:
            return True
        
        if self.circuit_state == VisionCircuitState.OPEN:
            # Check if recovery window has passed
            if self.circuit_open_time:
                elapsed = (datetime.utcnow() - self.circuit_open_time).total_seconds()
                if elapsed >= self.circuit_timeout:
                    # Try recovery
                    self.circuit_state = VisionCircuitState.HALF_OPEN
                    self.failure_count = 0
                    logger.info("Vision circuit breaker transitioning to HALF_OPEN")
                    return True
            return False
        
        # HALF_OPEN: allow single test request
        return True
    
    def _record_success(self, response_time: float) -> None:
        """Record successful request"""
        self.successful_requests += 1
        self.response_time_sum += response_time
        self.failure_count = 0  # Reset failure counter
        
        # If in HALF_OPEN, transition back to CLOSED
        if self.circuit_state == VisionCircuitState.HALF_OPEN:
            self.circuit_state = VisionCircuitState.CLOSED
            logger.info("Vision circuit breaker back to CLOSED (recovery successful)")
    
    def _record_failure(self) -> None:
        """Record failed request"""
        self.failed_requests += 1
        self.failure_count += 1
        
        # If failures exceed threshold, open circuit
        if self.failure_count >= self.failure_threshold and self.circuit_state != VisionCircuitState.OPEN:
            self.circuit_state = VisionCircuitState.OPEN
            self.circuit_open_time = datetime.utcnow()
            logger.error(f"Vision circuit breaker OPEN after {self.failure_count} failures")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get connector metrics"""
        avg_response_time = (
            self.response_time_sum / self.successful_requests
            if self.successful_requests > 0
            else 0.0
        )
        
        return {
            "circuit_state": self.circuit_state.value,
            "total_requests": self.total_requests,
            "successful": self.successful_requests,
            "failed": self.failed_requests,
            "skipped_circuit_open": self.skipped_requests,
            "failure_count": self.failure_count,
            "avg_response_time": round(avg_response_time, 3),
            "circuit_open_since": self.circuit_open_time.isoformat() if self.circuit_open_time else None,
        }


# Global instance
_vision_connector: Optional[VisionServiceConnector] = None


def get_vision_connector() -> VisionServiceConnector:
    """Get or create Vision Service connector"""
    global _vision_connector
    if _vision_connector is None:
        _vision_connector = VisionServiceConnector()
    return _vision_connector


async def init_vision_connector() -> VisionServiceConnector:
    """Initialize Vision Service connector and verify health"""
    connector = get_vision_connector()
    
    try:
        is_healthy = await connector.health_check()
        if is_healthy:
            logger.info("Vision Service health check passed")
        else:
            logger.warning("Vision Service health check failed, but continuing")
    except Exception as e:
        logger.warning(f"Vision Service initialization warning: {e}")
    
    return connector
