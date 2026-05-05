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

from fastapi import APIRouter, HTTPException, File, UploadFile, Query
from PIL import Image

from ..models import FaceDetectionResponse, CompleteAnalysisResponse, FaceData, BoundingBox, EmotionScores, ObjectDetectionResponse, DetectedObject
from ..config import Config
from ..services.resource_pool import ResourcePool
from ..services.face_detector import (
    process_face_with_emotions,
    detect_faces_deepface,
    validate_detector_backend,
    validate_embedding_model
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Global resource pool reference (set by app.py)
_resource_pool: ResourcePool = None


def set_resource_pool(pool: ResourcePool):
    """Set the global resource pool reference"""
    global _resource_pool
    _resource_pool = pool


@router.post("/detect/faces", response_model=FaceDetectionResponse)
async def detect_faces_from_camera(
    detector_backend: str = Query(default=Config.DETECTOR_BACKEND, description="Face detection algorithm"),
    model_name: str = Query(default=Config.EMBEDDING_MODEL, description="Embedding model name"),
    analyze_emotions: bool = Query(default=False, description="Whether to detect emotions")
):
    """
    Detect faces from camera feed.
    Production endpoint from Vision-Nexus
    
    Parameters:
    - detector_backend: Face detection algorithm (opencv, retinaface, mtcnn, ssd)
    - model_name: Embedding model (Facenet, Facenet512, VGG-Face, ArcFace)
    - analyze_emotions: Whether to detect emotions (requires ENABLE_EMOTION_DETECTION=true)
    
    Returns:
    - Face locations, embeddings, and optional emotion analysis
    """
    if _resource_pool is None:
        raise HTTPException(status_code=500, detail="Resource pool not initialized")
    
    try:
        # Validate parameters
        validate_detector_backend(detector_backend, Config.VALID_BACKENDS)
        validate_embedding_model(model_name, Config.VALID_EMBEDDING_MODELS)
        
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
                    face_data = process_face_with_emotions(
                        face_obj, idx, model_name, frame, _resource_pool, analyze_emotions
                    )
                    
                    # Convert to response model
                    response_face = FaceData(
                        face_id=face_data['face_id'],
                        bounding_box=BoundingBox(**face_data['bounding_box']),
                        confidence=face_data['confidence'],
                        embedding=face_data['embedding'],
                        embedding_model=face_data['embedding_model'],
                        dominant_emotion=face_data.get('dominant_emotion'),
                        emotion_scores=EmotionScores(**face_data['emotion_scores']) if face_data['emotion_scores'] else None
                    )
                    faces_data.append(response_face)
                except ImportError as e:
                    # Dependency issue (TensorFlow, etc) - return graceful response
                    if "tensorflow" in str(e).lower() or "tensorflowload" in str(e).lower():
                        logger.warning(f"TensorFlow not available for embeddings: {e}")
                        return FaceDetectionResponse(
                            status="partial",
                            timestamp=datetime.utcnow().isoformat(),
                            frame_width=frame_width,
                            frame_height=frame_height,
                            faces_detected=len(face_objs),  # Can detect faces even without embeddings
                            faces=[]  # Return count but no details due to missing embedding model
                        )
                    # Re-raise if it's a different import error
                    raise
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
        logger.error(f"Invalid parameter: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Face detection error: {e}")
        # More graceful error response
        logger.info("Returning degraded response due to error")
        return FaceDetectionResponse(
            status="error",
            timestamp=datetime.utcnow().isoformat(),
            frame_width=0,
            frame_height=0,
            faces_detected=0,
            faces=[],
        )


@router.post("/detect/faces/upload", response_model=FaceDetectionResponse)
async def detect_faces_from_upload(
    file: UploadFile = File(...),
    detector_backend: str = Query(default=Config.DETECTOR_BACKEND),
    model_name: str = Query(default=Config.EMBEDDING_MODEL),
    analyze_emotions: bool = Query(default=False)
):
    """
    Detect faces from uploaded image.
    Production endpoint from Vision-Nexus
    
    Parameters:
    - file: Image file to analyze
    - detector_backend: Face detection algorithm
    - model_name: Embedding model
    - analyze_emotions: Whether to detect emotions
    """
    if _resource_pool is None:
        raise HTTPException(status_code=500, detail="Resource pool not initialized")
    
    try:
        # Log request parameters
        logger.info(f"Upload endpoint called: detector_backend={detector_backend}, model_name={model_name}, analyze_emotions={analyze_emotions}")
        
        # Validate parameters
        validate_detector_backend(detector_backend, Config.VALID_BACKENDS)
        validate_embedding_model(model_name, Config.VALID_EMBEDDING_MODELS)
        
        # Read uploaded file
        contents = file.file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image file")
        
        frame_height, frame_width = img.shape[:2]
        
        logger.info(f"Detecting faces in uploaded image ({frame_width}x{frame_height})...")
        face_objs = detect_faces_deepface(img, detector_backend)
        logger.info(f"Face detection complete: {len(face_objs)} faces detected, analyze_emotions={analyze_emotions}")
        
        # Process each face
        faces_data = []
        for idx, face_obj in enumerate(face_objs):
            try:
                face_data = process_face_with_emotions(
                    face_obj, idx, model_name, img, _resource_pool, analyze_emotions
                )
                
                response_face = FaceData(
                    face_id=face_data['face_id'],
                    bounding_box=BoundingBox(**face_data['bounding_box']),
                    confidence=face_data['confidence'],
                    embedding=face_data['embedding'],
                    embedding_model=face_data['embedding_model'],
                    dominant_emotion=face_data.get('dominant_emotion'),
                    emotion_scores=EmotionScores(**face_data['emotion_scores']) if face_data['emotion_scores'] else None
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
        logger.error(f"Invalid parameter: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload processing error: {e}")
        raise HTTPException(status_code=400, detail=f"Upload processing failed: {str(e)}")


@router.post("/analyze/complete", response_model=CompleteAnalysisResponse)
async def complete_analysis(
    detector_backend: str = Query(default=Config.DETECTOR_BACKEND),
    model_name: str = Query(default=Config.EMBEDDING_MODEL),
    analyze_emotions: bool = Query(default=Config.ENABLE_EMOTION_DETECTION)
):
    """
    Complete analysis of current camera frame.
    Includes face detection, embeddings, emotion analysis, object detection placeholder.
    Production endpoint from Vision-Nexus
    """
    if _resource_pool is None:
        raise HTTPException(status_code=500, detail="Resource pool not initialized")
    
    try:
        # Validate parameters
        validate_detector_backend(detector_backend, Config.VALID_BACKENDS)
        validate_embedding_model(model_name, Config.VALID_EMBEDDING_MODELS)
        
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
                    face_data = process_face_with_emotions(
                        face_obj, idx, model_name, frame, _resource_pool, analyze_emotions
                    )
                    
                    response_face = FaceData(
                        face_id=face_data['face_id'],
                        bounding_box=BoundingBox(**face_data['bounding_box']),
                        confidence=face_data['confidence'],
                        embedding=face_data['embedding'],
                        embedding_model=face_data['embedding_model'],
                        dominant_emotion=face_data.get('dominant_emotion'),
                        emotion_scores=EmotionScores(**face_data['emotion_scores']) if face_data['emotion_scores'] else None
                    )
                    faces_data.append(response_face)
                except Exception as e:
                    logger.error(f"Error processing face {idx}: {e}")
                    continue
            
            return CompleteAnalysisResponse(
                status="success",
                timestamp=datetime.utcnow().isoformat(),
                frame_width=frame_width,
                frame_height=frame_height,
                faces_detected=len(faces_data),
                faces=faces_data,
                objects_detected=0  # Object detection future feature
            )
    
    except ValueError as e:
        logger.error(f"Invalid parameter: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        # Return graceful response instead of 500
        logger.info("Returning degraded response due to analysis error")
        return CompleteAnalysisResponse(
            status="error",
            timestamp=datetime.utcnow().isoformat(),
            frame_width=0,
            frame_height=0,
            faces_detected=0,
            faces=[],
            objects_detected=0
        )


@router.post("/detect/objects", response_model=ObjectDetectionResponse)
async def detect_objects_from_camera(
    confidence_threshold: float = Query(default=0.5, ge=0.0, le=1.0, description="Minimum confidence for detection")
):
    """
    Detect objects in camera feed using YOLOv8
    
    Parameters:
    - confidence_threshold: Minimum confidence score (0.0-1.0, default 0.5)
    
    Returns:
    - Detected objects with class labels, confidence scores, and bounding boxes
    """
    if _resource_pool is None:
        raise HTTPException(status_code=500, detail="Resource pool not initialized")
    
    try:
        # Get object detector
        detector = _resource_pool.get_object_detector()
        if detector is None or not detector.available:
            raise HTTPException(status_code=503, detail="Object detector not available")
        
        # Get camera frame
        with _resource_pool.get_camera(timeout=5) as camera:
            success, frame = camera.read()
            if not success:
                return {
                    "status": "unavailable",
                    "timestamp": datetime.utcnow().isoformat(),
                    "frame_width": 0,
                    "frame_height": 0,
                    "objects_detected": 0,
                    "detections": []
                }
            
            frame_height, frame_width = frame.shape[:2]
            
            # Run detection
            results = detector.detect(frame, confidence_threshold=confidence_threshold)
            
            if results is None:
                return {
                    "status": "error",
                    "timestamp":datetime.utcnow().isoformat(),
                    "frame_width": frame_width,
                    "frame_height": frame_height,
                    "objects_detected": 0,
                    "detections": []
                }
            
            # Build response
            detections = []
            for det in results.get("detections", []):
                detected_obj = {
                    "class_id": det["class_id"],
                    "class_name": det["class_name"],
                    "confidence": det["confidence"],
                    "bounding_box": {
                        "x": det["bounding_box"]["x"],
                        "y": det["bounding_box"]["y"],
                        "width": det["bounding_box"]["width"],
                        "height": det["bounding_box"]["height"]
                    }
                }
                detections.append(detected_obj)
            
            return {
                "status": "success",
                "timestamp": datetime.utcnow().isoformat(),
                "frame_width": frame_width,
                "frame_height": frame_height,
                "objects_detected": len(detections),
                "detections": detections
            }
            
    except ValueError as e:
        logger.error(f"Invalid parameter: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Object detection error: {e}")
        raise HTTPException(status_code=500, detail="Object detection failed")


@router.post("/detect/objects/upload", response_model=ObjectDetectionResponse)
async def detect_objects_from_upload(
    file: UploadFile = File(...),
    confidence_threshold: float = Query(default=0.5, ge=0.0, le=1.0, description="Minimum confidence for detection")
):
    """
    Detect objects in uploaded image using YOLOv8
    
    Parameters:
    - file: Image file to analyze
    - confidence_threshold: Minimum confidence score (0.0-1.0, default 0.5)
    
    Returns:
    - Detected objects with class labels, confidence scores, and bounding boxes
    """
    if _resource_pool is None:
        raise HTTPException(status_code=500, detail="Resource pool not initialized")
    
    try:
        # Get object detector
        detector = _resource_pool.get_object_detector()
        if detector is None or not detector.available:
            raise HTTPException(status_code=503, detail="Object detector not available")
        
        # Read uploaded file
        contents = file.file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image file")
        
        frame_height, frame_width = img.shape[:2]
        
        logger.info(f"Detecting objects in uploaded image ({frame_width}x{frame_height}), confidence_threshold={confidence_threshold}...")
        
        # Run detection
        results = detector.detect(img, confidence_threshold=confidence_threshold)
        
        if results is None:
            return {
                "status": "error",
                "timestamp": datetime.utcnow().isoformat(),
                "frame_width": frame_width,
                "frame_height": frame_height,
                "objects_detected": 0,
                "detections": []
            }
        
        # Build response
        detections = []
        for det in results.get("detections", []):
            detected_obj = {
                "class_id": det["class_id"],
                "class_name": det["class_name"],
                "confidence": det["confidence"],
                "bounding_box": {
                    "x": det["bounding_box"]["x"],
                    "y": det["bounding_box"]["y"],
                    "width": det["bounding_box"]["width"],
                    "height": det["bounding_box"]["height"]
                }
            }
            detections.append(detected_obj)
        
        logger.info(f"Object detection complete: {len(detections)} objects detected")
        
        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "frame_width": frame_width,
            "frame_height": frame_height,
            "objects_detected": len(detections),
            "detections": detections
        }
            
    except ValueError as e:
        logger.error(f"Invalid parameter: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload object detection error: {e}")
        raise HTTPException(status_code=400, detail=f"Object detection failed: {str(e)}")
