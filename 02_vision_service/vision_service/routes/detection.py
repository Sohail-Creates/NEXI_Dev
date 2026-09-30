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
from ..services.inference import INFERENCE_SLOTS
from ..services.face_detector import (
    detect_faces_deepface,
    process_face,
    NoFaceDetected,
    FaceEmbeddingError,
    require_deepface,
    validate_detector_backend,
    validate_embedding_model
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Global resource pool reference (set by app.py)
_resource_pool = None


class ObjectInferenceError(RuntimeError):
    """Raised when object inference is unavailable or fails unexpectedly."""


def _process_faces(frame, detector_backend: str, model_name: str):
    """Run face detection/embedding; distinguish no-face from model failure."""
    try:
        face_objs = detect_faces_deepface(frame, detector_backend)
    except NoFaceDetected:
        return []

    faces = []
    for index, face_obj in enumerate(face_objs):
        face_data = process_face(face_obj, index, model_name)
        faces.append(FaceData(
            face_id=face_data["face_id"],
            bounding_box=BoundingBox(**face_data["bounding_box"]),
            confidence=face_data["confidence"],
            embedding=face_data["embedding"],
            embedding_model=face_data["embedding_model"],
        ))
    return faces


def _inference_error(exc: Exception):
    if isinstance(exc, FaceEmbeddingError):
        return HTTPException(
            status_code=500,
            detail={"code": "EMBEDDING_FAILED", "message": str(exc)},
        )
    if isinstance(exc, ObjectInferenceError):
        return HTTPException(
            status_code=503,
            detail={"code": "OBJECT_INFERENCE_FAILED", "message": str(exc)},
        )
    return HTTPException(
        status_code=500,
        detail={"code": "FACE_INFERENCE_FAILED", "message": "Face inference failed"},
    )


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
def detect_faces_from_camera(
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
            
            try:
                with INFERENCE_SLOTS:
                    faces_data = _process_faces(frame, detector_backend, model_name)
            except Exception as exc:
                logger.exception("Camera face inference failed")
                raise _inference_error(exc) from exc
            
            return FaceDetectionResponse(
                status="success" if faces_data else "no_face_detected",
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
def detect_faces_from_upload(
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
        
        try:
            with INFERENCE_SLOTS:
                faces_data = _process_faces(img, detector_backend, model_name)
        except Exception as exc:
            logger.exception("Uploaded-image face inference failed")
            raise _inference_error(exc) from exc
        
        return FaceDetectionResponse(
            status="success" if faces_data else "no_face_detected",
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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Upload processing failed")
        raise HTTPException(status_code=500, detail="Upload processing failed") from e


@router.post("/analyze/complete", response_model=CompleteAnalysisResponse)
def complete_analysis(
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
            
            try:
                with INFERENCE_SLOTS:
                    faces_data = _process_faces(frame, detector_backend, model_name)
                    detector = _resource_pool.get_object_detector()
                    if detector is None:
                        raise ObjectInferenceError("Object detector is unavailable")
                    object_results = detector.detect(frame)
                    if object_results is None:
                        raise ObjectInferenceError("Object detection inference failed")
            except Exception as exc:
                logger.exception("Complete analysis inference failed")
                raise _inference_error(exc) from exc
            
            return CompleteAnalysisResponse(
                status="success" if faces_data else "no_face_detected",
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
