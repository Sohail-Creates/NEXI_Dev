"""
Vision Service Pydantic Models
Updated for Pydantic v2.x compatibility
"""

from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict


# ============================================================================
# REQUEST/RESPONSE MODELS FOR FACE DETECTION
# ============================================================================

class BoundingBox(BaseModel):
    """Bounding box for detected face"""
    x: int
    y: int
    width: int
    height: int


class EmotionScores(BaseModel):
    """Emotion confidence scores (0.0-1.0)"""
    angry: float
    disgust: float
    fear: float
    happy: float
    sad: float
    surprise: float
    neutral: float


class FaceData(BaseModel):
    """Detected face with embeddings and optional emotion analysis"""
    face_id: int
    bounding_box: BoundingBox
    confidence: float
    embedding: List[float]
    embedding_model: str
    dominant_emotion: Optional[str] = None
    emotion_scores: Optional[EmotionScores] = None


class FaceDetectionResponse(BaseModel):
    """Response from face detection endpoint"""
    status: str
    timestamp: str
    frame_width: int
    frame_height: int
    faces_detected: int
    faces: List[FaceData]
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "success",
                "timestamp": "2026-02-19T15:30:00",
                "frame_width": 640,
                "frame_height": 480,
                "faces_detected": 1,
                "faces": [
                    {
                        "face_id": 0,
                        "bounding_box": {"x": 100, "y": 150, "width": 200, "height": 250},
                        "confidence": 0.98,
                        "embedding": [0.1, 0.2, -0.15],  # 128D actual
                        "embedding_model": "Facenet",
                        "dominant_emotion": "happy",
                        "emotion_scores": {
                            "angry": 0.01,
                            "disgust": 0.01,
                            "fear": 0.01,
                            "happy": 0.85,
                            "sad": 0.05,
                            "surprise": 0.05,
                            "neutral": 0.02
                        }
                    }
                ]
            }
        }
    )


class CompleteAnalysisResponse(BaseModel):
    """Response from complete analysis endpoint (faces + emotions + objects)"""
    status: str
    timestamp: str
    frame_width: int
    frame_height: int
    faces_detected: int
    faces: List[FaceData]
    objects_detected: int = 0
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "success",
                "timestamp": "2026-02-19T15:30:00",
                "frame_width": 640,
                "frame_height": 480,
                "faces_detected": 1,
                "faces": [],
                "objects_detected": 0
            }
        }
    )




# ============================================================================
# REQUEST/RESPONSE MODELS FOR OBJECT DETECTION
# ============================================================================

class DetectedObject(BaseModel):
    """Detected object with bounding box and class info"""
    class_id: int
    class_name: str
    confidence: float
    bounding_box: BoundingBox


class ObjectDetectionResponse(BaseModel):
    """Response from object detection endpoint"""
    status: str
    timestamp: str
    frame_width: int
    frame_height: int
    objects_detected: int
    detections: List[DetectedObject]
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "success",
                "timestamp": "2026-02-19T15:30:00",
                "frame_width": 640,
                "frame_height": 480,
                "objects_detected": 2,
                "detections": [
                    {
                        "class_id": 0,
                        "class_name": "person",
                        "confidence": 0.95,
                        "bounding_box": {"x": 100, "y": 150, "width": 200, "height": 300}
                    },
                    {
                        "class_id": 2,
                        "class_name": "car",
                        "confidence": 0.87,
                        "bounding_box": {"x": 400, "y": 200, "width": 150, "height": 120}
                    }
                ]
            }
        }
    )


class HealthCheckResponse(BaseModel):
    """Health check endpoint response"""
    status: str
    camera: str
    opencv_version: str
    emotion_detection: str
    timestamp: str
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "camera": "available",
                "opencv_version": "4.8.0.76",
                "emotion_detection": "enabled",
                "timestamp": "2026-02-19T15:30:00"
            }
        }
    )


class ServiceHealthResponse(BaseModel):
    """Root health check response"""
    service: str
    version: str
    status: str
    features: List[str]
    timestamp: str


class FaceDataResponse(BaseModel):
    """Real-time face data for web UI polling"""
    face_count: int
    primary_emotion: Optional[str] = None
    confidence: Optional[float] = None
    timestamp: str


class CameraStateResponse(BaseModel):
    """Camera state response"""
    status: str
