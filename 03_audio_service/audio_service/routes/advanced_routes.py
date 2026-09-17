"""
Week 2 API routes for audio intelligence features.
Implements endpoints for wake word detection, speaker verification, and speech-to-text.
"""

import logging
import os
from datetime import datetime
import numpy as np
from fastapi import APIRouter, HTTPException, status, UploadFile, File
from fastapi.responses import JSONResponse

from audio_service.models import (
    WakeWordStatusResponse,
    WakeWordDetectResponse,
    EnrollSpeakerRequest,
    EnrollSpeakerResponse,
    ListSpeakersResponse,
    VerifySpeakerRequest,
    VerifySpeakerResponse,
    TranscribeRequest,
    TranscribeResponse,
    ProcessCommandRequest,
    ProcessCommandResponse,
    ErrorResponse
)
from audio_service.services.wake_word_service import WakeWordService
from audio_service.services.speaker_service import SpeakerService, SpeakerServiceError
from audio_service.services.stt_service import STTService, STTServiceError
from audio_service.utils.errors import WakeWordError

logger = logging.getLogger(__name__)

# Import Resemblyzer at MODULE LEVEL (DLL loads ONCE, not per-request!)
try:
    from resemblyzer import preprocess_wav
    RESEMBLYZER_AVAILABLE = True
    logger.info(" Resemblyzer imported successfully at module level")
except Exception as e:
    RESEMBLYZER_AVAILABLE = False
    logger.error(f" Resemblyzer import failed at module level: {e}")
    logger.error("Audio processing endpoints will be unavailable")
    preprocess_wav = None  # Set to None so code doesn't crash

# Create router for Week 2 endpoints
router = APIRouter(
    prefix="/api/v1",
    tags=["Audio Intelligence"]
)

# Initialize services as singletons
# These will be shared across all requests
wake_word_service = WakeWordService()
stt_service = STTService()

# Speaker service - LAZY initialization (only when needed)
_speaker_service_instance: object = None

def get_speaker_service():
    """Get or create speaker service lazily on first use"""
    global _speaker_service_instance
    if _speaker_service_instance is None:
        logger.info("Initializing SpeakerService on first use")
        _speaker_service_instance = SpeakerService()
    return _speaker_service_instance


# Wake Word Detection Endpoints

@router.post(
    "/wake-word/start",
    response_model=WakeWordStatusResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Wake word detection started successfully"},
        500: {"model": ErrorResponse, "description": "Failed to start wake word detection"}
    }
)
async def start_wake_word_detection():
    """
    Start continuous wake word detection.
    
    This begins the background listening loop that monitors audio input for the
    wake word activation phrase. When detected, it automatically records the
    subsequent command audio.
    
    Returns:
        WakeWordStatusResponse: Status confirming detection has started
        
    Raises:
        HTTPException: If wake word detection fails to start
    """
    try:
        logger.info("Received request to start wake word detection")
        
        # Define callback for when wake word is detected
        def on_wake_word_detected(audio_file: str, confidence: float):
            """
            Callback function triggered when wake word is detected.
            
            This logs the detection event and could trigger additional processing
            like automatic speaker verification and transcription.
            """
            logger.info(
                f"Wake word detected callback: audio={audio_file}, confidence={confidence}"
            )
            # Future enhancement: Automatically process the command here
        
        # Start the wake word detection service
        wake_word_service.start_listening(detection_callback=on_wake_word_detected)
        
        response = WakeWordStatusResponse(
            status="listening",
            is_listening=True,
            message="Wake word detection started successfully"
        )
        
        logger.info("Wake word detection started successfully")
        return response
        
    except WakeWordError as e:
        logger.error(f"Wake word service error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": str(e),
                "error_type": "WakeWordError"
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error starting wake word detection: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": "An unexpected error occurred",
                "error_type": "InternalServerError"
            }
        )


@router.post(
    "/wake-word/stop",
    response_model=WakeWordStatusResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Wake word detection stopped successfully"},
        500: {"model": ErrorResponse, "description": "Failed to stop wake word detection"}
    }
)
async def stop_wake_word_detection():
    """
    Stop continuous wake word detection.
    
    This gracefully stops the listening loop and releases audio resources.
    
    Returns:
        WakeWordStatusResponse: Status confirming detection has stopped
        
    Raises:
        HTTPException: If stopping fails
    """
    try:
        logger.info("Received request to stop wake word detection")
        
        wake_word_service.stop_listening()
        
        response = WakeWordStatusResponse(
            status="stopped",
            is_listening=False,
            message="Wake word detection stopped successfully"
        )
        
        logger.info("Wake word detection stopped successfully")
        return response
        
    except WakeWordError as e:
        logger.error(f"Wake word service error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": str(e),
                "error_type": "WakeWordError"
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error stopping wake word detection: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": "An unexpected error occurred",
                "error_type": "InternalServerError"
            }
        )


@router.get(
    "/wake-word/status",
    response_model=WakeWordStatusResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Wake word status retrieved successfully"}
    }
)
async def get_wake_word_status():
    """
    Get current status of wake word detection.
    
    Returns:
        WakeWordStatusResponse: Current wake word detection status
    """
    try:
        status_info = wake_word_service.get_status()
        
        response = WakeWordStatusResponse(
            status="listening" if status_info["is_listening"] else "stopped",
            is_listening=status_info["is_listening"],
            message=f"Wake word detection is {'active' if status_info['is_listening'] else 'inactive'}"
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error getting wake word status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": "Failed to get status",
                "error_type": "InternalServerError"
            }
        )


