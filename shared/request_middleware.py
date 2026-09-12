"""Shared correlation, transport-transition, and request-latency middleware."""

from __future__ import annotations

import logging
import re
import time
import uuid

from config.ssl_config import get_tls_config
from shared.utils.logging_setup import install_log_redaction
from shared.utils.trace_context import trace_id_context


CORRELATION_HEADER = "X-Correlation-ID"


class RequestObservabilityMiddleware:
    def __init__(self, app, service_name: str) -> None:
        self.app = app
        self.service_name = service_name
        self.logger = logging.getLogger(f"{service_name}.request")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_id = headers.get(b"x-correlation-id") or headers.get(b"x-request-id")
        correlation_id = raw_id.decode("utf-8", errors="replace") if raw_id else str(uuid.uuid4())
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", correlation_id):
            correlation_id = str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = correlation_id
        token = trace_id_context.set(correlation_id)
        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "")
        scheme = scope.get("scheme", "http")
        started = time.perf_counter()
        status_code = 500

        if scheme == "http" and get_tls_config().plaintext_transition:
            self.logger.warning(
                "PLAINTEXT_TRANSITION service=%s method=%s path=%s correlation_id=%s",
                self.service_name, method, path, correlation_id,
            )

        async def send_observed(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = [
                    (key, value) for key, value in message.get("headers", [])
                    if key.lower() not in {b"x-correlation-id", b"x-request-id"}
                ]
                response_headers.append((b"x-correlation-id", correlation_id.encode("ascii")))
                response_headers.append((b"x-request-id", correlation_id.encode("ascii")))
                message["headers"] = response_headers
            await send(message)

        self.logger.info(
            "REQUEST_START service=%s method=%s path=%s correlation_id=%s",
            self.service_name, method, path, correlation_id,
        )
        try:
            await self.app(scope, receive, send_observed)
        finally:
            duration_ms = (time.perf_counter() - started) * 1000.0
            self.logger.info(
                "REQUEST_END service=%s method=%s path=%s status=%s duration_ms=%.3f correlation_id=%s",
                self.service_name, method, path, status_code, duration_ms, correlation_id,
            )
            trace_id_context.reset(token)


def install_request_observability(app, service_name: str) -> None:
    """Install last so rejected requests pass through the observer, too."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    install_log_redaction()
    app.add_middleware(RequestObservabilityMiddleware, service_name=service_name)
