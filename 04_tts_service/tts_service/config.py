"""
Configuration module for NEXI TTS Service.

This module handles environment variables and configuration management.
Uses python-dotenv to load configuration from .env file.
"""
import os
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False


# Load environment variables from .env file if available
if DOTENV_AVAILABLE:
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)


class Config:
    """Configuration settings for TTS service."""

    # Paths
    PIPER_MODELS_DIR: Path = Path(
        os.environ.get("PIPER_MODELS_DIR", Path(__file__).parent.parent / "models")
    ).resolve()

    # Timeouts (seconds)
    SYNTHESIS_TIMEOUT_SECONDS: int = int(
        os.environ.get("TTS_SYNTHESIS_TIMEOUT", 60)
    )
    QUEUE_TIMEOUT_SECONDS: int = int(
        os.environ.get("TTS_QUEUE_TIMEOUT", 60)
    )
    MODEL_CACHE_TIMEOUT: int = int(
        os.environ.get("TTS_MODEL_CACHE_TIMEOUT", 3600)
    )

    # Limits
    MAX_TEXT_LENGTH: int = int(
        os.environ.get("TTS_MAX_TEXT_LENGTH", 5000)
    )

    # Logging
    LOG_LEVEL: str = os.environ.get("TTS_LOG_LEVEL", "INFO")

    # Server
    HOST: str = os.environ.get("HOST", "0.0.0.0")
    PORT: int = int(os.environ.get("PORT", 8003))
    WORKERS: int = int(os.environ.get("WORKERS", 1))

    # Service Meta
    SERVICE_NAME: str = "NEXI TTS"
    SERVICE_VERSION: str = "1.0.0"

    @classmethod
    def to_dict(cls) -> dict:
        """Return configuration as dictionary."""
        return {
            "service_name": cls.SERVICE_NAME,
            "service_version": cls.SERVICE_VERSION,
            "piper_models_dir": str(cls.PIPER_MODELS_DIR),
            "synthesis_timeout": cls.SYNTHESIS_TIMEOUT_SECONDS,
            "queue_timeout": cls.QUEUE_TIMEOUT_SECONDS,
            "model_cache_timeout": cls.MODEL_CACHE_TIMEOUT,
            "max_text_length": cls.MAX_TEXT_LENGTH,
            "log_level": cls.LOG_LEVEL,
            "host": cls.HOST,
            "port": cls.PORT,
            "workers": cls.WORKERS,
        }

    @classmethod
    def validate(cls) -> list:
        """
        Validate configuration.
        Returns list of errors (empty if valid).
        """
        errors = []

        if not cls.PIPER_MODELS_DIR.exists():
            errors.append(
                f"PIPER_MODELS_DIR does not exist: {cls.PIPER_MODELS_DIR}"
            )

        if cls.SYNTHESIS_TIMEOUT_SECONDS <= 0:
            errors.append("SYNTHESIS_TIMEOUT_SECONDS must be positive")

        if cls.MAX_TEXT_LENGTH < 10:
            errors.append("MAX_TEXT_LENGTH must be at least 10")

        if cls.PORT not in range(1, 65536):
            errors.append(f"PORT must be between 1 and 65535, got {cls.PORT}")

        return errors
