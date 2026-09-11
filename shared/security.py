"""Single Phase 5 trust boundary shared by all NEXI services."""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterable
from typing import Optional

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from shared.api_errors import error_response


INTERNAL_TOKEN_HEADER = "X-NEXI-Service-Token"
TRUSTED_USER_HEADER = "X-NEXI-Trusted-User-ID"
_TRUE = {"1", "true", "yes", "on"}


def auth_enforcement_enabled() -> bool:
    return os.getenv("AUTH_ENFORCEMENT_ENABLED", "false").strip().lower() in _TRUE


def _internal_token() -> str:
    return os.getenv("NEXI_INTERNAL_SERVICE_TOKEN", "").strip()


def internal_service_headers(user_id: Optional[str] = None) -> dict[str, str]:
    """Build trusted internal headers without forwarding an end-user token."""
    if not auth_enforcement_enabled():
        return {}
    token = _internal_token()
    if not token:
        raise RuntimeError("NEXI_INTERNAL_SERVICE_TOKEN is required when auth enforcement is enabled")
    headers = {INTERNAL_TOKEN_HEADER: token}
    if user_id:
        headers[TRUSTED_USER_HEADER] = user_id
    return headers


def merge_internal_headers(
    headers: Optional[dict[str, str]] = None, *, user_id: Optional[str] = None
) -> dict[str, str]:
    merged = dict(headers or {})
    merged.update(internal_service_headers(user_id))
    return merged


def is_internal_request(request: Request) -> bool:
    if not auth_enforcement_enabled():
        return True
    expected = _internal_token()
    supplied = request.headers.get(INTERNAL_TOKEN_HEADER, "")
    return bool(expected and supplied and secrets.compare_digest(supplied, expected))


async def require_internal_service(request: Request) -> Optional[str]:
    if not is_internal_request(request):
        raise HTTPException(status_code=401, detail="Valid internal service credential required")
    return request.headers.get(TRUSTED_USER_HEADER)


def trusted_internal_user(request: Request) -> Optional[str]:
    if not is_internal_request(request):
        return None
    return request.headers.get(TRUSTED_USER_HEADER)


def allowed_origins() -> list[str]:
    raw = os.getenv("NEXI_ALLOWED_ORIGINS", "http://localhost:3000")
    origins = [value.strip() for value in raw.split(",") if value.strip()]
    if not origins or "*" in origins:
        raise RuntimeError("NEXI_ALLOWED_ORIGINS must contain explicit origins and cannot contain '*'")
    return origins


def is_protected_path(path: str, prefixes: Iterable[str]) -> bool:
    return any(path == prefix or path.startswith(prefix.rstrip("/") + "/") for prefix in prefixes)


class InternalRouteAuthMiddleware(BaseHTTPMiddleware):
    """Apply shared service authentication to declared internal route families."""

    def __init__(self, app, protected_prefixes: Iterable[str]):
        super().__init__(app)
        self.protected_prefixes = tuple(protected_prefixes)

    async def dispatch(self, request: Request, call_next):
        if (
            request.method != "OPTIONS"
            and auth_enforcement_enabled()
            and is_protected_path(request.url.path, self.protected_prefixes)
            and not is_internal_request(request)
        ):
            return error_response(request, 401, "Valid internal service credential required")
        return await call_next(request)


class UploadGuardMiddleware(BaseHTTPMiddleware):
    """Reject oversized or mistyped upload requests before consuming ASGI body bytes."""

    def __init__(self, app, rules: dict[str, tuple[int, tuple[str, ...]]]):
        super().__init__(app)
        self.rules = rules

    async def dispatch(self, request: Request, call_next):
        rule = next(
            (value for prefix, value in self.rules.items() if is_protected_path(request.url.path, (prefix,))),
            None,
        )
        if request.method in {"POST", "PUT", "PATCH"} and rule:
            max_bytes, allowed_types = rule
            content_type = request.headers.get("content-type", "").lower()
            if not any(content_type.startswith(value) for value in allowed_types):
                return error_response(request, 415, "Unsupported upload content type")
            raw_length = request.headers.get("content-length")
            if raw_length is None:
                return error_response(request, 411, "Content-Length required")
            try:
                content_length = int(raw_length)
            except ValueError:
                return error_response(request, 400, "Invalid Content-Length")
            if content_length > max_bytes:
                return error_response(request, 413, "Upload exceeds configured size limit")
        return await call_next(request)
