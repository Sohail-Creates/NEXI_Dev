"""
Vision Service Face Detection Routes
Production routes from Vision-Nexus
"""

import io
import cv2
import numpy as np
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, File, UploadFile, Query, Response
from PIL import Image

from ..models import FaceDetectionResponse, CompleteAnalysisResponse, FaceData, BoundingBox, ObjectDetectionResponse, DetectedObject
from ..config import Config
from ..services.resource_pool import ResourcePool
from ..services.face_detector import (
    detect_faces_deepface,
    process_face,
    require_deepface,
    validate_detector_backend,
    validate_embedding_model
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Global resource pool reference (set by app.py)
_resource_pool = None


def set_resource_pool(pool: ResourcePool):
    """Set the global resource pool reference"""
    global _resource_pool
    _resource_pool = pool


@router.get("/frame", responses={200: {"content": {"image/jpeg": {}}}})
async def capture_call_frame(lease_id: str = Query(..., min_length=1)):
    """Capture one JPEG through the existing camera context using a call lease."""
    if _resource_pool is None:
        raise HTTPException(status_code=500, detail="Resource pool not initialized")
    try:
        with _resource_pool.get_camera(
            timeout=Config.CAMERA_TIMEOUT,
            delegated_lease_id=lease_id,
        ) as camera:
            success, frame = camera.read()
            if not success:
                raise HTTPException(status_code=503, detail="Camera frame unavailable")
            encoded, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not encoded:
                raise HTTPException(status_code=500, detail="Camera frame encoding failed")
            return Response(content=buffer.tobytes(), media_type="image/jpeg")
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Call frame capture failed: %s", exc)
        raise HTTPException(status_code=500, detail="Call frame capture failed") from exc


@router.post("/detect/faces", response_model=FaceDetectionResponse)
async def detect_faces_from_camera(
    detector_backend: str = Query(default=Config.DETECTOR_BACKEND, description="Face detection algorithm"),
    model_name: str = Query(default=Config.EMBEDDING_MODEL, description="Embedding model name"),
):
    """
    Detect faces from camera feed.
    """
    if _resource_pool is None:
        raise HTTPException(status_code=500, detail="Resource pool not initialized")
    
    try:
        # Validate parameters
        validate_detector_backend(detector_backend, Config.VALID_BACKENDS)
        validate_embedding_model(model_name, Config.VALID_EMBEDDING_MODELS)
        require_deepface()
        
        # Get camera and read frame
        with _resource_pool.get_camera(timeout=Config.CAMERA_TIMEOUT) as camera:
            success, frame = camera.read()
            if not success:
                # Camera not available - return empty detection instead of 500
                logger.warning("Failed to capture frame from camera - returning empty response")
                return FaceDetectionResponse(
                    status="unavailable",
                    timestamp=datetime.utcnow().isoformat(),
                    frame_width=0,
                    frame_height=0,
                    faces_detected=0,
                    faces=[]
                )
            
            frame_height, frame_width = frame.shape[:2]
            
            # Detect faces
            face_objs = detect_faces_deepface(frame, detector_backend)
            
            # Process each face
            faces_data = []
            for idx, face_obj in enumerate(face_objs):
                try:
                    face_data = process_face(
                        face_obj, idx, model_name
                    )
                    
                    # Convert to response model
                    response_face = FaceData(
                        face_id=face_data['face_id'],
                        bounding_box=BoundingBox(**face_data['bounding_box']),
                        confidence=face_data['confidence'],
                        embedding=face_data['embedding'],
                        embedding_model=face_data['embedding_model'],
                        dominant_emotion=None,
                        emotion_scores=None
                    )
                    faces_data.append(response_face)
                except Exception as e:
                    logger.error(f"Error processing face {idx}: {e}")
                    continue
            
            return FaceDetectionResponse(
                status="success",
                timestamp=datetime.utcnow().isoformat(),
                frame_width=frame_width,
                frame_height=frame_height,
                faces_detected=len(faces_data),
                faces=faces_data
            )
    
    except ValueError as e:
        logger.error(f"Face detection validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        raise
    except ModuleNotFoundError as e:
        logger.error(f"Face model unavailable: {e}")
        raise HTTPException(
            status_code=503,
            detail={"code": "FACE_MODEL_UNAVAILABLE", "message": str(e)},
        ) from e
    except Exception as e:
        logger.error(f"Face detection error: {e}")
        raise HTTPException(status_code=500, detail="Face detection failed") from e


@router.post("/detect/faces/upload", response_model=FaceDetectionResponse)
async def detect_faces_from_upload(
    file: UploadFile = File(...),
    detector_backend: str = Query(default=Config.DETECTOR_BACKEND),
    model_name: str = Query(default=Config.EMBEDDING_MODEL)
):
    """
    Detect faces from uploaded image.
    """
    if _resource_pool is None:
        raise HTTPException(status_code=500, detail="Resource pool not initialized")
    
    try:
        # Validate parameters
        validate_detector_backend(detector_backend, Config.VALID_BACKENDS)
        validate_embedding_model(model_name, Config.VALID_EMBEDDING_MODELS)
        require_deepface()
        
        # Read uploaded file
        contents = file.file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image file")
        
        frame_height, frame_width = img.shape[:2]
        
        face_objs = detect_faces_deepface(img, detector_backend)
        
        # Process each face
        faces_data = []
        for idx, face_obj in enumerate(face_objs):
            try:
                face_data = process_face(
                    face_obj, idx, model_name
                )
                
                response_face = FaceData(
                    face_id=face_data['face_id'],
                    bounding_box=BoundingBox(**face_data['bounding_box']),
                    confidence=face_data['confidence'],
                    embedding=face_data['embedding'],
                    embedding_model=face_data['embedding_model'],
                    dominant_emotion=None,
                    emotion_scores=None
                )
                faces_data.append(response_face)
            except Exception as e:
                logger.error(f"Error processing face {idx}: {e}")
                continue
        
        return FaceDetectionResponse(
            status="success",
            timestamp=datetime.utcnow().isoformat(),
            frame_width=frame_width,
            frame_height=frame_height,
            faces_detected=len(faces_data),
            faces=faces_data
        )
    
    except ModuleNotFoundError as e:
        logger.error(f"Face model unavailable: {e}")
        raise HTTPException(
            status_code=503,
            detail={"code": "FACE_MODEL_UNAVAILABLE", "message": str(e)},
        ) from e
    except Exception as e:
        logger.error(f"Upload processing error: {e}")
        raise HTTPException(status_code=400, detail=f"Upload processing failed: {str(e)}")


@router.post("/analyze/complete", response_model=CompleteAnalysisResponse)
async def complete_analysis(
    detector_backend: str = Query(default=Config.DETECTOR_BACKEND),
    model_name: str = Query(default=Config.EMBEDDING_MODEL)
):
    """
    Complete analysis of current camera frame.
    """
    if _resource_pool is None:
        raise HTTPException(status_code=500, detail="Resource pool not initialized")
    
    try:
        # Validate parameters
        validate_detector_backend(detector_backend, Config.VALID_BACKENDS)
        validate_embedding_model(model_name, Config.VALID_EMBEDDING_MODELS)
        require_deepface()
        
        # Get camera and read frame
        with _resource_pool.get_camera(timeout=Config.CAMERA_TIMEOUT) as camera:
            success, frame = camera.read()
            if not success:
                raise HTTPException(status_code=500, detail="Failed to capture frame")
            
            frame_height, frame_width = frame.shape[:2]
            
            # Detect faces
            face_objs = detect_faces_deepface(frame, detector_backend)
            
            # Process each face
            faces_data = []
            for idx, face_obj in enumerate(face_objs):
                try:
                    face_data = process_face(
                        face_obj, idx, model_name
                    )
                    
                    response_face = FaceData(
                        face_id=face_data['face_id'],
                        bounding_box=BoundingBox(**face_data['bounding_box']),
                        confidence=face_data['confidence'],
                        embedding=face_data['embedding'],
                        embedding_model=face_data['embedding_model'],
                        dominant_emotion=None,
                        emotion_scores=None
                    )
                    faces_data.append(response_face)
                except Exception as e:
                    logger.error(f"Error processing face {idx}: {e}")
                    continue
            
            # Detect Objects
            detector = _resource_pool.get_object_detector()
            object_results = detector.detect(frame) if detector is not None else {"detections": []}
            
            return CompleteAnalysisResponse(
                status="success",
                timestamp=datetime.utcnow().isoformat(),
                frame_width=frame_width,
                frame_height=frame_height,
                faces_detected=len(faces_data),
                faces=faces_data,
                objects_detected=len(object_results.get("detections", [])),
                objects=[DetectedObject(**det) for det in object_results.get("detections", [])]
            )
    
    except ModuleNotFoundError as e:
        logger.error(f"Face model unavailable: {e}")
        raise HTTPException(
            status_code=503,
            detail={"code": "FACE_MODEL_UNAVAILABLE", "message": str(e)},
        ) from e
    except ValueError as e:
        logger.error(f"Analysis validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        raise HTTPException(status_code=500, detail="Complete analysis failed") from e