@router.post(
    "/wake-word/detect",
    response_model=WakeWordDetectResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Wake word detected and command audio recorded successfully"},
        408: {"model": ErrorResponse, "description": "Wake word detection timeout"},
        500: {"model": ErrorResponse, "description": "Wake word detection failed"}
    }
)
async def detect_wake_word_and_record():
    """
    Detect wake word and automatically record command audio.
    
    This endpoint performs a blocking listen operation (timeout: 30 seconds) that:
    1. Listens for the wake word "Hey Nexi"
    2. Automatically records the command audio (3 seconds by default)
    3. Returns the audio file path for further processing
    
    This is ideal for sequential workflows where you want to wait for the user
    to say the wake word and capture their command in one call.
    
    Returns:
        WakeWordDetectResponse: Detection result with audio file path
        
    Raises:
        HTTPException 408: If wake word not detected within 30 seconds
        HTTPException 500: If detection or recording fails
    """
    try:
        logger.info("Received request to detect wake word and record command")
        
        # Call the service method that combines detection and recording
        result = await wake_word_service.detect_and_record_once()
        
        # Wrap result in response model
        response = WakeWordDetectResponse(
            status=result.get("status", "success"),
            keyword=result.get("keyword", "Hi Nexi"),
            detection_time=result.get("detection_time", 0.0),
            frames_processed=result.get("frames_processed", 0),
            speech_frames=result.get("speech_frames", 0),
            audio_file=result.get("audio_file", ""),
            confidence=result.get("confidence", 0.85)
        )
        
        logger.info(f"Wake word detected and command recorded: {response.audio_file}")
        return response
        
    except TimeoutError as e:
        logger.error(f"Wake word detection timeout: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail={
                "status": "error",
                "message": "Wake word detection timeout - no wake word detected within 30 seconds",
                "error_type": "TimeoutError"
            }
        )
    except WakeWordError as e:
        logger.error(f"Wake word service error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": str(e),
                "error_type": "WakeWordError"
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error detecting wake word and recording: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": "An unexpected error occurred during wake word detection",
                "error_type": "InternalServerError"
            }
        )


# Speaker Verification Endpoints

@router.post(
    "/enroll-speaker",
    response_model=EnrollSpeakerResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Speaker enrolled successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request parameters"},
        500: {"model": ErrorResponse, "description": "Enrollment failed"}
    }
)
async def enroll_speaker(request: EnrollSpeakerRequest):
    """
    Enroll a new speaker for voice verification.
    
    This records a voice sample from the speaker and generates a unique voice
    embedding that can be used for future identification.
    
    Args:
        request: Enrollment request with user ID and optional duration
        
    Returns:
        EnrollSpeakerResponse: Enrollment confirmation with metadata and embedding
        
    Raises:
        HTTPException: If enrollment fails
    """
    try:
        logger.info(f"Enrolling speaker: {request.user_id}")
        
        # Perform speaker enrollment - now returns (audio_file, embedding_size, embedding_array)
        audio_file, embedding_size, embedding_array = get_speaker_service().enroll_speaker(
            user_id=request.user_id,
            duration=request.duration
        )
        
        response = EnrollSpeakerResponse(
            status="success",
            message=f"Speaker enrolled successfully: {request.user_id}",
            user_id=request.user_id,
            audio_file=audio_file,
            embedding_size=embedding_size,
            voice_embedding=embedding_array,
            timestamp=datetime.now().isoformat()
        )
        
        logger.info(f"Speaker enrolled successfully: {request.user_id} with embedding size {embedding_size}")
        return response
        
    except ValueError as e:
        logger.error(f"Invalid enrollment parameters: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "status": "error",
                "message": str(e),
                "error_type": "ValidationError"
            }
        )
    except SpeakerServiceError as e:
        logger.error(f"Speaker service error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": str(e),
                "error_type": "SpeakerServiceError"
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error during enrollment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": "An unexpected error occurred",
                "error_type": "InternalServerError"
            }
        )


@router.post(
    "/enroll-speaker-files",
    response_model=EnrollSpeakerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enroll speaker with uploaded audio files"
)
async def enroll_speaker_with_files(request: dict):
    """
    Enroll a speaker using uploaded audio files (alternative to microphone recording).
    
    Args:
        request: JSON with user_id and audio_files list
    """
    try:
        user_id = request.get("user_id")
        audio_files = request.get("audio_files", [])
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="user_id is required"
            )
        
        if not audio_files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="audio_files list is required"
            )
        
        logger.info(f"Enrolling speaker with files: {user_id}, {len(audio_files)} files")
        
        # Use speaker service to create embedding from files
        result = get_speaker_service().enroll_speaker_from_files(user_id, audio_files)
        
        return EnrollSpeakerResponse(
            status="success",
            message=f"Speaker enrolled successfully: {user_id}",
            user_id=user_id,
            audio_file=", ".join(audio_files),
            embedding_size=result.get("embedding_size", 0),
            voice_embedding=result.get("embedding_array"),
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Error enrolling speaker with files: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/speakers",
    response_model=ListSpeakersResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Speakers list retrieved successfully"}
    }
)
async def list_enrolled_speakers():
    """
    Get list of all enrolled speakers.
    
    Returns:
        ListSpeakersResponse: List of enrolled speaker user IDs
    """
    try:
        logger.info("Listing enrolled speakers")
        
        speakers = get_speaker_service().list_enrolled_speakers()
        
        response = ListSpeakersResponse(
            status="success",
            count=len(speakers),
            speakers=speakers
        )
        
        logger.info(f"Retrieved {len(speakers)} enrolled speakers")
        return response
        
    except Exception as e:
        logger.error(f"Error listing speakers: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": "Failed to list speakers",
                "error_type": "InternalServerError"
            }
        )


