"""
Service client modules for inter-service communication.
All services are called through dedicated client classes.
Every call goes through circuit breaker.
"""

from .audio_client import AudioServiceClient
from .vision_client import VisionServiceClient
from .tts_client import TTSServiceClient
from .teachme_client import TeachMeServiceClient
from .models import ServiceCallResult

__all__ = [
    "AudioServiceClient",
    "VisionServiceClient",
    "TTSServiceClient",
    "TeachMeServiceClient",
    "ServiceCallResult",
]
