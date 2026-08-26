from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from enum import Enum

class LearningType(str, Enum):
    OBJECT = "object"
    FACT = "fact"

class ObjectData(BaseModel):
    name: str = Field(..., description="Name of the object")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="Object attributes")
    category: Optional[str] = Field(None, description="Object category")
    description: Optional[str] = Field(None, description="Object description")

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