@router.post(
    "/speaker-sync",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Speaker sync completed successfully"},
        500: {"description": "Sync failed"}
    }
)
async def sync_speakers_from_central():
    """
    Sync speaker embeddings from Central Server to Audio Service.
    
    This pulls all user embeddings from the Central Server and updates the local
    speaker_embeddings database. This ensures speaker verification uses the latest
    enrolled data from the central system.
    
    **Embedding Format Handling:**
    - Central Server stores: List[List[float]] (multiple samples per user)
    - Audio Service needs: Single averaged embedding per user
    - This endpoint averages all samples → single embedding per user
    
    Returns:
        Dictionary with sync status, count of speakers synced, and validation results
    """
    try:
        import requests
        import numpy as np
        from config.ports import ServicePorts
        
        logger.info("="*70)
        logger.info(" SPEAKER SYNC INITIATED FROM CENTRAL SERVER")
        logger.info("="*70)
        
        # Get Central Server URL
        central_url = ServicePorts.get_base_url("central")
        
        # Fetch all users from Central Server
        try:
            from shared.security import internal_service_headers
            from config.ssl_config import client_verify
            response = requests.get(
                f"{central_url}/users/list", headers=internal_service_headers(), timeout=10,
                verify=client_verify(central_url),
            )
            if response.status_code != 200:
                logger.error(f"Failed to fetch users from Central Server: {response.status_code}")
                return {
                    "success": False,
                    "message": "Failed to fetch users from Central Server",
                    "speakers_synced": 0
                }
            
            users_response = response.json()
            users = users_response.get("users", []) if isinstance(users_response, dict) else users_response
            
            if not isinstance(users, list):
                users = []
            
            logger.info(f"Fetched {len(users)} users from Central Server")
            
        except Exception as e:
            logger.error(f"Error fetching users from Central Server: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to fetch from Central Server: {str(e)}",
                "speakers_synced": 0
            }
        
        # Extract voice embeddings from users
        synced_count = 0
        skipped_count = 0
        validation_issues = []
        speaker_service = get_speaker_service()
        
        # CRITICAL: Clear old embeddings before syncing (fresh sync)
        logger.info(f"[PRE-SYNC] Audio Service has {len(speaker_service.speaker_embeddings)} speakers. Clearing for fresh sync...")
        speaker_service.speaker_embeddings.clear()
        logger.info("[PRE-SYNC]  Cleared. Ready to sync fresh data.")
        
        for user_idx, user in enumerate(users):
            try:
                # Handle both "user_id" and "id" field names (defensive programming)
                user_id = user.get("user_id") or user.get("id")
                if not user_id:
                    logger.warning(f"User record {user_idx} missing both user_id and id fields")
                    validation_issues.append(f"User {user_idx}: missing ID field")
                    skipped_count += 1
                    continue
                
                # Get voice embeddings (List[List[float]] from Central Server)
                voice_embeddings = user.get("voice_embeddings", [])
                
                if not voice_embeddings:
                    logger.debug(f"User {user_id} has no voice embeddings")
                    skipped_count += 1
                    continue
                
                # Validate embedding format
                if not isinstance(voice_embeddings, list) or len(voice_embeddings) == 0:
                    logger.warning(f"User {user_id}: invalid embedding format (not a list or empty)")
                    validation_issues.append(f"User {user_id}: invalid embedding format")
                    skipped_count += 1
                    continue
                
                # Check if embeddings are lists (expected format)
                if not isinstance(voice_embeddings[0], (list, np.ndarray)):
                    logger.warning(f"User {user_id}: expected List[List[float]], got List[{type(voice_embeddings[0]).__name__}]")
                    validation_issues.append(f"User {user_id}: embedding is not nested list")
                    skipped_count += 1
                    continue
                
                # Convert to numpy arrays for averaging
                try:
                    embeddings_array = np.array(voice_embeddings, dtype=np.float32)
                    
                    # Average all voice embeddings into one (Resemblyzer pattern)
                    avg_embedding = np.mean(embeddings_array, axis=0)
                    
                    # Validate averaged embedding size (should be 256 for Resemblyzer)
                    if len(avg_embedding) != 256:
                        logger.warning(
                            f"User {user_id}: embedding dimension is {len(avg_embedding)}, "
                            f"expected 256 (Resemblyzer standard)"
                        )
                        validation_issues.append(
                            f"User {user_id}: embedding size {len(avg_embedding)} (expected 256)"
                        )
                    
                    # Update the speaker service embeddings
                    speaker_service.speaker_embeddings[user_id] = avg_embedding
                    
                    # VERIFY: Check it was actually stored
                    if user_id in speaker_service.speaker_embeddings:
                        synced_count += 1
                        logger.info(f" [{synced_count}] {user_id}: Stored avg embedding ({len(voice_embeddings)} samples → 256-dim)")
                    else:
                        logger.error(f" {user_id}: Failed to store embedding!")
                        validation_issues.append(f"User {user_id}: failed to store in memory")
                        skipped_count += 1
                        continue
                    
                except Exception as e:
                    logger.error(f"Failed to process embeddings for user {user_id}: {str(e)}")
                    validation_issues.append(f"User {user_id}: processing error - {str(e)}")
                    skipped_count += 1
                    continue
                
            except Exception as e:
                logger.warning(f"Error syncing user {user.get('user_id', 'unknown')}: {str(e)}")
                validation_issues.append(f"User {user.get('user_id', 'unknown')}: {str(e)}")
                skipped_count += 1
                continue
        
        # Save the updated embeddings to disk
        try:
            logger.info(f"[PERSIST] Saving {len(speaker_service.speaker_embeddings)} embeddings to disk...")
            speaker_service._save_embeddings()
            logger.info(f"[PERSIST]  Successfully persisted {len(speaker_service.speaker_embeddings)} embeddings")
        except Exception as e:
            logger.error(f"[PERSIST]  Failed to save embeddings to disk: {str(e)}")
            validation_issues.append(f"Disk save failed: {str(e)}")
            # Don't fail the sync if save fails, as embeddings are in memory
        
        # Final confirmation
        final_count = len(speaker_service.speaker_embeddings)
        logger.info("="*70)
        logger.info(f" SPEAKER SYNC COMPLETE: {final_count} embeddings ready for verification")
        logger.info("="*70)
        
        return {
            "success": True,
            "message": f"Synced {synced_count} speakers from Central Server",
            "speakers_synced": synced_count,
            "speakers_skipped": skipped_count,
            "validation_issues": validation_issues if validation_issues else None,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Unexpected error during speaker sync: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "SPEAKER_SYNC_FAILED", "message": "Speaker synchronization failed"},
        ) from e


