"""
Service Client Factory - Singleton pattern for all service clients.
Provides centralized client creation and lifecycle management.
"""

from typing import Dict, Optional
from functools import lru_cache
import logging

from config.settings import settings
from shared.clients.base_client import AsyncHTTPClient
from shared.clients.audio_client import AudioServiceClient

logger = logging.getLogger(__name__)


class ServiceClientFactory:
    """Factory for creating and managing service clients."""

    _instance: Optional["ServiceClientFactory"] = None
    _clients: Dict[str, AsyncHTTPClient] = {}

    def __new__(cls) -> "ServiceClientFactory":
        """Implement singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_instance(cls) -> "ServiceClientFactory":
        """Get singleton instance."""
        return cls()

    def get_audio_client(self) -> AudioServiceClient:
        """Get or create audio service client."""
        if "audio" not in self._clients:
            logger.info(f"Creating AudioServiceClient for {settings.audio_service_url}")
            self._clients["audio"] = AudioServiceClient(
                base_url=settings.audio_service_url,
                timeout=settings.audio_service_timeout,
                max_retries=settings.audio_service_max_retries,
            )
        return self._clients["audio"]

    def get_vision_client(self) -> AsyncHTTPClient:
        """Get or create vision service client."""
        if "vision" not in self._clients:
            logger.info(f"Creating AsyncHTTPClient for {settings.vision_service_url}")
            self._clients["vision"] = AsyncHTTPClient(
                base_url=settings.vision_service_url,
                timeout=30,
                circuit_breaker_enabled=settings.enable_circuit_breaker,
            )
        return self._clients["vision"]

    def get_tts_client(self) -> AsyncHTTPClient:
        """Get or create TTS service client."""
        if "tts" not in self._clients:
            logger.info(f"Creating AsyncHTTPClient for {settings.tts_service_url}")
            self._clients["tts"] = AsyncHTTPClient(
                base_url=settings.tts_service_url,
                timeout=30,
                circuit_breaker_enabled=settings.enable_circuit_breaker,
            )
        return self._clients["tts"]

    def get_teachme_client(self) -> AsyncHTTPClient:
        """Get or create TeachMe service client."""
        if "teachme" not in self._clients:
            logger.info(f"Creating AsyncHTTPClient for {settings.teachme_service_url}")
            self._clients["teachme"] = AsyncHTTPClient(
                base_url=settings.teachme_service_url,
                timeout=30,
                circuit_breaker_enabled=settings.enable_circuit_breaker,
            )
        return self._clients["teachme"]

    async def close_all(self) -> None:
        """Close all client connections."""
        logger.info("Closing all service clients")
        for name, client in self._clients.items():
            try:
                await client.close()
                logger.debug(f"Closed {name} client")
            except Exception as e:
                logger.error(f"Error closing {name} client: {e}")
        self._clients.clear()

    def get_client(self, service_name: str) -> AsyncHTTPClient:
        """Get client by service name."""
        if service_name == "audio":
            return self.get_audio_client()
        elif service_name == "vision":
            return self.get_vision_client()
        elif service_name == "tts":
            return self.get_tts_client()
        elif service_name == "teachme":
            return self.get_teachme_client()
        else:
            raise ValueError(f"Unknown service: {service_name}")


@lru_cache(maxsize=1)
def get_service_factory() -> ServiceClientFactory:
    """Get cached singleton instance of service factory."""
    return ServiceClientFactory.get_instance()
