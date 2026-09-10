"""
User Management Routes
======================

Routes for user registration, management, and data handling.
All user-related endpoints are centralized here for maintainability.
"""

from fastapi import APIRouter, HTTPException, Request, Form, File, UploadFile, Query
from typing import Dict, Any, Optional
from datetime import datetime
import uuid
import logging
import threading
import shutil
from pathlib import Path
import os

# Configure logger
logger = logging.getLogger(__name__)

# ==============================================================================
# RACE CONDITION PROTECTION
# ==============================================================================

# Per-user mutex for enrollment atomicity
_enrollment_locks: Dict[str, threading.RLock] = {}
_locks_mutex = threading.Lock()

def _get_enrollment_lock(username: str) -> threading.RLock:
    """Get or create mutex for user enrollment"""
    with _locks_mutex:
        if username not in _enrollment_locks:
            _enrollment_locks[username] = threading.RLock()
        return _enrollment_locks[username]

# Create router
router = APIRouter(prefix="/users", tags=["User Management"])


def _get_app_state(request: Request):
    """Get application state from request context"""
    return request.app.state


def _find_user_record(app_state, username: str) -> Optional[Dict]:
    """Find user by username"""
    if not app_state or "users" not in app_state.db:
        return None
    
    for user in app_state.db.get("users", []):
        if user.get("name") == username:
            return user
    return None


async def _persist_users(app_state, request: Request, immediate: bool = False):
    """Persist users to storage"""
    try:
        from sqlite_store import write_records
        users = app_state.db.get("users", [])
        write_records("users", users, request.state.user_connection)
        logger.info(f"[PERSIST]  Persisted {len(users)} users to disk")
    except Exception as e:
        logger.error(f"[PERSIST]  Failed to persist users: {str(e)}")
        request.state.persistence_failed = True
        raise


# ============================================================================
# USER MANAGEMENT ENDPOINTS
# ============================================================================

