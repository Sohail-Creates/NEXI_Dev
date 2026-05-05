"""
Phase 5: Verification Endpoint for Central Server
Orchestrates speaker verification across the system.

Endpoint: POST /users/verify
- Accepts audio file or pre-extracted embedding
- Calls Audio Service to extract speaker embedding (if audio provided)
- Calls Verification Service to match against enrolled users
- Returns APIResponse with verification result

Full verification flow:
1. Input validation (audio file exists OR embedding provided)
2. If audio: Call Audio Service /process-voice to extract embedding
3. Call Verification Service to match embedding
4. Return result with user_name, similarity_score, confidence

Non-Negotiable Rules:
- No silent failures - all errors explicit
- All embeddings validated
- Similarity scores always computed
- Never return uncertain results
- Full error context in response
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, File, UploadFile, Form
import aiohttp
import asyncio
import tempfile
import os
from datetime import datetime
from dataclasses import dataclass

# Import shared models
import sys
sys.path.insert(0, '/d:/Internship/TN_Team/Nexi_Robo')
from shared.models.api_response import APIResponse, ErrorCode, success_response, error_response

# Import verification service
from verification_service import get_verification_service, VerificationResult

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["verification"])

# Audio Service URL
AUDIO_SERVICE_URL = "http://localhost:8002"


@dataclass
class VerifyRequest:
    """Request for speaker verification."""
    audio_file: Optional[bytes] = None
    user_name: Optional[str] = None
    embedding: Optional[List[float]] = None


async def call_audio_service_for_verification(file_path: str, trace_id: str) -> tuple:
    """
    Call Audio Service to extract speaker embedding.
    
    Args:
        file_path: Path to audio file
        trace_id: Correlation ID for logging
        
    Returns:
        Tuple of (success: bool, embeddings: List[float], error: str)
    """
    try:
        if not os.path.exists(file_path):
            return False, None, f"Audio file not found: {file_path}"
        
        with open(file_path, 'rb') as f:
            files = {'file': f}
            headers = {'X-Correlation-ID': trace_id}
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{AUDIO_SERVICE_URL}/api/v1/process-voice",
                    files=files,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    data = await response.json()
                    
                    # Validate response contract
                    if not data.get("success"):
                        error_info = data.get("error", {})
                        error_msg = error_info.get("message", "Unknown error from Audio Service")
                        logger.error(f"[{trace_id}] Audio Service failed: {error_msg}")
                        return False, None, error_msg
                    
                    response_data = data.get("data", {})
                    embeddings = response_data.get("embeddings")
                    
                    if not embeddings:
                        return False, None, "No embeddings returned from Audio Service"
                    
                    # Validate embeddings (should be 256D, non-zero)
                    if not isinstance(embeddings, list):
                        return False, None, "Invalid embedding format from Audio Service"
                    
                    if len(embeddings) != 256:
                        return False, None, f"Invalid embedding dimension: {len(embeddings)} (expected 256)"
                    
                    if all(x == 0 for x in embeddings):
                        return False, None, "Embeddings are all zeros (invalid audio)"
                    
                    logger.info(f"[{trace_id}] Audio Service returned valid 256D embeddings")
                    return True, embeddings, None
    
    except aiohttp.ClientError as e:
        error_msg = f"Audio Service connection error: {str(e)}"
        logger.error(f"[{trace_id}] {error_msg}")
        return False, None, error_msg
    except asyncio.TimeoutError:
        error_msg = "Audio Service timeout"
        logger.error(f"[{trace_id}] {error_msg}")
        return False, None, error_msg
    except Exception as e:
        error_msg = f"Unexpected error calling Audio Service: {str(e)}"
        logger.error(f"[{trace_id}] {error_msg}")
        return False, None, error_msg


@router.post("/verify", response_model=APIResponse)
async def verify_speaker(
    trace_id: str = "verify-" + datetime.utcnow().isoformat(),
    audio_file: Optional[UploadFile] = File(None),
    embedding: Optional[str] = Form(None),
    user_name: Optional[str] = Form(None)
) -> APIResponse:
    """
    Verify speaker identity.
    
    Two modes:
    1. Identify speaker from audio:
       - POST /users/verify with audio_file
       - Returns best matching user with similarity score
    
    2. Verify specific user:
       - POST /users/verify with audio_file and user_name
       - Returns match result for that specific user
    
    3. Verify with pre-extracted embedding:
       - POST /users/verify with embedding (JSON) and optional user_name
    
    Args:
        audio_file: Audio file to process (wav, mp3, ogg)
        embedding: Pre-extracted 256D embedding (JSON array string)
        user_name: Optional user to verify against
        trace_id: Correlation ID
        
    Returns:
        APIResponse with verification result:
        {
            "success": true,
            "data": {
                "result": "match" | "no_match" | "insufficient_data",
                "user_name": "string",
                "similarity_score": 0.0-1.0,
                "threshold": 0.75,
                "confidence": 0.0-1.0,
                "timestamp": "ISO8601"
            },
            "error": null
        }
    """
    logger.info(f"[{trace_id}] Verification request: user={user_name}, audio={audio_file is not None}, embedding={embedding is not None}")
    
    try:
        # Get verification service
        verification_service = get_verification_service()
        
        # Extract speaker embedding
        speaker_embedding = None
        
        if audio_file:
            # Mode 1: Extract embedding from audio file
            logger.info(f"[{trace_id}] Processing audio file: {audio_file.filename}")
            
            # Save temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                content = await audio_file.read()
                tmp.write(content)
                tmp_path = tmp.name
            
            try:
                # Call Audio Service
                success, embeddings, error = await call_audio_service_for_verification(tmp_path, trace_id)
                
                if not success:
                    logger.error(f"[{trace_id}] Audio extraction failed: {error}")
                    return error_response(
                        code=ErrorCode.PROCESSING_FAILED,
                        message="Failed to extract speaker embedding from audio",
                        details={"audio_error": error},
                        trace_id=trace_id
                    )
                
                speaker_embedding = embeddings
            
            finally:
                # Clean up temp file
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
        
        elif embedding:
            # Mode 2: Use pre-extracted embedding
            logger.info(f"[{trace_id}] Using pre-extracted embedding")
            
            try:
                import json
                speaker_embedding = json.loads(embedding)
                
                # Validate
                if not isinstance(speaker_embedding, list):
                    return error_response(
                        code=ErrorCode.INVALID_INPUT,
                        message="Embedding must be JSON array",
                        details={"field": "embedding"},
                        trace_id=trace_id
                    )
                
                if len(speaker_embedding) != 256:
                    return error_response(
                        code=ErrorCode.INVALID_INPUT,
                        message=f"Embedding must be 256D, got {len(speaker_embedding)}D",
                        details={"field": "embedding", "expected": 256, "got": len(speaker_embedding)},
                        trace_id=trace_id
                    )
            
            except json.JSONDecodeError as e:
                return error_response(
                    code=ErrorCode.INVALID_INPUT,
                    message="Invalid embedding JSON",
                    details={"error": str(e)},
                    trace_id=trace_id
                )
        
        else:
            # Mode 3: Neither audio nor embedding provided
            return error_response(
                code=ErrorCode.MISSING_FIELD,
                message="Either 'audio_file' or 'embedding' must be provided",
                details={"required_fields": ["audio_file or embedding"]},
                trace_id=trace_id
            )
        
        # Verify speaker
        if speaker_embedding is None:
            return error_response(
                code=ErrorCode.PROCESSING_FAILED,
                message="Failed to extract speaker embedding",
                details={},
                trace_id=trace_id
            )
        
        logger.info(f"[{trace_id}] Calling verification service (user={user_name})")
        verification_result = verification_service.verify_speaker(
            speaker_embedding,
            expected_user=user_name
        )
        
        # Check for errors
        if verification_result.result == VerificationResult.ERROR:
            logger.error(f"[{trace_id}] Verification error: {verification_result.error_message}")
            return error_response(
                code=ErrorCode.PROCESSING_FAILED,
                message="Speaker verification failed",
                details={"verification_error": verification_result.error_message},
                trace_id=trace_id
            )
        
        # Return success
        logger.info(f"[{trace_id}] Verification complete: {verification_result.result.value}, user={verification_result.user_name}, score={verification_result.similarity_score:.4f}")
        
        return success_response(
            data=verification_result.to_dict(),
            trace_id=trace_id
        )
    
    except Exception as e:
        logger.error(f"[{trace_id}] Unexpected verification error: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.SERVICE_ERROR,
            message="Unexpected verification error",
            details={"error": str(e)},
            trace_id=trace_id
        )


@router.get("/verify/status", response_model=APIResponse)
async def verify_status(trace_id: str = "verify-status") -> APIResponse:
    """
    Check verification service status.
    
    Returns:
        APIResponse with service status
    """
    try:
        verification_service = get_verification_service()
        
        # Check if any users enrolled
        enrollments = verification_service._load_enrollments()
        
        return success_response(
            data={
                "status": "ready",
                "enrolled_users": len(enrollments),
                "similarity_threshold": verification_service.SIMILARITY_THRESHOLD,
                "min_similarity": verification_service.MIN_SIMILARITY,
                "max_similarity": verification_service.MAX_SIMILARITY
            },
            trace_id=trace_id
        )
    
    except Exception as e:
        logger.error(f"[{trace_id}] Error checking verification status: {e}")
        return error_response(
            code=ErrorCode.SERVICE_ERROR,
            message="Failed to check verification status",
            details={"error": str(e)},
            trace_id=trace_id
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Verification endpoints ready")
    print("- POST /users/verify - Verify speaker identity")
    print("- GET /users/verify/status - Check service status")
