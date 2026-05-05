from __future__ import annotations

import asyncio
import io
import logging
import sys
import threading
import time
import traceback
import uuid
import wave
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from piper import PiperVoice, SynthesisConfig

from .config import Config
from .parallel_worker_pool import get_worker_pool
from .service_config import get_service_config
from .error_context import ERROR_LOGGER, ErrorSeverity, ErrorCategory
from .metrics import metrics_registry, record_successful_synthesis, record_validation_error, record_timeout_error, record_synthesis_error
from .speaker_manager import get_speaker_manager

# Import Phase 1 security: Rate limiting
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))
from shared.rate_limiter import create_rate_limit_middleware


# ==========================
# Logging Setup
# ==========================
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
LOGGER = logging.getLogger("nexi.tts")

# Validate configuration
config_errors = Config.validate()
if config_errors:
    for error in config_errors:
        LOGGER.warning("Config error: %s", error)

PIPER_MODELS_DIR = Config.PIPER_MODELS_DIR
PIPER_MODELS_DIR.mkdir(parents=True, exist_ok=True)
LOGGER.info("Piper models directory: %s", PIPER_MODELS_DIR)

# Configuration constants
SYNTHESIS_TIMEOUT_SECONDS = Config.SYNTHESIS_TIMEOUT_SECONDS
MAX_TEXT_LENGTH = Config.MAX_TEXT_LENGTH
QUEUE_TIMEOUT_SECONDS = Config.QUEUE_TIMEOUT_SECONDS


# REMOVED: Urdu voices now included in VOICE_DEFINITIONS with shahid
# They are loaded through the same Piper mechanism with .onnx models in urdu/ subdirectory

# ==========================
# Voice Definition
# ==========================
@dataclass(frozen=True)
class PiperVoiceDefinition:
    id: str
    name: str
    locale: str
    gender: str
    description: str
    model: str   # ONNX file name
    speaker_id: Optional[int] = None
    length_scale: Optional[float] = 1.0
    noise_scale: Optional[float] = 0.667
    noise_w_scale: Optional[float] = 0.8

    def as_api_dict(self) -> Dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "locale": self.locale,
            "gender": self.gender,
            "description": self.description,
        }

    def model_path(self) -> Path:
        return PIPER_MODELS_DIR / self.model

    def config_path(self) -> Path:
        return self.model_path().with_suffix(self.model_path().suffix + ".json")


@dataclass
class VoiceRuntime:
    """Lightweight voice metadata (no model loading in constructor)."""
    definition: PiperVoiceDefinition
    model_path: Path
    config_path: Path
    
    def is_available(self) -> bool:
        """Check if model files exist."""
        return self.model_path.exists() and self.config_path.exists()


# ==========================
# Voice Library (Production Ready)
# ==========================
VOICE_DEFINITIONS = [
    PiperVoiceDefinition(
        id="ryan",
        name="Ryan (Male, English)",
        locale="en-US",
        gender="Male",
        description="High quality male voice - clear and natural",
        model="en_US-ryan-high.onnx",
        length_scale=1.0,
        noise_scale=0.667,
        noise_w_scale=0.8,
    ),
    PiperVoiceDefinition(
        id="jenny",
        name="Jenny (Female, English)",
        locale="en-GB",
        gender="Female",
        description="British English accent - natural female voice",
        model="en_GB-jenny_dioco-medium.onnx",
        length_scale=1.0,
        noise_scale=0.667,
        noise_w_scale=0.8,
    ),
    PiperVoiceDefinition(
        id="shahid",
        name="Shahid (Male, Urdu)",
        locale="ur-PK",
        gender="Male",
        description="Rehnuma Shahid - Natural male voice for Urdu language",
        model="urdu/ur_ma-rehnuma_shahid-low.onnx",
        length_scale=1.0,
        noise_scale=0.667,
        noise_w_scale=0.8,
    ),
]


# Thread-safe service configuration
SERVICE_CONFIG = get_service_config()

AVAILABLE_VOICES: List[Dict[str, str]] = []
VOICE_INDEX: Dict[str, VoiceRuntime] = {}
SERVICE_READY = False
SPEAKER_MANAGER = None


