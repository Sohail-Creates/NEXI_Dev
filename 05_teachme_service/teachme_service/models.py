from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from enum import Enum
import math

class LearningType(str, Enum):
    OBJECT = "object"
    FACT = "fact"


class VisionObservation(BaseModel):
    """One selected Vision detection, kept intact across the teach request."""
    class_id: Optional[int] = Field(None, ge=0)
    class_name: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0, le=1, allow_inf_nan=False)
    bounding_box: Dict[str, int]
    embedding: Optional[List[float]] = Field(None, min_length=64, max_length=64)
    embedding_model: Optional[str] = None
    embedding_dimension: Optional[int] = None
    instance_embedding: Optional[List[float]] = Field(None, min_length=512, max_length=512)
    instance_embedding_model: Optional[str] = None
    instance_embedding_dimension: Optional[int] = None
    instance_embedding_version: Optional[int] = None

    @field_validator("bounding_box")
    @classmethod
    def valid_box(cls, box: Dict[str, int]) -> Dict[str, int]:
        if set(box) != {"x", "y", "width", "height"} or box["x"] < 0 or box["y"] < 0 or box["width"] <= 0 or box["height"] <= 0:
            raise ValueError("Vision observation requires a positive x/y/width/height box")
        return box

    @field_validator("embedding")
    @classmethod
    def finite_embedding(cls, values: Optional[List[float]]) -> Optional[List[float]]:
        if values is None:
            return values
        if not all(math.isfinite(value) for value in values) or math.fsum(value * value for value in values) <= 0:
            raise ValueError("Vision observation embedding must be finite and nonzero")
        return values

    @field_validator("instance_embedding")
    @classmethod
    def finite_instance(cls, values: Optional[List[float]]) -> Optional[List[float]]:
        if values is not None and (not all(math.isfinite(v) for v in values) or math.fsum(v*v for v in values) <= 0):
            raise ValueError("Instance embedding must be finite and nonzero")
        return values

    @model_validator(mode="after")
    def valid_spaces(self):
        if self.embedding is None and self.instance_embedding is None:
            raise ValueError("Vision observation requires a visual embedding")
        if self.embedding is not None and (not self.embedding_model or self.embedding_dimension != 64):
            raise ValueError("P3 embedding model/dimension mismatch")
        if self.instance_embedding is not None and (
            self.instance_embedding_model != "torchvision-resnet18-imagenet1k-v1"
            or self.instance_embedding_dimension != 512 or self.instance_embedding_version != 1
        ):
            raise ValueError("Instance embedding model/dimension/version mismatch")
        return self

class ObjectData(BaseModel):
    name: str = Field(..., description="Name of the object")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="Object attributes")
    category: Optional[str] = Field(None, description="Object category")
    description: Optional[str] = Field(None, description="Object description")
    # Transient Vision result. Persist it once on KnowledgeItem, outside the
    # 384-dimensional semantic embedding and the text-derived attributes.
    visual_embedding: Optional[List[float]] = Field(None, min_length=64, max_length=64, exclude=True)
    vision_observation: Optional[VisionObservation] = Field(None, exclude=True)
    vision_observations: Optional[List[VisionObservation]] = Field(None, min_length=1, max_length=6, exclude=True)
    instance_prototypes: Optional[List[List[float]]] = Field(None, exclude=True)
    instance_embedding_model: Optional[str] = Field(None, exclude=True)
    instance_embedding_version: Optional[int] = Field(None, exclude=True)

class FactData(BaseModel):
    subject: str = Field(..., description="Subject of the fact")
    predicate: str = Field(..., description="Relationship or action")
    object: str = Field(..., description="Object of the fact")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional context")

class LearningRequest(BaseModel):
    type: LearningType = Field(..., description="Type of learning - object or fact")
    data: Union[ObjectData, FactData] = Field(..., description="Learning data")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence level")


class VisualRecognitionRequest(BaseModel):
    embedding: List[float]
    embedding_model: str
    embedding_version: Optional[int] = None

    @model_validator(mode="after")
    def valid_query(self):
        dimension = 512 if self.embedding_model == "torchvision-resnet18-imagenet1k-v1" else 64
        if len(self.embedding) != dimension or not all(math.isfinite(v) for v in self.embedding) or math.fsum(v*v for v in self.embedding) <= 0:
            raise ValueError("Invalid visual query vector")
        if dimension == 512 and self.embedding_version != 1:
            raise ValueError("Instance model version mismatch")
        if dimension == 64 and self.embedding_model != "yolov8n-p3-roi-avg-v1":
            raise ValueError("Unsupported visual embedding model")
        return self

class KnowledgeItem(BaseModel):
    id: str
    type: LearningType
    data: Union[ObjectData, FactData]
    tags: List[str]
    confidence: float
    created_at: datetime
    updated_at: datetime
    embedding: Optional[List[float]] = Field(None, description="Vector embedding for similarity search")
    semantic_embedding_hash: Optional[str] = Field(None, exclude_if=lambda value: value is None)
    semantic_embedding_version: Optional[str] = Field(None, exclude_if=lambda value: value is None)
    visual_embedding: Optional[List[float]] = Field(
        None, min_length=64, max_length=64, exclude_if=lambda value: value is None,
        description="Vision P3 object features",
    )
    instance_prototypes: Optional[List[List[float]]] = None
    instance_embedding_model: Optional[str] = None
    instance_embedding_version: Optional[int] = None

    @model_validator(mode="after")
    def validate_instance_prototypes(self):
        if self.instance_prototypes is not None:
            if not 1 <= len(self.instance_prototypes) <= 6:
                raise ValueError("Instance prototype count must be 1..6")
            for vector in self.instance_prototypes:
                if len(vector) != 512 or not all(math.isfinite(v) for v in vector) or math.fsum(v*v for v in vector) <= 0:
                    raise ValueError("Invalid instance prototype")
            if self.instance_embedding_model != "torchvision-resnet18-imagenet1k-v1" or self.instance_embedding_version != 1:
                raise ValueError("Instance prototype model/version mismatch")
        return self
    
    def dict(self, **kwargs):
        """Override dict method to convert datetime to ISO format strings"""
        d = super().dict(**kwargs)
        # Convert datetime objects to ISO format strings
        d['created_at'] = self.created_at.isoformat()
        d['updated_at'] = self.updated_at.isoformat()
        return d

class SyncRequest(BaseModel):
    items: List[KnowledgeItem]

class SyncResponse(BaseModel):
    success: bool
    message: str
    synced_count: int

class TeachingRequest(BaseModel):
    owner_id: str
    image_base64: str
    label_text: str
    metadata: Optional[Dict[str, Any]] = None

class QueryRequest(BaseModel):
    owner_id: str
    image_base64: Optional[str] = None
    query_text: str

class KnowledgeObject(BaseModel):
    object_id: str
    label: str
    metadata: Dict[str, Any]
    confidence: float

class QueryHistoryItem(BaseModel):
    query_id: str
    owner_id: str
    query_text: str
    response_text: str
    confidence: float
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Optional[Dict[str, Any]] = None
