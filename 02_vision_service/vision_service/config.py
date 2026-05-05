"""
Vision Service Configuration
Loaded from environment variables with sensible defaults
Production implementation from Vision-Nexus
Loads from root .env file like all other NEXI services
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from root directory (consistent with Audio & Central Server)
# Audio Service also uses load_dotenv() without path, which loads from cwd root
# For explicit clarity, we load from the project root
root_env_path = Path(__file__).parent.parent.parent / ".env"
if root_env_path.exists():
    load_dotenv(dotenv_path=root_env_path)
else:
    # Fallback: load from current working directory
    load_dotenv()

logger = logging.getLogger(__name__)


class Config:
    """Service configuration - can be overridden by environment variables"""
    
    # Server Configuration
    PORT = int(os.getenv("VISION_PORT", "8001"))
    HOST = os.getenv("VISION_HOST", "0.0.0.0")
    CENTRAL_SERVER_URL = os.getenv("CENTRAL_SERVER_URL", "http://localhost:8000")

    
    # Model Configuration
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "Facenet")
    DETECTOR_BACKEND = os.getenv("DETECTOR_BACKEND", "opencv")
    
    # Feature Control
    ENABLE_EMOTION_DETECTION = os.getenv("ENABLE_EMOTION_DETECTION", "true").lower() == "true"
    ENABLE_OBJECT_DETECTION = os.getenv("ENABLE_OBJECT_DETECTION", "true").lower() == "true"
    OBJECT_DETECTION_MODEL = os.getenv("OBJECT_DETECTION_MODEL", "yolov8n")  # yolov8n (nano) or yolov8s (small)
    
    # Operational Settings
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "logs/vision_service.log")
    
    # Timeout Values (seconds)
    CAMERA_TIMEOUT = int(os.getenv("CAMERA_TIMEOUT", "10"))
    MODEL_LOAD_TIMEOUT = int(os.getenv("MODEL_LOAD_TIMEOUT", "120"))
    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
    
    # Retry Policy for Model Loading (from Vision-Nexus)
    MODEL_LOAD_MAX_RETRIES = int(os.getenv("MODEL_LOAD_MAX_RETRIES", "3"))
    MODEL_LOAD_BACKOFF_SECONDS = int(os.getenv("MODEL_LOAD_BACKOFF_SECONDS", "2"))
    
    # Validation
    VALID_BACKENDS = ["opencv", "retinaface", "mtcnn", "ssd"]
    VALID_EMBEDDING_MODELS = ["Facenet", "Facenet512", "VGG-Face", "ArcFace", "DeepFace"]
    
    @classmethod
    def validate(cls):
        """
        Validate configuration on startup
        From Vision-Nexus - warns instead of failing
        """
        logger.info("Validating configuration...")
        
        # Validate embedding model
        if cls.EMBEDDING_MODEL not in cls.VALID_EMBEDDING_MODELS:
            logger.warning(
                f"Invalid EMBEDDING_MODEL '{cls.EMBEDDING_MODEL}'. "
                f"Valid options: {cls.VALID_EMBEDDING_MODELS}. Using default 'Facenet'."
            )
            cls.EMBEDDING_MODEL = "Facenet"
        
        # Validate detector backend
        if cls.DETECTOR_BACKEND not in cls.VALID_BACKENDS:
            logger.warning(
                f"Invalid DETECTOR_BACKEND '{cls.DETECTOR_BACKEND}'. "
                f"Valid options: {cls.VALID_BACKENDS}. Using default 'opencv'."
            )
            cls.DETECTOR_BACKEND = "opencv"
        
        # Validate retries
        if cls.MODEL_LOAD_MAX_RETRIES < 1:
            logger.warning("MODEL_LOAD_MAX_RETRIES must be >= 1. Using default 3.")
            cls.MODEL_LOAD_MAX_RETRIES = 3
        
        # Validate timeouts
        if cls.CAMERA_TIMEOUT < 1:
            logger.warning("CAMERA_TIMEOUT must be >= 1. Using default 10.")
            cls.CAMERA_TIMEOUT = 10
        
        logger.info(" Configuration validation complete")
        logger.info(f"  Backend: {cls.DETECTOR_BACKEND}")
        logger.info(f"  Embedding Model: {cls.EMBEDDING_MODEL}")
        logger.info(f"  Emotion Detection: {'ENABLED' if cls.ENABLE_EMOTION_DETECTION else 'DISABLED'}")
        logger.info(f"  Object Detection: {'ENABLED' if cls.ENABLE_OBJECT_DETECTION else 'DISABLED'} ({cls.OBJECT_DETECTION_MODEL})")
        logger.info(f"  Log Level: {cls.LOG_LEVEL}")


config = Config()