# ==========================
# Service State
# ==========================
class ServiceState:
    def __init__(self):
        self.start_time = time.time()
        self.requests_processed = 0
        self.requests_failed = 0
        self.last_error: Optional[str] = None
        self.lock = threading.Lock()

    def record_success(self):
        with self.lock:
            self.requests_processed += 1

    def record_failure(self, error: str):
        with self.lock:
            self.requests_failed += 1
            self.last_error = error

    def uptime_seconds(self) -> float:
        return time.time() - self.start_time

    def get_stats(self) -> Dict:
        with self.lock:
            return {
                "uptime_seconds": self.uptime_seconds(),
                "requests_processed": self.requests_processed,
                "requests_failed": self.requests_failed,
                "last_error": self.last_error,
            }


SERVICE_STATE = ServiceState()


# ==========================
# Registry Setup
# ==========================
def refresh_voice_registry():
    """Build voice registry without loading models (lazy loading on demand)."""
    global AVAILABLE_VOICES, VOICE_INDEX

    discovered = []
    registry = {}

    for definition in VOICE_DEFINITIONS:
        model_path = definition.model_path()
        config_path = definition.config_path()

        # Check files exist but don't load yet
        if not model_path.exists() or not config_path.exists():
            LOGGER.warning("Model files not found for voice: %s", definition.id)
            LOGGER.warning("  Model: %s", model_path)
            LOGGER.warning("  Config: %s", config_path)
            continue

        runtime = VoiceRuntime(
            definition=definition,
            model_path=model_path,
            config_path=config_path,
        )

        registry[definition.id] = runtime
        discovered.append(definition.as_api_dict())
        LOGGER.info("Registered voice: %s (lazy load enabled)", definition.id)

    if not discovered:
        raise RuntimeError("No Piper models found!")

    AVAILABLE_VOICES = discovered
    VOICE_INDEX = registry

    LOGGER.info("Voice registry ready: %d voices (models will load on demand)", len(discovered))


def ensure_default_voice() -> None:
    """Ensure default voice is properly initialized."""
    # Default voice is already set in SERVICE_CONFIG
    LOGGER.info("Default voice configured: %s", SERVICE_CONFIG.default_voice)


def resolve_voice(voice_id: Optional[str]) -> str:
    """
    Resolve and validate voice ID (thread-safe).
    PHASE 1.2: Standardized to SHORT voice IDs everywhere
    PHASE 1.3: Thread-safe access to default voice
    Supported voices: ryan, jenny, shahid
    """
    vid = voice_id or SERVICE_CONFIG.default_voice
    
    # Validate voice exists before returning
    if vid not in VOICE_INDEX:
        available = ", ".join(VOICE_INDEX.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Invalid voice_id: {vid}. Available: {available}"
        )
    
    return vid


# ==========================
# Request Schema
# ==========================
class SpeechRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH)
    voice_id: Optional[str] = None
    language: Optional[str] = None  # Language hint: 'en' or 'ur' (skip detection)
    model_config = ConfigDict(extra="ignore")


# ==========================
# PARALLEL WORKER POOL (Phase 2 Optimization)
# ==========================

# 3 parallel workers for 3x throughput
# Each worker independently manages ONNX instances for true parallelization
WORKER_POOL = None


