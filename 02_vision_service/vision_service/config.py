"""
Vision Service Configuration
"""

import os
import logging

class Config:
    HOST = os.getenv("VISION_HOST", "0.0.0.0")
    PORT = int(os.getenv("VISION_PORT", "8001"))
    LOG_LEVEL = os.getenv("VISION_LOG_LEVEL", "INFO")
    
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "Facenet")
    DETECTOR_BACKEND = os.getenv("DETECTOR_BACKEND", "opencv")
    
    ENABLE_OBJECT_DETECTION = os.getenv("ENABLE_OBJECT_DETECTION", "true").lower() == "true"
    OBJECT_DETECTION_MODEL = os.getenv("OBJECT_DETECTION_MODEL", "yolov8n")
    
    CAMERA_TIMEOUT = int(os.getenv("CAMERA_TIMEOUT", "10"))
    CENTRAL_SERVER_URL = os.getenv("CENTRAL_SERVER_URL", "https://localhost:8000")
    
    MODEL_LOAD_MAX_RETRIES = 3
    MODEL_LOAD_BACKOFF_SECONDS = 2
    
    VALID_BACKENDS = ["opencv", "ssd", "dlib", "mtcnn", "retinaface"]
    VALID_EMBEDDING_MODELS = ["Facenet", "Facenet512", "VGG-Face", "ArcFace", "DeepFace"]
    
    @staticmethod
    def validate():
        pass