@router.get(
    "/speakers/debug",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Debug info about current speaker state"},
        500: {"description": "Debug retrieval failed"}
    }
)
async def debug_speakers():
    """
    DEBUG ENDPOINT: Get detailed information about current speaker embeddings state.
    
    This endpoint helps troubleshoot speaker verification issues by showing:
    - How many speakers are currently in memory
    - Dimension validation (should be 256 for Resemblyzer)
    - Storage consistency check
    - Disk persistence status
    
    Returns:
        Dictionary with debug information about speaker embeddings
    """
    try:
        speaker_service = get_speaker_service()
        
        logger.info(" DEBUG: Checking speaker embeddings state...")
        
        # Get current speakers in memory
        speakers_in_memory = list(speaker_service.speaker_embeddings.keys())
        speaker_count = len(speakers_in_memory)
        
        # Validate each speaker embedding
        validation_report = {
            "total_speakers": speaker_count,
            "valid_speakers": 0,
            "invalid_speakers": [],
            "dimension_errors": []
        }
        
        for user_id in speakers_in_memory:
            embedding = speaker_service.speaker_embeddings.get(user_id)
            
            if embedding is None:
                validation_report["invalid_speakers"].append(f"{user_id}: None value")
                continue
            
            # Check type
            if not isinstance(embedding, (np.ndarray, list)):
                validation_report["invalid_speakers"].append(
                    f"{user_id}: wrong type {type(embedding).__name__}"
                )
                continue
            
            # Convert to array for dimension check
            try:
                emb_array = np.array(embedding, dtype=np.float32)
                if len(emb_array.shape) != 1:
                    validation_report["invalid_speakers"].append(
                        f"{user_id}: wrong shape {emb_array.shape}"
                    )
                    continue
                
                # Check dimension
                if emb_array.shape[0] != 256:
                    validation_report["dimension_errors"].append(
                        f"{user_id}: {emb_array.shape[0]} dims (expected 256)"
                    )
                    validation_report["invalid_speakers"].append(f"{user_id}: wrong dimension")
                    continue
                
                # Check for NaN or Inf
                if np.isnan(emb_array).any() or np.isinf(emb_array).any():
                    validation_report["invalid_speakers"].append(
                        f"{user_id}: contains NaN or Inf"
                    )
                    continue
                
                validation_report["valid_speakers"] += 1
                
            except Exception as e:
                validation_report["invalid_speakers"].append(f"{user_id}: {str(e)}")
                continue
        
        # Check disk file
        disk_status = {
            "file_exists": False,
            "file_size_bytes": 0,
            "last_modified": None
        }
        
        try:
            embeddings_path = getattr(speaker_service, '_embeddings_path', None)
            if embeddings_path and os.path.exists(embeddings_path):
                disk_status["file_exists"] = True
                stat_info = os.stat(embeddings_path)
                disk_status["file_size_bytes"] = stat_info.st_size
                disk_status["last_modified"] = datetime.fromtimestamp(
                    stat_info.st_mtime
                ).isoformat()
        except Exception as e:
            logger.warning(f"Could not check disk file: {str(e)}")
        
        logger.info(f" DEBUG: {validation_report['valid_speakers']}/{speaker_count} speakers valid")
        
        return {
            "status": "debug",
            "timestamp": datetime.now().isoformat(),
            "memory": {
                "speakers_loaded": speaker_count,
                "speaker_ids": speakers_in_memory
            },
            "validation": validation_report,
            "disk": disk_status,
            "summary": {
                "memory_ready": speaker_count > 0,
                "all_valid": len(validation_report["invalid_speakers"]) == 0,
                "can_verify": speaker_count > 0 and len(validation_report["invalid_speakers"]) == 0
            }
        }
        
    except Exception as e:
        logger.error(f"Error in debug endpoint: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Debug failed: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }


@router.post(
    "/verify-speaker",
    response_model=VerifySpeakerResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Speaker verification completed"},
        400: {"model": ErrorResponse, "description": "Invalid request parameters"},
        500: {"model": ErrorResponse, "description": "Verification failed"}
    }
)
async def verify_speaker(file: UploadFile = File(...)):
    """
    Verify speaker identity from uploaded audio file.
    
    This compares the voice in the audio file against all enrolled speakers
    to determine who is speaking.
    
    Args:
        file: Audio file (WAV, MP3) to verify speaker identity
        
    Returns:
        VerifySpeakerResponse: Verification result with user ID and confidence
        
    Raises:
        HTTPException: If verification fails
    """
    import tempfile
    import os
    
    temp_file_path = None
    
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File name is required"
            )
        
        # Save uploaded file temporarily
        temp_fd, temp_file_path = tempfile.mkstemp(suffix=".wav")
        try:
            content = await file.read()
            os.write(temp_fd, content)
            os.close(temp_fd)
        except Exception as e:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            logger.error(f"Failed to save uploaded file: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to process uploaded file"
            )
        
        logger.info(f"Verifying speaker from uploaded audio: {file.filename}")
        
        # Perform speaker verification on the temporary file
        user_id, confidence = get_speaker_service().verify_speaker(temp_file_path)
        
        # Determine if speaker was successfully verified
        threshold = get_speaker_service().get_verification_threshold()
        is_verified = confidence >= threshold and user_id != "unknown"
        token_result = None
        if is_verified:
            from shared.jwt_manager import get_jwt_manager
            token_result = get_jwt_manager().create_session_token(user_id)
        
        response = VerifySpeakerResponse(
            status="success",
            user_id=user_id,
            confidence=round(confidence, 4),
            is_verified=is_verified,
            threshold=threshold,
            timestamp=datetime.now().isoformat(),
            access_token=token_result["token"] if token_result else None,
            token_type=token_result["type"] if token_result else None,
            expires_in=token_result["expires_in"] if token_result else None,
        )
        
        logger.info(
            f"Speaker verification completed: user_id={user_id}, "
            f"confidence={confidence:.4f}, verified={is_verified}"
        )
        return response
        
    except ValueError as e:
        logger.error(f"Invalid verification parameters: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "status": "error",
                "message": str(e),
                "error_type": "ValidationError"
            }
        )
    except SpeakerServiceError as e:
        logger.error(f"Speaker service error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": str(e),
                "error_type": "SpeakerServiceError"
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error during verification: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": "An unexpected error occurred during speaker verification",
                "error_type": "InternalServerError"
            }
        )
    finally:
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception as e:
                logger.warning(f"Failed to clean up temp file: {str(e)}")