# ==========================
# FastAPI Lifespan & Initialization
# ==========================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.
    Initializes parallel worker pool with per-worker caches.
    PHASE 1: Eliminated shared cache lock bottleneck.
    Each worker now has independent cache instance.
    OPTIMIZATION: Initialize speaker manager for Jenny default + smart switching.
    """
    global SERVICE_READY, WORKER_POOL, SPEAKER_MANAGER
    
    # Startup
    try:
        LOGGER.info("TTS Service starting up...")
        
        refresh_voice_registry()
        ensure_default_voice()
        
        # Initialize parallel worker pool (Phase 1 optimization: per-worker caches)
        LOGGER.info("Starting parallel worker pool (3 workers with independent caches)...")
        WORKER_POOL = get_worker_pool(
            num_workers=3,
            models_dir=str(PIPER_MODELS_DIR)
        )
        await WORKER_POOL.start()
        
        # Initialize speaker manager for intelligent speaker lifecycle management
        LOGGER.info("Initializing speaker manager...")
        from .unified_model_cache import get_unified_model_cache
        # Get cache from first worker for quick access to model loading
        if WORKER_POOL and WORKER_POOL.worker_caches:
            worker_cache = WORKER_POOL.worker_caches[0]
        else:
            worker_cache = get_unified_model_cache(str(PIPER_MODELS_DIR))
        
        SPEAKER_MANAGER = get_speaker_manager(worker_cache)
        SPEAKER_MANAGER.initialize_default_speaker()
        
        SERVICE_READY = True
        LOGGER.info("TTS Service ready (3 independent worker caches, true parallelism, Jenny default voice)")
        
    except Exception as ex:
        SERVICE_READY = False
        LOGGER.error("Failed to start TTS service: %s", str(ex), exc_info=True)
        raise

    yield

    # Shutdown - Graceful
    LOGGER.info("TTS Service shutting down...")
    
    if WORKER_POOL:
        await WORKER_POOL.stop()
    
    SERVICE_READY = False
    LOGGER.info("TTS Service shutdown complete")


app = FastAPI(
    title=Config.SERVICE_NAME,
    version=Config.SERVICE_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add Phase 1 security: Rate limiting middleware
# Exempt: /health endpoints (should always be available)
rate_limit_middleware = create_rate_limit_middleware()
app.middleware("http")(rate_limit_middleware)


# ==========================
# Middleware for Request Tracking
# ==========================
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add unique request ID for distributed tracing."""
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ==========================
# Health Check Endpoints
# ==========================
@app.get("/health")
def health_check():
    """
    Basic health check endpoint.
    Returns 200 if service is running, ready to accept requests.
    """
    if not SERVICE_READY:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    return {
        "status": "healthy",
        "service": Config.SERVICE_NAME,
        "version": Config.SERVICE_VERSION,
        "timestamp": time.time(),
    }


@app.get("/health/detailed")
def health_detailed():
    """
    Detailed health check with service statistics.
    Useful for monitoring and observability.
    PHASE 2.3: Includes circuit breaker status.
    PHASE 3.2: Includes error context.
    PHASE 4.1: Includes metrics.
    """
    if not SERVICE_READY:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    stats = SERVICE_STATE.get_stats()
    worker_stats = WORKER_POOL.get_stats() if WORKER_POOL else {}
    
    # PHASE 2.3: Add circuit breaker status
    from .circuit_breaker import get_all_breakers
    breaker_stats = get_all_breakers()
    
    # PHASE 3.2: Add error context
    error_stats = ERROR_LOGGER.get_error_stats()
    
    # PHASE 4.1: Add metrics
    metrics_dict = metrics_registry.get_metrics_dict()
    
    return {
        "status": "healthy",
        "service": Config.SERVICE_NAME,
        "version": Config.SERVICE_VERSION,
        "timestamp": time.time(),
        "available_voices": len(AVAILABLE_VOICES),
        "worker_pool": worker_stats,
        "circuit_breakers": breaker_stats,
        "stats": stats,
        "error_stats": error_stats,
        "metrics": metrics_dict,
    }


# ==========================
# Routes
# ==========================
@app.get("/voices")
def list_voices():
    """
    List all available voices in the TTS service.
    Includes English (Piper) and Urdu (Rehnuma) voices.
    Returns current default voice as well.
    PHASE 1.3: Thread-safe default voice access
    """
    # All voices now in AVAILABLE_VOICES (both English and Urdu)
    all_voices = AVAILABLE_VOICES.copy() if AVAILABLE_VOICES else []
    
    # Count English and Urdu voices
    english_voices = [v for v in all_voices if "English" in v.get("name", "")]
    urdu_voices = [v for v in all_voices if "Urdu" in v.get("name", "")]
    
    return {
        "voices": all_voices,
        "default": SERVICE_CONFIG.default_voice,
        "count": len(all_voices),
        "english_count": len(english_voices),
        "urdu_count": len(urdu_voices),
    }


