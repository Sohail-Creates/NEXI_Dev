"""
Main FastAPI application for Audio Service.
This module initializes the FastAPI app and includes all routes.
"""

import logging
import uvicorn
import sys
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from audio_service.config import (
    API_CONFIG,
    LOG_FORMAT,
    LOG_LEVEL,
    QUEUE_CONFIG,
    BACKEND_CONFIG,
    PIPELINE_CONFIG
)
from audio_service.routes import audio_routes
from audio_service.routes import advanced_routes
from audio_service.routes import conversation_routes
from audio_service.routes import orchestration_routes

# Import Phase 1 security: Rate limiting
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))
from shared.rate_limiter import create_rate_limit_middleware

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT
)
logger = logging.getLogger(__name__)

# Global instances
queue_processor = None
stop_word_detector = None
conversation_state_manager = None
vad_recorder = None
playback_manager = None
orchestrator = None


def _on_stop_word_detected():
    """
    Callback when stop word is detected.
    Transitions conversation state and interrupts playback.
    """
    logger.info("● STOP WORD DETECTED")
    
    if conversation_state_manager:
        try:
            conversation_state_manager.transition_to(ConversationState.EXITING)
            logger.info("Conversation state: EXITING")
        except Exception as e:
            logger.error(f"Error updating conversation state: {e}")
    
    if playback_manager:
        try:
            playback_manager.activate_interrupt()
            logger.info("Playback interrupted")
        except Exception as e:
            logger.error(f"Error interrupting playback: {e}")


