"""
Service Configuration - Centralized endpoint configuration

All service endpoints are configured through environment variables.
Defaults point to localhost development environment.
"""

import os


class ServiceConfig:
    """Service URL configuration for all NEXI microservices"""
    
    # Central microservices
    CENTRAL_SERVER = os.getenv("NEXI_CENTRAL_SERVER_URL", "http://localhost:8000")
    AUDIO_SERVICE = os.getenv("NEXI_AUDIO_SERVICE_URL", "http://localhost:8002")
    ENROLLMENT_SERVICE = os.getenv("NEXI_ENROLLMENT_SERVICE_URL", "http://localhost:8005")
    VISION_SERVICE = os.getenv("NEXI_VISION_SERVICE_URL", "http://localhost:8001")
    TTS_SERVICE = os.getenv("NEXI_TTS_SERVICE_URL", "http://localhost:8003")
    TEACHME_SERVICE = os.getenv("NEXI_TEACHME_SERVICE_URL", "http://localhost:8004")
    LLM_SERVICE = os.getenv("NEXI_LLM_SERVICE_URL", "http://localhost:8006")
    
    # API endpoints
    AUDIO_API = f"{AUDIO_SERVICE}/api/v1"
    VISION_API = f"{VISION_SERVICE}/api/v1"
    TEACHME_API = f"{TEACHME_SERVICE}/api/v1"
    LLM_API = f"{LLM_SERVICE}/api/v1"


# Export for easy importing
__all__ = ["ServiceConfig"]
