"""
Vision Service - Routes Module
API route handlers
"""

from . import health
from . import detection
from . import streaming
from . import camera

__all__ = ["health", "detection", "streaming", "camera"]
