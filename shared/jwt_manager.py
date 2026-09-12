"""
JWT Session Management with Token Timeouts
Implements access tokens, refresh tokens, and session tokens with expiration
"""

import os
import secrets
try:
    import jwt
    JWT_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised by the fail-closed test
    jwt = None
    JWT_AVAILABLE = False
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import logging
from dataclasses import dataclass, field
from enum import Enum
from fastapi import HTTPException, Request
from shared.credential_rotation import SecretPair

logger = logging.getLogger(__name__)


class TokenType(str, Enum):
    """Types of JWT tokens"""
    ACCESS = "access"        # Short-lived, for API requests
    REFRESH = "refresh"      # Long-lived, for refreshing access token
    SESSION = "session"      # Session token with stay-logged-in
    API_KEY = "api_key"      # API key for service-to-service


@dataclass
class TokenConfig:
    """Token configuration"""
    # Expiration times
    access_token_expire_minutes: int = 30  # 30 minutes
    refresh_token_expire_days: int = 7     # 7 days
    session_token_expire_minutes: int = field(
        default_factory=lambda: int(os.getenv("NEXI_SESSION_TOKEN_EXPIRE_MINUTES", "30"))
    )
    
    # JWT settings
    secret_key: str = field(default_factory=lambda: os.getenv("NEXI_JWT_SECRET", "").strip())
    previous_secret_key: str = field(
        default_factory=lambda: os.getenv("NEXI_JWT_SECRET_PREVIOUS", "").strip()
    )
    algorithm: str = "HS256"
    
    # Token validation
    verify_exp: bool = True
    verify_iss: bool = True  # Verify issuer
    issuer: str = "nexi-system"
    
    # Session
    max_concurrent_sessions: int = 5
    revoke_on_logout: bool = True


