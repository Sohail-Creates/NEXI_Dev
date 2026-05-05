"""
Vision Service Face Detection Module
Face detection and embedding extraction using DeepFace
Production implementation from Vision-Nexus
"""

import cv2
import numpy as np
import logging
import time
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


def load_model_with_retry(
    model_name: str = "Facenet",
    max_retries: int = 3,
    backoff_seconds: int = 2
) -> bool:
    """
    Load DeepFace model with exponential backoff retry logic
    Production implementation from Vision-Nexus
    
    Args:
        model_name: Name of embedding model to load
        max_retries: Maximum retry attempts
        backoff_seconds: Initial backoff delay (seconds)
    
    Returns:
        True if model loaded successfully, False otherwise
    """
    from deepface import DeepFace
    
    for attempt in range(max_retries):
        try:
            logger.info(
                f"Loading {model_name} model (attempt {attempt + 1}/{max_retries})..."
            )
            DeepFace.build_model(model_name)
            logger.info(f"Successfully loaded {model_name} model")
            return True
            
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = backoff_seconds ** attempt  # Exponential backoff
                logger.warning(f"Failed to load {model_name}: {str(e)[:100]}")
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logger.error(
                    f"Failed to load {model_name} after {max_retries} attempts: {e}"
                )
                return False
    
    return False


def validate_detector_backend(backend: str, valid_backends: List[str]) -> None:
    """
    Validate detector backend parameter
    From Vision-Nexus
    """
    if backend not in valid_backends:
        raise ValueError(f"Detector backend must be one of {valid_backends}, got '{backend}'")


def validate_embedding_model(model: str, valid_models: List[str]) -> None:
    """
    Validate embedding model parameter
    From Vision-Nexus
    """
    if model not in valid_models:
        raise ValueError(f"Embedding model must be one of {valid_models}, got '{model}'")


def process_face_with_emotions(
    face_obj: Dict[str, Any],
    face_index: int,
    model_name: str,
    full_frame: np.ndarray,
    resource_pool=None,
    enable_emotion_detection: bool = False
) -> Dict[str, Any]:
    """
    Process detected face with optional emotion analysis
    Production logic from Vision-Nexus
    
    Args:
        face_obj: Face object from DeepFace.extract_faces()
        face_index: Index of face in detection results
        model_name: Embedding model to use
        full_frame: Full frame for emotion extraction
        resource_pool: ResourcePool instance for FER access
        enable_emotion_detection: Whether to analyze emotions
    
    Returns:
        Dictionary with face data, embedding, and optional emotions
    """
    from deepface import DeepFace
    from ..models import BoundingBox, EmotionScores
    
    try:
        # Extract bounding box
        facial_area = face_obj.get('facial_area', {})
        bbox = {
            'x': int(facial_area.get('x', 0)),
            'y': int(facial_area.get('y', 0)),
            'width': int(facial_area.get('w', 0)),
            'height': int(facial_area.get('h', 0))
        }
        
        confidence = float(face_obj.get('confidence', 0.99))
        face_img = face_obj.get('face')
        
        # Extract embedding
        embedding = [0.0] * 128
        try:
            embedding_objs = DeepFace.represent(
                img_path=face_img,
                model_name=model_name,
                enforce_detection=False
            )
            embedding = embedding_objs[0]['embedding']
            logger.debug(f"Face {face_index}: Generated {len(embedding)}-dimensional embedding")
        except Exception as e:
            logger.warning(f"Failed to generate embedding for face {face_index}: {str(e)[:100]}")
        
        # Emotion detection (optional)
        dominant_emotion = None
        emotion_scores = {}  # FIXED: Return empty dict instead of None
        
        if enable_emotion_detection and resource_pool is not None:
            logger.info(f"Face {face_index}: Attempting emotion detection...")
            try:
                x = facial_area.get('x', 0)
                y = facial_area.get('y', 0)
                w = facial_area.get('w', 0)
                h = facial_area.get('h', 0)
                
                padding = 20
                y1 = max(0, y - padding)
                y2 = min(full_frame.shape[0], y + h + padding)
                x1 = max(0, x - padding)
                x2 = min(full_frame.shape[1], x + w + padding)
                
                face_region = full_frame[y1:y2, x1:x2]
                logger.info(f"Face {face_index}: Extracted face region ({x2-x1}x{y2-y1})")
                
                fer = resource_pool.get_fer_detector()
                if fer is not None:
                    logger.info(f"Face {face_index}: FER detector ready, analyzing emotions...")
                    emotions = fer.detect_emotions(face_region)
                    
                    if emotions and len(emotions) > 0:
                        emotion_dict = emotions[0]['emotions']
                        logger.info(f"Face {face_index}: Raw emotions: {emotion_dict}")
                        
                        if emotion_dict and any(v > 0 for v in emotion_dict.values()):
                            dominant_emotion = max(emotion_dict, key=emotion_dict.get)
                        else:
                            logger.warning(f"Face {face_index}: All emotion scores are 0, using neutral")
                            dominant_emotion = "neutral"
                        
                        emotion_scores = {
                            'angry': float(emotion_dict.get('angry', 0)),
                            'disgust': float(emotion_dict.get('disgust', 0)),
                            'fear': float(emotion_dict.get('fear', 0)),
                            'happy': float(emotion_dict.get('happy', 0)),
                            'sad': float(emotion_dict.get('sad', 0)),
                            'surprise': float(emotion_dict.get('surprise', 0)),
                            'neutral': float(emotion_dict.get('neutral', 0))
                        }
                        logger.info(f"Face {face_index}: Detected emotion={dominant_emotion}, scores={emotion_scores}")
                    else:
                        logger.warning(f"Face {face_index}: No emotions returned from FER detector")
                else:
                    logger.error(f"Face {face_index}: FER detector is None")
            except Exception as e:
                logger.error(f"Emotion detection failed for face {face_index}: {e}", exc_info=True)
        
        return {
            'face_id': face_index,
            'bounding_box': bbox,
            'confidence': confidence,
            'embedding': embedding,
            'embedding_model': model_name,
            'dominant_emotion': dominant_emotion,
            'emotion_scores': emotion_scores
        }
        
    except Exception as e:
        logger.error(f"Error processing face {face_index}: {e}")
        raise


def detect_faces_deepface(
    frame: np.ndarray,
    detector_backend: str = "opencv"
) -> List[Dict[str, Any]]:
    """
    Detect faces in frame using DeepFace
    From Vision-Nexus
    
    Args:
        frame: Input frame (numpy array, BGR format)
        detector_backend: Backend to use for face detection
    
    Returns:
        List of face objects from DeepFace.extract_faces()
    """
    from deepface import DeepFace
    
    try:
        logger.info(f"Detecting faces with {detector_backend} backend...")
        face_objs = DeepFace.extract_faces(
            img_path=frame,
            detector_backend=detector_backend,
            enforce_detection=False,
            align=True
        )
        logger.info(f"Face detection complete: {len(face_objs)} faces detected")
        return face_objs
        
    except Exception as e:
        logger.error(f"Error in face detection: {e}")
        return []