@app.post("/speak")
async def speak(req: SpeechRequest, request: Request):
    """
    Synthesize text to speech using specified voice.
    Returns audio as WAV file in response body.
    PHASE 1.4: Enhanced input validation
    PHASE 3.2: Error context logging
    PHASE 4.1: Prometheus metrics
    
    Args:
        text: Text to synthesize (1-5000 chars, non-empty)
        voice_id: Voice identifier (optional, uses default if not provided)
        language: Language hint ('en', 'urdu', 'english', 'ur', optional)
    """
    if not SERVICE_READY:
        raise HTTPException(status_code=503, detail="Service not ready")

    request_id = request.state.request_id
    start_time = time.time()
    
    # VALIDATION 1: Empty or whitespace-only text
    if not req.text or not req.text.strip():
        ERROR_LOGGER.log_validation_error(
            request_id=request_id,
            message="Text cannot be empty",
            voice_id=req.voice_id,
            text_length=len(req.text) if req.text else 0
        )
        record_validation_error(req.voice_id)
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    
    # VALIDATION 2: Text length
    if len(req.text) > MAX_TEXT_LENGTH:
        error_msg = f"Text too long ({len(req.text)} chars). Maximum: {MAX_TEXT_LENGTH}"
        ERROR_LOGGER.log_validation_error(
            request_id=request_id,
            message=error_msg,
            voice_id=req.voice_id,
            text_length=len(req.text)
        )
        record_validation_error(req.voice_id)
        raise HTTPException(status_code=400, detail=error_msg)
    
    # VALIDATION 3: Language parameter
    if req.language:
        normalized_language = req.language.lower()
        if normalized_language not in ["en", "english", "ur", "urdu"]:
            error_msg = f"Invalid language: {req.language}. Use 'en', 'english', 'ur', or 'urdu'"
            ERROR_LOGGER.log_validation_error(
                request_id=request_id,
                message=error_msg,
                voice_id=req.voice_id
            )
            record_validation_error(req.voice_id)
            raise HTTPException(status_code=400, detail=error_msg)
    
    # VALIDATION 4: Voice ID (will raise HTTPException if invalid)
    try:
        voice_id = resolve_voice(req.voice_id)
    except HTTPException as e:
        ERROR_LOGGER.log_validation_error(
            request_id=request_id,
            message=str(e.detail),
            voice_id=req.voice_id
        )
        record_validation_error(req.voice_id)
        raise
    
    LOGGER.info("[%s] Speak request validated: voice=%s, language_hint=%s, text_len=%d", 
                request_id, voice_id, req.language, len(req.text))

    try:
        # Submit task to parallel worker pool
        metrics_registry.set_active_requests(
            int(metrics_registry.active_requests._value.get()) + 1
        )
        
        wav_bytes = await WORKER_POOL.submit_task(
            text=req.text,
            voice_id=voice_id,
            request_id=request_id,
            language_hint=req.language,
            timeout=QUEUE_TIMEOUT_SECONDS + SYNTHESIS_TIMEOUT_SECONDS
        )
        
        # Calculate latency
        latency_seconds = time.time() - start_time
        
        # Record success metrics
        SERVICE_STATE.record_success()
        record_successful_synthesis(
            voice_id=voice_id,
            latency_seconds=latency_seconds,
            text_length=len(req.text),
            language_hint=req.language
        )
        
        LOGGER.info("[%s] Synthesis completed: %d bytes, latency=%.2fs", 
                   request_id, len(wav_bytes), latency_seconds)
        
        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={"X-Request-ID": request_id}
        )
    
    except asyncio.TimeoutError:
        latency_seconds = time.time() - start_time
        error_msg = "Request timeout while waiting for audio synthesis"
        LOGGER.error("[%s] %s (latency=%.2fs)", request_id, error_msg, latency_seconds)
        
        ERROR_LOGGER.log_timeout_error(
            request_id=request_id,
            timeout_seconds=QUEUE_TIMEOUT_SECONDS + SYNTHESIS_TIMEOUT_SECONDS,
            voice_id=voice_id,
            text_length=len(req.text)
        )
        
        SERVICE_STATE.record_failure(error_msg)
        record_timeout_error(voice_id)
        
        raise HTTPException(status_code=504, detail=error_msg)
    
    except Exception as e:
        latency_seconds = time.time() - start_time
        error_msg = f"Synthesis failed: {str(e)}"
        tb_str = traceback.format_exc()
        
        LOGGER.error("[%s] %s (latency=%.2fs)\n%s", 
                    request_id, error_msg, latency_seconds, tb_str)
        
        ERROR_LOGGER.log_synthesis_error(
            request_id=request_id,
            message=str(e),
            traceback=tb_str,
            voice_id=voice_id,
            text_length=len(req.text),
            response_time_ms=latency_seconds * 1000
        )
        
        SERVICE_STATE.record_failure(error_msg)
        record_synthesis_error(voice_id)
        
        raise HTTPException(status_code=500, detail=error_msg)
    
    finally:
        # Update active request count
        try:
            current = int(metrics_registry.active_requests._value.get())
            metrics_registry.set_active_requests(max(0, current - 1))
        except:
            pass