def _on_playback_interrupted(interrupt_info: dict):
    """
    Callback when playback is interrupted.
    
    Args:
        interrupt_info: Dict with interrupt details (timestamp, position, etc.)
    """
    logger.info(f"Playback interrupted at {interrupt_info.get('playback_position')}/{interrupt_info.get('total_frames')} frames")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager for startup and shutdown events.
    
    Initializes queue processor and continuous conversation components on startup
    and gracefully shuts them down.
    """
    global queue_processor, stop_word_detector, conversation_state_manager, vad_recorder, playback_manager, orchestrator
    
    # Startup
    logger.info("Starting Audio Service with integrated pipeline features...")
    
    try:
        # Initialize queue processor
        from audio_service.services.queue_service import QueueService
        from audio_service.services.backend_service import BackendService
        from audio_service.services.queue_processor import QueueProcessor
        
        logger.info("Initializing queue processor...")
        
        queue_service = QueueService(
            db_path=QUEUE_CONFIG["db_path"],
            max_retry_count=QUEUE_CONFIG["max_retry_count"],
            max_queue_size=QUEUE_CONFIG["max_queue_size"]
        )
        
        backend_service = BackendService(
            base_url=BACKEND_CONFIG["base_url"],
            api_key=BACKEND_CONFIG.get("api_key"),
            timeout=BACKEND_CONFIG["timeout"],
            max_retries=BACKEND_CONFIG["max_retries"],
            verify_ssl=BACKEND_CONFIG["verify_ssl"],
            circuit_breaker_config=BACKEND_CONFIG.get("circuit_breaker")
        )
        
        queue_processor = QueueProcessor(
            queue_service=queue_service,
            backend_service=backend_service,
            poll_interval=PIPELINE_CONFIG["queue_poll_interval"],
            batch_size=PIPELINE_CONFIG["queue_batch_size"]
        )
        
        # Start queue processor
        queue_processor.start()
        logger.info("Queue processor started successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize queue processor: {e}", exc_info=True)
        logger.warning("Service will continue without queue processor")
    
    # Initialize continuous conversation components
    try:
        from audio_service.services.stop_word_detector import StopWordDetector
        from audio_service.services.conversation_state import ConversationStateManager
        from audio_service.services.vad_recorder import VADRecorder
        from audio_service.services.playback_manager import PlaybackManager
        from audio_service.config import (
            STOP_WORD_CONFIG,
            VAD_RECORDER_CONFIG,
            CONVERSATION_CONFIG
        )
        
        logger.info("Initializing continuous conversation components...")
        
        # Initialize conversation state manager (first, needed by others)
        conversation_state_manager = ConversationStateManager(
            timeout_seconds=CONVERSATION_CONFIG["timeout_seconds"]
        )
        logger.info(f"✓ ConversationStateManager initialized (timeout={CONVERSATION_CONFIG['timeout_seconds']}s)")
        
        # Initialize stop word detector with version check
        if STOP_WORD_CONFIG.get("enabled", True) and STOP_WORD_CONFIG.get("model_path"):
            try:
                # Check Porcupine version before initializing
                # Use importlib.metadata (works with both v3 and v4)
                try:
                    from importlib.metadata import version
                    porcupine_version_str = version('pvporcupine')
                    porcupine_version = tuple(map(int, porcupine_version_str.split(".")[:2]))
                except Exception:
                    # Fallback: try __version__ attribute (v3 only)
                    import pvporcupine
                    if hasattr(pvporcupine, '__version__'):
                        porcupine_version = tuple(map(int, pvporcupine.__version__.split(".")[:2]))
                    else:
                        # If no version found, assume v4.0+ (current/recent)
                        porcupine_version = (4, 0)
                
                model_version = (4, 0)  # stop-nec-e_en_windows_v4_0_0.ppn is v4
                
                if porcupine_version < model_version:
                    logger.warning(
                        f"Stop Word Detector: Skipping initialization due to version mismatch. "
                        f"Model requires Porcupine v{model_version[0]}.x but v{porcupine_version[0]}.{porcupine_version[1]} is installed. "
                        f"To enable stop word detection, upgrade: pip install 'pvporcupine>=4.0.0'"
                    )
                    stop_word_detector = None
                else:
                    stop_word_detector = StopWordDetector(
                        model_path=STOP_WORD_CONFIG["model_path"],
                        access_key=STOP_WORD_CONFIG["access_key"],
                        sensitivity=STOP_WORD_CONFIG["sensitivity"],
                        callback=lambda: _on_stop_word_detected()
                    )
                    stop_word_detector.start()
                    logger.info("✓ StopWordDetector initialized and started")
            
            except FileNotFoundError:
                logger.warning("Stop word model not found - feature disabled")
                stop_word_detector = None
            except Exception as e:
                logger.warning(f"Stop word detection failed (non-critical): {e}")
                logger.info("Continuing with audio service (stop word detection unavailable)")
                stop_word_detector = None
        else:
            logger.info("Stop word detection disabled or model path not found")
            stop_word_detector = None
        
        # Initialize VAD recorder
        vad_recorder = VADRecorder(
            sample_rate=VAD_RECORDER_CONFIG["sample_rate"],
            chunk_size=VAD_RECORDER_CONFIG["chunk_size"],
            silence_threshold_ms=VAD_RECORDER_CONFIG["silence_threshold_ms"],
            max_duration_seconds=VAD_RECORDER_CONFIG["max_recording_seconds"]
        )
        logger.info("✓ VADRecorder initialized")
        
        # Initialize playback manager
        playback_manager = PlaybackManager(
            sample_rate=22050  # Match TTS service output
        )
        playback_manager.set_interrupt_callback(lambda info: _on_playback_interrupted(info))
        logger.info("✓ PlaybackManager initialized")
        
        logger.info("✓ All continuous conversation components initialized")
        
    except Exception as e:
        logger.error(f"Failed to initialize conversation components: {e}", exc_info=True)
        logger.warning("Service will continue with limited continuous conversation features")
    
    # Initialize conversation orchestrator (Phase 5)
    try:
        from audio_service.services.conversation_orchestrator import ConversationOrchestrator
        
        logger.info("Initializing conversation orchestrator...")
        
        orchestrator = ConversationOrchestrator(
            conversation_state_manager=conversation_state_manager,
            audio_service_url="http://localhost:8002",
            vision_service_url="http://localhost:8001",
            teachme_service_url="http://localhost:8005",
            llm_service_url="http://localhost:8006",
            tts_service_url="http://localhost:8003"
        )
        
        # Start orchestrator session pool
        await orchestrator.start()
        logger.info("✓ ConversationOrchestrator initialized and ready")
        
    except Exception as e:
        logger.error(f"Failed to initialize orchestrator: {e}", exc_info=True)
        logger.warning("Service will continue without orchestrator (client-driven only)")
    
    logger.info("Audio Service startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Audio Service...")
    
    # Shutdown orchestrator
    if orchestrator:
        try:
            logger.info("Stopping orchestrator...")
            await orchestrator.stop()
            logger.info("Orchestrator stopped")
        except Exception as e:
            logger.error(f"Error stopping orchestrator: {e}")
    
    # Shutdown stop word detector
    if stop_word_detector:
        try:
            logger.info("Stopping stop word detector...")
            stop_word_detector.stop()
            logger.info("Stop word detector stopped")
        except Exception as e:
            logger.error(f"Error stopping stop word detector: {e}")
    
    # Shutdown playback manager
    if playback_manager:
        try:
            logger.info("Stopping playback manager...")
            playback_manager.stop_playback()
            logger.info("Playback manager stopped")
        except Exception as e:
            logger.error(f"Error stopping playback manager: {e}")
    
    # Shutdown queue processor
    if queue_processor:
        try:
            logger.info("Stopping queue processor...")
            queue_processor.stop(timeout=10.0)
            logger.info("Queue processor stopped")
        except Exception as e:
            logger.error(f"Error stopping queue processor: {e}")
    
    logger.info("Audio Service shutdown complete")


# Initialize FastAPI application with lifespan
app = FastAPI(
    title=API_CONFIG["title"],
    description=API_CONFIG["description"],
    version=API_CONFIG["version"],
    lifespan=lifespan
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

# Include routers
# Week 1: Basic audio recording functionality
app.include_router(audio_routes.router)
# Week 2: Audio intelligence features (wake word, speaker verification, STT)
app.include_router(advanced_routes.router)
# Phase 3: Continuous conversation with stop word detection and VAD recording
app.include_router(conversation_routes.router)
# Phase 5-9: Full orchestration with service integration
app.include_router(orchestration_routes.router)


@app.get("/", tags=["Health"])
async def root():
    """
    Root endpoint for health check.
    
    Returns:
        dict: Status message indicating the API is operational
    """
    logger.info("Health check endpoint accessed")
    return {
        "status": "success",
        "message": "Audio Service API is running",
        "version": API_CONFIG["version"]
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint to verify service availability.
    
    Returns:
        dict: Health status of the service
    """
    logger.info("Health check endpoint accessed")
    
    health_status = {
        "status": "healthy",
        "service": "audio-service",
        "version": API_CONFIG["version"]
    }
    
    # Add queue processor status if available (lightweight check only)
    if queue_processor:
        try:
            health_status["queue_processor"] = {
                "running": queue_processor._running
            }
        except Exception as e:
            logger.warning(f"Failed to get queue processor status: {e}")
    
    return health_status


