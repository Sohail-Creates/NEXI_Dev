import httpx
import os
from typing import Optional, Dict
from fastapi import HTTPException
import logging
import asyncio
from shared.security import internal_service_headers
from config.ssl_config import client_verify

logger = logging.getLogger(__name__)

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
            logger.error(f"Image file not found: {image_path}")
            raise HTTPException(status_code=400, detail="Image file not found on server")
        
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
                        last_error = f"HTTP {response.status_code}"
                        if attempt < self.max_retries - 1:
                            wait_time = 2 ** attempt
                            logger.warning(f"Vision Service error, retrying in {wait_time}s")
                            await asyncio.sleep(wait_time)
                            continue
                        logger.error(f"Vision Service returned {response.status_code}")
                        raise HTTPException(status_code=503, detail="Vision Service error")
                    
                    result = response.json()
                    
                    # Validate response structure
                    if not isinstance(result, dict):
                        logger.error(f"Invalid Vision Service response format: {type(result)}")
                        raise HTTPException(status_code=503, detail="Invalid response format")
                    
                    # Vision's authoritative response is a collection; enrollment
                    # consumes the first detected face from the uploaded sample.
                    faces = result.get("faces")
                    if not isinstance(faces, list) or not faces:
                        raise HTTPException(status_code=400, detail="No face detected in image")

                    face = faces[0]
                    if not isinstance(face, dict) or not face.get("embedding"):
                        logger.error("Vision Service didn't return face embedding")
                        raise HTTPException(status_code=503, detail="Failed to extract face data")
                    
                    return {
                        "embedding": face["embedding"],
                        "confidence": float(face.get("confidence", 0.0)),
                        "face_detected": True
                    }
                    
            except httpx.TimeoutException:
                last_error = "Timeout"
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Vision Service timeout, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                    continue
                logger.error("Vision Service timeout")
                raise HTTPException(status_code=503, detail="Vision Service timeout")
                
            except httpx.RequestError as e:
                last_error = str(e)
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Vision Service connection error, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                    continue
                logger.error(f"Vision Service connection error: {str(e)}")
                raise HTTPException(status_code=503, detail="Cannot reach Vision Service")
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Vision Service error: {type(e).__name__}: {str(e)}")
                raise HTTPException(status_code=503, detail=f"Vision Service error: {str(e)}")
        
        # All retries exhausted
        logger.error(f"Vision Service failed after {self.max_retries} attempts: {last_error}")
        raise HTTPException(status_code=503, detail=f"Vision Service unavailable: {last_error}")
