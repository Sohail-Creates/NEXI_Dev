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


def require_deepface():
    """Return the optional face runtime or preserve its actionable import error."""
    from deepface import DeepFace

    return DeepFace


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
    DeepFace = require_deepface()
    
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


def process_face(
    face_obj: Dict[str, Any],
    face_index: int,
    model_name: str,
) -> Dict[str, Any]:
    """
    Process detected face without emotion analysis
    
    Args:
        face_obj: Face object from DeepFace.extract_faces()
        face_index: Index of face in detection results
        model_name: Embedding model to use
    
    Returns:
        Dictionary with face data and embedding
    """
    DeepFace = require_deepface()
    
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
        
        return {
            'face_id': face_index,
            'bounding_box': bbox,
            'confidence': confidence,
            'embedding': embedding,
            'embedding_model': model_name,
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
    DeepFace = require_deepface()
    
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

