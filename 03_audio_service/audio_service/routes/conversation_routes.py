"""
Continuous Conversation API Routes.
Handles stop word detection, VAD recording, and conversation state management endpoints.
"""

import logging
import asyncio
from typing import Optional
from fastapi import APIRouter, HTTPException, status, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from audio_service.services.conversation_state import ConversationState

logger = logging.getLogger(__name__)

# Get wake word service for coordination with stop word detection
def get_wake_word_service():
    """Get wake word service instance from advanced routes."""
    try:
        from audio_service.routes.advanced_routes import wake_word_service
        return wake_word_service
    except Exception as e:
        logger.warning(f"Could not import wake word service: {e}")
        return None

router = APIRouter(
    prefix="/api/v1",
    tags=["Continuous Conversation"]
)


class DetectionModeRequest(BaseModel):
    """Request model for setting detection mode."""
    mode: str = "idle"  # "idle" or "conversation"


class RecordUntilSilenceResponse(BaseModel):
    """Response model for VAD recording."""
    success: bool
    audio_file: Optional[str] = None
    duration: float
    stopped_by: str  # "silence", "max_duration", or "error"
    chunks_recorded: int
    error: Optional[str] = None


class ConversationStateResponse(BaseModel):
    """Response model for conversation state."""
    state: str
    duration_seconds: float
    elapsed_time_seconds: float
    timeout_seconds: float
    timed_out: bool


@router.post("/set-detection-mode", status_code=status.HTTP_200_OK)
async def set_detection_mode(request: DetectionModeRequest):
    """
    Set detection mode: 'idle' (wake word only) or 'conversation' (stop word only).
    
    This endpoint coordinates both wake word and stop word detectors to ensure
    only one is active at a time, avoiding audio stream conflicts.
    
    Args:
        request: DetectionModeRequest with mode field ("idle" or "conversation")
        
    Returns:
        dict: Status confirming mode change and detector states
    """
    from main import stop_word_detector, conversation_state_manager
    
    mode = request.mode.lower()
    
    if mode not in ["idle", "conversation"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Mode must be 'idle' or 'conversation'"}
        )
    
    logger.info(f"Setting detection mode: {mode}")
    
    try:
        if mode == "conversation":
            # STEP 1: Stop wake word detection (release audio for stop word)
            wake_word_service = get_wake_word_service()
            if wake_word_service:
                try:
                    wake_word_service.stop()
                    logger.info("Wake word detection stopped for conversation mode")
                except Exception as e:
                    logger.warning(f"Failed to stop wake word service: {e}")
            else:
                logger.debug("Wake word service not available")
            
            # STEP 2: Start stop word detection
            if stop_word_detector:
                try:
                    stop_word_detector.activate()
                    logger.info("Stop word detection activated")
                except Exception as e:
                    logger.error(f"Failed to activate stop word detector: {e}")
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail={"error": "Stop word detector not available"}
                    )
            else:
                logger.warning("Stop word detector not available")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={"error": "Stop word detector not initialized"}
                )
            
            # STEP 3: Transition conversation state
            if conversation_state_manager:
                conversation_state_manager.transition_to(ConversationState.CONVERSATION_ACTIVE)
                logger.info("Conversation state: ACTIVE")
            
            return {
                "success": True,
                "mode": "conversation",
                "wake_word_active": False,
                "stop_word_active": True,
                "conversation_state": "CONVERSATION_ACTIVE",
                "message": "Switched to conversation mode"
            }
        
        else:  # idle mode
            # STEP 1: Stop stop word detection
            if stop_word_detector:
                try:
                    stop_word_detector.deactivate()
                    logger.info("Stop word detection deactivated")
                except Exception as e:
                    logger.warning(f"Failed to deactivate stop word detector: {e}")
            
            # STEP 2: Start wake word detection
            wake_word_service = get_wake_word_service()
            if wake_word_service:
                try:
                    wake_word_service.start()
                    logger.info("Wake word detection started for idle mode")
                except Exception as e:
                    logger.error(f"Failed to start wake word service: {e}")
            else:
                logger.debug("Wake word service not available")
            
            # STEP 3: Transition conversation state
            if conversation_state_manager:
                conversation_state_manager.transition_to(ConversationState.IDLE)
                logger.info("Conversation state: IDLE")
            
            return {
                "success": True,
                "mode": "idle",
                "wake_word_active": True,
                "stop_word_active": False,
                "conversation_state": "IDLE",
                "message": "Switched to idle mode"
            }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting detection mode: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(e)}
        )


@router.post("/record-until-silence", response_model=RecordUntilSilenceResponse)
async def record_until_silence():
    """
    Record audio until silence is detected using VAD.
    
    Returns:
        RecordUntilSilenceResponse: Recording results
    """
    from main import vad_recorder, conversation_state_manager
    
    if not vad_recorder:
        logger.error("VAD recorder not initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "VAD recorder not initialized"}
        )
    
    logger.info("VAD recording requested")
    
    try:
        # Update conversation state (only if not already processing)
        if conversation_state_manager:
            current = conversation_state_manager.get_state()
            if current != ConversationState.PROCESSING_QUERY:
                conversation_state_manager.transition_to(ConversationState.PROCESSING_QUERY)
        
        # Record until silence
        result = vad_recorder.record_until_silence()
        
        logger.info(f"Recording complete: {result['duration']:.2f}s, stopped by: {result['stopped_by']}")
        
        return RecordUntilSilenceResponse(
            success=result.get("success", False),
            audio_file=result.get("audio_file"),
            duration=result.get("duration", 0),
            stopped_by=result.get("stopped_by", "error"),
            chunks_recorded=result.get("chunks_recorded", 0),
            error=result.get("error")
        )
    
    except Exception as e:
        logger.error(f"Error during VAD recording: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(e)}
        )


