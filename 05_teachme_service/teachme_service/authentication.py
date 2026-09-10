"""TeachMe adapters for the single shared Phase 5 credential system."""

from __future__ import annotations

from fastapi import HTTPException, Request

from shared import jwt_manager
from shared.jwt_manager import require_session_claims
from shared.security import auth_enforcement_enabled, require_internal_service


AUTH_ENABLED = True


async def require_api_key(request: Request):
    """Compatibility name: require the shared NEXI internal service token."""
    return await require_internal_service(request)


async def require_jwt(request: Request):
    """Compatibility name: require the shared signed user session token."""
    if not jwt_manager.JWT_AVAILABLE or jwt_manager.jwt is None:
        raise HTTPException(status_code=503, detail="JWT validation unavailable")
    return require_session_claims(request)


def init_authentication():
    """Validate fail-closed prerequisites without creating a private registry."""
    if auth_enforcement_enabled():
        jwt_manager.get_jwt_manager()._require_configuration()
    return jwt_manager.get_token_validator()