@app.post("/config/set_voice")
def set_voice(req: SpeechRequest):
    """
    Set the default voice for synthesis with intelligent speaker switching.
    
    OPTIMIZATION: Uses speaker manager to intelligently:
    - Load new speaker
    - Unload old default speaker (frees memory)
    - Keep other speakers in idle state (saves resources)
    
    Subsequent /speak requests will use this voice unless overridden.
    Thread-safe with atomic update to SERVICE_CONFIG.
    
    Args:
        voice_id: Voice to set as default (e.g., "jenny", "shahid")
    """
    if not req.voice_id:
        raise HTTPException(status_code=400, detail="voice_id is required")
    
    # Validate voice exists
    vid = resolve_voice(req.voice_id)
    
    try:
        # Use speaker manager for intelligent switching
        if SPEAKER_MANAGER:
            result = SPEAKER_MANAGER.switch_speaker(vid)
            
            # Also update SERVICE_CONFIG for compatibility
            if not SERVICE_CONFIG.set_default_voice_atomic(vid):
                raise HTTPException(status_code=400, detail=f"Failed to set default voice: {vid}")
            
            LOGGER.info("[Speaker Switch] %s", result)
            
            return {
                "status": "ok",
                "default_voice": vid,
                "voice_name": VOICE_INDEX[vid].definition.name,
                "speaker_operation": result,
            }
        else:
            # Fallback if speaker manager not initialized
            if not SERVICE_CONFIG.set_default_voice_atomic(vid):
                raise HTTPException(status_code=400, detail=f"Failed to set default voice: {vid}")
            
            LOGGER.info("Default voice set to: %s", vid)
            
            return {
                "status": "ok",
                "default_voice": vid,
                "voice_name": VOICE_INDEX[vid].definition.name,
            }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/cache/status")
def cache_status():
    """
    Get worker pool cache status.
    Shows per-worker cache stats, aggregated metrics.
    Useful for monitoring parallel worker cache behavior.
    """
    if not SERVICE_READY:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    pool_stats = WORKER_POOL.get_stats()
    
    # Aggregate cache stats across all workers
    all_english = set()
    all_urdu = set()
    total_hits = 0
    total_misses = 0
    
    for worker_cache in WORKER_POOL.worker_caches:
        voices = worker_cache.get_available_voices()
        all_english.update(voices.get("english", []))
        all_urdu.update(voices.get("urdu", []))
        
        stats = worker_cache.get_cache_stats()
        total_hits += stats.get("cache_hits", 0)
        total_misses += stats.get("cache_misses", 0)
    
    total_requests = total_hits + total_misses
    hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0
    
    return {
        "status": "ok",
        "worker_pool": {
            "num_workers": pool_stats["num_workers"],
            "tasks_processed": pool_stats["tasks_processed"],
            "tasks_failed": pool_stats["tasks_failed"],
            "queue_depths": pool_stats["queue_depths"],
        },
        "aggregated_cache": {
            "total_hits": total_hits,
            "total_misses": total_misses,
            "hit_rate_percent": round(hit_rate, 2),
            "total_requests": total_requests,
        },
        "per_worker_cache": pool_stats.get("worker_caches", []),
        "available_voices": {
            "english": sorted(list(all_english)),
            "urdu": sorted(list(all_urdu)),
            "total": len(all_english) + len(all_urdu),
        },
    }


# ==========================
# SPEAKER MANAGEMENT ENDPOINTS
# ==========================
@app.get("/speakers/status")
def get_speakers_status():
    """
    Get status of all speakers.
    Returns: Current loaded/idle state, default speaker, memory optimization info.
    
    OPTIMIZATION: Shows which speakers are loaded vs idle.
    - Jenny LOADED (default for fast response)
    - Shahid IDLE (available but not consuming memory)
    - Other speakers idle or unloaded
    """
    if not SERVICE_READY:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    if not SPEAKER_MANAGER:
        raise HTTPException(status_code=503, detail="Speaker manager not initialized")
    
    status = SPEAKER_MANAGER.get_all_speakers_status()
    
    return {
        "status": "ok",
        "speakers": status,
        "default_speaker": SPEAKER_MANAGER.get_current_default(),
        "summary": f"Loaded: {sum(1 for s in status.values() if s['is_loaded'])}, "
                   f"Idle: {sum(1 for s in status.values() if s['state'] == 'idle')}, "
                   f"Total: {len(status)}"
    }


