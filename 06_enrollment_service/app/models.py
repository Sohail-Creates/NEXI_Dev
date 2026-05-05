from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class EnrollmentRequest(BaseModel):
    user_name: str = Field(..., min_length=1, max_length=100)
    age: Optional[int] = Field(None, ge=1, le=120)
    relation: Optional[str] = Field(None, max_length=50)

class EnrollmentResponse(BaseModel):
    status: str
    message: str
    user_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

class UserCheckResponse(BaseModel):
    exists: bool
    user_id: Optional[str] = None
    enrollment_date: Optional[str] = None
    sample_count: Optional[Dict[str, int]] = None

class ImproveTrainingResponse(BaseModel):
    status: str
    message: str
    total_samples: Dict[str, int]

class UpdateModelResponse(BaseModel):
    status: str
    message: str
    total_samples: Dict[str, int]

class HealthCheckResponse(BaseModel):
    service: str
    status: str
    port: int
    dependencies: Optional[Dict[str, bool]] = None

class StorageStatsResponse(BaseModel):
    total_enrollments: int
    storage_directory: str
    encryption_enabled: bool
    disk_usage_mb: Optional[float] = None

class EnrollmentDataResponse(BaseModel):
    user_id: str
    user_name: str
    enrollment_data: Dict[str, Any]
    saved_at: str