from pydantic import BaseModel, Field, field_validator
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from enum import Enum
import math

class LearningType(str, Enum):
    OBJECT = "object"
    FACT = "fact"


class VisionObservation(BaseModel):
    """One selected Vision detection, kept intact across the teach request."""
    class_id: int = Field(ge=0)
    class_name: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    bounding_box: Dict[str, int]
    embedding: List[float] = Field(min_length=64, max_length=64)
    embedding_model: str = Field(min_length=1)
    embedding_dimension: int = Field(default=64, ge=64, le=64)

    @field_validator("bounding_box")
    @classmethod
    def valid_box(cls, box: Dict[str, int]) -> Dict[str, int]:
        if set(box) != {"x", "y", "width", "height"} or box["x"] < 0 or box["y"] < 0 or box["width"] <= 0 or box["height"] <= 0:
            raise ValueError("Vision observation requires a positive x/y/width/height box")
        return box

    @field_validator("embedding")
    @classmethod
    def finite_embedding(cls, values: List[float]) -> List[float]:
        if not all(math.isfinite(value) for value in values) or math.fsum(value * value for value in values) <= 0:
            raise ValueError("Vision observation embedding must be finite and nonzero")
        return values

class ObjectData(BaseModel):
    name: str = Field(..., description="Name of the object")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="Object attributes")
    category: Optional[str] = Field(None, description="Object category")
    description: Optional[str] = Field(None, description="Object description")
    # Transient Vision result. Persist it once on KnowledgeItem, outside the
    # 384-dimensional semantic embedding and the text-derived attributes.
    visual_embedding: Optional[List[float]] = Field(None, min_length=64, max_length=64, exclude=True)
    vision_observation: Optional[VisionObservation] = Field(None, exclude=True)

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

class KnowledgeItem(BaseModel):
    id: str
    type: LearningType
    data: Union[ObjectData, FactData]
    tags: List[str]
    confidence: float
    created_at: datetime
    updated_at: datetime
    embedding: Optional[List[float]] = Field(None, description="Vector embedding for similarity search")
    visual_embedding: Optional[List[float]] = Field(
        None, min_length=64, max_length=64, exclude_if=lambda value: value is None,
        description="Vision P3 object features",
    )
    
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