@app.get("/speakers/state/{speaker_id}")
def get_speaker_state(speaker_id: str):
    """
    Get state of a specific speaker.
    
    Args:
        speaker_id: Speaker to query (e.g., "jenny", "shahid")
        
    Returns:
        Speaker state: loaded, idle, or unloaded
    """
    if not SERVICE_READY:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    if not SPEAKER_MANAGER:
        raise HTTPException(status_code=503, detail="Speaker manager not initialized")
    
    try:
        state = SPEAKER_MANAGER.get_speaker_state(speaker_id)
        is_loaded = SPEAKER_MANAGER.is_speaker_loaded(speaker_id)
        
        return {
            "status": "ok",
            "speaker_id": speaker_id,
            "state": state.value,
            "is_loaded": is_loaded,
            "is_default": SPEAKER_MANAGER.get_current_default() == speaker_id,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/speakers/switch")
def switch_speaker(req: SpeechRequest):
    """
    Switch to a different speaker.
    
    OPTIMIZATION: Intelligently manages speaker lifecycle:
    - Loads new speaker if not already loaded
    - Unloads old default speaker (freeing memory)
    - Sets new speaker as default
    - Keeps idle speakers idle (saves resources)
    
    Args:
        voice_id: Speaker to switch to
        
    Returns:
        Operation result with details of what was loaded/unloaded
    """
    if not SERVICE_READY:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    if not SPEAKER_MANAGER:
        raise HTTPException(status_code=503, detail="Speaker manager not initialized")
    
    if not req.voice_id:
        raise HTTPException(status_code=400, detail="voice_id is required")
    
    try:
        # Validate voice exists
        vid = resolve_voice(req.voice_id)
        
        # Perform intelligent switch
        result = SPEAKER_MANAGER.switch_speaker(vid)
        
        # Update SERVICE_CONFIG for compatibility
        SERVICE_CONFIG.set_default_voice_atomic(vid)
        
        LOGGER.info("[Speaker Switch] Successfully switched to: %s", vid)
        
        return {
            "status": "ok",
            "result": result,
            "current_default": SPEAKER_MANAGER.get_current_default(),
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/speakers/stats")
def get_speakers_stats():
    """
    Get speaker resource usage statistics.
    Returns: Memory optimization info, access counts, speaker states.
    
    MONITORING: Use this to track resource efficiency.
    - How many speakers loaded (vs idle)
    - Speaker usage counts
    - Memory optimization status
    """
    if not SERVICE_READY:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    if not SPEAKER_MANAGER:
        raise HTTPException(status_code=503, detail="Speaker manager not initialized")
    
    stats = SPEAKER_MANAGER.get_resource_stats()
    
    return {
        "status": "ok",
        "stats": stats,
        "timestamp": time.time(),
    }


# ==========================
# Error Handlers
# ==========================
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Enhanced error response with request ID."""
    return Response(
        content=str({
            "error": exc.detail,
            "code": exc.status_code,
            "request_id": getattr(request.state, "request_id", "unknown"),
        }),
        status_code=exc.status_code,
        media_type="application/json",
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors gracefully."""
    request_id = getattr(request.state, "request_id", "unknown")
    LOGGER.error("[%s] Unhandled exception: %s", request_id, str(exc), exc_info=True)
    SERVICE_STATE.record_failure(str(exc))
    
    return Response(
        content=str({
            "error": "Internal server error",
            "code": 500,
            "request_id": request_id,
        }),
        status_code=500,
        media_type="application/json",
    )


# ==========================
# PHASE 4.1: Metrics & Monitoring Endpoints
# ==========================
@app.get("/metrics")
def get_prometheus_metrics():
    """
    Get Prometheus format metrics.
    Use this endpoint with Prometheus scraper.
    PHASE 4.1: Prometheus metrics integration
    """
    if not SERVICE_READY:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    return Response(
        content=metrics_registry.get_metrics_text(),
        media_type="text/plain; charset=utf-8"
    )


@app.get("/metrics/json")
def get_metrics_json():
    """
    Get metrics in JSON format.
    PHASE 4.1: Structured metrics for dashboards and monitoring
    """
    if not SERVICE_READY:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    # Get current stats
    service_stats = SERVICE_STATE.get_stats()
    worker_stats = WORKER_POOL.get_stats() if WORKER_POOL else {}
    metrics_dict = metrics_registry.get_metrics_dict()
    
    return {
        "timestamp": time.time(),
        "service_stats": service_stats,
        "worker_pool_stats": worker_stats,
        "metrics": metrics_dict,
    }


# ==========================
# PHASE 3.2: Error Context & Diagnostics Endpoints
# ==========================
@app.get("/errors")
def get_error_summary():
    """
    Get error summary and statistics.
    PHASE 3.2: Error context logging and analysis
    """
    if not SERVICE_READY:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    error_stats = ERROR_LOGGER.get_error_stats()
    error_rate = ERROR_LOGGER.get_error_rate(window_seconds=60)
    
    return {
        "timestamp": time.time(),
        "error_stats": error_stats,
        "error_rate_per_minute": round(error_rate * 60, 2),
        "total_errors": len(ERROR_LOGGER.error_history),
        "max_history": ERROR_LOGGER.max_history,
    }


@app.get("/errors/recent")
def get_recent_errors(limit: int = 20):
    """
    Get recent error details.
    PHASE 3.2: Detailed error context for debugging
    
    Query parameters:
        limit: Maximum number of errors to return (default 20, max 100)
    """
    if not SERVICE_READY:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    limit = min(limit, 100)  # Cap at 100
    recent = ERROR_LOGGER.get_recent_errors(limit)
    
    return {
        "timestamp": time.time(),
        "count": len(recent),
        "errors": recent,
    }


@app.get("/errors/by_category/{category}")
def get_errors_by_category(category: str):
    """
    Get errors filtered by category.
    Compatible categories: validation, synthesis, timeout, resource, configuration, worker, unknown
    PHASE 3.2: Error categorization and analysis
    """
    if not SERVICE_READY:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    try:
        from .error_context import ErrorCategory
        error_cat = ErrorCategory[category.upper()]
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Valid: {', '.join([e.value for e in ErrorCategory])}"
        )
    
    errors = ERROR_LOGGER.get_errors_by_category(error_cat)
    
    return {
        "timestamp": time.time(),
        "category": category,
        "count": len(errors),
        "errors": errors,
    }


# ==========================
# Diagnostics Endpoint
# ==========================
@app.get("/diagnostics")
def get_full_diagnostics():
    """
    Complete diagnostics information.
    Includes service state, errors, metrics, and worker health.
    PHASE 3.2 + PHASE 4.1: Full observability
    """
    if not SERVICE_READY:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    service_stats = SERVICE_STATE.get_stats()
    error_stats = ERROR_LOGGER.get_error_stats()
    worker_stats = WORKER_POOL.get_stats() if WORKER_POOL else {}
    metrics_dict = metrics_registry.get_metrics_dict()
    
    # Calculate health score (0-100)
    health_score = 100
    if error_stats["total_errors"] > 100:
        health_score -= 10
    if error_stats["critical_errors"] > 5:
        health_score -= 20
    if service_stats["requests_failed"] > service_stats["requests_processed"] * 0.1:
        health_score -= 15
    if not all([v.is_available() for v in VOICE_INDEX.values()]):
        health_score -= 20
    
    health_score = max(0, health_score)
    
    return {
        "timestamp": time.time(),
        "service": {
            "name": Config.SERVICE_NAME,
            "version": Config.SERVICE_VERSION,
            "uptime_seconds": service_stats["uptime_seconds"],
            "health_score": health_score,
        },
        "requests": {
            "processed": service_stats["requests_processed"],
            "failed": service_stats["requests_failed"],
            "success_rate": (
                (service_stats["requests_processed"] - service_stats["requests_failed"]) /
                service_stats["requests_processed"] * 100
                if service_stats["requests_processed"] > 0 else 0
            ),
        },
        "errors": error_stats,
        "voices": {
            "available": len(AVAILABLE_VOICES),
            "voice_ids": [v["id"] for v in AVAILABLE_VOICES],
        },
        "worker_pool": worker_stats,
        "metrics_snapshot": metrics_dict,
    }
