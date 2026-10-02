import httpx
import os
from typing import Optional, Dict
from fastapi import HTTPException
import logging
import asyncio
import math
from shared.security import internal_service_headers
from config.ssl_config import client_verify
from app.utils.validators import ErrorFormatter

logger = logging.getLogger(__name__)


def photo_error(status: int, reason: str, message: str) -> HTTPException:
    # Lazy import avoids a client/service import cycle; one metadata shape.
    from app.services.photo_validation import validation_result
    return HTTPException(status_code=status, detail={
        **validation_result(valid=False, reason=reason), "code": reason, "message": message})

class VisionClient:
    """Client for communicating with Vision Service with timeout & retry"""
    
    def __init__(self):
        self.base_url = os.getenv("VISION_SERVICE_URL", "https://localhost:8001")
        self.timeout = int(os.getenv("SERVICE_TIMEOUT", 30))
        self.max_retries = int(os.getenv("SERVICE_MAX_RETRIES", 2))
    
    async def check_health(self) -> bool:
        """Check if Vision Service is healthy"""
        try:
            async with httpx.AsyncClient(timeout=5.0, headers=internal_service_headers(), verify=client_verify(self.base_url)) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except Exception as e:
            logger.debug(f"Vision Service health check failed: {str(e)}")
            return False
    
    async def get_face_embedding(self, image_path: str) -> Dict:
        """
        Send image to Vision Service and get face embedding with retry logic
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Dict containing face embedding and metadata
            
        Raises:
            HTTPException: If Vision Service fails or face not detected
        """
        # Validate file exists
        if not os.path.exists(image_path):
            logger.error("photo_validation", extra={"reason": "INVALID_IMAGE", "result": "failed"})
            raise photo_error(400, "INVALID_IMAGE", "Image file not found on server")
        
        # Retry logic
        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, headers=internal_service_headers(), verify=client_verify(self.base_url)) as client:
                    with open(image_path, 'rb') as f:
                        files = {'file': (os.path.basename(image_path), f, 'image/jpeg')}
                        
                        response = await client.post(
                            f"{self.base_url}/api/v1/detect/faces/upload",
                            files=files,
                        )
                    
                    if response.status_code != 200:
                        try:
                            detail = response.json()
                        except ValueError:
                            detail = response.text
                        last_error = f"HTTP {response.status_code}: {ErrorFormatter.error_message(detail)}"
                        if response.status_code >= 500 and attempt < self.max_retries - 1:
                            wait_time = 2 ** attempt
                            logger.warning(f"Vision Service error, retrying in {wait_time}s")
                            await asyncio.sleep(wait_time)
                            continue
                        logger.error("Vision Service returned %s", last_error)
                        # Never forward arbitrary upstream exception text/paths.
                        if response.status_code in (400, 413, 415, 422):
                            raise photo_error(response.status_code, "INVALID_IMAGE", "Invalid image file, format or size")
                        if "FACE_MODEL_UNAVAILABLE" in str(detail) or "MODEL_NOT_READY" in str(detail):
                            raise photo_error(503, "MODEL_NOT_READY", "Face model is not ready")
                        raise photo_error(503, "INFERENCE_ERROR", "Face inference failed; check server logs")
                    
                    result = response.json()
                    
                    # Validate response structure
                    if not isinstance(result, dict):
                        logger.error(f"Invalid Vision Service response format: {type(result)}")
                        raise photo_error(503, "REQUEST_FAILURE", "Invalid response from Vision Service")
                    
                    # Vision's authoritative response is a collection; enrollment
                    # consumes the first detected face from the uploaded sample.
                    faces = result.get("faces")
                    if not isinstance(faces, list):
                        raise photo_error(503, "REQUEST_FAILURE", "Invalid face response from Vision Service")
                    if not faces:
                        raise photo_error(400, "NO_FACE_DETECTED", "No face detected in image")

                    face = faces[0]
                    if not isinstance(face, dict) or not face.get("embedding"):
                        logger.error("Vision Service didn't return face embedding")
                        raise photo_error(503, "INFERENCE_ERROR", "Failed to extract face data")
                    vector = face["embedding"]
                    if (not isinstance(vector, list) or
                        not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in vector) or
                        not any(value != 0 for value in vector)):
                        raise photo_error(503, "INFERENCE_ERROR", "Vision returned an invalid face embedding")
                    
                    return {
                        "embedding": face["embedding"],
                        "confidence": float(face.get("confidence", 0.0)),
                        "face_detected": True
                    }
                    
            except httpx.TimeoutException as e:
                last_error = ErrorFormatter.error_message(e)
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Vision Service timeout, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                    continue
                logger.exception("Vision Service timeout: %s", type(e).__name__)
                raise photo_error(503, "REQUEST_FAILURE", "Vision Service timed out; try again") from e
                
            except httpx.RequestError as e:
                last_error = ErrorFormatter.error_message(e)
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Vision Service connection error, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                    continue
                logger.exception("Vision Service connection error: %s", last_error)
                raise photo_error(503, "REQUEST_FAILURE", "Cannot reach Vision Service; check service readiness") from e
                
            except HTTPException:
                raise
            except Exception as e:
                message = ErrorFormatter.error_message(e)
                logger.exception("Vision Service error: %s: %s", type(e).__name__, message)
                raise photo_error(503, "INFERENCE_ERROR", "Face inference failed; check server logs") from e
        
        # All retries exhausted
        logger.error(f"Vision Service failed after {self.max_retries} attempts: {last_error}")
        raise photo_error(503, "REQUEST_FAILURE", "Vision Service unavailable")
