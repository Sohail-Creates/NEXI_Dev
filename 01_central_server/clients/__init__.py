"""
Central Server Clients Package
Provides typed clients for external microservices.
"""

from .audio_client import AudioServiceClient, AudioServiceError

__all__ = ["AudioServiceClient", "AudioServiceError"]
