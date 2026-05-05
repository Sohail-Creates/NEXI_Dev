"""
Unified logging configuration for all services.
Provides structured JSON logging and rotation.
"""

import logging
import logging.config
import json
from typing import Dict, Any

from config.settings import settings


def get_logging_config() -> Dict[str, Any]:
    """Get logging configuration dictionary."""

    if settings.log_format == "json":
        return {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
                    "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
                },
                "standard": {
                    "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": settings.log_level,
                    "formatter": "json",
                    "stream": "ext://sys.stdout",
                },
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": settings.log_level,
                    "formatter": "json",
                    "filename": "logs/app.log",
                    "maxBytes": 10485760,  # 10MB
                    "backupCount": 5,
                },
            },
            "root": {
                "level": settings.log_level,
                "handlers": ["console", "file"],
            },
        }
    else:
        # Standard text logging
        return {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": settings.log_level,
                    "formatter": "standard",
                    "stream": "ext://sys.stdout",
                },
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": settings.log_level,
                    "formatter": "standard",
                    "filename": "logs/app.log",
                    "maxBytes": 10485760,  # 10MB
                    "backupCount": 5,
                },
            },
            "root": {
                "level": settings.log_level,
                "handlers": ["console", "file"],
            },
        }


def setup_logging() -> None:
    """Setup logging for the application."""
    try:
        config = get_logging_config()
        logging.config.dictConfig(config)
        logger = logging.getLogger(__name__)
        logger.info(f"Logging configured - Level: {settings.log_level}, Format: {settings.log_format}")
    except Exception as e:
        # Fallback to basic logging if json logger not available
        logging.basicConfig(
            level=getattr(logging, settings.log_level),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
        logger = logging.getLogger(__name__)
        logger.warning(f"Fallback to basic logging: {e}")
