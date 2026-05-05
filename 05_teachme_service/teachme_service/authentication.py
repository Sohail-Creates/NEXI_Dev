"""
Authentication Module for TeachMe Service
Supports:
- JWT token-based authentication
- API key authentication (for service-to-service)
- Token generation and verification
- API key management
"""

import os
import secrets
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from functools import wraps

try:
    import jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    logger_temp = logging.getLogger(__name__)
    logger_temp.warning("PyJWT not installed - JWT features disabled")

logger = logging.getLogger(__name__)

# Configuration from environment
JWT_SECRET_KEY = os.getenv("TEACHME_JWT_SECRET", "change-this-in-production-" + secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))
AUTH_ENABLED = os.getenv("TEACHME_AUTH_ENABLED", "true").lower() == "true"


class AuthenticationManager:
    """Manages authentication tokens and API keys"""
    
    def __init__(self):
        self.jwt_secret = JWT_SECRET_KEY
        self.jwt_algorithm = JWT_ALGORITHM
        self.jwt_expiry = timedelta(hours=JWT_EXPIRY_HOURS)
        
        # In-memory API keys (in production, use database)
        # Format: {api_key: {name, created_at, last_used, is_active}}
        self.api_keys: Dict[str, Dict[str, Any]] = {}
        
        # Trusted service keys (hardcoded for now, move to DB next sprint)
        self._init_default_api_keys()
        
        logger.info(f"AuthenticationManager initialized (JWT: {JWT_AVAILABLE}, AUTH_ENABLED: {AUTH_ENABLED})")
    
    def _init_default_api_keys(self) -> None:
        """Initialize default API keys for trusted services"""
        # Central Server key
        central_server_key = os.getenv("CENTRAL_SERVER_API_KEY", "central-server-default-key-" + secrets.token_hex(16))
        self.api_keys[central_server_key] = {
            "name": "central_server",
            "created_at": datetime.utcnow().isoformat(),
            "last_used": None,
            "is_active": True,
        }
        
        # Admin key for testing/maintenance
        admin_key = os.getenv("TEACHME_ADMIN_KEY", "admin-default-key-" + secrets.token_hex(16))
        self.api_keys[admin_key] = {
            "name": "admin",
            "created_at": datetime.utcnow().isoformat(),
            "last_used": None,
            "is_active": True,
        }
        
        logger.debug(f"Initialized {len(self.api_keys)} default API keys")
    
    def generate_jwt_token(self, user_id: str, additional_claims: Optional[Dict] = None) -> str:
        """
        Generate JWT token for user
        
        Args:
            user_id: User identifier
            additional_claims: Additional JWT claims
            
        Returns:
            JWT token string
        """
        if not JWT_AVAILABLE:
            raise RuntimeError("JWT not available - install PyJWT")
        
        now = datetime.utcnow()
        payload = {
            "user_id": user_id,
            "iat": now,
            "exp": now + self.jwt_expiry,
            "type": "access_token",
        }
        
        if additional_claims:
            payload.update(additional_claims)
        
        token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
        logger.debug(f"Generated JWT token for user: {user_id}")
        
        return token
    
    def verify_jwt_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify and decode JWT token
        
        Args:
            token: JWT token string
            
        Returns:
            Token payload dict or None if invalid
        """
        if not JWT_AVAILABLE:
            logger.warning("JWT verification requested but JWT not available")
            return None
        
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("JWT token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token: {e}")
            return None
    
    def create_api_key(self, service_name: str) -> str:
        """
        Create new API key for service
        
        Args:
            service_name: Name of service
            
        Returns:
            API key string
        """
        api_key = f"teachme_{service_name}_{secrets.token_urlsafe(32)}"
        
        self.api_keys[api_key] = {
            "name": service_name,
            "created_at": datetime.utcnow().isoformat(),
            "last_used": None,
            "is_active": True,
        }
        
        logger.info(f"Created API key for service: {service_name}")
        return api_key
    
    def verify_api_key(self, api_key: str) -> bool:
        """
        Verify API key is valid and active
        
        Args:
            api_key: API key string
            
        Returns:
            True if valid and active
        """
        if api_key not in self.api_keys:
            logger.warning(f"API key verification failed: key not found")
            return False
        
        key_info = self.api_keys[api_key]
        
        if not key_info.get("is_active", False):
            logger.warning(f"API key verification failed: key inactive")
            return False
        
        # Update last_used timestamp
        self.api_keys[api_key]["last_used"] = datetime.utcnow().isoformat()
        
        return True
    
    def revoke_api_key(self, api_key: str) -> bool:
        """
        Revoke API key
        
        Args:
            api_key: API key to revoke
            
        Returns:
            True if revoked successfully
        """
        if api_key not in self.api_keys:
            logger.warning(f"Revoke failed: API key not found")
            return False
        
        self.api_keys[api_key]["is_active"] = False
        logger.info(f"Revoked API key: {self.api_keys[api_key]['name']}")
        
        return True
    
    def get_api_key_info(self, api_key: str) -> Optional[Dict[str, Any]]:
        """Get information about API key"""
        if api_key not in self.api_keys:
            return None
        
        key_info = self.api_keys[api_key].copy()
        key_info["key_masked"] = f"{api_key[:10]}...{api_key[-6:]}"
        
        return key_info
    
    def list_api_keys(self) -> Dict[str, Dict[str, Any]]:
        """List all API keys with masked keys"""
        result = {}
        for api_key, info in self.api_keys.items():
            masked_info = info.copy()
            masked_info["key_masked"] = f"{api_key[:10]}...{api_key[-6:]}"
            result[api_key] = masked_info
        
        return result


# Global instance
_auth_manager: Optional[AuthenticationManager] = None


def get_auth_manager() -> AuthenticationManager:
    """Get or create authentication manager"""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthenticationManager()
    return _auth_manager


def require_api_key(func):
    """
    Decorator for routes requiring API key authentication
    
    Usage:
        @app.get("/protected")
        @require_api_key
        async def protected_route(request: Request):
            return {"message": "protected data"}
    """
    @wraps(func)
    async def wrapper(request, *args, **kwargs):
        if not AUTH_ENABLED:
            # Auth disabled, allow all requests
            return await func(request, *args, **kwargs)
        
        # Extract API key from header
        api_key = request.headers.get("X-API-Key")
        
        if not api_key:
            logger.warning("Protected endpoint accessed without API key")
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="API key required")
        
        # Verify API key
        auth_manager = get_auth_manager()
        if not auth_manager.verify_api_key(api_key):
            logger.warning(f"Invalid API key attempted")
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Invalid or inactive API key")
        
        # Add API key info to request
        request.state.api_key = api_key
        request.state.api_key_info = auth_manager.get_api_key_info(api_key)
        
        return await func(request, *args, **kwargs)
    
    return wrapper


def require_jwt(func):
    """
    Decorator for routes requiring JWT authentication
    
    Usage:
        @app.get("/user-data")
        @require_jwt
        async def user_data(request: Request):
            user_id = request.state.user_id
            return {"user_id": user_id}
    """
    @wraps(func)
    async def wrapper(request, *args, **kwargs):
        if not AUTH_ENABLED or not JWT_AVAILABLE:
            # Auth disabled, allow all requests
            return await func(request, *args, **kwargs)
        
        # Extract JWT from Authorization header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            logger.warning("Protected endpoint accessed without JWT")
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Bearer token required")
        
        token = auth_header[7:]  # Remove "Bearer " prefix
        
        # Verify JWT
        auth_manager = get_auth_manager()
        payload = auth_manager.verify_jwt_token(token)
        
        if not payload:
            logger.warning("Invalid JWT token attempted")
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Invalid or expired JWT token")
        
        # Add user info to request
        request.state.user_id = payload.get("user_id")
        request.state.jwt_payload = payload
        
        return await func(request, *args, **kwargs)
    
    return wrapper


def init_authentication() -> AuthenticationManager:
    """Initialize authentication system"""
    auth_manager = get_auth_manager()
    logger.info("Authentication system initialized")
    
    # Log available keys (without revealing full keys)
    available_keys = auth_manager.list_api_keys()
    logger.debug(f"Loaded {len(available_keys)} API keys")
    
    return auth_manager
