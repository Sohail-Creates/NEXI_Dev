"""
Vision Service Package
Face detection, embedding extraction, and emotion analysis service
"""

__version__ = "1.0.0"
__author__ = "Nexi Vision Team"

from .app import app, create_app

__all__ = ["app", "create_app"]
