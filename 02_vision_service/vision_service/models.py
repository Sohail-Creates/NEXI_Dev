from pydantic import BaseModel, Field
from typing import List, Optional, Dict

class BoundingBox(BaseModel):
    x: int
    y: int
    width: int
    height: int

class FaceData(BaseModel):
    face_id: int
    bounding_box: BoundingBox
    confidence: float
    embedding: List[float]
    embedding_model: str

class FaceDetectionResponse(BaseModel):
    status: str
    timestamp: str
    frame_width: int
    frame_height: int
    faces_detected: int
    faces: List[FaceData]

class DetectedObject(BaseModel):
    class_id: int
    class_name: str
    confidence: float
    bounding_box: BoundingBox

class ObjectDetectionResponse(BaseModel):
    status: str
    timestamp: str
    frame_width: int
    frame_height: int
    objects_detected: int
    detections: List[DetectedObject]

class CompleteAnalysisResponse(BaseModel):
    status: str
    timestamp: str
    frame_width: int
    frame_height: int
    faces_detected: int
    faces: List[FaceData]
    objects_detected: int
    objects: List[DetectedObject]

class CameraStateResponse(BaseModel):
    status: str
    message: str


class ServiceHealthResponse(BaseModel):
    service: str
    version: str
    status: str
    features: List[str]
    timestamp: str


class HealthCheckResponse(BaseModel):
    status: str
    camera: str
    face_model: str
    opencv_version: str
    emotion_detection: str
    timestamp: str


class FaceDataResponse(BaseModel):
    face_count: int
    primary_emotion: Optional[str] = None
    confidence: Optional[float] = None
    timestamp: str
