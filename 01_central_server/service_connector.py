"""
Service Connector with Circuit Breaker Pattern
- Resilient inter-service communication
- Automatic retry with exponential backoff
- Circuit breaker to prevent cascading failures
- Health checks and metrics
"""

import asyncio
import logging
from typing import Any, Dict, Optional, Callable
from enum import Enum
from datetime import datetime, timedelta
import aiohttp
from shared.security import internal_service_headers
from config.ssl_config import client_ssl_context

logger: logging.Logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


class ServiceConnector:
    """
    Resilient service connector with circuit breaker.
    
    Features:
    - Automatic retry with exponential backoff
    - Circuit breaker pattern (fail-fast)
    - Health check integration
    - Metrics collection
    - Timeout enforcement
    """

    def __init__(self, service_name: str, config: Any) -> None:
        self.service_name: str = service_name
        self.config_dict = config if isinstance(config, dict) else {}
        
        # Extract values from config dict
        self.base_url = self.config_dict.get("url", "https://localhost:8000")
        self.max_retries = self.config_dict.get("max_retries", 3)
        self.timeout = self.config_dict.get("timeout", 10)
        
        # Circuit breaker configuration
        self.circuit_breaker_enabled = self.config_dict.get("circuit_breaker_enabled", True)
        self.circuit_breaker_threshold = self.config_dict.get("circuit_breaker_threshold", 5)
        self.circuit_breaker_timeout = self.config_dict.get("circuit_breaker_timeout", 60)
        
        # For backward compatibility
        self.config = self.config_dict
        
        # Circuit breaker state
        self.circuit_state: CircuitState = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.last_success_time: Optional[datetime] = None
        
        # Metrics
        self.metrics: Dict[str, int] = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "retried_requests": 0,
            "circuit_opens": 0,
            "avg_response_time_ms": 0,
        }
        
        # HTTP session (created lazily)
        self.session: Optional[aiohttp.ClientSession] = None
        
        logger.info(f"ServiceConnector initialized for {service_name}")

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=client_ssl_context(self.base_url)))
        return self.session

    async def close_session(self) -> None:
        """Close HTTP session"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    async def request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Make HTTP request with circuit breaker and retry logic.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: Service endpoint path
            data: Request body (for POST/PUT)
            timeout: Request timeout in seconds
        
        Returns:
            Response JSON or None if failed
        """
        if timeout is None:
            timeout = self.timeout
        
        self.metrics["total_requests"] += 1
        
        # Check circuit breaker
        if not self._check_circuit():
            logger.warning(
                f"Circuit breaker OPEN for {self.service_name}, "
                f"rejecting request to {endpoint}"
            )
            return None
        
        # Retry logic
        for attempt in range(self.max_retries):
            try:
                return await self._make_request(
                    method, endpoint, data, timeout
                )
            except Exception as e:
                is_last_attempt = attempt == self.max_retries - 1
                
                if is_last_attempt:
                    self._record_failure()
                    logger.error(
                        f"Failed after {self.max_retries} attempts "
                        f"({self.service_name} {method} {endpoint}): {e}"
                    )
                    return None
                
                # Exponential backoff
                backoff = 2 ** attempt
                logger.warning(
                    f"Request failed, retry {attempt + 1}/{self.max_retries} "
                    f"in {backoff:.1f}s ({self.service_name}): {e}"
                )
                self.metrics["retried_requests"] += 1
                await asyncio.sleep(backoff)

    async def health_check(self) -> bool:
        """
        Check if service is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            response: Dict[str, Any] | None = await self.request("GET", "/health", timeout=2.0)
            is_healthy: bool = response is not None
            
            if is_healthy:
                self._record_success()
            
            return is_healthy
        except Exception as e:
            logger.error(f"Health check failed for {self.service_name}: {e}")
            self._record_failure()
            return False

    def get_metrics(self) -> Dict[str, Any]:
        """Get connector metrics"""
        return {
            "service": self.service_name,
            "circuit_state": self.circuit_state.value,
            "failure_count": self.failure_count,
            "last_failure": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "last_success": self.last_success_time.isoformat() if self.last_success_time else None,
            **self.metrics,
        }

    # ========================================================================
    # PRIVATE METHODS
    # ========================================================================

    def _check_circuit(self) -> bool:
        """Check if request should be allowed through circuit breaker"""
        if self.circuit_state == CircuitState.CLOSED:
            return True
        
        if self.circuit_state == CircuitState.OPEN:
            # Try to transition to half-open
            if self.last_failure_time:
                elapsed: timedelta = datetime.utcnow() - self.last_failure_time
                if elapsed >= timedelta(seconds=self.circuit_breaker_timeout):
                    logger.info(
                        f"Circuit breaker transitioning to HALF_OPEN "
                        f"for {self.service_name}"
                    )
                    self.circuit_state: CircuitState = CircuitState.HALF_OPEN
                    return True
            return False
        
        # HALF_OPEN: allow single request
        return True

    def _record_failure(self) -> None:
        """Record a failure"""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        self.metrics["failed_requests"] += 1
        
        # Open circuit if threshold exceeded
        if self.failure_count >= self.circuit_breaker_threshold:
            if self.circuit_state != CircuitState.OPEN:
                logger.error(
                    f"Circuit breaker OPENING for {self.service_name} "
                    f"(failures: {self.failure_count})"
                )
                self.circuit_state: CircuitState = CircuitState.OPEN
                self.metrics["circuit_opens"] += 1

    def _record_success(self) -> None:
        """Record a success"""
        self.last_success_time = datetime.utcnow()
        self.metrics["successful_requests"] += 1
        
        # Close circuit if in half-open
        if self.circuit_state == CircuitState.HALF_OPEN:
            logger.info(
                f"Circuit breaker CLOSING for {self.service_name} "
                f"(recovery successful)"
            )
            self.circuit_state: CircuitState = CircuitState.CLOSED
            self.failure_count = 0

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]],
        timeout: float,
    ) -> Optional[Dict[str, Any]]:
        """Make actual HTTP request"""
        session: aiohttp.ClientSession = await self.get_session()
        url: str = f"{self.base_url}{endpoint}"
        
        try:
            async with asyncio.timeout(timeout):
                async with session.request(
                    method,
                    url,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    headers=internal_service_headers(),
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        self._record_success()
                        logger.debug(
                            f"Success: {self.service_name} {method} {endpoint}"
                        )
                        return result
                    else:
                        raise Exception(
                            f"HTTP {response.status}"
                        )
        except asyncio.TimeoutError:
            raise Exception(f"Timeout ({timeout}s)")
        except Exception as e:
            raise


class ServiceRegistry:
    """Manages all service connectors"""

    def __init__(self, services_config: Dict[str, Any]) -> None:
        self.connectors: Dict[str, ServiceConnector] = {}
        
        for service_name, config in services_config.items():
            self.connectors[service_name] = ServiceConnector(service_name, config)
        
        logger.info(f"ServiceRegistry initialized with {len(self.connectors)} services")

    def get_connector(self, service_name: str) -> Optional[ServiceConnector]:
        """Get connector for service"""
        return self.connectors.get(service_name)

    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all services"""
        results = {}
        
        for service_name, connector in self.connectors.items():
            results[service_name] = await connector.health_check()
        
        return results

    def get_all_metrics(self) -> Dict[str, Any]:
        """Get metrics from all connectors"""
        return {
            name: connector.get_metrics()
            for name, connector in self.connectors.items()
        }

    async def close_all(self) -> None:
        """Close all service sessions"""
        for connector in self.connectors.values():
            await connector.close_session()


# Global service registry (initialized in main)
service_registry: Optional[ServiceRegistry] = None


async def init_service_registry(services_config: Dict[str, Any]) -> ServiceRegistry:
    """Initialize service registry"""
    global service_registry
    service_registry = ServiceRegistry(services_config)
    return service_registry


def get_service_registry() -> ServiceRegistry:
    """Get service registry instance"""
    if service_registry is None:
        raise RuntimeError("ServiceRegistry not initialized")
    return service_registry
