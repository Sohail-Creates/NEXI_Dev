"""
Vision Service Configuration
"""

import os
import logging
from pathlib import Path


_SERVICE_ROOT = Path(__file__).resolve().parents[1]
_MODEL_CACHE_ROOT = Path(
    os.getenv("VISION_MODEL_CACHE_DIR", _SERVICE_ROOT / "models")
).resolve()
_MODEL_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault(
    "DEEPFACE_HOME",
    str(_MODEL_CACHE_ROOT),
)

class Config:
    HOST = os.getenv("VISION_HOST", "0.0.0.0")
    PORT = int(os.getenv("VISION_PORT", "8001"))
    LOG_LEVEL = os.getenv("VISION_LOG_LEVEL", "INFO")
    
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "Facenet")
    DETECTOR_BACKEND = os.getenv("DETECTOR_BACKEND", "opencv")
    
    ENABLE_OBJECT_DETECTION = os.getenv("ENABLE_OBJECT_DETECTION", "true").lower() == "true"
    OBJECT_DETECTION_MODEL = os.getenv("OBJECT_DETECTION_MODEL", "yolov8n")
    DEEPFACE_HOME = Path(os.environ["DEEPFACE_HOME"])
    
    CAMERA_TIMEOUT = int(os.getenv("CAMERA_TIMEOUT", "10"))
    CAMERA_DEVICE = os.getenv("VISION_CAMERA_DEVICE", "").strip() or None
    # Loopback IP avoids Windows' localhost IPv6 fallback delay while remaining
    # fully overrideable for container/remote deployments.
    CENTRAL_SERVER_URL = os.getenv("CENTRAL_SERVER_URL", "https://127.0.0.1:8000")
    
    MODEL_LOAD_MAX_RETRIES = 3
    MODEL_LOAD_BACKOFF_SECONDS = 2
    
    VALID_BACKENDS = ["opencv", "ssd", "dlib", "mtcnn", "retinaface"]
    VALID_EMBEDDING_MODELS = ["Facenet", "Facenet512", "VGG-Face", "ArcFace", "DeepFace"]
    
    @staticmethod
    def validate():
        pass
