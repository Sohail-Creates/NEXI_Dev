"""
Vision Service Emotion Detection Module
Facial Expression Recognition using FER
"""

import numpy as np
import logging
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


class EmotionDetector:
    """Wrapper for FER emotion detection"""
    
    EMOTION_LABELS = ["angry", "disgust", "fear", "happy", "sad", "surprise", "neutral"]
    
    def __init__(self, fer_instance=None):
        """
        Initialize emotion detector
        
        Args:
            fer_instance: Pre-initialized FER instance (optional)
        """
        self.fer = fer_instance
        self.available = fer_instance is not None
    
    def detect(self, face_image: np.ndarray) -> Optional[Dict]:
        """
        Detect emotions in face image
        
        Args:
            face_image: Face image (numpy array, BGR format)
        
        Returns:
            Dictionary with emotion scores or None if detection failed
        """
        if not self.available or self.fer is None:
            logger.debug("FER detector not available")
            return None
        
        try:
            # Run emotion detection
            result = self.fer.detect_emotions(face_image)
            
            if not result or len(result) == 0:
                logger.debug("No emotions detected in face")
                return None
            
            # Extract emotion scores from first face
            emotions = result[0].get("emotions", {})
            
            if not emotions:
                logger.debug("Empty emotion scores")
                return None
            
            # Find dominant emotion
            dominant_emotion = max(emotions, key=emotions.get)
            dominant_score = emotions.get(dominant_emotion, 0)
            
            # Normalize scores to 0-1 range
            normalized_emotions = {}
            total = sum(emotions.values())
            
            for emotion in self.EMOTION_LABELS:
                score = emotions.get(emotion, 0)
                normalized_emotions[emotion] = score / total if total > 0 else 0
            
            return {
                "dominant_emotion": dominant_emotion,
                "scores": normalized_emotions,
                "confidence": float(dominant_score)
            }
            
        except Exception as e:
            logger.error(f"Error in emotion detection: {e}")
            return None
    
    def detect_batch(self, face_images: List[np.ndarray]) -> List[Optional[Dict]]:
        """
        Detect emotions in multiple face images
        
        Args:
            face_images: List of face images
        
        Returns:
            List of emotion detection results
        """
        results = []
        for face_image in face_images:
            result = self.detect(face_image)
            results.append(result)
        return results
    
    def is_available(self) -> bool:
        """Check if emotion detector is available"""
        return self.available and self.fer is not None


def create_emotion_detector(fer_instance=None) -> EmotionDetector:
    """
    Factory function to create emotion detector
    
    Args:
        fer_instance: Pre-initialized FER instance (optional)
    
    Returns:
        EmotionDetector instance
    """
    return EmotionDetector(fer_instance)
