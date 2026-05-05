"""
Shared Utilities - Logging Setup
Centralized logging configuration for all services
"""

import logging
import sys
from typing import Optional


def setup_logging(service_name: str, level: str = "INFO") -> logging.Logger:
    """
    Setup logging for a service.
    
    Args:
        service_name: Name of the service
        level: Log level (DEBUG, INFO, WARNING, ERROR)
    
    Returns:
        Configured logger
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    logger = logging.getLogger(service_name)
    logger.setLevel(log_level)
    
    # Remove existing handlers
    logger.handlers = []
    
    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    
    # Create formatter
    formatter = logging.Formatter(
        fmt=(
            "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get logger for a module"""
    return logging.getLogger(name)