# Voice Embedding Processing Endpoint (for enrollment service)

@router.post(
    "/process-voice",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Voice embedding extracted successfully"},
        400: {"model": ErrorResponse, "description": "Invalid audio file"},
        500: {"model": ErrorResponse, "description": "Processing failed"}
    }
)
async def process_voice_file(file: UploadFile = File(...)):
    """
    Extract voice embedding from uploaded audio file.
    
    This endpoint processes a single audio file and extracts a voice embedding
    without enrolling the speaker. Used by the enrollment service to get
    embeddings during the enrollment workflow.
    
    Args:
        file: Audio file (WAV, MP3) to process
        
    Returns:
        dict: Contains voice embedding, quality score, and voice detection status
        
    Raises:
        HTTPException: If processing fails or no voice detected
    """
    import tempfile
    import os
    from audio_service.utils.audio_preprocessing import load_audio_file, validate_audio_duration
    
    temp_file_path = None
    
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File name is required"
            )
        
        # Save uploaded file temporarily
        temp_fd, temp_file_path = tempfile.mkstemp(suffix=".wav")
        try:
            content = await file.read()
            os.write(temp_fd, content)
            os.close(temp_fd)
        except Exception as e:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            logger.error(f"Failed to save uploaded file: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to process uploaded file"
            )
        
        logger.info(f"Processing voice from uploaded file: {file.filename}")
        
        # Initialize speaker service encoder
        try:
            get_speaker_service().initialize_encoder()
        except Exception as e:
            logger.error(f"Failed to initialize speaker encoder: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Voice encoder initialization failed: {str(e)}"
            )
        
        # Load and validate audio
        try:
            audio_data, sample_rate = load_audio_file(temp_file_path)
        except Exception as e:
            logger.error(f"Failed to load audio file: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to load audio file. Ensure it's a valid WAV or MP3 file."
            )
        
        # Validate audio duration
        if not validate_audio_duration(
            audio_data,
            sample_rate,
            min_duration=0.5  # At least 0.5 seconds of audio
        ):
            logger.warning(f"Audio file too short: {file.filename}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Audio is too short. Please provide at least 0.5 seconds of speech."
            )
        
        # Preprocess audio for Resemblyzer
        if not RESEMBLYZER_AVAILABLE:
            logger.error("Resemblyzer not available")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Voice processing unavailable - Resemblyzer failed to load at startup"
            )
        
        try:
            # Resemblyzer expects audio at 16kHz
            preprocessed_audio = preprocess_wav(audio_data, source_sr=sample_rate)
        except Exception as e:
            logger.error(f"Failed to preprocess audio: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to preprocess audio. Ensure it contains clear speech."
            )
        
        # Check if preprocessed audio is valid (not empty)
        if preprocessed_audio is None or len(preprocessed_audio) == 0:
            logger.warning(f"Preprocessed audio is empty: {file.filename}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No clear voice detected in the audio. Please provide clearer speech."
            )
        
        # Generate embedding
        try:
            embedding = get_speaker_service().encoder.embed_utterance(preprocessed_audio)
        except Exception as e:
            logger.error(f"Failed to generate embedding: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to extract voice embedding"
            )
        
        # Validate embedding
        if embedding is None or len(embedding) == 0:
            logger.error(f"Generated embedding is invalid: {file.filename}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate valid voice embedding"
            )
        
        # Convert numpy array to list for JSON serialization
        embedding_list = embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)
        
        # Estimate quality score based on preprocessed audio characteristics
        # This is a heuristic: scale by audio intensity/RMS
        import numpy as np
        audio_rms = np.sqrt(np.mean(preprocessed_audio ** 2))
        # Normalize to 0-1 range (RMS typically 0.0-0.3 for speech)
        quality_score = min(1.0, max(0.0, audio_rms / 0.2))
        
        # Return response in APIResponse format: {"success": true, "data": {...}, "error": null}
        # This is compatible with AudioClient parsing which expects result.get("success")
        response_data = {
            "embedding": embedding_list,
            "embedding_size": len(embedding_list),
            "quality_score": round(float(quality_score), 3),
            "voice_detected": True,
            "audio_file": file.filename,
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(
            f"Voice embedding extracted successfully: "
            f"size={len(embedding_list)}, quality={quality_score:.3f}, file={file.filename}"
        )
        
        # Return as plain dict (not Pydantic object) for maximum compatibility
        # FastAPI will serialize this to JSON automatically
        response = {
            "success": True,
            "data": response_data,
            "error": None
        }
        
        logger.info(f"[/process-voice] Returning response: success={response['success']}, data keys={list(response['data'].keys())}")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing voice: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error processing voice: {str(e)}"
        )
    finally:
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception as e:
                logger.warning(f"Failed to clean up temp file: {str(e)}")