@router.post("/data/add_user")
async def add_user(user_data: Dict[str, Any], request: Request):
    """Register new user"""
    try:
        app_state = _get_app_state(request)
        if not app_state:
            raise Exception("Application state not initialized")
        
        name = user_data.get("name")
        if not name:
            raise HTTPException(status_code=400, detail="User name required")
        
        # Check if user exists
        existing = _find_user_record(app_state, name)
        if existing:
            raise HTTPException(status_code=409, detail="User already exists")
        
        # Add user
        if "users" not in app_state.db:
            app_state.db["users"] = []
        
        app_state.db["users"].append(user_data)
        await _persist_users(app_state, request)
        
        logger.info(f"Enrolled user: {name}")
        return {"status": "success", "message": f"User {name} enrolled"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Add user error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_users(request: Request):
    """List all registered users with their embeddings"""
    try:
        app_state = _get_app_state(request)
        if not app_state:
            raise Exception("Application state not initialized")
        
        logger.info(f"[LIST-USERS] DEBUG: Total users in app_state.db={len(app_state.db.get('users', []))}")
        
        users_list = []
        for idx, user in enumerate(app_state.db.get("users", [])):
            voice_embs = user.get("voice_embeddings", [])
            face_embs = user.get("face_embeddings", [])
            logger.info(f"[LIST-USERS] DEBUG: User {idx} ({user.get('user_id')}): voice_embeddings={len(voice_embs)}, face_embeddings={len(face_embs)}")
            
            users_list.append({
                "user_id": user.get("user_id"),
                "user_name": user.get("name"),
                "enrollment_date": user.get("enrollment_timestamp", "Unknown"),
                "sample_count": {
                    "images": len(face_embs),
                    "audio": len(voice_embs),
                },
                # Include embeddings for service sync
                "voice_embeddings": voice_embs,
                "face_embeddings": face_embs
            })
        
        logger.info(f"[LIST-USERS] DEBUG: Returning {len(users_list)} users")
        return {"users": users_list}
    except Exception as e:
        logger.error(f"List users error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/check")
async def check_user_exists(name: str, request: Request):
    """Check if user exists"""
    try:
        app_state = _get_app_state(request)
        user = _find_user_record(app_state, name)
        if user:
            return {
                "exists": True,
                "user_id": user.get("user_id"),
                "enrollment_date": user.get("enrollment_timestamp"),
                "sample_count": {
                    "images": len(user.get("face_embeddings", [])),
                    "audio": len(user.get("voice_embeddings", [])),
                }
            }
        return {"exists": False}
    except Exception as e:
        logger.error(f"Check user error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/{user_name}")
async def search_user_by_name(user_name: str, request: Request):
    """Get user data by name"""
    try:
        app_state = _get_app_state(request)
        user = _find_user_record(app_state, user_name)
        if user:
            return user
        raise HTTPException(status_code=404, detail=f"User '{user_name}' not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search user error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}")
async def get_user_by_id(user_id: str, request: Request):
    """Get user profile by user_id."""
    try:
        app_state = _get_app_state(request)
        if not app_state:
            raise Exception("Application state not initialized")

        for user in app_state.db.get("users", []):
            if user.get("user_id") == user_id:
                return user

        raise HTTPException(status_code=404, detail=f"User with ID '{user_id}' not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user by ID error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}/conversation-history")
async def get_user_conversation_history(
    user_id: str,
    limit: int = Query(5, ge=1, le=100),
    request: Request = None,
):
    """Get latest conversation turns for a user."""
    try:
        app_state = _get_app_state(request)
        if not app_state:
            raise Exception("Application state not initialized")

        user = None
        for u in app_state.db.get("users", []):
            if u.get("user_id") == user_id:
                user = u
                break

        if not user:
            raise HTTPException(status_code=404, detail=f"User with ID '{user_id}' not found")

        history = user.get("conversation_history", [])
        if not isinstance(history, list):
            history = []

        return {
            "user_id": user_id,
            "history": history[-limit:],
            "count": len(history),
            "limit": limit,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get conversation history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{user_id}")
async def delete_user(user_id: str, request: Request):
    """Delete user and all associated data"""
    try:
        app_state = _get_app_state(request)
        if not app_state:
            raise Exception("Application state not initialized")
        
        # Find user by user_id
        user_index = -1
        for i, user in enumerate(app_state.db.get("users", [])):
            if user.get("user_id") == user_id:
                user_index = i
                break
        
        if user_index == -1:
            raise HTTPException(status_code=404, detail=f"User with ID '{user_id}' not found")
        
        deleted_user = app_state.db["users"].pop(user_index)
        deleted_name = deleted_user.get("name", "Unknown")
        
        # Persist deletion immediately
        await _persist_users(app_state, request, immediate=True)
        
        logger.info(f"User deleted: {deleted_name} (ID: {user_id})")
        
        return {
            "status": "deleted",
            "message": f"User '{deleted_name}' and all associated data deleted successfully",
            "user_id": user_id,
            "user_name": deleted_name
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete user error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete user: {str(e)}")


@router.post("/register")
async def register_user(
    name: str = Form(None),
    audio_file: Optional[UploadFile] = File(None),
    photo_file: Optional[UploadFile] = File(None),
    user_name: str = Form(None),
    user_email: str = Form(None),
    request: Request = None
):
    """Register user with audio and/or photo files.
    
    Accepts both Form and JSON input for maximum flexibility.
    """
    try:
        # Accept either 'name' or 'user_name'
        username = (name or user_name or "").strip()
        email = user_email or ""
        
        if not username:
            return {
                "status": "error",
                "error_code": "MISSING_NAME",
                "message": "User name is required"
            }
        
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        
        user_record = {
            "user_id": user_id,
            "name": username,
            "email": email,
            "has_voice": audio_file is not None,
            "has_face": photo_file is not None,
            "enrollment_timestamp": datetime.utcnow().isoformat()
        }
        
        return {
            "status": "success",
            "data": {
                "user_id": user_id,
                "name": username,
                "email": email,
                "has_voice": audio_file is not None,
                "has_face": photo_file is not None,
                "enrolled_at": user_record["enrollment_timestamp"]
            },
            "message": f"User '{username}' enrolled successfully"
        }
        
    except Exception as e:
        logger.error(f"User registration error: {str(e)}")
        return {
            "status": "error",
            "error_code": "REGISTRATION_FAILED",
            "message": f"Registration failed: {str(e)}"
        }


@router.post("/register-with-voice")
async def register_user_with_voice(
    name: str = Form(...),
    email: str = Form(...),
    audio_sample1: UploadFile = File(...),
    audio_sample2: UploadFile = File(...),
    audio_sample3: UploadFile = File(...),
    request: Request = None
):
    """Register user with 3 voice samples for speaker enrollment via Audio Service.
    
    Audio Service will compute speaker embeddings and enrollment confidence.
    
    Args:
        name: User's name for registration
        email: User's email address
        audio_sample1: First voice sample (WAV/MP3)
        audio_sample2: Second voice sample (WAV/MP3)
        audio_sample3: Third voice sample (WAV/MP3)
        request: FastAPI request context
    
    Returns:
        User ID, enrollment status, and confidence score from Audio Service
    """
    try:
        if not name or not name.strip():
            return {
                "status": "error",
                "error_code": "MISSING_NAME",
                "message": "User name is required"
            }
        
        if not email or not email.strip():
            return {
                "status": "error",
                "error_code": "MISSING_EMAIL",
                "message": "User email is required"
            }
        
        # Get audio_client from app state
        audio_client = request.app.state.audio_client
        if not audio_client:
            logger.error("Audio Service client not initialized")
            return {
                "status": "error",
                "error_code": "AUDIO_SERVICE_NOT_AVAILABLE",
                "message": "Audio Service is not available"
            }
        
        name = name.strip()
        email = email.strip()
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        
        # Create temp directory for audio files
        temp_audio_dir = Path(__file__).parent.parent / "temp_uploads" / "audio_enrollment"
        temp_audio_dir.mkdir(parents=True, exist_ok=True)
        
        audio_file_paths = []
        audio_bytes_list = []  # Store audio bytes for correct API call
        try:
            # Save all three audio samples to temporary location AND collect bytes
            for idx, audio_sample in enumerate([audio_sample1, audio_sample2, audio_sample3], 1):
                # Create unique filename
                file_ext = Path(audio_sample.filename).suffix or ".wav"
                temp_file_path = temp_audio_dir / f"{user_id}_sample{idx}_{uuid.uuid4().hex[:8]}{file_ext}"
                
                # Write audio file AND collect bytes for enrollment
                content = await audio_sample.read()
                with open(temp_file_path, "wb") as f:
                    f.write(content)
                
                audio_file_paths.append(str(temp_file_path))
                audio_bytes_list.append(content)  # Store bytes for API call
                logger.info(f"Saved audio sample {idx} for user {user_id} to {temp_file_path}")
            
            # Call Audio Service to enroll speaker with AUDIO BYTES (not file paths)
            # audio_client.enroll_speaker expects: speaker_id, audio_samples (list of bytes)
            logger.info(f"[register_user_with_voice] Calling audio_client.enroll_speaker({user_id}, {len(audio_bytes_list)} samples)")
            try:
                enrollment_result = await audio_client.enroll_speaker(
                    speaker_id=user_id,
                    audio_samples=audio_bytes_list  # Correct: list of audio bytes
                )
                logger.info(f"[register_user_with_voice]  enroll_speaker returned: type={type(enrollment_result).__name__}")
            except Exception as enroll_err:
                logger.error(f"[register_user_with_voice]  enroll_speaker EXCEPTION: {str(enroll_err)}")
                logger.error(f"[register_user_with_voice] Exception type: {type(enroll_err).__name__}")
                import traceback
                logger.error(f"[register_user_with_voice] Traceback:\n{traceback.format_exc()}")
                return {
                    "status": "error",
                    "error_code": "AUDIO_SERVICE_EXCEPTION",
                    "message": f"Audio service exception: {str(enroll_err)}"
                }
            
            # Check enrollment result (ServiceCallResult object - has .success, .data, .error_code, .error_message attributes)
            logger.info(f"[register_user_with_voice] Checking enrollment_result.success...")
            if not enrollment_result or not enrollment_result.success:
                error_msg = enrollment_result.error_message if enrollment_result else "Unknown error"
                error_code = enrollment_result.error_code if enrollment_result else "UNKNOWN_ERROR"
                logger.error(f"[register_user_with_voice]  enrollment_result.success={enrollment_result.success if enrollment_result else 'NONE'}")
                logger.error(f"[register_user_with_voice] error_code: {error_code}")
                logger.error(f"[register_user_with_voice] error_message: {error_msg}")
                return {
                    "status": "error",
                    "error_code": error_code,
                    "message": f"Speaker enrollment failed: {error_msg}",
                    "details": {
                        "success": False,
                        "error_code": error_code,
                        "error_message": error_msg
                    }
                }
            
            # Extract enrollment data from the result (ServiceCallResult.data is the actual dict)
            logger.info(f"[register_user_with_voice]  enrollment_result.success=True")
            logger.info(f"[register_user_with_voice] enrollment_result.data type: {type(enrollment_result.data).__name__}")
            enrollment_data = enrollment_result.data if enrollment_result else {}
            
            # Create user record in database
            app_state = _get_app_state(request)
            if not app_state:
                raise Exception("Application state not initialized")
            
            if "users" not in app_state.db:
                app_state.db["users"] = []
            
            user_record = {
                "user_id": user_id,
                "name": name,
                "email": email,
                "has_voice": True,
                "has_face": False,
                "enrollment_timestamp": datetime.utcnow().isoformat(),
                "audio_samples": audio_file_paths,
                "voice_embedding": enrollment_data.get("voice_embedding", enrollment_data.get("embedding_array")),
                "speaker_enrollment": {
                    "status": "success",
                    "speaker_id": enrollment_data.get("speaker_id", user_id),
                    "num_samples": enrollment_data.get("num_samples", 3),
                    "embedding_size": enrollment_data.get("embedding_size", 0),
                    "enrolled_at": datetime.utcnow().isoformat()
                }
            }
            
            app_state.db["users"].append(user_record)
            
            # Persist user data
            await _persist_users(app_state, request)
            
            logger.info(f"User {user_id} ({name}) enrolled successfully with {enrollment_data.get('num_samples', 3)} voice samples")
            
            return {
                "status": "success",
                "data": {
                    "user_id": user_id,
                    "name": name,
                    "email": email,
                    "has_voice": True,
                    "enrollment_num_samples": enrollment_data.get("num_samples", 3),
                    "embedding_size": enrollment_data.get("embedding_size", 0),
                    "speaker_id": enrollment_data.get("speaker_id", user_id),
                    "enrolled_at": user_record["enrollment_timestamp"]
                },
                "message": f"User '{name}' enrolled successfully with {enrollment_data.get('num_samples', 3)} voice samples"
            }
        
        finally:
            # Clean up temporary audio files after enrollment
            for audio_path in audio_file_paths:
                try:
                    if os.path.exists(audio_path):
                        os.remove(audio_path)
                        logger.info(f"Cleaned up temporary audio file: {audio_path}")
                except Exception as e:
                    logger.warning(f"Could not clean up {audio_path}: {str(e)}")
        
    except Exception as e:
        logger.error(f"User voice registration error: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "error_code": "REGISTRATION_FAILED",
            "message": f"Voice registration failed: {str(e)}"
        }


@router.post("/register-old")
async def register_user_old(user_data: Dict[str, Any], request: Request):
    """DEPRECATED: Old registration endpoint. Use POST /users/register instead."""
    return {
        "status": "deprecated",
        "message": "This endpoint is deprecated. Use POST /users/register instead with audio_file and photo_file parameters."
    }


@router.put("/{user_id}/embeddings")
async def update_user_embeddings(user_id: str, payload: Dict[str, Any], request: Request):
    """Replace user embeddings entirely (used for re-enrollment)."""
    try:
        app_state = _get_app_state(request)
        if not app_state:
            raise Exception("Application state not initialized")
        
        users = app_state.db.get("users", [])
        user = None
        user_index = -1
        
        for idx, u in enumerate(users):
            if u.get("user_id") == user_id or u.get("name") == user_id:
                user = u
                user_index = idx
                break
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")
        
        if not payload:
            raise HTTPException(status_code=400, detail="Payload cannot be empty")

        new_voice_embeddings = payload.get("voice_embeddings")
        new_face_embeddings = payload.get("face_embeddings")

        # Backward compatibility: if no embedding fields are provided, keep legacy metadata-only update.
        if new_voice_embeddings is None and new_face_embeddings is None:
            user["last_updated"] = datetime.utcnow().isoformat()
            app_state.db["users"][user_index] = user
            await _persist_users(app_state, request)

            logger.info(f"User {user_id} metadata updated (no embeddings in payload)")
            return {
                "status": "updated",
                "message": f"Embeddings updated for user {user_id}",
                "replace_mode": False,
            }

        if not isinstance(new_voice_embeddings, list) or not isinstance(new_face_embeddings, list):
            raise HTTPException(status_code=400, detail="voice_embeddings and face_embeddings must be lists")

        user["voice_embeddings"] = new_voice_embeddings
        user["face_embeddings"] = new_face_embeddings
        user["face_confidences"] = payload.get("face_confidences", [0.0] * len(new_face_embeddings))
        user["voice_qualities"] = payload.get("voice_qualities", [0.0] * len(new_voice_embeddings))
        user["total_voice_embeddings"] = len(new_voice_embeddings)
        user["total_face_embeddings"] = len(new_face_embeddings)
        user["last_updated"] = datetime.utcnow().isoformat()

        app_state.db["users"][user_index] = user
        await _persist_users(app_state, request)
        
        logger.info(
            f"User {user_id} embeddings replaced: "
            f"voice={len(new_voice_embeddings)}, face={len(new_face_embeddings)}"
        )
        
        return {
            "status": "updated",
            "message": f"Embeddings updated for user {user_id}",
            "replace_mode": True,
            "new_counts": {
                "voice_embeddings": len(new_voice_embeddings),
                "face_embeddings": len(new_face_embeddings),
            },
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update user embeddings error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_id}/append-embeddings")
async def append_user_embeddings(user_id: str, request: Request):
    """Append new embeddings to existing user (used for improve training).
    
    Accumulates: Old embeddings + New embeddings = All embeddings saved
    Preserves all historical embeddings for improved model training.
    """
    try:
        # Get JSON payload
        body = await request.json()
        
        app_state = _get_app_state(request)
        if not app_state:
            raise Exception("Application state not initialized")
        
        users = app_state.db.get("users", [])
        user = None
        user_index = -1
        
        for idx, u in enumerate(users):
            if u.get("user_id") == user_id or u.get("name") == user_id:
                user = u
                user_index = idx
                break
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")
        
        if not body:
            raise HTTPException(status_code=400, detail="Payload cannot be empty")
        
        # Extract new embeddings from request
        new_voice_embeddings = body.get("voice_embeddings", [])
        new_face_embeddings = body.get("face_embeddings", [])
        new_face_confidences = body.get("face_confidences", [])
        new_voice_qualities = body.get("voice_qualities", [])
        
        if not new_voice_embeddings or not new_face_embeddings:
            raise HTTPException(status_code=400, detail="voice_embeddings and face_embeddings required")
        
        # IMPORTANT: Append to existing embeddings (do NOT replace)
        # This ensures all historical data is preserved for improved training
        existing_voice_embeddings = user.get("voice_embeddings", [])
        existing_face_embeddings = user.get("face_embeddings", [])
        existing_face_confidences = user.get("face_confidences", [])
        existing_voice_qualities = user.get("voice_qualities", [])
        
        # Accumulate embeddings
        user["voice_embeddings"] = existing_voice_embeddings + new_voice_embeddings
        user["face_embeddings"] = existing_face_embeddings + new_face_embeddings
        user["face_confidences"] = existing_face_confidences + new_face_confidences
        user["voice_qualities"] = existing_voice_qualities + new_voice_qualities
        
        # Update metadata
        user["last_updated"] = datetime.utcnow().isoformat()
        user["total_voice_embeddings"] = len(user["voice_embeddings"])
        user["total_face_embeddings"] = len(user["face_embeddings"])
        
        app_state.db["users"][user_index] = user
        await _persist_users(app_state, request)
        
        logger.info(f"User {user_id} embeddings appended: +{len(new_voice_embeddings)} voice, +{len(new_face_embeddings)} face = {len(user['voice_embeddings'])} total voice, {len(user['face_embeddings'])} total face")
        
        return {
            "status": "appended",
            "message": f"Embeddings appended for user {user_id}",
            "new_counts": {
                "voice_embeddings": len(user["voice_embeddings"]),
                "face_embeddings": len(user["face_embeddings"])
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Append user embeddings error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add-embeddings")
async def add_user_embeddings(request: Request):
    """
    Add embeddings for a user (used when embeddings already extracted).
    
    Accepts JSON body with voice and face embeddings.
    """
    try:
        import json
        
        # Get the request body as JSON
        body = await request.json()
        
        user_name = body.get("user_name")
        age = body.get("age")
        relation = body.get("relation")
        voice_embeddings = body.get("voice_embeddings", [])
        face_embeddings = body.get("face_embeddings", [])
        
        logger.info(f"[ADD-EMBEDDINGS] REQUEST RECEIVED:")
        logger.info(f"  user_name: {user_name}")
        logger.info(f"  voice_embeddings in body: {len(voice_embeddings)} items (type: {type(voice_embeddings).__name__})")
        logger.info(f"  face_embeddings in body: {len(face_embeddings)} items (type: {type(face_embeddings).__name__})")
        
        if voice_embeddings and len(voice_embeddings) > 0:
            logger.info(f"  voice_embeddings[0]: type={type(voice_embeddings[0]).__name__}, len={len(voice_embeddings[0]) if hasattr(voice_embeddings[0], '__len__') else 'N/A'}")
        else:
            logger.warning(f"    voice_embeddings is empty or None!")
        
        if not user_name or not user_name.strip():
            return {
                "success": False,
                "error": "User name required",
                "message": "Failed to add embeddings: missing user name"
            }
        
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        app_state = request.app.state if request else None
        
        logger.info(f"[ADD-EMBEDDINGS] DEBUG: voice_embeddings type={type(voice_embeddings).__name__}, count={len(voice_embeddings)}")
        logger.info(f"[ADD-EMBEDDINGS] DEBUG: face_embeddings type={type(face_embeddings).__name__}, count={len(face_embeddings)}")
        
        if voice_embeddings and len(voice_embeddings) > 0:
            logger.info(f"[ADD-EMBEDDINGS] DEBUG: voice_embeddings[0] type={type(voice_embeddings[0]).__name__}, len={len(voice_embeddings[0]) if isinstance(voice_embeddings[0], (list, tuple)) else 'N/A'}")
        
        if app_state:
            if not hasattr(app_state, 'db') or not app_state.db:
                app_state.db = {"users": []}
            if "users" not in app_state.db:
                app_state.db["users"] = []
            
            user_record = {
                "user_id": user_id,
                "name": user_name.strip(),
                "age": age,
                "relation": relation,
                "voice_embeddings": voice_embeddings,
                "face_embeddings": face_embeddings,
                "face_confidences": body.get("face_confidences", [0.0] * len(face_embeddings)),
                "voice_qualities": body.get("voice_qualities", [0.0] * len(voice_embeddings)),
                "enrollment_timestamp": datetime.utcnow().isoformat(),
                "status": "enrolled",
                "total_voice_embeddings": len(voice_embeddings),
                "total_face_embeddings": len(face_embeddings)
            }
            
            logger.info(f"[ADD-EMBEDDINGS] DEBUG: About to append user_record with voice_embeddings={len(user_record.get('voice_embeddings', []))}")
            
            app_state.db["users"].append(user_record)
            logger.info(f"User {user_id} stored with embeddings - voice:{len(voice_embeddings)}, face:{len(face_embeddings)}")
            logger.info(f"[ADD-EMBEDDINGS] DEBUG: After append, total users in db={len(app_state.db['users'])}")
            logger.info(f"[ADD-EMBEDDINGS] DEBUG: Just stored user has voice_embeddings={len(app_state.db['users'][-1].get('voice_embeddings', []))}")
            
            # CRITICAL FIX: Persist to disk!
            await _persist_users(app_state, request, immediate=True)
            logger.info(f"[ADD-EMBEDDINGS]  User {user_id} persisted to disk")
        
        return {
            "success": True,
            "data": {
                "user_id": user_id,
                "name": user_name,
                "embeddings_stored": True,
                "voice_embeddings_count": len(voice_embeddings),
                "face_embeddings_count": len(face_embeddings)
            },
            "message": "User embeddings stored successfully"
        }
        
    except Exception as e:
        logger.error(f"Add embeddings error: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to add embeddings: {str(e)}"
        }


@router.post("/enroll-complete")
async def enroll_user_complete(
    user_name: str = Form(...),
    age: Optional[str] = Form(None),
    relation: Optional[str] = Form(None),
    audio_samples: list = File(...),
    request: Request = None
):
    """
    Complete user enrollment with audio samples (from Streamlit app.py).
    
    THIS IS THE PRIMARY ENDPOINT FOR STREAMLIT INTEGRATION.
    
    Flow:
    1. Receives multipart audio files from Streamlit
    2. Calls Audio Service via audio_client.enroll_speaker() to extract embeddings
    3. Stores user with real embeddings in Central Server
    4. Returns user_id and enrollment confirmation
    
    Args:
        user_name: User's full name
        age: User's age (optional)
        relation: User's relation (optional)
        audio_samples: List of uploaded audio files (WAV/MP3)
        request: FastAPI request context for accessing app state
    
    Returns:
        {
            "success": true,
            "data": {
                "user_id": "user_xyz",
                "name": "John Doe",
                "enrolled_with": 5,
                "embeddings_count": 5,
                "enrollment_timestamp": "2026-02-10T12:34:56"
            },
            "message": "User enrolled successfully"
        }
    """
    try:
        if not user_name or not user_name.strip():
            return {
                "success": False,
                "error": "User name is required",
                "message": "Enrollment failed: missing user name"
            }
        
        # Get audio client from app state
        app_state = request.app.state if request else None
        if not app_state or not hasattr(app_state, 'audio_client'):
            logger.error("[/users/enroll-complete] Audio client not available in app state")
            return {
                "success": False,
                "error": "AUDIO_SERVICE_UNAVAILABLE",
                "message": "Audio Service client not initialized"
            }
        
        audio_client = app_state.audio_client
        user_name = user_name.strip()
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        
        # Convert UploadFile list to bytes
        audio_data = []
        try:
            if not audio_samples or len(audio_samples) == 0:
                return {
                    "success": False,
                    "error": "NO_AUDIO_SAMPLES",
                    "message": "At least one audio sample required for enrollment"
                }
            
            for idx, file in enumerate(audio_samples):
                content = await file.read()
                audio_data.append(content)
                logger.info(f"[/users/enroll-complete] Read audio sample {idx+1}/{len(audio_samples)} ({len(content)} bytes)")
        except Exception as e:
            logger.error(f"[/users/enroll-complete] Failed to read audio files: {e}")
            return {
                "success": False,
                "error": "AUDIO_READ_FAILED",
                "message": f"Failed to read audio files: {str(e)}"
            }
        
        # Call AudioClient to enroll and extract embeddings
        logger.info(f"[/users/enroll-complete] Calling AudioClient.enroll_speaker() for {user_id} with {len(audio_data)} samples")
        
        enrollment_result = await audio_client.enroll_speaker(
            speaker_id=user_id,
            audio_samples=audio_data,
            phrase="default"
        )
        
        if not enrollment_result or not enrollment_result.success:
            logger.error(f"[/users/enroll-complete] AudioClient enrollment failed: {enrollment_result}")
            error_msg = enrollment_result.error_message if enrollment_result else "Unknown error"
            return {
                "success": False,
                "error": "AUDIO_ENROLLMENT_FAILED",
                "message": f"Audio enrollment failed: {error_msg}"
            }
        
        # Extract embeddings from result
        embeddings_data = enrollment_result.data
        voice_embeddings = embeddings_data.get("embedding_array") or [embeddings_data.get("voice_embedding")]
        embedding_size = embeddings_data.get("embedding_size", 256)
        
        logger.info(f"[/users/enroll-complete] Successfully enrolled speaker - embeddings: {len(voice_embeddings)}, size: {embedding_size}")
        
        # Store user with embeddings in Central Server
        if not hasattr(app_state, 'db') or not app_state.db:
            app_state.db = {"users": []}
        
        if "users" not in app_state.db:
            app_state.db["users"] = []
        
        user_record = {
            "user_id": user_id,
            "name": user_name,
            "age": age,
            "relation": relation,
            "voice_embeddings": voice_embeddings,  # REAL embeddings from Audio Service
            "face_embeddings": [[0.0] * 512 for _ in range(len(voice_embeddings))],  # Placeholder for vision
            "num_voice_samples": len(audio_data),
            "enrollment_timestamp": datetime.utcnow().isoformat(),
            "embedding_size": embedding_size,
            "status": "enrolled"
        }
        
        app_state.db["users"].append(user_record)
        logger.info(f"[/users/enroll-complete] User {user_id} stored in Central Server database")
        
        return {
            "success": True,
            "data": {
                "user_id": user_id,
                "name": user_name,
                "age": age,
                "relation": relation,
                "enrolled_with": len(audio_data),
                "embeddings_count": len(voice_embeddings),
                "embedding_size": embedding_size,
                "enrollment_timestamp": user_record["enrollment_timestamp"]
            },
            "message": f"User '{user_name}' enrolled successfully with {len(audio_data)} voice samples"
        }
        
    except Exception as e:
        logger.error(f"[/users/enroll-complete] Unexpected error: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": "ENROLLMENT_ERROR",
            "message": f"Enrollment error: {str(e)}"
        }


async def init_user_router():
    """Initialize user router."""
    logger.info("User router initialized")
    return router
