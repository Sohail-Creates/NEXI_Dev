"""
Base HTTP client with circuit breaker, retry, and timeout logic.
Used by all services for making requests to other services.
"""

import logging
from typing import Any, Optional, Callable, Dict
from datetime import datetime, timedelta
import asyncio

import httpx
from shared.security import merge_internal_headers
from config.ssl_config import client_verify
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from shared.utils.error_handling import (
    ServiceUnavailableError,
    ServiceTimeoutError,
    CircuitBreakerOpenError,
)

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Circuit breaker for fault tolerance."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = "closed"  # closed, open, half-open

    def record_success(self) -> None:
        """Record successful request."""
        self.failure_count = 0
        self.state = "closed"
        logger.debug(f"Circuit breaker reset to closed")

    def record_failure(self) -> None:
        """Record failed request."""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.warning(
                f"Circuit breaker opened after {self.failure_count} failures"
            )

    def can_attempt(self) -> bool:
        """Check if request can be attempted."""
        if self.state == "closed":
            return True

        if self.state == "open":
            if self.last_failure_time is None:
                return False

            elapsed = datetime.utcnow() - self.last_failure_time
            if elapsed > timedelta(seconds=self.recovery_timeout):
                self.state = "half-open"
                logger.info("Circuit breaker half-open, attempting recovery")
                return True
            return False

        return True


class AsyncHTTPClient:
    """Async HTTP client with circuit breaker, retry, and timeout."""

    def __init__(
        self,
        base_url: str = "https://localhost:8000",
        timeout: int = 30,
        max_retries: int = 3,
        circuit_breaker_enabled: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.circuit_breaker = CircuitBreaker() if circuit_breaker_enabled else None
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Context manager entry."""
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=self.timeout, verify=client_verify(self.base_url))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.close()

    async def close(self) -> None:
        """Close the client."""
        if self.client:
            await self.client.aclose()
            self.client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure client is initialized."""
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=self.timeout, verify=client_verify(self.base_url))
        return self.client

    async def _check_circuit_breaker(self) -> None:
        """Check circuit breaker state."""
        if self.circuit_breaker is None:
            return

        if not self.circuit_breaker.can_attempt():
            raise CircuitBreakerOpenError(
                service_name=self.base_url,
                recovery_time=self.circuit_breaker.recovery_timeout,
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.RequestError, asyncio.TimeoutError)),
        reraise=True,
    )
    async def _make_request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> httpx.Response:
        """Make HTTP request with retry logic."""
        client = self._ensure_client()
        kwargs["headers"] = merge_internal_headers(kwargs.get("headers"))
        return await client.request(method, url, **kwargs)

    async def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Make GET request."""
        await self._check_circuit_breaker()

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            response = await self._make_request("GET", url, params=params, **kwargs)
            response.raise_for_status()
            if self.circuit_breaker:
                self.circuit_breaker.record_success()
            return response.json()
        except httpx.TimeoutException as e:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            raise ServiceTimeoutError(
                service_name=self.base_url,
                timeout_seconds=self.timeout,
            ) from e
        except httpx.RequestError as e:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            raise ServiceUnavailableError(
                service_name=self.base_url,
                details={"error": str(e)},
            ) from e

    async def post(
        self,
        endpoint: str,
        json: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Make POST request."""
        await self._check_circuit_breaker()

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            response = await self._make_request("POST", url, json=json, **kwargs)
            response.raise_for_status()
            if self.circuit_breaker:
                self.circuit_breaker.record_success()
            return response.json()
        except httpx.TimeoutException as e:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            raise ServiceTimeoutError(
                service_name=self.base_url,
                timeout_seconds=self.timeout,
            ) from e
        except httpx.RequestError as e:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            raise ServiceUnavailableError(
                service_name=self.base_url,
                details={"error": str(e)},
            ) from e

    async def put(
        self,
        endpoint: str,
        json: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Make PUT request."""
        await self._check_circuit_breaker()

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            response = await self._make_request("PUT", url, json=json, **kwargs)
            response.raise_for_status()
            if self.circuit_breaker:
                self.circuit_breaker.record_success()
            return response.json()
        except httpx.TimeoutException as e:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            raise ServiceTimeoutError(
                service_name=self.base_url,
                timeout_seconds=self.timeout,
            ) from e
        except httpx.RequestError as e:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            raise ServiceUnavailableError(
                service_name=self.base_url,
                details={"error": str(e)},
            ) from e

    async def delete(
        self,
        endpoint: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """Make DELETE request."""
        await self._check_circuit_breaker()

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            response = await self._make_request("DELETE", url, **kwargs)
            response.raise_for_status()
            if self.circuit_breaker:
                self.circuit_breaker.record_success()
            return response.json()
        except httpx.TimeoutException as e:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            raise ServiceTimeoutError(
                service_name=self.base_url,
                timeout_seconds=self.timeout,
            ) from e
        except httpx.RequestError as e:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            raise ServiceUnavailableError(
                service_name=self.base_url,
                details={"error": str(e)},
            ) from e

    async def patch(
        self,
        endpoint: str,
        json: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Make PATCH request."""
        await self._check_circuit_breaker()

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            response = await self._make_request("PATCH", url, json=json, **kwargs)
            response.raise_for_status()
            if self.circuit_breaker:
                self.circuit_breaker.record_success()
            return response.json()
        except httpx.TimeoutException as e:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            raise ServiceTimeoutError(
                service_name=self.base_url,
                timeout_seconds=self.timeout,
            ) from e
        except httpx.RequestError as e:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            raise ServiceUnavailableError(
                service_name=self.base_url,
                details={"error": str(e)},
            ) from e