# Speech-to-Text Endpoints

@router.post(
    "/transcribe",
    response_model=TranscribeResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Audio transcribed successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request parameters"},
        500: {"model": ErrorResponse, "description": "Transcription failed"}
    }
)
async def transcribe_audio(file: UploadFile = File(...), language: str = "auto"):
    """
    Transcribe audio file to text.
    
    This converts spoken audio into written text using Groq's Whisper API,
    with support for automatic language detection.
    
    Args:
        file: Audio file (WAV, MP3) to transcribe
        language: Language code or 'auto' for automatic detection (default: auto)
        
    Returns:
        TranscribeResponse: Transcription result with text and metadata
        
    Raises:
        HTTPException: If transcription fails
    """
    import tempfile
    import os
    
    temp_file_path = None
    
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File name is required"
            )
        
        # Save uploaded file temporarily
        temp_fd, temp_file_path = tempfile.mkstemp(suffix=".wav")
        try:
            content = await file.read()
            os.write(temp_fd, content)
            os.close(temp_fd)
        except Exception as e:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            logger.error(f"Failed to save uploaded file: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to process uploaded file"
            )
        
        logger.info(
            f"Transcribing uploaded audio: {file.filename} (language: {language})"
        )
        
        # Validate audio file before processing
        if not stt_service.validate_audio_file(temp_file_path):
            raise ValueError("Invalid or unsuitable audio file for transcription")
        
        # Perform transcription on the temporary file
        result = stt_service.transcribe_with_metadata(
            audio_file_path=temp_file_path,
            language=language
        )
        
        response = TranscribeResponse(
            status="success",
            text=result["text"],
            language=result["language"],
            duration=result["duration"],
            success=result["success"],
            confidence=result.get("confidence"),
            timestamp=result["timestamp"]
        )
        
        logger.info(
            f"Transcription completed: text_length={len(result['text'])}, "
            f"language={result['language']}, success={result['success']}"
        )
        return response
        
    except ValueError as e:
        logger.error(f"Invalid transcription parameters: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "status": "error",
                "message": str(e),
                "error_type": "ValidationError"
            }
        )
    except STTServiceError as e:
        logger.error(f"STT service error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": str(e),
                "error_type": "STTServiceError"
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error during transcription: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": "An unexpected error occurred during transcription",
                "error_type": "InternalServerError"
            }
        )
    finally:
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception as e:
                logger.warning(f"Failed to clean up temp file: {str(e)}")


# Complete Processing Pipeline Endpoint

