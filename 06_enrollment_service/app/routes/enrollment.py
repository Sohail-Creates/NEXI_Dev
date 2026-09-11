from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, Path, Request
from shared.jwt_manager import require_user_ownership
from shared.security import require_internal_service
from typing import List, Optional
from app.models import (
    EnrollmentResponse, 
    HealthCheckResponse, 
    UserCheckResponse,
    ImproveTrainingResponse,
    UpdateModelResponse,
    StorageStatsResponse,
    EnrollmentDataResponse
)
from app.services.enrollment_service import EnrollmentService
from app.services.user_check_service import UserCheckService
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/enrollment", tags=["Enrollment"])

# Initialize services
enrollment_service = EnrollmentService(
    upload_dir=os.getenv("TEMP_UPLOAD_DIR", "./temp_uploads"),
    max_photo_size=int(os.getenv("MAX_PHOTO_SIZE", 5242880)),
    max_voice_size=int(os.getenv("MAX_VOICE_SIZE", 10485760))
)

user_check_service = UserCheckService()


@router.get("/check-user", response_model=UserCheckResponse)
async def check_user(request: Request, name: str = Query(..., description="Name of the user to check")):

    await require_internal_service(request)
    result = await user_check_service.check_user_exists(name)
    return UserCheckResponse(**result)


@router.post("/enroll", response_model=EnrollmentResponse)
async def enroll_user(
    user_name: str = Form(..., description="Name of the user"),
    photos: List[UploadFile] = File(..., description="Exactly 5 photos (JPG/PNG, max 5MB each)"),
    voice_samples: List[UploadFile] = File(..., description="Exactly 5 voice samples (WAV/MP3, max 10MB each)"),
    age: Optional[int] = Form(None, description="User's age (optional)"),
    relation: Optional[str] = Form(None, description="Relationship (e.g., 'Father', 'Sister') (optional)")
):
    """
    Enroll a new user with 5 photos and 5 voice samples
    """
    try:
        result = await enrollment_service.process_enrollment(
            user_name=user_name,
            photos=photos,
            voice_samples=voice_samples,
            age=age,
            relation=relation
        )
        
        return EnrollmentResponse(**result)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/improve-training/{user_id}", response_model=ImproveTrainingResponse)
async def improve_training(
    request: Request,
    user_id: str,
    additional_photos: List[UploadFile] = File(..., description="5 additional photos"),
    additional_voice_samples: List[UploadFile] = File(..., description="5 additional voice samples")
):
    """
    Add 5 more photos and 5 more voice samples to existing user
    (OLD samples are KEPT, NEW samples are ADDED)
    """
    try:
        require_user_ownership(request, user_id)
        result = await enrollment_service.improve_training(
            user_id=user_id,
            additional_photos=additional_photos,
            additional_voice_samples=additional_voice_samples
        )
        
        return ImproveTrainingResponse(**result)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-model/{user_id}", response_model=UpdateModelResponse)
async def update_model(
    request: Request,
    user_id: str,
    new_photos: List[UploadFile] = File(..., description="5 new photos (replaces old)"),
    new_voice_samples: List[UploadFile] = File(..., description="5 new voice samples (replaces old)")
):
    """
    Replace all old photos and voice samples with new ones (RE-ENROLLMENT)
    (OLD samples are DELETED, REPLACED by NEW samples)
    """
    try:
        require_user_ownership(request, user_id)
        result = await enrollment_service.update_model(
            user_id=user_id,
            new_photos=new_photos,
            new_voice_samples=new_voice_samples
        )
        
        return UpdateModelResponse(**result)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health-detailed", response_model=HealthCheckResponse)
async def health_check_detailed():

    dependencies = await enrollment_service.check_dependencies()
    
    all_healthy = all(dependencies.values())
    
    return HealthCheckResponse(
        service=os.getenv("SERVICE_NAME", "Enrollment Service"),
        status="healthy" if all_healthy else "degraded",
        port=int(os.getenv("SERVICE_PORT", 8005)),
        dependencies=dependencies
    )


@router.get("/storage/stats", response_model=StorageStatsResponse)
async def get_storage_stats(request: Request):

    try:
        await require_internal_service(request)
        stats = await enrollment_service.get_storage_stats()
        return StorageStatsResponse(**stats)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get storage stats: {str(e)}")


@router.get("/storage/list")
async def list_enrollments(request: Request):

    try:
        await require_internal_service(request)
        user_ids = await enrollment_service.list_all_enrollments()
        return {
            "status": "success",
            "total_enrollments": len(user_ids),
            "user_ids": user_ids
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list enrollments: {str(e)}")


@router.get("/storage/{user_id}", response_model=EnrollmentDataResponse)
async def get_enrollment_data(
    request: Request,
    user_id: str = Path(..., description="User ID to retrieve")
):

    try:
        require_user_ownership(request, user_id)
        data = await enrollment_service.get_enrollment_data(user_id)
        
        if not data:
            raise HTTPException(
                status_code=404,
                detail=f"No enrollment data found for user_id: {user_id}"
            )
        
        return EnrollmentDataResponse(
            user_id=user_id,
            user_name=data.get("user_name", "Unknown"),
            enrollment_data=data,
            saved_at=data.get("saved_at", "Unknown")
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve enrollment data: {str(e)}")


@router.delete("/storage/{user_id}")
async def delete_enrollment_data(
    request: Request,
    user_id: str = Path(..., description="User ID to delete")
):

    try:
        require_user_ownership(request, user_id)
        success = await enrollment_service.delete_enrollment_data(user_id)
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"No enrollment data found for user_id: {user_id}"
            )
        
        return {
            "status": "success",
            "message": f"Enrollment data for user '{user_id}' deleted successfully",
            "user_id": user_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete enrollment data: {str(e)}")


@router.delete("/delete-user/{user_name}")
async def delete_user_synchronized(
    request: Request,
    user_name: str = Path(..., description="User name to delete")
):
    """Delete user from both Central Server and local storage"""
    try:
        actual_user_id, _ = await enrollment_service.find_enrollment_by_user_name(user_name)
        require_user_ownership(request, actual_user_id or user_name)
        result = await enrollment_service.delete_user_from_all(user_name)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete user: {str(e)}")
