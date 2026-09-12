"""
Service URL Configuration

Provides centralized service URL management with environment variable support.
All services support fallback to localhost defaults, enabling:
- Local development (no env vars needed)
- Docker/Kubernetes deployment (env vars set)
- Multi-machine deployment (IPs provided via env vars)

Environment Variables:
  CENTRAL_SERVER_URL        - Central Server (default: http://localhost:8000)
  VISION_SERVICE_URL        - Vision Service (default: http://localhost:8001)
  AUDIO_SERVICE_URL         - Audio Service (default: http://localhost:8002)
  TTS_SERVICE_URL           - TTS Service (default: http://localhost:8003)
  TEACHME_SERVICE_URL       - TeachMe Service (default: http://localhost:8004)
  ENROLLMENT_SERVICE_URL    - Enrollment Service (default: http://localhost:8005)
  LLM_SERVICE_URL           - LLM Service (default: http://localhost:8006)

Usage:
  from shared.config import ServiceConfig
  
  # Get service URL (uses env var or localhost default)
  vision_url = ServiceConfig.get_service_url("vision")
  
  # Or directly:
  url = ServiceConfig.VISION_SERVICE_URL  # Evaluates env var or default
"""

import os
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ServiceConfig:
    """
    Centralized service URL configuration.
    
    Supports environment variables for deployment flexibility while maintaining
    localhost defaults for local development.
    """
    
    # Service name to environment variable mapping
    ENV_VAR_MAP = {
        "central": "CENTRAL_SERVER_URL",
        "vision": "VISION_SERVICE_URL",
        "audio": "AUDIO_SERVICE_URL",
        "tts": "TTS_SERVICE_URL",
        "teachme": "TEACHME_SERVICE_URL",
        "enrollment": "ENROLLMENT_SERVICE_URL",
        "llm": "LLM_SERVICE_URL"
    }
    
    # Localhost defaults (used if env var not set)
    DEFAULT_URLS = {
        "central": "https://localhost:8000",
        "vision": "https://localhost:8001",
        "audio": "https://localhost:8002",
        "tts": "https://localhost:8003",
        "teachme": "https://localhost:8004",
        "enrollment": "https://localhost:8005",
        "llm": "https://localhost:8006"
    }
    
    # Cache for resolved URLs (avoid repeated env var lookups)
    _url_cache: Dict[str, str] = {}
    
    @classmethod
    def get_service_url(cls, service_name: str, use_cache: bool = True) -> str:
        """
        Get service URL from environment variable or fallback to localhost.
        
        Args:
            service_name: Service identifier ("central", "vision", "audio", etc.)
            use_cache: Use cached URL if available (recommended for performance)
        
        Returns:
            Complete service URL (e.g., "http://localhost:8001")
        
        Raises:
            ValueError: If service_name is not recognized
        
        Examples:
            url = ServiceConfig.get_service_url("vision")  # http://localhost:8001
            url = ServiceConfig.get_service_url("vision", use_cache=False)  # Force refresh
        """
        # Validate service name
        if service_name not in cls.ENV_VAR_MAP:
            raise ValueError(
                f"Unknown service: {service_name}. "
                f"Valid services: {list(cls.ENV_VAR_MAP.keys())}"
            )
        
        # Check cache first (if enabled)
        if use_cache and service_name in cls._url_cache:
            return cls._url_cache[service_name]
        
        # Get environment variable name
        env_var = cls.ENV_VAR_MAP[service_name]
        default_url = cls.DEFAULT_URLS[service_name]
        
        # Try environment variable first, fall back to localhost
        url = os.getenv(env_var, default_url)
        
        # Validate and normalize URL format
        if not url:
            url = default_url
        
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"
        
        # Cache the result
        cls._url_cache[service_name] = url
        
        return url
    
    @classmethod
    def clear_cache(cls):
        """Clear URL cache (useful for testing)."""
        cls._url_cache.clear()
    
    @classmethod
    def get_all_urls(cls) -> Dict[str, str]:
        """
        Get all service URLs.
        
        Returns:
            Dictionary of {service_name: url}
        """
        return {
            service_name: cls.get_service_url(service_name)
            for service_name in cls.ENV_VAR_MAP.keys()
        }
    
    # Convenience properties for direct access
    @classmethod
    @property
    def CENTRAL_SERVER_URL(cls) -> str:
        return cls.get_service_url("central")
    
    @classmethod
    @property
    def VISION_SERVICE_URL(cls) -> str:
        return cls.get_service_url("vision")
    
    @classmethod
    @property
    def AUDIO_SERVICE_URL(cls) -> str:
        return cls.get_service_url("audio")
    
    @classmethod
    @property
    def TTS_SERVICE_URL(cls) -> str:
        return cls.get_service_url("tts")
    
    @classmethod
    @property
    def TEACHME_SERVICE_URL(cls) -> str:
        return cls.get_service_url("teachme")
    
    @classmethod
    @property
    def ENROLLMENT_SERVICE_URL(cls) -> str:
        return cls.get_service_url("enrollment")
    
    @classmethod
    @property
    def LLM_SERVICE_URL(cls) -> str:
        return cls.get_service_url("llm")
    
    @classmethod
    def validate_services(cls, service_names: Optional[list] = None) -> bool:
        """
        Validate that services are reachable.
        
        Args:
            service_names: List of services to validate. If None, validates all.
        
        Returns:
            True if all services reachable, False otherwise
        """
        import httpx
        import asyncio
        
        if service_names is None:
            service_names = list(cls.ENV_VAR_MAP.keys())
        
        async def check_service(service_name: str) -> bool:
            try:
                url = cls.get_service_url(service_name)
                from config.ssl_config import client_verify
                async with httpx.AsyncClient(timeout=2.0, verify=client_verify(url)) as client:
                    response = await client.get(f"{url}/health")
                    return response.status_code == 200
            except Exception as e:
                logger.warning(f"Service {service_name} unavailable: {e}")
                return False
        
        async def validate_all():
            results = await asyncio.gather(
                *[check_service(name) for name in service_names],
                return_exceptions=True
            )
            return all(r is True for r in results)
        
        try:
            return asyncio.run(validate_all())
        except Exception as e:
            logger.error(f"Service validation error: {e}")
            return False


# Logging helper
def log_service_urls():
    """Log all service URLs (useful for debugging)."""
    urls = ServiceConfig.get_all_urls()
    logger.info("=" * 60)
    logger.info("SERVICE URLS:")
    for service, url in urls.items():
        env_var = ServiceConfig.ENV_VAR_MAP[service]
        is_env_set = env_var in os.environ
        env_indicator = " ENV VAR" if is_env_set else "(localhost)"
        logger.info(f"  {service:15} → {url:40} {env_indicator}")
    logger.info("=" * 60)