class JWTManager:
    """Manage JWT tokens with expiration"""
    
    def __init__(self, config: Optional[TokenConfig] = None):
        """
        Initialize JWT manager
        
        Args:
            config: Token configuration
        """
        self.config = config or TokenConfig()
        self.revoked_tokens: set[str] = set()  # Revoked token JTIs
        self.active_sessions: Dict[str, list[str]] = {}  # user_id -> [token_jti, ...]

    def _require_configuration(self) -> None:
        if not JWT_AVAILABLE or jwt is None:
            raise RuntimeError("PyJWT is required; authentication fails closed")
        if not self.config.secret_key:
            raise RuntimeError("NEXI_JWT_SECRET is required for token operations")

    def _verification_keys(self) -> tuple[str, ...]:
        return SecretPair(self.config.secret_key, self.config.previous_secret_key or None).active

    def _decode(self, token: str, *, verify_exp: bool = True) -> Dict[str, Any]:
        last_error = None
        for secret_key in self._verification_keys():
            try:
                return jwt.decode(
                    token,
                    secret_key,
                    algorithms=[self.config.algorithm],
                    options={"verify_exp": verify_exp, "verify_iss": self.config.verify_iss},
                    issuer=self.config.issuer if self.config.verify_iss else None,
                )
            except jwt.InvalidTokenError as exc:
                last_error = exc
        raise last_error or jwt.InvalidTokenError("No JWT verification key configured")
    
    def create_access_token(
        self,
        subject: str,  # User ID or service name
        additional_claims: Optional[Dict[str, Any]] = None,
        expires_in_minutes: Optional[int] = None
    ) -> Dict[str, str]:
        """
        Create an access token (short-lived).
        
        Args:
            subject: Token subject (user ID)
            additional_claims: Additional JWT claims
            expires_in_minutes: Custom expiration time
        
        Returns:
            Dictionary with token and expiration info
        """
        self._require_configuration()
        now = datetime.now(timezone.utc)
        expires_in = expires_in_minutes or self.config.access_token_expire_minutes
        expiration = now + timedelta(minutes=expires_in)
        
        claims = {
            "sub": subject,
            "type": TokenType.ACCESS.value,
            "iat": now,
            "exp": expiration,
            "iss": self.config.issuer,
        }
        
        if additional_claims:
            claims.update(additional_claims)
        
        # Generate JTI (JWT ID) for token tracking
        import uuid
        claims["jti"] = str(uuid.uuid4())
        
        token = jwt.encode(
            claims,
            self.config.secret_key,
            algorithm=self.config.algorithm
        )
        
        logger.info(f"JWT: Created access token for {subject}, expires in {expires_in} minutes")
        
        return {
            "token": token,
            "type": "bearer",
            "expires_in": expires_in * 60,  # In seconds
            "expires_at": expiration.isoformat(),
            "jti": claims["jti"]
        }
    
    def create_refresh_token(
        self,
        subject: str,
        additional_claims: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """
        Create a refresh token (long-lived).
        
        Args:
            subject: Token subject (user ID)
            additional_claims: Additional JWT claims
        
        Returns:
            Dictionary with token and expiration info
        """
        self._require_configuration()
        now = datetime.now(timezone.utc)
        expiration = now + timedelta(days=self.config.refresh_token_expire_days)
        
        import uuid
        jti = str(uuid.uuid4())
        
        claims = {
            "sub": subject,
            "type": TokenType.REFRESH.value,
            "iat": now,
            "exp": expiration,
            "iss": self.config.issuer,
            "jti": jti
        }
        
        if additional_claims:
            claims.update(additional_claims)
        
        # Track session
        if subject not in self.active_sessions:
            self.active_sessions[subject] = []
        
        if len(self.active_sessions[subject]) >= self.config.max_concurrent_sessions:
            # Revoke oldest session
            oldest_jti = self.active_sessions[subject].pop(0)
            self.revoked_tokens.add(oldest_jti)
            logger.info(f"JWT: Revoked oldest session for {subject}")
        
        self.active_sessions[subject].append(jti)
        
        token = jwt.encode(
            claims,
            self.config.secret_key,
            algorithm=self.config.algorithm
        )
        
        logger.info(f"JWT: Created refresh token for {subject}, expires in {self.config.refresh_token_expire_days} days")
        
        return {
            "token": token,
            "type": "bearer",
            "expires_in": self.config.refresh_token_expire_days * 24 * 60 * 60,  # In seconds
            "expires_at": expiration.isoformat(),
            "jti": jti
        }
    
    def create_session_token(
        self,
        subject: str,
        additional_claims: Optional[Dict[str, Any]] = None,
        expires_in_minutes: Optional[float] = None,
    ) -> Dict[str, str]:
        """
        Create a session token (for "stay logged in").
        
        Args:
            subject: Token subject (user ID)
            additional_claims: Additional JWT claims
        
        Returns:
            Dictionary with token and expiration info
        """
        self._require_configuration()
        now = datetime.now(timezone.utc)
        lifetime = (
            self.config.session_token_expire_minutes
            if expires_in_minutes is None
            else expires_in_minutes
        )
        expiration = now + timedelta(minutes=lifetime)
        
        import uuid
        claims = {
            "sub": subject,
            "type": TokenType.SESSION.value,
            "iat": now,
            "exp": expiration,
            "iss": self.config.issuer,
            "jti": str(uuid.uuid4())
        }
        
        if additional_claims:
            claims.update(additional_claims)
        
        token = jwt.encode(
            claims,
            self.config.secret_key,
            algorithm=self.config.algorithm
        )
        
        logger.info("JWT: Created session token for %s, expires in %s minutes", subject, lifetime)
        
        return {
            "token": token,
            "type": "bearer",
            "expires_in": int(lifetime * 60),
            "expires_at": expiration.isoformat(),
            "jti": claims["jti"]
        }
    
    def verify_token(self, token: str, token_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Verify and decode a token.
        
        Args:
            token: JWT token string
            token_type: Expected token type (access, refresh, session)
        
        Returns:
            Decoded token claims
        
        Raises:
            jwt.InvalidTokenError: If token is invalid or expired
        """
        self._require_configuration()
        try:
            payload = self._decode(token, verify_exp=self.config.verify_exp)
            
            # Check if token is revoked
            if payload.get("jti") in self.revoked_tokens:
                logger.warning(f"JWT: Token with JTI {payload.get('jti')} is revoked")
                raise jwt.InvalidTokenError("Token has been revoked")
            
            # Verify token type if specified
            if token_type and payload.get("type") != token_type:
                logger.warning(f"JWT: Token type mismatch. Expected {token_type}, got {payload.get('type')}")
                raise jwt.InvalidTokenError(f"Invalid token type: {payload.get('type')}")
            
            logger.debug(f"JWT: Token verified for subject {payload.get('sub')}")
            return payload
        
        except jwt.ExpiredSignatureError as e:
            logger.warning(f"JWT: Token expired: {e}")
            raise jwt.ExpiredSignatureError("Token has expired")
        except jwt.InvalidTokenError as e:
            logger.warning(f"JWT: Invalid token: {e}")
            raise
    
    def refresh_access_token(self, refresh_token: str) -> Dict[str, str]:
        """
        Create a new access token using a refresh token.
        
        Args:
            refresh_token: Valid refresh token
        
        Returns:
            New access token
        
        Raises:
            jwt.InvalidTokenError: If refresh token is invalid
        """
        payload = self.verify_token(refresh_token, token_type=TokenType.REFRESH.value)
        
        return self.create_access_token(
            subject=payload["sub"],
            additional_claims={"refresh_from": payload.get("jti")}
        )
    
    def revoke_token(self, token: str) -> bool:
        """
        Revoke a token (add to blacklist).
        
        Args:
            token: JWT token to revoke
        
        Returns:
            True if revoked successfully
        """
        try:
            # Don't verify expiration for revocation
            payload = self._decode(token, verify_exp=False)
            
            jti = payload.get("jti")
            if jti:
                self.revoked_tokens.add(jti)
                logger.info(f"JWT: Revoked token with JTI {jti}")
                return True
        except jwt.InvalidTokenError as e:
            logger.error(f"JWT: Failed to revoke token: {e}")
        
        return False
    
    def logout_user(self, user_id: str) -> int:
        """
        Logout a user by revoking all their active sessions.
        
        Args:
            user_id: User ID
        
        Returns:
            Number of sessions revoked
        """
        sessions = self.active_sessions.get(user_id, [])
        count = len(sessions)
        
        for jti in sessions:
            self.revoked_tokens.add(jti)
        
        # Clear active sessions
        if user_id in self.active_sessions:
            del self.active_sessions[user_id]
        
        logger.info(f"JWT: Logged out user {user_id}, revoked {count} sessions")
        return count
    
    def get_active_sessions(self, user_id: str) -> int:
        """Get number of active sessions for a user"""
        return len(self.active_sessions.get(user_id, []))


# ============================================================================
# TOKEN MIDDLEWARE/DEPENDENCIES FOR FASTAPI
# ============================================================================

class TokenValidator:
    """Validate tokens in FastAPI"""
    
    def __init__(self, jwt_manager: JWTManager):
        """
        Initialize token validator
        
        Args:
            jwt_manager: JWT manager instance
        """
        self.jwt_manager = jwt_manager
    
    async def get_current_user(self, token: str) -> Dict[str, Any]:
        """
        Dependency for FastAPI to get current user from access token
        
        Args:
            token: Access token from Authorization header
        
        Returns:
            Token payload with user info
        
        Raises:
            HTTPException: If token is invalid
        """
        try:
            return self.jwt_manager.verify_token(token, token_type=TokenType.ACCESS.value)
        except jwt.InvalidTokenError as e:
            raise ValueError(f"Invalid access token: {e}")

    def validate_session_token(self, token: str) -> Dict[str, Any]:
        """Validate a user session token and return its immutable claims."""
        return self.jwt_manager.verify_token(token, token_type=TokenType.SESSION.value)
    
    async def validate_refresh_token(self, token: str) -> Dict[str, Any]:
        """Validate refresh token"""
        try:
            return self.jwt_manager.verify_token(token, token_type=TokenType.REFRESH.value)
        except jwt.InvalidTokenError as e:
            raise ValueError(f"Invalid refresh token: {e}")


# ============================================================================
# EXPORT
# ============================================================================

__all__ = [
    "TokenType",
    "TokenConfig",
    "JWTManager",
    "TokenValidator"
]


_jwt_manager: Optional[JWTManager] = None


def get_jwt_manager() -> JWTManager:
    global _jwt_manager
    if _jwt_manager is None:
        _jwt_manager = JWTManager()
    return _jwt_manager


def get_token_validator() -> TokenValidator:
    return TokenValidator(get_jwt_manager())


def bearer_token_from_request(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer ") or not header[7:].strip():
        raise HTTPException(status_code=401, detail="Bearer session token required")
    return header[7:].strip()


def require_session_claims(request: Request) -> Dict[str, Any]:
    """Validate only at an external boundary; internal calls use service trust."""
    from shared.security import auth_enforcement_enabled, is_internal_request, trusted_internal_user

    if not auth_enforcement_enabled():
        return {"sub": "auth-disabled", "type": TokenType.SESSION.value, "disabled": True}

    if is_internal_request(request):
        user_id = trusted_internal_user(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Trusted internal user context required")
        return {"sub": user_id, "type": TokenType.SESSION.value, "internal": True}
    try:
        return get_token_validator().validate_session_token(bearer_token_from_request(request))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired session token") from exc


def require_user_ownership(request: Request, user_id: str) -> Dict[str, Any]:
    from shared.security import auth_enforcement_enabled
    if not auth_enforcement_enabled():
        return {"sub": user_id, "type": TokenType.SESSION.value, "disabled": True}
    claims = require_session_claims(request)
    subject = str(claims.get("sub", ""))
    if not subject or not secrets.compare_digest(subject, user_id):
        raise HTTPException(status_code=403, detail="Token does not own requested user")
    return claims