@app.get("/queue/status", tags=["Queue Management"])
async def get_queue_status():
    """
    Get current queue processor status.
    
    Returns:
        dict: Queue processor status and statistics
    """
    if not queue_processor:
        return {
            "status": "disabled",
            "message": "Queue processor not initialized"
        }
    
    try:
        status = queue_processor.get_status()
        return {
            "status": "success",
            **status
        }
    except Exception as e:
        logger.error(f"Failed to get queue status: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@app.post("/queue/add", tags=["Queue Management"])
async def add_to_queue(request: dict):
    """
    Manually add a command to the offline queue.
    
    Args:
        request: Command data with 'text', 'user_id', and optional 'metadata'
    
    Returns:
        dict: Queue operation result with queue_id
    """
    if not queue_processor or not queue_processor.queue_service:
        return {
            "status": "error",
            "message": "Queue service not initialized"
        }
    
    try:
        text = request.get("text")
        user_id = request.get("user_id", "unknown")
        metadata = request.get("metadata", {})
        
        if not text:
            return {
                "status": "error",
                "message": "Missing 'text' field in request"
            }
        
        # Enqueue the command
        command_data = {
            "text": text,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            **metadata
        }
        
        queue_id = queue_processor.queue_service.enqueue_command(
            command_type="voice_command",
            command_data=command_data
        )
        
        logger.info(f"Command added to queue: {queue_id}")
        
        return {
            "success": True,
            "queue_id": queue_id,
            "message": "Command added to queue successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to add command to queue: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@app.post("/queue/process-now", tags=["Queue Management"])
async def trigger_queue_processing():
    """
    Manually trigger queue processing.
    
    Returns:
        dict: Number of commands processed
    """
    if not queue_processor:
        return {
            "status": "error",
            "message": "Queue processor not initialized"
        }
    
    try:
        processed = queue_processor.process_now()
        return {
            "status": "success",
            "processed_count": processed,
            "message": f"Processed {processed} queued commands"
        }
    except Exception as e:
        logger.error(f"Failed to trigger queue processing: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=API_CONFIG["host"],
        port=API_CONFIG["port"],
        reload=False,
        log_level=LOG_LEVEL.lower()
    )