@router.post(
    "/process-command",
    response_model=ProcessCommandResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Command processed successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request parameters"},
        500: {"model": ErrorResponse, "description": "Processing failed"}
    }
)
async def process_command(request: ProcessCommandRequest):
    """
    Complete command processing pipeline.
    
    This is the main endpoint that integrates speaker verification and
    speech-to-text transcription into a single workflow. It processes
    command audio from wake word detection and returns comprehensive results.
    
    Args:
        request: Process command request with audio file and options
        
    Returns:
        ProcessCommandResponse: Complete processing results
        
    Raises:
        HTTPException: If processing fails
    """
    try:
        logger.info(f"Processing command from audio: {request.audio_file}")
        
        # Initialize result variables
        user_id = "unknown"
        speaker_confidence = 0.0
        is_verified = False
        
        # Step 1: Speaker verification (if enabled)
        if request.verify_speaker:
            try:
                user_id, speaker_confidence = get_speaker_service().verify_speaker(
                    request.audio_file
                )
                threshold = get_speaker_service().get_verification_threshold()
                is_verified = speaker_confidence >= threshold and user_id != "unknown"
                
                logger.info(
                    f"Speaker verification: user_id={user_id}, "
                    f"confidence={speaker_confidence:.4f}"
                )
            except Exception as verify_error:
                # Log error but continue with transcription
                logger.warning(f"Speaker verification failed: {str(verify_error)}")
        
        # Step 2: Speech-to-text transcription
        transcription_result = stt_service.transcribe_with_metadata(
            audio_file_path=request.audio_file,
            language=request.language
        )
        
        # Get audio duration
        from audio_service.utils.audio_preprocessing import load_audio_file
        audio_data, sample_rate = load_audio_file(request.audio_file)
        duration = len(audio_data) / sample_rate
        
        # Build comprehensive response
        response = ProcessCommandResponse(
            status="success",
            text=transcription_result["text"],
            language=transcription_result["language"],
            user_id=user_id,
            speaker_confidence=round(speaker_confidence, 4),
            is_verified=is_verified,
            audio_file=request.audio_file,
            duration=round(duration, 2),
            timestamp=datetime.now().isoformat(),
            success=transcription_result["success"]
        )
        
        logger.info(
            f"Command processing completed: text='{response.text}', "
            f"language={response.language}, user={response.user_id}"
        )
        
        return response
        
    except ValueError as e:
        logger.error(f"Invalid processing parameters: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "status": "error",
                "message": str(e),
                "error_type": "ValidationError"
            }
        )
    except (SpeakerServiceError, STTServiceError) as e:
        logger.error(f"Service error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": str(e),
                "error_type": type(e).__name__
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error processing command: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": "An unexpected error occurred",
                "error_type": "InternalServerError"
            }
        )


# ============================================================================
# Week 3 Enhancement Endpoints
# ============================================================================

