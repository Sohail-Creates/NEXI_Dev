"""
Unified configuration settings for Nexi Robo project.
Uses Pydantic BaseSettings with environment variable loading.
ALL PORT CONFIGURATION MUST USE config.ports.ServicePorts
"""

from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache
from config.ports import ServicePorts


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # =============== PROJECT CONFIG ===============
    environment: str = "development"
    debug: bool = True
    project_name: str = "Nexi Robo"
    project_version: str = "1.0.0"

    # =============== CENTRALIZED PORT CONFIGURATION ===============
    # NOTE: All ports are defined in config/ports.py
    # NEVER hardcode ports here - use ServicePorts instead
    
    # CENTRAL SERVER (see config/ports.py)
    central_server_host: str = "0.0.0.0"
    central_server_port: int = ServicePorts.CENTRAL_SERVER
    central_server_url: str = ServicePorts.get_base_url("central")

    # AUDIO SERVICE (see config/ports.py)
    audio_service_host: str = "0.0.0.0"
    audio_service_port: int = ServicePorts.AUDIO_SERVICE
    audio_service_url: str = ServicePorts.get_base_url("audio")
    audio_service_timeout: int = 5  # Changed from 30s to 5s for fast-fail
    audio_service_max_retries: int = 3

    # ENROLLMENT SERVICE (see config/ports.py)
    enrollment_service_port: int = ServicePorts.ENROLLMENT_SERVICE
    enrollment_service_url: str = ServicePorts.get_base_url("enrollment")

    # VISION SERVICE (see config/ports.py)
    vision_service_port: int = ServicePorts.VISION_SERVICE
    vision_service_url: str = ServicePorts.get_base_url("vision")
    
    # TTS SERVICE (see config/ports.py)
    tts_service_port: int = ServicePorts.TTS_SERVICE
    tts_service_url: str = ServicePorts.get_base_url("tts")
    
    # TEACHME SERVICE (see config/ports.py)
    teachme_service_port: int = ServicePorts.TEACHME_SERVICE
    teachme_service_url: str = ServicePorts.get_base_url("teachme")

    # LLM SERVICE (see config/ports.py)
    llm_service_port: int = ServicePorts.LLM_SERVICE
    llm_service_url: str = ServicePorts.get_base_url("llm")
    llm_service_timeout: int = 5
    llm_max_context_tokens: int = 8192
    llm_max_response_tokens: int = 150
    llm_inference_timeout: float = 2.0

    # =============== DATABASE CONFIG ===============
    database_url: str = "sqlite:///./data/nexi_robo.db"
    json_data_dir: str = "./data"

    # =============== LOGGING CONFIG ===============
    log_level: str = "INFO"
    log_format: str = "json"  # json or text

    # =============== FEATURE FLAGS ===============
    enable_circuit_breaker: bool = True
    enable_audio_cache: bool = True
    enable_voice_enrollment: bool = True

    # =============== API KEYS ===============
    groq_api_key: Optional[str] = None

    # =============== PORCUPINE CONFIG ===============
    porcupine_access_key: Optional[str] = None
    porcupine_model_path: str = "./models/porcupine_model.pv"

    # =============== STORAGE CONFIG ===============
    upload_dir: str = "./storage/uploads"
    temp_dir: str = "./storage/temp"
    backup_dir: str = "./storage/backups"
    max_upload_size_mb: int = 50

    # =============== CACHE CONFIG ===============
    cache_ttl_hours: int = 24
    cache_max_items: int = 10000

    # =============== CIRCUIT BREAKER CONFIG ===============
    # CRITICAL: Use fast timeouts for good UX (5s max, not 30-60s)
    circuit_breaker_failure_threshold: int = 3    # Open after 3 failures (not 5)
    circuit_breaker_recovery_timeout: int = 10    # Retry after 10s (not 60s)
    circuit_breaker_request_timeout: int = 5      # Request timeout 5s (not 30s)
    circuit_breaker_expected_exception: str = "Exception"

    # =============== RESOURCES CONFIG ===============
    microphone_max_concurrent: int = 3
    camera_max_concurrent: int = 2
    storage_max_concurrent: int = 4

    # =============== PERSISTENCE CONFIG ===============
    persistence_auto_save_interval: int = 30
    persistence_backup_enabled: bool = True
    persistence_backup_interval: int = 3600

    # =============== AUDIO SERVICE CONFIG (DETAILED) ===============
    audio_sample_rate: int = 16000
    audio_channels: int = 1
    audio_chunk_size: int = 1024
    audio_format: str = "pcm_16"
    audio_queue_db_path: str = "audio_service/data/queue.db"
    audio_queue_max_retry: int = 3
    audio_queue_max_size: int = 1000
    audio_queue_poll_interval: int = 1
    audio_queue_batch_size: int = 10
    porcupine_wake_word_enabled: bool = True
    speaker_verification_enabled: bool = True
    stt_enabled: bool = True

    # =============== ENROLLMENT CONFIG ===============
    enrollment_enabled: bool = True
    speaker_enrollment_required: bool = True
    speaker_verification_threshold: float = 0.85

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "allow"  # Allow extra fields from .env

    def get_database_url(self) -> str:
        """Get database URL."""
        return self.database_url

    def get_audio_service_url(self) -> str:
        """Get audio service URL."""
        return self.audio_service_url

    def get_central_server_url(self) -> str:
        """Get central server URL."""
        return self.central_server_url


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Default instance
settings = get_settings()
