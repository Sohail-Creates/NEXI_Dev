"""Typed Central client for the LLM service."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx
from config.ssl_config import client_verify
from shared.security import internal_service_headers

from shared.config import ServiceConfig
from shared.focus_mode import FocusModeClient
from shared.models.api_response import ErrorCode
from shared.utils.circuit_breaker import CircuitBreaker


class LLMServiceClient:
    """Call the LLM service while preserving Phase 3 cooperative yielding."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 150.0,
        max_retries: int = 1,
        focus_mode_client=None,
    ):
        self.base_url = (base_url or ServiceConfig.get_service_url("llm")).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.logger = logging.getLogger(__name__)
        self.focus_mode_client = focus_mode_client or FocusModeClient()
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=15,
            name="llm_service",
        )

    async def cooperate_with_focus(self, request_context="conversation"):
        return await self.focus_mode_client.async_defer_if_needed(request_context)

    async def generate_response(
        self,
        query: str,
        language: str = "en",
        user_context: Optional[Dict[str, Any]] = None,
        vision_context: Optional[Dict[str, Any]] = None,
        knowledge_items: Optional[List[Dict[str, Any]]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        max_response_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        request_context: str = "conversation",
    ) -> Tuple[bool, Dict[str, Any]]:
        """Generate text; all failures remain failures and never become canned text."""
        await self.cooperate_with_focus(request_context)
        if not self.circuit_breaker.is_available():
            return False, {
                "error": "LLM service unavailable (circuit breaker open)",
                "error_code": ErrorCode.SERVICE_UNAVAILABLE,
            }

        payload: Dict[str, Any] = {"query": query, "language": language}
        if max_response_tokens is not None:
            payload["max_tokens"] = max_response_tokens
        if temperature is not None:
            payload["temperature"] = temperature

        try:
            async with httpx.AsyncClient(verify=client_verify(self.base_url)) as client:
                if hasattr(client, "headers"):
                    client.headers.update(internal_service_headers())
                response = await asyncio.wait_for(
                    client.post(
                        f"{self.base_url}/api/v1/generate",
                        json=payload,
                        timeout=self.timeout,
                    ),
                    timeout=90.0,
                )
            if response.status_code != 200:
                self.circuit_breaker.record_failure()
                return False, {"error": f"LLM service HTTP {response.status_code}"}

            result = response.json()
            if not result.get("success"):
                self.circuit_breaker.record_failure()
                return False, {"error": result.get("error", "LLM generation failed")}

            self.circuit_breaker.record_success()
            return True, {
                "response": result.get("text", ""),
                "language": language,
                "metadata": result.get("metadata", {}),
            }
        except (asyncio.TimeoutError, httpx.TimeoutException):
            self.circuit_breaker.record_failure()
            return False, {"error": "LLM service timeout"}
        except (httpx.ConnectError, httpx.RequestError):
            self.circuit_breaker.record_failure()
            return False, {"error": "LLM service unavailable"}
        except Exception as exc:
            self.circuit_breaker.record_failure(exc)
            self.logger.error("LLM service error: %s", exc, exc_info=True)
            return False, {"error": str(exc)}

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(verify=client_verify(self.base_url)) as client:
                response = await client.get(f"{self.base_url}/api/v1/health", timeout=5.0)
            if response.status_code != 200:
                return False
            data = response.json()
            healthy = data.get("status") == "healthy" or data.get("openrouter") is True
            if healthy:
                self.circuit_breaker.record_success()
            return healthy
        except Exception as exc:
            self.logger.warning("Health check failed: %s", exc)
            return False

    async def get_model_info(self) -> Optional[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(verify=client_verify(self.base_url)) as client:
                response = await client.get(f"{self.base_url}/api/v1/model-info", timeout=5.0)
            return response.json() if response.status_code == 200 else None
        except Exception as exc:
            self.logger.warning("Failed to get model info: %s", exc)
            return None

    def get_circuit_breaker_status(self) -> Dict[str, Any]:
        return {
            "is_closed": self.circuit_breaker.is_available(),
            "failure_count": self.circuit_breaker.failure_count,
            "success_count": self.circuit_breaker.success_count,
            "state": self.circuit_breaker.state.value,
        }
