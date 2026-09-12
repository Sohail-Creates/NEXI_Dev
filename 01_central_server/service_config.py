"""
Local configuration for Central Server.
Wraps global settings and provides service-specific configuration objects.
Used by local components (resource_manager, persistence, service_connector).
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
from collections.abc import ItemsView


@dataclass
class ResourcesConfig:
    """Resource management configuration."""
    microphone_max_concurrent: int = 3
    camera_max_concurrent: int = 2
    storage_max_concurrent: int = 4


@dataclass
class PersistenceConfig:
    """Persistence layer configuration."""
    data_dir: str = "./01_central_server/data"  # Data directory
    backup_dir: str = "./01_central_server/data/backups"  # Backup directory
    db_path: str = "./01_central_server/data/central_server.db"  # Database path
    auto_save_interval: int = 30  # seconds
    backup_enabled: bool = True
    backup_interval: int = 3600  # 1 hour
    max_backup_versions: int = 5  # Keep max 5 backup versions


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass
class ServiceConfig:
    """Service configuration - service URLs with retry/timeout settings."""
    audio_url: str = "https://localhost:8002"
    vision_url: str = "https://localhost:8001"
    tts_url: str = "https://localhost:8003"
    enrollment_url: str = "https://localhost:8005"
    teachme_url: str = "https://localhost:8004"
    llm_url: str = "https://localhost:8006"
    
    def get_service_configs(self) -> Dict[str, Dict[str, Any]]:
        """Return proper config dicts for each service with circuit breaker settings."""
        return {
            "audio": {
                "url": self.audio_url,
                "max_retries": 3,
                "timeout": 10,
                "circuit_breaker_enabled": True,
                "circuit_breaker_threshold": 5,
                "circuit_breaker_timeout": 60,
            },
            "vision": {
                "url": self.vision_url,
                "max_retries": 3,
                "timeout": 10,
                "circuit_breaker_enabled": True,
                "circuit_breaker_threshold": 5,
                "circuit_breaker_timeout": 60,
            },
            "tts": {
                "url": self.tts_url,
                "max_retries": 3,
                "timeout": 10,
                "circuit_breaker_enabled": True,
                "circuit_breaker_threshold": 5,
                "circuit_breaker_timeout": 60,
            },
            "enrollment": {
                "url": self.enrollment_url,
                "max_retries": 3,
                "timeout": 10,
                "circuit_breaker_enabled": True,
                "circuit_breaker_threshold": 5,
                "circuit_breaker_timeout": 60,
            },
            "teachme": {
                "url": self.teachme_url,
                "max_retries": 3,
                "timeout": 15,
                "circuit_breaker_enabled": True,
                "circuit_breaker_threshold": 5,
                "circuit_breaker_timeout": 60,
            },
            "llm": {
                "url": self.llm_url,
                "max_retries": 1,
                "timeout": 5,
                "circuit_breaker_enabled": True,
                "circuit_breaker_threshold": 3,
                "circuit_breaker_timeout": 15,
            }
        }
    
    def items(self):
        """Return items for iteration - legacy compatibility."""
        return self.get_service_configs().items()


@dataclass
class Config:
    """Main configuration object for central server."""
    central_port: int = 8000
    environment: str = "development"
    resources: ResourcesConfig = None
    persistence: PersistenceConfig = None
    logging: LoggingConfig = None
    services: ServiceConfig = None

    def __post_init__(self) -> None:
        if self.resources is None:
            self.resources = ResourcesConfig()
        if self.persistence is None:
            self.persistence = PersistenceConfig()
        if self.logging is None:
            self.logging = LoggingConfig()
        if self.services is None:
            self.services = ServiceConfig()


# Global instance
_config = Config()


def get_config() -> Config:
    """Get the configuration instance."""
    return _config


# Backward compatibility
config: Config = _config

