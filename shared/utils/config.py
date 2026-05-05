"""
Configuration classes for NEXI Services.
Provides configuration management for service communication and client settings.
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class ClientConfig:
    """Configuration for service clients."""
    host: str = "localhost"
    port: int = 8000
    timeout: int = 30
    max_retries: int = 3
    use_circuit_breaker: bool = True

    @property
    def url(self) -> str:
        """Get service URL."""
        return f"http://{self.host}:{self.port}"


@dataclass
class ServiceConfig:
    """Configuration for individual services."""
    name: str
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    workers: int = 1
    timeout: int = 30

    @property
    def url(self) -> str:
        """Get service URL."""
        return f"http://{self.host}:{self.port}"


@dataclass
class Config:
    """Global application configuration."""
    environment: str = "development"
    debug: bool = True
    
    # Central Server
    central_server: ServiceConfig = None
    
    # Services
    audio_service: ClientConfig = None
    vision_service: ClientConfig = None
    tts_service: ClientConfig = None
    enrollment_service: ClientConfig = None
    teachme_service: ClientConfig = None
    
    # Database
    database_url: str = "sqlite:///./data/nexi_robo.db"
    
    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = None
    
    # Feature flags
    enable_circuit_breaker: bool = True
    enable_caching: bool = True
    
    def __post_init__(self):
        """Initialize default values if not provided."""
        if self.central_server is None:
            self.central_server = ServiceConfig(
                name="central_server",
                port=8000
            )
        
        if self.audio_service is None:
            self.audio_service = ClientConfig(port=8002)
        
        if self.vision_service is None:
            self.vision_service = ClientConfig(port=8001)
        
        if self.tts_service is None:
            self.tts_service = ClientConfig(port=8003)
        
        if self.enrollment_service is None:
            self.enrollment_service = ClientConfig(port=8004)
        
        if self.teachme_service is None:
            self.teachme_service = ClientConfig(port=8005)
