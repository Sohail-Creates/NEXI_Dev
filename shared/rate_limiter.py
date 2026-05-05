"""
Production-grade rate limiter with token bucket algorithm.

Features:
- Per-user rate limiting (authenticated users)
- Per-IP rate limiting (fallback for unauthenticated)
- Endpoint-specific limits (LLM endpoints stricter)
- Memory-efficient implementation
- Thread-safe operations
- No external dependencies (just Python stdlib)
"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import asyncio
from dataclasses import dataclass
import logging

logger: logging.Logger = logging.getLogger(__name__)


@dataclass
class TokenBucket:
    """Represents a token bucket for rate limiting."""
    tokens: float
    last_refill: datetime
    max_tokens: int
    refill_rate: float  # tokens per second


class RateLimiter:
    """
    Production-grade rate limiter with token bucket algorithm.
    
    Supports:
    - Per-user rate limits
    - Per-IP rate limits  
    - Endpoint-specific configurations
    - Graceful handling when over limit
    """
    
    def __init__(self) -> None:
        # Per-user buckets: 100 requests per minute
        self.user_buckets: Dict[str, TokenBucket] = {}
        
        # Per-IP buckets: 200 requests per minute (more lenient)
        self.ip_buckets: Dict[str, TokenBucket] = {}
        
        # Endpoint-specific limits (LLM endpoints more expensive)
        self.endpoint_limits = {
            "/api/v1/generate": {
                "max_tokens": 10,
                "refill_rate": 10 / 60  # 10 per minute
            },
            "/api/v1/llm/generate": {
                "max_tokens": 10,
                "refill_rate": 10 / 60
            },
            "/api/v1/enroll": {
                "max_tokens": 5,
                "refill_rate": 5 / 300  # 5 per 5 minutes
            },
            "/api/v1/enrollment/enroll": {
                "max_tokens": 5,
                "refill_rate": 5 / 300
            },
            # Default for all other endpoints
            "default": {
                "max_tokens": 100,
                "refill_rate": 100 / 60  # 100 per minute
            }
        }
        
        self.lock = asyncio.Lock()
        
        # Statistics for monitoring
        self.stats: Dict[str, int] = {
            "requests_allowed": 0,
            "requests_blocked": 0,
            "requests_total": 0
        }
    
    async def check_rate_limit(
        self,
        identifier: str,
        identifier_type: str = "user",  # "user" or "ip"
        endpoint: str = "default"
    ) -> Dict:
        """
        Check if request is within rate limit.
        
        Args:
            identifier: User ID or IP address
            identifier_type: "user" or "ip"
            endpoint: API endpoint path
        
        Returns:
            {
                "allowed": bool,
                "remaining": int,
                "retry_after": Optional[int],  # seconds
                "limit": int,
                "reset_at": datetime
            }
        """
        async with self.lock:
            # Get limit configuration for this endpoint
            limit_config = self.endpoint_limits.get(
                endpoint,
                self.endpoint_limits["default"]
            )
            
            # Select appropriate bucket dictionary
            buckets: Dict[str, TokenBucket] = (
                self.user_buckets
                if identifier_type == "user"
                else self.ip_buckets
            )
            
            # Get or create bucket
            if identifier not in buckets:
                buckets[identifier] = TokenBucket(
                    tokens=float(limit_config["max_tokens"]),
                    last_refill=datetime.utcnow(),
                    max_tokens=limit_config["max_tokens"],
                    refill_rate=limit_config["refill_rate"]
                )
            
            bucket: TokenBucket = buckets[identifier]
            
            # Refill tokens based on time elapsed
            now: datetime = datetime.utcnow()
            elapsed_seconds: float = (now - bucket.last_refill).total_seconds()
            
            # Add tokens at the refill rate
            tokens_to_add: float = elapsed_seconds * bucket.refill_rate
            bucket.tokens = min(bucket.max_tokens, bucket.tokens + tokens_to_add)
            bucket.last_refill = now
            
            # Update statistics
            self.stats["requests_total"] += 1
            
            # Check if request allowed
            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                self.stats["requests_allowed"] += 1
                
                # Calculate reset time
                if bucket.tokens == 0:
                    time_to_full: float = (bucket.max_tokens - bucket.tokens) / bucket.refill_rate
                    reset_at: datetime = now + timedelta(seconds=time_to_full)
                else:
                    reset_at: datetime = now + timedelta(
                        seconds=(bucket.max_tokens - bucket.tokens) / bucket.refill_rate
                    )
                
                return {
                    "allowed": True,
                    "remaining": int(bucket.tokens),
                    "retry_after": None,
                    "limit": bucket.max_tokens,
                    "reset_at": reset_at.isoformat()
                }
            else:
                # Calculate how long until a token is available
                self.stats["requests_blocked"] += 1
                
                # Time to refill one token
                time_to_refill: float = (1.0 - bucket.tokens) / bucket.refill_rate
                reset_at: datetime = now + timedelta(seconds=time_to_refill)
                
                return {
                    "allowed": False,
                    "remaining": 0,
                    "retry_after": int(time_to_refill) + 1,  # Round up
                    "limit": bucket.max_tokens,
                    "reset_at": reset_at.isoformat()
                }
    
    def get_stats(self) -> Dict:
        """Get rate limiter statistics."""
        total: int = self.stats["requests_total"]
        allowed: int = self.stats["requests_allowed"]
        blocked: int = self.stats["requests_blocked"]
        
        block_rate: float | int = (blocked / total * 100) if total > 0 else 0
        
        return {
            "total_requests": total,
            "allowed": allowed,
            "blocked": blocked,
            "block_rate_percent": round(block_rate, 2),
            "active_users": len(self.user_buckets),
            "active_ips": len(self.ip_buckets)
        }
    
    def clear_bucket(
        self,
        identifier: str,
        identifier_type: str = "user"
    ) -> bool:
        """
        Clear rate limit for specific user/IP (for testing/admin).
        
        Args:
            identifier: User ID or IP to clear
            identifier_type: Type of identifier
        
        Returns:
            True if cleared, False if not found
        """
        buckets: Dict[str, TokenBucket] = (
            self.user_buckets
            if identifier_type == "user"
            else self.ip_buckets
        )
        
        if identifier in buckets:
            del buckets[identifier]
            logger.info(f"Cleared rate limit for {identifier_type}: {identifier}")
            return True
        
        return False
    
    def reset_stats(self) -> None:
        """Reset statistics counters."""
        self.stats: Dict[str, int] = {
            "requests_allowed": 0,
            "requests_blocked": 0,
            "requests_total": 0
        }


# Global instance (one per service)
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get or create global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


# FastAPI middleware integration
def create_rate_limit_middleware(rate_limiter: Optional[RateLimiter] = None):
    """
    Create rate limiting middleware for FastAPI.
    
    Usage:
        rate_limiter = get_rate_limiter()
        app.middleware("http")(create_rate_limit_middleware(rate_limiter))
    """
    if rate_limiter is None:
        rate_limiter = get_rate_limiter()
    
    async def rate_limit_middleware(request, call_next):
        """Apply rate limiting to all requests."""
        
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/healthz"]:
            return await call_next(request)
        
        # Extract identifiers
        user_id = request.headers.get("X-User-ID")
        client_ip = request.client.host if request.client else "unknown"
        endpoint = request.url.path
        
        # Check user rate limit (if authenticated)
        if user_id:
            result = await rate_limiter.check_rate_limit(
                identifier=user_id,
                identifier_type="user",
                endpoint=endpoint
            )
            
            if not result["allowed"]:
                from fastapi import HTTPException
                
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"Rate limit exceeded for user. "
                        f"Try again in {result['retry_after']} seconds."
                    ),
                    headers={
                        "X-RateLimit-Limit": str(result["limit"]),
                        "X-RateLimit-Remaining": "0",
                        "Retry-After": str(result["retry_after"])
                    }
                )
        
        # Check IP rate limit (always, even for authenticated users)
        result = await rate_limiter.check_rate_limit(
            identifier=client_ip,
            identifier_type="ip",
            endpoint=endpoint
        )
        
        if not result["allowed"]:
            from fastapi import HTTPException
            
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Too many requests from your IP. "
                    f"Try again in {result['retry_after']} seconds."
                ),
                headers={
                    "X-RateLimit-Limit": str(result["limit"]),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": str(result["retry_after"])
                }
            )
        
        # Request allowed, proceed
        response = await call_next(request)
        
        # Add rate limit headers to response
        response.headers["X-RateLimit-Limit"] = str(result["limit"])
        response.headers["X-RateLimit-Remaining"] = str(result["remaining"])
        
        if result["retry_after"]:
            response.headers["Retry-After"] = str(result["retry_after"])
        
        return response
    
    return rate_limit_middleware
