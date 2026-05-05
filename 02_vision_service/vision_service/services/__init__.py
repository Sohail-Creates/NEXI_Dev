"""
Vision Service - Services Module
Core service implementations
"""

from .resource_pool import ResourcePool
from .face_detector import (
    load_model_with_retry,
    detect_faces_deepface,
    process_face_with_emotions,
    validate_detector_backend,
    validate_embedding_model
)
from .emotion_detector import EmotionDetector
from .queue_service import VisionQueueService
from .queue_processor import VisionQueueProcessor

__all__ = [
    "ResourcePool",
    "load_model_with_retry",
    "detect_faces_deepface",
    "process_face_with_emotions",
    "validate_detector_backend",
    "validate_embedding_model",
    "EmotionDetector",
    "VisionQueueService",
    "VisionQueueProcessor"
]
