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
    embedding: List[float]
    embedding_model: str
    embedding_dimension: int
    instance_embedding: Optional[List[float]] = None
    instance_embedding_model: Optional[str] = None
    instance_embedding_dimension: Optional[int] = None
    instance_embedding_version: Optional[int] = None

class ObjectDetectionResponse(BaseModel):
    status: str
    timestamp: str
    frame_width: int
    frame_height: int
    objects_detected: int
    detections: List[DetectedObject]


class ObjectSignatureResponse(BaseModel):
    status: str
    bounding_box: BoundingBox
    instance_embedding: List[float]
    instance_embedding_model: str
    instance_embedding_dimension: int
    instance_embedding_version: int

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
    object_model: str
    instance_model: str
    opencv_version: str
    emotion_detection: str
    timestamp: str


class FaceDataResponse(BaseModel):
    face_count: int
    primary_emotion: Optional[str] = None
    confidence: Optional[float] = None
    timestamp: str
