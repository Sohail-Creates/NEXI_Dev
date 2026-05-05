import httpx
import os
import sys
from typing import Dict, Optional
from fastapi import HTTPException
import logging
import asyncio

# Add shared utils to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from shared.utils import CircuitBreaker

logger = logging.getLogger(__name__)

class CentralServerClient:
    """Client for communicating with Central Server with circuit breaker"""
    
    def __init__(self):
        self.base_url = os.getenv("CENTRAL_SERVER_URL", "http://localhost:8000")
        self.timeout = int(os.getenv("SERVICE_TIMEOUT", 30))
        self.max_retries = int(os.getenv("SERVICE_MAX_RETRIES", 3))
        self.circuit_breaker = CircuitBreaker()
    
    async def check_health(self) -> bool:
        """Check if Central Server is healthy"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Central Server health check failed: {str(e)}")
            return False
    
    async def register_user(self, user_data: Dict) -> Dict:
        """
        Send user enrollment data to Central Server with retry and circuit breaker
        
        Args:
            user_data: Dictionary containing user information and embeddings
            
        Returns:
            Dict containing user_id and registration status
            
        Raises:
            HTTPException: If registration fails
        """
        # Check circuit breaker
        if not self.circuit_breaker.can_request():
            logger.error("Circuit breaker OPEN: Central Server unavailable")
            raise HTTPException(
                status_code=503,
                detail="Central Server is currently unavailable. Please try again later."
            )
        
        # Validate user_data structure
        if not isinstance(user_data, dict):
            logger.error("Invalid user_data format")
            raise HTTPException(status_code=400, detail="Invalid registration data format")
        
        user_name = user_data.get("name") or user_data.get("user_name")
        if not user_name:
            logger.error("User name missing from registration data")
            raise HTTPException(status_code=400, detail="User name is required")
        
        if not user_data.get("face_embeddings") or not user_data.get("voice_embeddings"):
            logger.error("Embeddings missing from registration data")
            raise HTTPException(status_code=400, detail="Face and voice embeddings are required")
        
        # Retry logic with exponential backoff
        endpoint = "/users/data/add_user"
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    url = f"{self.base_url}{endpoint}"
                    logger.info(f"Registering user with Central Server (attempt {attempt + 1}/{self.max_retries})")
                    
                    payload = dict(user_data)
                    payload["name"] = user_name
                    response = await client.post(url, json=payload)
                    
                    if response.status_code == 200:
                        try:
                            result = response.json()
                        except Exception as e:
                            logger.error(f"Failed to parse Central Server response: {str(e)}")
                            raise HTTPException(status_code=502, detail="Invalid response format")
                        
                        # Validate response contains user_id
                        if not result.get("user_id"):
                            logger.error(f"Central Server response missing user_id: {result}")
                            raise HTTPException(status_code=502, detail="Registration incomplete")
                        
                        # Success - update circuit breaker
                        self.circuit_breaker.record_success()
                        logger.info(f"User {user_name} registered as {result.get('user_id')}")
                        
                        return {
                            "user_id": result.get("user_id"),
                            "status": result.get("status", "registered"),
                            "message": result.get("message", "User registered successfully")
                        }
                    
                    elif response.status_code == 404:
                        logger.error(f"Registration endpoint not found: {endpoint}")
                        raise HTTPException(status_code=503, detail="Central Server endpoint not found")
                    
                    else:
                        # Transient error - record and retry
                        last_error = f"HTTP {response.status_code}"
                        if attempt < self.max_retries - 1:
                            wait_time = 2 ** attempt  # Exponential backoff
                            logger.warning(f"Registration failed (attempt {attempt + 1}), retrying in {wait_time}s")
                            await asyncio.sleep(wait_time)
                        continue
                
            except httpx.TimeoutException as e:
                last_error = f"Timeout: {str(e)}"
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Central Server timeout, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                    continue
                    
            except httpx.RequestError as e:
                last_error = f"Request error: {str(e)}"
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Central Server connection error, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                    continue
        
        # All retries failed - update circuit breaker and raise
        self.circuit_breaker.record_failure()
        logger.error(f"Central Server registration failed after {self.max_retries} attempts: {last_error}")
        raise HTTPException(
            status_code=503,
            detail=f"Central Server registration failed. {last_error}"
        )
    
    async def get_user_by_name(self, user_name: str) -> Optional[Dict]:
        """
        Get user data from Central Server by name
        
        Args:
            user_name: Name of the user to retrieve
            
        Returns:
            Dict containing user data or None if not found
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/users/search/{user_name}"
                )
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    logger.info(f"User '{user_name}' not found in Central Server")
                    return None
                else:
                    logger.error(f"Failed to get user: HTTP {response.status_code}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error querying Central Server for user '{user_name}': {str(e)}")
            return None
    
    async def update_user_embeddings(
        self,
        user_id: str,
        face_embeddings: list,
        voice_embeddings: list,
        avg_face_confidence: float = 0.0,
        avg_voice_quality: float = 0.0,
        face_confidences: list = None,
        voice_qualities: list = None
    ) -> Dict:
        """
        Replace user embeddings entirely (for re-enrollment/update_model)
        
        Args:
            user_id: User ID
            face_embeddings: List of new face embeddings
            voice_embeddings: List of new voice embeddings
            avg_face_confidence: Average confidence for faces
            avg_voice_quality: Average quality for voice
            face_confidences: Per-sample confidence scores
            voice_qualities: Per-sample quality scores
            
        Returns:
            Dict with update status
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                payload = {
                    "face_embeddings": face_embeddings,
                    "voice_embeddings": voice_embeddings,
                    "avg_face_confidence": avg_face_confidence,
                    "avg_voice_quality": avg_voice_quality,
                    "face_confidences": face_confidences or [0.0] * len(face_embeddings),
                    "voice_qualities": voice_qualities or [0.0] * len(voice_embeddings)
                }
                
                response = await client.put(
                    f"{self.base_url}/users/{user_id}/embeddings",
                    json=payload,
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"User {user_id} embeddings updated")
                    return result
                elif response.status_code == 404:
                    raise HTTPException(status_code=404, detail=f"User {user_id} not found")
                else:
                    error_detail = response.text
                    raise HTTPException(status_code=response.status_code, detail=error_detail)
                    
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating user embeddings: {str(e)}")
            raise HTTPException(status_code=503, detail=f"Failed to update user embeddings: {str(e)}")
    
    async def append_user_embeddings(
        self,
        user_id: str,
        face_embeddings: list,
        voice_embeddings: list,
        face_confidences: list = None,
        voice_qualities: list = None
    ) -> Dict:
        """
        Append new embeddings to user (for improve training)
        
        Args:
            user_id: User ID
            face_embeddings: List of new face embeddings to append
            voice_embeddings: List of new voice embeddings to append
            face_confidences: Per-sample confidence scores
            voice_qualities: Per-sample quality scores
            
        Returns:
            Dict with update status and new total counts
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                payload = {
                    "face_embeddings": face_embeddings,
                    "voice_embeddings": voice_embeddings,
                    "face_confidences": face_confidences or [0.0] * len(face_embeddings),
                    "voice_qualities": voice_qualities or [0.0] * len(voice_embeddings)
                }
                
                response = await client.post(
                    f"{self.base_url}/users/{user_id}/append-embeddings",
                    json=payload,
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"User {user_id} embeddings appended")
                    return result
                elif response.status_code == 404:
                    raise HTTPException(status_code=404, detail=f"User {user_id} not found")
                else:
                    error_detail = response.text
                    raise HTTPException(status_code=response.status_code, detail=error_detail)
                    
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error appending user embeddings: {str(e)}")
            raise HTTPException(status_code=503, detail=f"Failed to append user embeddings: {str(e)}")