@router.post(
    "/wake-word/power-mode",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Set wake word detection power mode"
)
async def set_power_mode(request: dict):
    """Set the power mode for wake word detection (Week 3 feature)"""
    try:
        mode = request.get("mode", "balanced")
        wake_word_service.set_power_mode(mode)
        
        return {
            "status": "success",
            "mode": wake_word_service.current_power_mode,
            "vad_enabled": wake_word_service.vad_enabled,
            "sleep_duration_ms": wake_word_service.sleep_duration_ms
        }
    except Exception as e:
        logger.error(f"Error setting power mode: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/wake-word/power-mode",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Get current power mode"
)
async def get_power_mode():
    """Get the current power mode settings"""
    try:
        return {
            "status": "success",
            "mode": wake_word_service.current_power_mode,
            "vad_enabled": wake_word_service.vad_enabled,
            "sleep_duration_ms": wake_word_service.sleep_duration_ms
        }
    except Exception as e:
        logger.error(f"Error getting power mode: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/wake-word/stats",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Get wake word detection statistics"
)
async def get_wake_word_stats():
    """Get statistics from wake word detection (Week 3 feature)"""
    try:
        stats = wake_word_service.get_statistics()
        return {
            "status": "success",
            **stats
        }
    except Exception as e:
        logger.error(f"Error getting statistics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/wake-word/detect/simple",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Detect wake word (simple blocking call)"
)
async def detect_wake_word_simple():
    """Simple blocking call that waits for wake word detection."""
    try:
        result = await wake_word_service.detect_wake_word_once()
        return {
            "status": "success",
            "keyword": result.get("keyword", "Hi Nexi"),
            "detection_time": result.get("detection_time", 0),
            "frames_processed": result.get("frames_processed", 0),
            "speech_frames": result.get("speech_frames", 0)
        }
    except Exception as e:
        logger.error(f"Error detecting wake word: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/stt/circuit-breaker-status",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Get circuit breaker status"
)
async def get_circuit_breaker_status():
    """Get the current circuit breaker status (Week 3 feature)"""
    try:
        cb_status = stt_service.get_circuit_breaker_status()
        return {
            "status": "success",
            **cb_status
        }
    except Exception as e:
        logger.error(f"Error getting circuit breaker status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post(
    "/process-pipeline",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Complete voice processing pipeline"
)
async def process_pipeline(send_to_backend: bool = True):
    """
    Complete end-to-end voice processing pipeline.
    
    This endpoint orchestrates the complete workflow:
    1. Detect wake word
    2. Record command with silence detection
    3. Transcribe audio (via Groq API)
    4. Verify speaker (optional)
    5. Send results to backend (if online)
    6. Queue for later (if offline)
    
    Args:
        send_to_backend: Send results to central backend server
    
    Returns:
        dict: Pipeline execution results
    """
    try:
        from audio_service.services.queue_service import QueueService
        from audio_service.services.backend_service import BackendService
        from audio_service.config import QUEUE_CONFIG, BACKEND_CONFIG
        
        logger.info(
            f"Starting pipeline: send_to_backend={send_to_backend}"
        )
        
        pipeline_start = datetime.now()
        results = {
            "pipeline_id": f"pipeline_{pipeline_start.strftime('%Y%m%d_%H%M%S')}",
            "steps": {},
            "status": "in_progress"
        }
        
        # Step 1: Detect wake word
        logger.info("Pipeline Step 1: Detecting wake word...")
        try:
            wake_result = await wake_word_service.detect_wake_word_once()
            results["steps"]["wake_word"] = {
                "status": "success",
                "keyword": wake_result.get("keyword", "Hi Nexi"),
                "detection_time": wake_result.get("detection_time", 0)
            }
            logger.info(f"Wake word detected: {wake_result.get('keyword')}")
        except Exception as e:
            logger.error(f"Wake word detection failed: {e}")
            results["steps"]["wake_word"] = {
                "status": "failed",
                "error": str(e)
            }
            results["status"] = "failed"
            return results
        
        # Step 2: Record command with silence detection
        logger.info("Pipeline Step 2: Recording command...")
        try:
            audio_file = wake_word_service.record_command_with_silence_detection(
                max_duration=10.0,
                silence_threshold=0.5,
                min_duration=0.5
            )
            results["steps"]["recording"] = {
                "status": "success",
                "audio_file": audio_file
            }
            logger.info(f"Command recorded: {audio_file}")
        except Exception as e:
            logger.error(f"Recording failed: {e}")
            results["steps"]["recording"] = {
                "status": "failed",
                "error": str(e)
            }
            results["status"] = "failed"
            return results
        
        # Step 3: Transcribe audio
        logger.info("Pipeline Step 3: Transcribing...")
        try:
            # Always use Groq API path
            text, language, duration = stt_service.transcribe_audio(
                audio_file_path=audio_file,
                language="auto"
            )
            
            results["steps"]["transcription"] = {
                "status": "success",
                "text": text,
                "language": language,
                "duration": duration
            }
            logger.info(f"Transcription complete: text='{text}', language={language}")
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            results["steps"]["transcription"] = {
                "status": "failed",
                "error": str(e)
            }
            results["status"] = "failed"
            return results
        
        # Step 4: Send to backend or queue
        if send_to_backend:
            logger.info("Pipeline Step 4: Sending to backend...")
            try:
                backend_service = BackendService(
                    base_url=BACKEND_CONFIG["base_url"],
                    api_key=BACKEND_CONFIG.get("api_key"),
                    timeout=BACKEND_CONFIG.get("timeout", 30.0),
                    verify_ssl=BACKEND_CONFIG.get("verify_ssl", True)
                )
                
                # Check if backend is available
                if backend_service.check_health():
                    # Send directly
                    backend_response = backend_service.send_pipeline_result(
                        transcription=text,
                        speaker_id=None,
                        is_speaker_verified=False,
                        metadata={
                            "language": language,
                            "duration": duration,
                            "offline_mode": False,
                            "audio_file": audio_file
                        }
                    )
                    
                    results["steps"]["backend"] = {
                        "status": "success",
                        "method": "direct",
                        "response": backend_response
                    }
                    logger.info("Results sent to backend successfully")
                else:
                    # Queue for later
                    queue_service = QueueService(
                        db_path=QUEUE_CONFIG["db_path"],
                        max_retry_count=QUEUE_CONFIG["max_retry_count"]
                    )
                    
                    command_id = queue_service.enqueue_command(
                        command_type="pipeline_result",
                        command_data={
                            "transcription": text,
                            "speaker_id": None,
                            "is_speaker_verified": False,
                            "metadata": {
                                "language": language,
                                "duration": duration,
                                "offline_mode": False,
                                "audio_file": audio_file
                            }
                        },
                        audio_file_path=audio_file,
                        priority=5
                    )
                    
                    results["steps"]["backend"] = {
                        "status": "queued",
                        "method": "queue",
                        "queue_id": command_id
                    }
                    logger.info(f"Results queued (backend offline): queue_id={command_id}")
                
            except Exception as e:
                logger.error(f"Backend communication failed: {e}")
                results["steps"]["backend"] = {
                    "status": "failed",
                    "error": str(e)
                }
        else:
            results["steps"]["backend"] = {
                "status": "skipped",
                "reason": "send_to_backend=False"
            }
        
        # Pipeline complete
        pipeline_end = datetime.now()
        pipeline_duration = (pipeline_end - pipeline_start).total_seconds()
        
        results["status"] = "completed"
        results["pipeline_duration"] = pipeline_duration
        results["completed_at"] = pipeline_end.isoformat()
        
        logger.info(f"Pipeline completed in {pipeline_duration:.2f}s")
        
        return results
        
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline execution failed: {str(e)}"
        )
