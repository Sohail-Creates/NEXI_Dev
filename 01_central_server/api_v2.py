"""
Central Server v2.0 - Full Orchestration

Orchestrates all services:
  User Registration → Audio Service → Vision Service → Enrollment Orchestrator → Storage
  
Uses unified `APIResponse` contract. All errors are explicit.
"""

import os
import sys
import asyncio
import aiohttp
import threading
import datetime
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from contextlib import asynccontextmanager
import tempfile
import json

# Add parent to path
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '06_enrollment_service'))

from shared.models import (
    APIResponse, ErrorCode, error_response, success_response, 
    get_logger, setup_logging
)
from shared.utils.circuit_breaker import CircuitBreaker, CircuitBreakerError, CircuitState
from shared.utils.trace_context import TraceContextMiddleware, get_trace_headers, get_trace_id, set_trace_id  # FEATURE #8
from shared.utils.bulkhead import get_bulkhead_manager  # FEATURE #6
from shared.clients.llm_client import LLMServiceClient
from orchestrator import get_orchestrator
from verification_service import (
    get_verification_service, VerificationResult
)
from services.context_builder import ContextBuilder
from persistence import load_users, save_users

# Setup
setup_logging('INFO')
logger = get_logger('CentralServer')

# Service endpoints
AUDIO_SERVICE_URL = os.getenv('AUDIO_SERVICE_URL', 'http://localhost:8002')
VISION_SERVICE_URL = os.getenv('VISION_SERVICE_URL', 'http://localhost:8001')

# Global HTTP session
http_session: Optional[aiohttp.ClientSession] = None

# Global circuit breakers for resilience
vision_circuit_breaker: Optional[CircuitBreaker] = None

# FEATURE #4: Degraded Mode Operation - Embedding Cache
# Allows system to serve cached embeddings when Vision Service unavailable
embedding_cache: Dict[str, Dict[str, Any]] = {}
embedding_cache_file: str = "data/embedding_cache.json"
degraded_mode_enabled: bool = bool(os.getenv("DEGRADED_MODE_ENABLED", "true").lower() in ["true", "1", "yes"])
cache_lock = None

# FEATURE #5: Rate Limiting - Prevent request flooding
request_rate_tracking: Dict[str, Dict[str, Any]] = {}  # {user_id: {count, reset_time}}
rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
rate_limit_lock = threading.Lock()

# FEATURE #6: Bulkhead Isolation - Separate thread pools per service
bulkhead_manager = None
bulkhead_enabled: bool = bool(os.getenv("BULKHEAD_ENABLED", "true").lower() in ["true", "1", "yes"])