@router.post("/interrupt-playback", status_code=status.HTTP_200_OK)
async def interrupt_playback():
    """
    Interrupt current audio playback (stop TTS).
    
    Returns:
        dict: Status of interruption
    """
    from main import playback_manager
    
    if not playback_manager:
        logger.warning("Playback manager not initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "Playback manager not initialized"}
        )
    
    logger.info("Playback interruption requested")
    
    try:
        playback_manager.activate_interrupt()
        
        state = playback_manager.get_state()
        
        return {
            "success": True,
            "message": "Playback interrupted",
            "state": state.get("state")
        }
    
    except Exception as e:
        logger.error(f"Error interrupting playback: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(e)}
        )


@router.get("/conversation-state", response_model=ConversationStateResponse)
async def get_conversation_state():
    """
    Get current conversation state and timeout status.
    
    Returns:
        ConversationStateResponse: Current state details
    """
    from main import conversation_state_manager
    
    if not conversation_state_manager:
        logger.warning("Conversation state manager not initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "Conversation state manager not initialized"}
        )
    
    try:
        status_dict = conversation_state_manager.get_status()
        
        return ConversationStateResponse(
            state=status_dict.get("current_state", "unknown"),
            duration_seconds=status_dict.get("conversation_duration_s", 0),
            elapsed_time_seconds=status_dict.get("elapsed_since_speech_s", 0),
            timeout_seconds=conversation_state_manager.timeout_seconds,
            timed_out=status_dict.get("timeout_exceeded", False)
        )
    
    except Exception as e:
        logger.error(f"Error getting conversation state: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(e)}
        )


@router.get("/poll-stop-word", status_code=status.HTTP_200_OK)
async def poll_stop_word(timeout: float = Query(1.0, ge=0.1, le=60.0)):
    """
    Poll for stop word detection events.
    
    Waits for detection event from stop word detector's async queue with timeout.
    Will be called repeatedly by Central Server to receive detection notifications.
    
    Args:
        timeout: Seconds to wait for event (0.1 to 60.0 seconds)
        
    Returns:
        {
            "event_detected": bool,
            "event": dict with detection details (timestamp, keyword, etc) or null,
            "queue_size": int (number of remaining events in queue)
        }
    """
    from main import stop_word_detector
    
    if not stop_word_detector:
        logger.warning("Stop word detector not initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "Stop word detector not initialized"}
        )
    
    logger.debug(f"Stop word polling started (timeout={timeout}s)")
    
    try:
        # Wait for detection event from detector's async queue
        event = await stop_word_detector.get_next_event(timeout=timeout)
        
        if event:
            logger.info(f"Stop word event polled successfully: {event['keyword']}")
            return {
                "event_detected": True,
                "event": event,
                "queue_size": stop_word_detector.get_event_count()
            }
        else:
            # Timeout occurred - no event received
            logger.debug("Stop word polling timeout - no event detected")
            return {
                "event_detected": False,
                "event": None,
                "queue_size": 0
            }
    
    except Exception as e:
        logger.error(f"Error polling stop word: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(e)}
        )


@router.get("/stop-word-events/status", status_code=status.HTTP_200_OK)
async def get_stop_word_events_status():
    """
    Get stop word event queue status without consuming events.
    
    Use this to check if events are pending before calling poll-stop-word.
    Useful for UI status indicators or conditional polling logic.
    
    Returns:
        {
            "has_pending_events": bool,
            "pending_count": int,
            "detector_active": bool,
            "detector_running": bool
        }
    """
    from main import stop_word_detector
    
    if not stop_word_detector:
        logger.warning("Stop word detector not initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "Stop word detector not initialized"}
        )
    
    try:
        return {
            "has_pending_events": stop_word_detector.has_pending_events(),
            "pending_count": stop_word_detector.get_event_count(),
            "detector_active": stop_word_detector.is_active,
            "detector_running": stop_word_detector.is_running
        }
    
    except Exception as e:
        logger.error(f"Error getting stop word events status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(e)}
        )


# Test and debugging endpoints

@router.get("/test/stop-word-status", tags=["Testing"])
async def test_stop_word_status():
    """
    Test endpoint to check stop word detector status.
    
    Returns:
        dict: Stop word detector status
    """
    from main import stop_word_detector
    
    if not stop_word_detector:
        return {
            "status": "not_initialized",
            "message": "Stop word detector not initialized"
        }
    
    try:
        state = stop_word_detector.get_state()
        return {
            "status": "ok",
            "detector_state": state
        }
    except Exception as e:
        logger.error(f"Error getting stop word status: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@router.get("/test/conversation-status", tags=["Testing"])
async def test_conversation_status():
    """
    Test endpoint to check conversation state manager status.
    
    Returns:
        dict: Conversation state details
    """
    from main import conversation_state_manager
    
    if not conversation_state_manager:
        return {
            "status": "not_initialized",
            "message": "Conversation state manager not initialized"
        }
    
    try:
        status_dict = conversation_state_manager.get_status()
        return {
            "status": "ok",
            "conversation_state": status_dict
        }
    except Exception as e:
        logger.error(f"Error getting conversation status: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@router.get("/test/playback-status", tags=["Testing"])
async def test_playback_status():
    """
    Test endpoint to check playback manager status.
    
    Returns:
        dict: Playback state details
    """
    from main import playback_manager
    
    if not playback_manager:
        return {
            "status": "not_initialized",
            "message": "Playback manager not initialized"
        }
    
    try:
        state = playback_manager.get_state()
        return {
            "status": "ok",
            "playback_state": state
        }
    except Exception as e:
        logger.error(f"Error getting playback status: {e}")
        return {
            "status": "error",
            "error": str(e)
        }