# LLM Service Integration
llm_client: Optional[LLMServiceClient] = None
context_builder: Optional[ContextBuilder] = None
llm_enabled: bool = bool(os.getenv("LLM_ENABLED", "true").lower() in ["true", "1", "yes"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle"""
    global http_session, vision_circuit_breaker, cache_lock, embedding_cache, bulkhead_manager, llm_client, context_builder
    
    logger.info("Central Server starting...")
    http_session = aiohttp.ClientSession()
    cache_lock = threading.Lock()
    
    # Initialize circuit breaker for Vision Service
    vision_circuit_breaker = CircuitBreaker(
        name="vision_service",
        failure_threshold=5,
        recovery_timeout=60.0,
        success_threshold=2
    )
    
    # FEATURE #6: Initialize bulkhead isolation for services
    if bulkhead_enabled:
        bulkhead_manager = get_bulkhead_manager()
        bulkhead_manager.register_service("vision", max_workers=int(os.getenv("VISION_BULKHEAD_WORKERS", "3")))
        bulkhead_manager.register_service("audio", max_workers=int(os.getenv("AUDIO_BULKHEAD_WORKERS", "3")))
        bulkhead_manager.register_service("enrollment", max_workers=int(os.getenv("ENROLLMENT_BULKHEAD_WORKERS", "2")))
        logger.info("[OK] Bulkhead isolation initialized with service pools")
    
    # FEATURE #4: Load embedding cache for degraded mode
    _load_embedding_cache()
    
    # Initialize LLM Service integration
    if llm_enabled:
        try:
            llm_service_url = os.getenv("LLM_SERVICE_URL", "http://localhost:8006")
            llm_client = LLMServiceClient(base_url=llm_service_url, timeout=150.0)  # CPU inference: allow extra time
            context_builder = ContextBuilder(user_storage=type('UserStorage', (), {
                'get_user': lambda self, uid: _get_user(uid),
                'save_user': lambda self, uid, data: _save_user(uid, data),
            })())
            logger.info(f"[OK] LLM Service integration initialized at {llm_service_url}")
        except Exception as e:
            logger.warning(f"[WARN] LLM Service integration failed: {e}")
            llm_client = None
            context_builder = None
    
    # Verify services are available
    try:
        async with http_session.get(f"{AUDIO_SERVICE_URL}/health", timeout=aiohttp.ClientTimeout(total=2)) as resp:
            if resp.status == 200:
                logger.info(f"[removed] Audio Service available at {AUDIO_SERVICE_URL}")
            else:
                logger.warning(f"[removed] Audio Service returned {resp.status}")
    except Exception as e:
        logger.warning(f"[removed] Audio Service may not be available: {e}")
    
    yield
    
    # FEATURE #4: Save embedding cache on shutdown
    _save_embedding_cache()
    
    await http_session.close()
    logger.info("Central Server shutdown")


# Initialize app
app = FastAPI(title="Central Server v2.0", version="2.0", lifespan=lifespan)

# FEATURE #8: Add trace propagation middleware
app.add_middleware(TraceContextMiddleware)


# ============================================================================
# FEATURE #4: DEGRADED MODE - EMBEDDING CACHE FUNCTIONS
# ============================================================================

def _load_embedding_cache():
    """Load embedding cache from persistent storage."""
    global embedding_cache
    try:
        cache_path = embedding_cache_file
        if os.path.exists(cache_path):
            with open(cache_path, 'r') as f:
                embedding_cache = json.load(f)
            logger.info(
                f"Loaded embedding cache: {len(embedding_cache)} entries from {cache_path}"
            )
        else:
            logger.debug(f"No existing embedding cache found at {cache_path}")
            embedding_cache = {}
    except Exception as e:
        logger.warning(f"Failed to load embedding cache: {e}")
        embedding_cache = {}


def _save_embedding_cache():
    """Save embedding cache to persistent storage."""
    global embedding_cache
    try:
        if not embedding_cache:
            logger.debug("Embedding cache is empty, skipping save")
            return
        
        cache_path = embedding_cache_file
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, 'w') as f:
            json.dump(embedding_cache, f, indent=2)
        logger.info(f"Saved embedding cache: {len(embedding_cache)} entries to {cache_path}")
    except Exception as e:
        logger.warning(f"Failed to save embedding cache: {e}")


def _cache_embedding(user_name: str, embedding: List[float]):
    """
    Store embedding in cache with locking for thread safety.
    
    Args:
        user_name: User identifier
        embedding: Face embedding vector
    """
    global embedding_cache, cache_lock
    try:
        with cache_lock:
            embedding_cache[user_name] = {
                'embedding': embedding,
                'cached_at': datetime.datetime.now().isoformat(),
                'source': 'degraded_mode'
            }
            logger.debug(f"Cached embedding for user: {user_name}")
    except Exception as e:
        logger.warning(f"Failed to cache embedding for {user_name}: {e}")


def _get_cached_embedding(user_name: str) -> Optional[List[float]]:
    """
    Retrieve embedding from cache with locking.
    
    Args:
        user_name: User identifier
    
    Returns:
        Face embedding vector or None if not found
    """
    global embedding_cache, cache_lock
    try:
        with cache_lock:
            if user_name in embedding_cache:
                cached_data = embedding_cache[user_name]
                logger.debug(f"Retrieved cached embedding for user: {user_name}")
                return cached_data.get('embedding')
            return None
    except Exception as e:
        logger.warning(f"Failed to retrieve cached embedding for {user_name}: {e}")
        return None


# ============================================================================
# FEATURE #5: RATE LIMITING - PREVENT REQUEST FLOODING
# ============================================================================

def _check_rate_limit(user_id: str) -> tuple[bool, Optional[str]]:
    """
    Check if user has exceeded rate limit.
    
    Args:
        user_id: User identifier
    
    Returns:
        (allowed, error_message) tuple
    """
    global request_rate_tracking, rate_limit_lock
    
    try:
        current_time = datetime.datetime.now()
        
        with rate_limit_lock:
            # Initialize tracking for user if not exists
            if user_id not in request_rate_tracking:
                request_rate_tracking[user_id] = {
                    'count': 0,
                    'reset_time': current_time + datetime.timedelta(minutes=1)
                }
            
            user_tracking = request_rate_tracking[user_id]
            
            # Check if reset time has passed
            if current_time >= user_tracking['reset_time']:
                user_tracking['count'] = 0
                user_tracking['reset_time'] = current_time + datetime.timedelta(minutes=1)
            
            # Check if limit exceeded
            if user_tracking['count'] >= rate_limit_per_minute:
                reset_in_seconds = int((user_tracking['reset_time'] - current_time).total_seconds())
                message = f"Rate limit exceeded: {rate_limit_per_minute} requests/minute. Retry in {reset_in_seconds}s"
                logger.warning(f"Rate limit exceeded for user {user_id}")
                return False, message
            
            # Increment counter
            user_tracking['count'] += 1
            
            return True, None
    
    except Exception as e:
        logger.warning(f"Error checking rate limit: {e}")
        # On error, allow the request (fail open)
        return True, None


# ============================================================================
# USER STORAGE HELPERS FOR LLM INTEGRATION
# ============================================================================

def _get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user data from persistent storage."""
    try:
        users = load_users()
        for user in users:
            if user.get("id") == user_id or user.get("user_id") == user_id:
                return user
        return None
    except Exception as e:
        logger.warning(f"Error getting user {user_id}: {e}")
        return None


def _save_user(user_id: str, user_data: Dict[str, Any]) -> bool:
    """Save user data to persistent storage."""
    try:
        users = load_users()
        # Find and update user
        for i, user in enumerate(users):
            if user.get("id") == user_id or user.get("user_id") == user_id:
                users[i] = user_data
                save_users(users)
                return True
        # If not found, add new user
        user_data["id"] = user_id
        users.append(user_data)
        save_users(users)
        return True
    except Exception as e:
        logger.warning(f"Error saving user {user_id}: {e}")
        return False


# ============================================================================
# PHASE 4: SERVICE ORCHESTRATION
# ============================================================================

async def call_audio_service(file_path: str) -> tuple[bool, Optional[list], Optional[str]]:
    """
    Call Audio Service to extract embeddings
    
    Returns:
        (success, embeddings_list, error_message)
    """
    
    trace_id = logger.get_trace_id()
    
    try:
        if not http_session:
            return False, None, "HTTP session not initialized"
        
        # Read file
        if not os.path.exists(file_path):
            return False, None, f"Audio file not found: {file_path}"
        
        # Call Audio Service
        with open(file_path, 'rb') as f:
            data = aiohttp.FormData()
            data.add_field('file', f, filename=os.path.basename(file_path))
            
            try:
                async with http_session.post(
                    f"{AUDIO_SERVICE_URL}/api/v1/process-voice",
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error(
                            f"Audio Service returned {resp.status}: {body}",
                            error_code=ErrorCode.SERVICE_ERROR,
                            trace_id=trace_id
                        )
                        return False, None, f"Audio Service error: {resp.status}"
                    
                    response_data = await resp.json()
                    
                    # Validate response format from Audio Service
                    if not isinstance(response_data, dict):
                        return False, None, "Invalid response format from Audio Service"
                    
                    # Check status field (Audio Service uses "status": "success")
                    if response_data.get('status') != 'success':
                        error_msg = response_data.get('error', 'Unknown error')
                        return False, None, f"Audio Service error: {error_msg}"
                    
                    # Extract embeddings - CORRECT PATH: direct "embedding" key, not nested
                    embeddings = response_data.get('embedding')
                    if not embeddings:
                        return False, None, "No embedding in Audio Service response"
                    
                    # Validate embedding dimension
                    if not isinstance(embeddings, list):
                        return False, None, f"Embedding should be list, got {type(embeddings)}"
                    
                    if len(embeddings) != 256:
                        return False, None, f"Invalid embedding dimension: {len(embeddings)} != 256"
                    
                    # Check non-zero
                    if all(abs(x) < 1e-8 for x in embeddings):
                        return False, None, "Audio Service returned zero embeddings"
                    
                    logger.info(
                        f"[removed] Audio embeddings extracted successfully",
                        embeddings_dim=len(embeddings)
                    )
                    
                    return True, [embeddings], None
            
            except asyncio.TimeoutError:
                logger.error("Audio Service timeout", error_code=ErrorCode.SERVICE_TIMEOUT)
                return False, None, "Audio Service timeout"
            except Exception as e:
                logger.error(f"Audio Service call failed: {e}", error_code=ErrorCode.SERVICE_ERROR)
                return False, None, f"Audio Service error: {str(e)}"
    
    except Exception as e:
        logger.error(f"Unexpected error calling Audio Service: {e}")
        return False, None, str(e)


# FEATURE #2: Exponential Backoff Retry Logic - Configuration
VISION_MAX_RETRIES = int(os.getenv("VISION_MAX_RETRIES", "3"))
VISION_RETRY_BACKOFF_FACTOR = float(os.getenv("VISION_RETRY_BACKOFF_FACTOR", "2.0"))
VISION_RETRY_MAX_DELAY = float(os.getenv("VISION_RETRY_MAX_DELAY", "8.0"))
VISION_RETRY_INITIAL_DELAY = float(os.getenv("VISION_RETRY_INITIAL_DELAY", "1.0"))

# Transient errors that should trigger retry
TRANSIENT_HTTP_ERRORS = {502, 503, 504}  # Bad Gateway, Service Unavailable, Gateway Timeout


async def _call_vision_http_with_retry(
    file_path: str, 
    session: aiohttp.ClientSession,
    url: str,
    max_retries: int = VISION_MAX_RETRIES
) -> tuple[Optional[int], Optional[Dict], Optional[str]]:
    """
    FEATURE #2: Make HTTP request to Vision Service with exponential backoff retry
    
    Handles transient failures (502, 503, 504, timeout) with exponential backoff.
    Does NOT retry permanent errors (400, 404, connection refused, etc).
    
    Args:
        file_path: Path to image file
        session: aiohttp ClientSession
        url: Vision Service URL
        max_retries: Maximum number of retries (default 3, so 4 total attempts)
    
    Returns:
        (status_code, response_json, error_message) tuple
        - status_code: HTTP status (200 on success, None on connection error)
        - response_json: Parsed JSON response (None on failure)
        - error_message: Error description (None on success)
    """
    
    for attempt in range(max_retries + 1):  # +1 for initial attempt
        retry_count = attempt
        is_final_attempt = (attempt == max_retries)
        
        try:
            with open(file_path, 'rb') as f:
                data = aiohttp.FormData()
                data.add_field('file', f, filename=os.path.basename(file_path))
                data.add_field('detector_backend', 'opencv')
                data.add_field('model_name', 'Facenet')
                data.add_field('analyze_emotions', 'True')
                
                logger.debug(f"Attempt {attempt + 1}/{max_retries + 1} to Vision Service")
                
                try:
                    # FEATURE #8: Add trace propagation to Vision Service request
                    headers = get_trace_headers()
                    async with session.post(
                        url,
                        data=data,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as resp:
                        status = resp.status
                        text = await resp.text()
                        
                        # HTTP 200: Success
                        if status == 200:
                            logger.debug(f"Vision Service success on attempt {attempt + 1}")
                            return status, json.loads(text) if text else {}, None
                        
                        # HTTP 502, 503, 504: Transient error - retry
                        if status in TRANSIENT_HTTP_ERRORS:
                            if is_final_attempt:
                                logger.error(
                                    f"Vision Service transient error {status} on final attempt {attempt + 1}"
                                )
                                return status, None, f"Vision Service returned {status} (all retries exhausted)"
                            else:
                                logger.warning(
                                    f"Vision Service transient error {status} on attempt {attempt + 1}, retrying..."
                                )
                                # Fall through to retry with backoff
                        
                        # HTTP 4xx, 5xx (non-transient): Don't retry
                        else:
                            logger.error(
                                f"Vision Service non-transient error {status} on attempt {attempt + 1}"
                            )
                            return status, None, f"Vision Service returned {status}"
                
                except asyncio.TimeoutError:
                    if is_final_attempt:
                        logger.error(f"Vision Service timeout on final attempt {attempt + 1}")
                        return None, None, "Vision Service timeout (all retries exhausted)"
                    else:
                        logger.warning(f"Vision Service timeout on attempt {attempt + 1}, retrying...")
                        # Fall through to retry with backoff
        
        except aiohttp.ClientError as e:
            # Connection errors: retry on transient, don't retry on others
            if is_final_attempt:
                logger.error(f"Vision Service connection error on final attempt {attempt + 1}: {e}")
                return None, None, f"Cannot reach Vision Service: {str(e)}"
            else:
                logger.warning(f"Vision Service connection error on attempt {attempt + 1}, retrying: {e}")
                # Fall through to retry with backoff
        
        except Exception as e:
            logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")
            return None, None, str(e)
        
        # Calculate backoff delay for next attempt
        if not is_final_attempt:
            delay = min(
                VISION_RETRY_INITIAL_DELAY * (VISION_RETRY_BACKOFF_FACTOR ** attempt),
                VISION_RETRY_MAX_DELAY
            )
            logger.debug(f"Waiting {delay:.1f}s before retry (attempt {attempt + 2})")
            await asyncio.sleep(delay)
    
    # Should not reach here
    return None, None, "Unknown error in retry loop"


async def call_vision_service(file_path: str) -> tuple[bool, Optional[list], Optional[str]]:
    """
    Call Vision Service to extract face embeddings
    
    Production implementation - Connects to Vision Service at VISION_SERVICE_URL
    Extracts 128D Facenet embeddings from detected faces
    Uses circuit breaker for resilience (prevents cascading failures)
    
    Returns:
        (success, embeddings_list, error_message)
    """
    
    trace_id = logger.get_trace_id()
    
    try:
        if not os.path.exists(file_path):
            return False, None, f"Image file not found: {file_path}"
        
        if not http_session:
            return False, None, "HTTP session not initialized"
        
        # Check circuit breaker state - if OPEN, fail fast without making request
        global vision_circuit_breaker
        if vision_circuit_breaker and vision_circuit_breaker.state == CircuitState.OPEN:
            logger.warning(
                f"Vision Service circuit breaker is OPEN - failing fast without attempting request. "
                f"Service will be retried in ~60 seconds"
            )
            return False, None, "Vision Service temporarily unavailable (circuit breaker open, will retry automatically)"
        
        # Call Vision Service /detect/faces/upload endpoint with retry logic
        logger.info(f"Calling Vision Service at {VISION_SERVICE_URL}/detect/faces/upload (with retry)")
        
        # FEATURE #2: Use retry helper for exponential backoff on transient errors
        status_code, response_data, retry_error = await _call_vision_http_with_retry(
            file_path=file_path,
            session=http_session,
            url=f"{VISION_SERVICE_URL}/detect/faces/upload",
            max_retries=VISION_MAX_RETRIES
        )
        
        # Handle retry helper errors
        if retry_error:
            logger.warning(f"Vision Service call failed after retries: {retry_error}")
            # Record failure in circuit breaker for transient errors
            if status_code in [502, 503, 504] or "timeout" in retry_error.lower():
                vision_circuit_breaker.failure_count += 1
                if vision_circuit_breaker.failure_count >= vision_circuit_breaker.failure_threshold:
                    vision_circuit_breaker.state = CircuitState.OPEN
                    logger.error(
                        f"Vision Service circuit breaker transitioned to OPEN "
                        f"after {vision_circuit_breaker.failure_count} failures"
                    )
            return False, None, retry_error
        
        # At this point, response_data should be valid JSON from successful request
        if not response_data:
            return False, None, "Empty response from Vision Service"
        
        # Validate response structure
        if response_data.get('status') != 'success':
            return False, None, f"Vision Service returned status: {response_data.get('status')}"
        
        # Extract faces from response
        faces = response_data.get('faces', [])
        if not faces:
            logger.warning("No faces detected in image")
            return False, None, "No faces detected in image"
        
        # Extract embeddings from all detected faces
        embeddings_list = []
        for idx, face in enumerate(faces):
            try:
                embedding = face.get('embedding')
                confidence = face.get('confidence', 0.0)
                emotion = face.get('dominant_emotion', 'unknown')
                
                if not embedding or not isinstance(embedding, list):
                    logger.warning(f"Face {idx}: Invalid embedding format")
                    continue
                
                if len(embedding) not in [128, 256]:
                    logger.warning(f"Face {idx}: Unexpected embedding dimension: {len(embedding)}")
                    continue
                
                # Validate embedding is not all zeros
                if all(abs(x) < 1e-8 for x in embedding):
                    logger.warning(f"Face {idx}: Zero embeddings returned")
                    continue
                
                # Store embedding with metadata
                embeddings_list.append({
                    'vector': embedding,
                    'confidence': confidence,
                    'emotion': emotion,
                    'dimension': len(embedding),
                    'model': face.get('embedding_model', 'Facenet')
                })
                
                logger.info(
                    f"[removed] Face {idx} embedding extracted",
                    confidence=confidence,
                    emotion=emotion,
                    dimension=len(embedding),
                    model=face.get('embedding_model')
                )
            
            except Exception as e:
                logger.error(f"Error processing face {idx}: {e}")
                continue
        
        if not embeddings_list:
            return False, None, "Unable to extract embeddings from detected faces"
        
        # SUCCESS: Record success in circuit breaker
        vision_circuit_breaker.failure_count = 0  # Reset failure count on success
        logger.debug("Circuit breaker: Recorded success, failure count reset")
        
        # For enrollment, we'll use the embeddings as-is from Vision Service
        # (128D Facenet by default, extensible to other models)
        embeddings_data = [item['vector'] for item in embeddings_list]
        
        logger.info(
            f"[removed] Face embeddings extracted successfully",
            faces_detected=len(embeddings_list),
            total_embeddings=len(embeddings_data)
        )
        
        # Return the list of embeddings (can be multiple if multiple faces detected)
        return True, embeddings_data, None
    
    except Exception as e:
        logger.error(f"Unexpected error calling Vision Service: {e}")
        return False, None, str(e)


@app.post("/users/register")
async def register_user(
    user_name: str,
    email: str,
    phone: str,
    audio_file: Optional[UploadFile] = File(None),
    image_file: Optional[UploadFile] = File(None)
) -> APIResponse:
    """
    Register new user with full orchestration
    
    Flow:
    1. Validate input
    2. Call Audio Service for voice embeddings (if audio provided)
    3. Call Vision Service for face embeddings (if image provided)
    4. Call Enrollment Orchestrator to store atomically
    5. Return result
    FEATURE #8: All requests include trace ID for cross-service tracking
    """
    
    # FEATURE #8: Get trace ID from context (created by middleware)
    trace_id = get_trace_id()
    
    try:
        logger.info(
            f"Starting user registration",
            user_name=user_name,
            email=email,
            trace_id=trace_id  # FEATURE #8: Include trace ID in logs
        )
        
        # ===== FEATURE #5: RATE LIMIT CHECK =====
        allowed, rate_limit_msg = _check_rate_limit(user_name)
        if not allowed:
            return error_response(
                code=ErrorCode.RATE_LIMIT_EXCEEDED,
                message=rate_limit_msg or "Rate limit exceeded",
                trace_id=trace_id
            )
        
        # ===== PHASE 1: INPUT VALIDATION =====
        if not user_name or not email or not phone:
            return error_response(
                code=ErrorCode.INVALID_INPUT,
                message="Missing required fields: user_name, email, phone",
                trace_id=trace_id
            )
        
        logger.info("[removed] Input validation passed")
        
        # ===== PHASE 2: AUDIO PROCESSING =====
        audio_embeddings = []
        audio_temp_path = None
        
        if audio_file:
            logger.info("Processing audio file...")
            try:
                # Save temp file
                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    content = await audio_file.read()
                    tmp.write(content)
                    audio_temp_path = tmp.name
                
                # Call Audio Service
                success, embeddings, error = await call_audio_service(audio_temp_path)
                if not success:
                    return error_response(
                        code=ErrorCode.INVALID_AUDIO,
                        message=error or "Audio processing failed",
                        trace_id=trace_id
                    )
                
                audio_embeddings = embeddings
                logger.info("[removed] Audio processing complete")
            
            finally:
                if audio_temp_path and os.path.exists(audio_temp_path):
                    try:
                        os.remove(audio_temp_path)
                    except:
                        pass
        
        # ===== PHASE 3: FACE PROCESSING =====
        face_embeddings = []
        face_temp_path = None
        
        if image_file:
            logger.info("Processing face image...")
            try:
                # Save temp file
                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    content = await image_file.read()
                    tmp.write(content)
                    face_temp_path = tmp.name
                
                # Call Vision Service
                success, embeddings, error = await call_vision_service(face_temp_path)
                
                # FEATURE #4: Fallback to cached embedding if Vision Service fails and degraded mode enabled
                if not success and degraded_mode_enabled:
                    logger.warning(
                        f"Vision Service call failed ({error}), attempting to use cached embedding for {user_name}"
                    )
                    cached_embedding = _get_cached_embedding(user_name)
                    if cached_embedding:
                        face_embeddings = [cached_embedding]
                        logger.warning(
                            f"[removed] Using cached face embedding for user {user_name} (degraded mode)"
                        )
                        success = True  # Override failure to use cache
                        error = None
                
                if not success:
                    return error_response(
                        code=ErrorCode.INVALID_IMAGE,
                        message=error or "Face processing failed",
                        trace_id=trace_id
                    )
                
                face_embeddings = embeddings
                
                # FEATURE #4: Cache embeddings for future degraded mode usage
                if success and embeddings and len(embeddings) > 0:
                    _cache_embedding(user_name, embeddings[0])  # Cache first embedding
                
                logger.info("[removed] Face processing complete")
            
            finally:
                if face_temp_path and os.path.exists(face_temp_path):
                    try:
                        os.remove(face_temp_path)
                    except:
                        pass
        
        # ===== PHASE 4: ATOMIC STORAGE =====
        logger.info("Starting atomic enrollment...")
        
        orchestrator = get_orchestrator()
        user_data = {
            'user_name': user_name,
            'email': email,
            'phone': phone,
            'voice_embeddings': audio_embeddings,
            'face_embeddings': face_embeddings
        }
        
        success, error_msg, result = await orchestrator.enroll_user(user_data)
        
        if not success:
            return error_response(
                code=ErrorCode.PROCESSING_FAILED,
                message=error_msg or "Enrollment failed",
                trace_id=trace_id
            )
        
        logger.info("[removed] User registered successfully", user_name=user_name)
        
        return success_response(
            data={
                'user_name': user_name,
                'email': email,
                'phone': phone,
                'audio_embeddings_count': len(audio_embeddings),
                'face_embeddings_count': len(face_embeddings),
                'message': 'User registered successfully'
            },
            trace_id=trace_id
        )
    
    except Exception as e:
        logger.error(f"Unexpected error during registration: {e}", error_code=ErrorCode.SERVICE_ERROR)
        return error_response(
            code=ErrorCode.SERVICE_ERROR,
            message="Internal server error",
            details={"error": str(e)},
            trace_id=trace_id
        )


@app.get("/users/list")
async def list_users() -> APIResponse:
    """List all enrolled users"""
    
    trace_id = logger.generate_trace_id()
    
    try:
        orchestrator = get_orchestrator()
        enrollments = orchestrator._load_enrollments()
        
        users_list = [
            {
                'user_name': user_id,
                'email': data.get('email'),
                'phone': data.get('phone'),
                'audio_samples': len(data.get('voice_embeddings', [])),
                'face_samples': len(data.get('face_embeddings', [])),
                'enrolled': data.get('enrollment_timestamp')
            }
            for user_id, data in enrollments.items()
        ]
        
        return success_response(
            data={'users': users_list, 'count': len(users_list)},
            trace_id=trace_id
        )
    
    except Exception as e:
        logger.error(f"Failed to list users: {e}", error_code=ErrorCode.SERVICE_ERROR)
        return error_response(
            code=ErrorCode.SERVICE_ERROR,
            message="Failed to list users",
            trace_id=trace_id
        )


# ============================================================================
# PHASE 5: SPEAKER VERIFICATION
# ============================================================================

@app.post("/users/verify")
async def verify_speaker(
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
        
    Returns:
        APIResponse with verification result
    """
    
    trace_id = logger.generate_trace_id()
    
    try:
        logger.info(f"Verification request: user={user_name}, audio={audio_file is not None}")
        
        # Get verification service
        verification_service = get_verification_service()
        
        # Extract speaker embedding
        speaker_embedding = None
        
        if audio_file:
            # Mode 1: Extract embedding from audio file
            logger.info(f"Processing audio file: {audio_file.filename}")
            
            # Save temp file
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                content = await audio_file.read()
                tmp.write(content)
                tmp_path = tmp.name
            
            try:
                # Call Audio Service
                success, embeddings, error = await call_audio_service(tmp_path)
                
                if not success:
                    logger.error(f"Audio extraction failed: {error}")
                    return error_response(
                        code=ErrorCode.PROCESSING_FAILED,
                        message="Failed to extract speaker embedding from audio",
                        details={"audio_error": error},
                        trace_id=trace_id
                    )
                
                speaker_embedding = embeddings[0] if embeddings else None
            
            finally:
                # Clean up temp file
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except:
                        pass
        
        elif embedding:
            # Mode 2: Use pre-extracted embedding
            logger.info("Using pre-extracted embedding")
            
            try:
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
        
        logger.info(f"Calling verification service (user={user_name})")
        verification_result = verification_service.verify_speaker(
            speaker_embedding,
            expected_user=user_name
        )
        
        # Check for errors
        if verification_result.result == VerificationResult.ERROR:
            logger.error(f"Verification error: {verification_result.error_message}")
            return error_response(
                code=ErrorCode.PROCESSING_FAILED,
                message="Speaker verification failed",
                details={"verification_error": verification_result.error_message},
                trace_id=trace_id
            )
        
        # Return success
        logger.info(f"Verification complete: {verification_result.result.value}, user={verification_result.user_name}")
        
        return success_response(
            data=verification_result.to_dict(),
            trace_id=trace_id
        )
    
    except Exception as e:
        logger.error(f"Unexpected verification error: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.SERVICE_ERROR,
            message="Unexpected verification error",
            details={"error": str(e)},
            trace_id=trace_id
        )


@app.get("/users/verify/status")
async def verify_status() -> APIResponse:
    """Check verification service status"""
    
    trace_id = logger.generate_trace_id()
    
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
        logger.error(f"Error checking verification status: {e}")
        return error_response(
            code=ErrorCode.SERVICE_ERROR,
            message="Failed to check verification status",
            details={"error": str(e)},
            trace_id=trace_id
        )


@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "service": "Central Server",
        "version": "2.0"
    }


@app.get("/status")
async def status():
    """
    Detailed status including:
    - Circuit breaker state
    - Bulkhead pool status
    - Statistics on requests
    FEATURE #6: Exposes bulkhead resource isolation metrics
    """
    global bulkhead_manager, vision_circuit_breaker
    
    status_info = {
        "service": "Central Server v2.0",
        "status": "running",
        "circuit_breaker": {
            "vision_service": {
                "state": str(vision_circuit_breaker.state) if vision_circuit_breaker else "not_initialized",
                "failure_count": vision_circuit_breaker.failure_count if vision_circuit_breaker else 0
            }
        },
        "bulkhead": {
            "enabled": bulkhead_enabled
        }
    }
    
    # FEATURE #6: Add bulkhead status if enabled
    if bulkhead_enabled and bulkhead_manager:
        status_info["bulkhead"]["pools"] = bulkhead_manager.get_all_status()
    
    return status_info


# ============================================================================
# LLM SERVICE INTEGRATION ROUTES
# ============================================================================

@app.post("/llm/generate-response", response_model=APIResponse)
async def llm_generate_response(
    user_id: str,
    query: str,
    language: str = "en",
    include_vision: bool = True,
    include_knowledge: bool = True,
) -> APIResponse:
    """
    Generate AI response with full context from NEXI services.
    
    Orchestrates:
    1. Context gathering (user profile, vision, knowledge, history)
    2. LLM inference
    3. Response storage in conversation history
    """
    if not llm_enabled or not llm_client or not context_builder:
        return error_response(
            error_code=ErrorCode.SERVICE_UNAVAILABLE,
            message="LLM service not available",
        )
    
    try:
        # Validate user exists
        user = _get_user(user_id)
        if not user:
            return error_response(
                error_code=ErrorCode.NOT_FOUND,
                message="User not found",
            )
        
        logger.info(f"Generating LLM response for user {user_id}: {query[:50]}...")
        
        # Build context from services
        context = await context_builder.build_context(
            user_id=user_id,
            query=query,
            include_vision=include_vision,
            include_knowledge=include_knowledge,
        )
        
        logger.debug(f"Context built: {list(context.keys())}")
        
        # Call LLM service
        success, llm_result = await llm_client.generate_response(
            query=query,
            language=language,
            user_context=context.get("user_context"),
            vision_context=context.get("vision_context"),
            knowledge_items=context.get("knowledge_items"),
            conversation_history=context.get("conversation_history"),
        )
        
        if not success:
            return error_response(
                error_code=ErrorCode.SERVICE_ERROR,
                message=llm_result.get("error", "LLM generation failed"),
            )
        
        # Extract response
        response_text = llm_result.get("response", "")
        
        # Store in conversation history
        try:
            if "conversation_history" not in user:
                user["conversation_history"] = []
            
            user["conversation_history"].append({
                "user": query,
                "assistant": response_text,
                "timestamp": datetime.datetime.now().isoformat(),
            })
            
            # Keep only last 50 turns
            if len(user["conversation_history"]) > 50:
                user["conversation_history"] = user["conversation_history"][-50:]
            
            _save_user(user_id, user)
        except Exception as e:
            logger.warning(f"Failed to store conversation: {e}")
        
        return success_response(
            data={
                "response": response_text,
                "language": language,
                "metadata": llm_result.get("metadata", {}),
            }
        )
    
    except Exception as e:
        logger.error(f"Error in LLM generation: {str(e)}", exc_info=True)
        return error_response(
            error_code=ErrorCode.INTERNAL_ERROR,
            message="Failed to generate response",
        )


@app.get("/llm/conversation")
async def llm_get_conversation(user_id: str) -> APIResponse:
    """Get conversation history for user."""
    try:
        user = _get_user(user_id)
        if not user:
            return error_response(
                error_code=ErrorCode.NOT_FOUND,
                message="User not found",
            )
        
        history = user.get("conversation_history", [])
        
        return success_response(
            data={
                "user_id": user_id,
                "conversation_count": len(history),
                "recent_turns": history[-10:] if history else [],
            }
        )
    
    except Exception as e:
        logger.error(f"Error getting conversation: {str(e)}")
        return error_response(
            error_code=ErrorCode.INTERNAL_ERROR,
            message="Failed to retrieve conversation",
        )


@app.delete("/llm/conversation")
async def llm_clear_conversation(user_id: str) -> APIResponse:
    """Clear conversation history for user."""
    try:
        user = _get_user(user_id)
        if not user:
            return error_response(
                error_code=ErrorCode.NOT_FOUND,
                message="User not found",
            )
        
        user["conversation_history"] = []
        _save_user(user_id, user)
        
        return success_response(
            data={"message": "Conversation history cleared"}
        )
    
    except Exception as e:
        logger.error(f"Error clearing conversation: {str(e)}")
        return error_response(
            error_code=ErrorCode.INTERNAL_ERROR,
            message="Failed to clear conversation",
        )


@app.get("/llm/health")
async def llm_health() -> Dict[str, Any]:
    """Check LLM service health."""
    if not llm_client:
        return {
            "service": "LLM",
            "healthy": False,
            "status": "not_initialized",
        }
    
    try:
        is_healthy = await llm_client.health_check()
        
        return {
            "service": "LLM",
            "healthy": is_healthy,
            "status": "ok" if is_healthy else "degraded",
            "circuit_breaker": llm_client.get_circuit_breaker_status(),
        }
    except Exception as e:
        logger.warning(f"Error checking LLM health: {str(e)}")
        return {
            "service": "LLM",
            "healthy": False,
            "status": "error",
            "error": str(e),
        }


@app.get("/")
async def root():
    """Service info"""
    return {
        "service": "Central Server v2.0",
        "status": "running",
        "endpoints": {
            "POST /users/register": "Register new user with orchestration",
            "GET /users/list": "List all users",
            "POST /users/verify": "Verify speaker identity (Phase 5)",
            "GET /users/verify/status": "Check verification service status",
            "POST /llm/generate-response": "Generate AI response with full context",
            "GET /llm/conversation": "Get conversation history",
            "DELETE /llm/conversation": "Clear conversation history",
            "GET /llm/health": "Check LLM service health",
            "GET /health": "Health check"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
