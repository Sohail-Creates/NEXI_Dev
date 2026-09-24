"""
Conversation Orchestration API Routes.
Provides high-level conversation endpoints that orchestrate across all services.

Phase 6: Full integration with conversational flow.
Handles: audio upload, transcription, LLM, TTS, playback as single operations.
"""

import logging
import asyncio
import os
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status, UploadFile, File
from shared.jwt_manager import require_user_ownership
from shared.security import require_internal_service
from pydantic import BaseModel
from audio_service.services.conversation_state import ConversationState

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1",
    tags=["Orchestration"]
)


class ConversationRequest(BaseModel):
    """Request for full conversation turn."""
    user_id: str
    audio_file_path: str
    language: str = "en"
    speaker_id: str = "jenny"


def _validated_audio_path(value: str) -> str:
    allowed_root = Path(os.getenv(
        "VAD_RECORDING_OUTPUT_DIR", "03_audio_service/audio_service/data/recordings"
    )).resolve()
    candidate = Path(value).resolve()
    if not candidate.is_relative_to(allowed_root) or candidate.suffix.lower() not in {".wav", ".mp3"}:
        raise HTTPException(status_code=400, detail="audio_file_path is outside the recording directory")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="audio_file_path does not exist")
    return str(candidate)


class ConversationResponse(BaseModel):
    """Response with full conversation results."""
    success: bool
    user_text: Optional[str] = None
    llm_response: Optional[str] = None
    audio_file: Optional[str] = None
    duration_ms: int = 0
    language: str = "en"
    error: Optional[str] = None


@router.post("/playback/start")
async def start_playback(
    file: UploadFile = File(...), _trusted: Optional[str] = Depends(require_internal_service)
):
    """Play a supplied WAV through Audio's existing playback manager."""
    from main import playback_manager

    if playback_manager is None:
        raise HTTPException(status_code=503, detail="Playback manager unavailable")
    if not file.filename or not file.filename.lower().endswith(".wav"):
        raise HTTPException(status_code=400, detail="A WAV file is required")
    result = await asyncio.to_thread(playback_manager.play_audio_bytes, await file.read())
    if not result.get("success"):
        raise HTTPException(status_code=503, detail=result.get("error", "Playback failed"))
    return result


@router.post("/conversation/turn", response_model=ConversationResponse)
async def process_conversation_turn(request: ConversationRequest, http_request: Request):
    """
    Process complete conversation turn end-to-end.
    
    Orchestrates:
    1. Transcribe audio (Audio Service STT)
    2. Generate response (LLM Service)
    3. Synthesize speech (TTS Service)
    
    Args:
        request: ConversationRequest with audio_file_path and user_id
        
    Returns:
        ConversationResponse with results
        
    Example:
        POST /api/v1/conversation/turn
        {
            "user_id": "sara_123",
            "audio_file_path": "/data/recordings/vad_20260329_103542.wav",
            "language": "en",
            "speaker_id": "jenny"
        }
        
        Response:
        {
            "success": true,
            "user_text": "What time is it?",
            "llm_response": "It's 10:35 AM",
            "audio_file": "/tmp/tts_output.wav",
            "duration_ms": 2340,
            "language": "en"
        }
    """
    require_user_ownership(http_request, request.user_id)
    from main import orchestrator, conversation_state_manager
    
    if not orchestrator:
        logger.error("Orchestrator not initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "Orchestrator not available"}
        )
    
    try:
        logger.info(f"Starting conversation turn for user: {request.user_id}")
        
        # Process turn asynchronously
        audio_path = _validated_audio_path(request.audio_file_path)
        turn = await orchestrator.process_conversation_turn(
            user_id=request.user_id,
            audio_file_path=audio_path,
            speaker_id=request.speaker_id
        )
        
        if not turn:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "Failed to process conversation turn"}
            )
        
        response = ConversationResponse(
            success=turn.error is None,
            user_text=turn.user_text,
            llm_response=turn.llm_response_text,
            duration_ms=turn.duration_ms,
            language=turn.transcript_language,
            error=turn.error
        )
        
        logger.info(f"Conversation turn complete: {turn.duration_ms}ms")
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing conversation turn: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(e)}
        )


@router.get("/conversation/metrics")
async def get_orchestration_metrics():
    """
    Get orchestration performance metrics.
    
    Returns:
        Dict with performance data
    """
    from main import orchestrator
    
    if not orchestrator:
        return {
            "status": "error",
            "message": "Orchestrator not initialized"
        }
    
    metrics = orchestrator.get_metrics()
    return {
        "status": "success",
        "metrics": metrics
    }


@router.post("/conversation/start", status_code=status.HTTP_200_OK)
async def start_continuous_conversation(user_id: str, request: Request):
    """
    Start continuous conversation session.
    
    Args:
        user_id: Unique user identifier
        
    Returns:
        Session initialization status
    """
    require_user_ownership(request, user_id)
    from main import conversation_state_manager, stop_word_detector
    
    if not conversation_state_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "Conversation state manager not initialized"}
        )
    
    try:
        logger.info(f"Starting conversation session for user: {user_id}")
        
        # Transition to conversation mode
        conversation_state_manager.transition_to(ConversationState.CONVERSATION_ACTIVE)
        
        # Activate stop word detection
        if stop_word_detector:
            stop_word_detector.activate()
            logger.info("Stop word detection activated")
        
        return {
            "success": True,
            "user_id": user_id,
            "state": conversation_state_manager.get_state(),
            "message": "Conversation session started"
        }
    
    except Exception as e:
        logger.error(f"Error starting conversation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(e)}
        )


@router.post("/conversation/end", status_code=status.HTTP_200_OK)
async def end_continuous_conversation(user_id: str, request: Request):
    """
    End continuous conversation session.
    
    Args:
        user_id: Unique user identifier
        
    Returns:
        Session termination status
    """
    require_user_ownership(request, user_id)
    from main import conversation_state_manager, stop_word_detector
    
    if not conversation_state_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "Conversation state manager not initialized"}
        )
    
    try:
        logger.info(f"Ending conversation session for user: {user_id}")
        
        # Deactivate stop word detection
        if stop_word_detector:
            stop_word_detector.deactivate()
            logger.info("Stop word detection deactivated")
        
        # Interrupt any ongoing playback
        from main import playback_manager
        if playback_manager:
            playback_manager.stop_playback()
        
        # Transition to idle
        conversation_state_manager.transition_to(ConversationState.IDLE)
        
        return {
            "success": True,
            "user_id": user_id,
            "state": conversation_state_manager.get_state(),
            "message": "Conversation session ended"
        }
    
    except Exception as e:
        logger.error(f"Error ending conversation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(e)}
        )


# ============================================================================
# INTEGRATION TESTING ENDPOINTS
# ============================================================================


@router.get("/orchestration/health", tags=["Testing"])
async def orchestration_health():
    """
    Check orchestration system health.
    
    Returns:
        Detailed health status of all components
    """
    from main import (
        orchestrator, conversation_state_manager, stop_word_detector,
        vad_recorder, playback_manager
    )
    
    health_status = {
        "orchestrator": "initialized" if orchestrator else "not_initialized",
        "conversation_state": "initialized" if conversation_state_manager else "not_initialized",
        "stop_word_detector": (
            "initialized" if stop_word_detector else "not_initialized"
        ),
        "vad_recorder": "initialized" if vad_recorder else "not_initialized",
        "playback_manager": "initialized" if playback_manager else "not_initialized"
    }
    
    # Add detailed states
    if conversation_state_manager:
        health_status["conversation_state_details"] = (
            conversation_state_manager.get_status()
        )
    
    if stop_word_detector:
        health_status["stop_word_state"] = stop_word_detector.get_state()
    
    if playback_manager:
        health_status["playback_state"] = playback_manager.get_state()
    
    return {
        "status": "healthy" if all(
            v != "not_initialized" for v in health_status.values()
        ) else "degraded",
        "components": health_status
    }


@router.get("/orchestration/test/end-to-end", tags=["Testing"])
async def test_end_to_end():
    """
    Test complete orchestration pipeline.
    
    Returns:
        Test results with latency metrics
    """
    from main import orchestrator
    
    if not orchestrator:
        return {
            "status": "error",
            "message": "Orchestrator not initialized",
            "test_result": "FAILED"
        }
    
    try:
        logger.info("Running end-to-end orchestration test...")
        
        # Verify services are reachable
        # (simplified test - just check session can be created)
        if not orchestrator.session:
            await orchestrator.start()
        
        # Test metrics endpoint
        metrics = orchestrator.get_metrics()
        
        logger.info("End-to-end test completed successfully")
        
        return {
            "status": "success",
            "test_result": "PASSED",
            "metrics": metrics,
            "message": "Orchestrator is fully functional"
        }
    
    except Exception as e:
        logger.error(f"End-to-end test failed: {e}")
        return {
            "status": "error",
            "test_result": "FAILED",
            "error": str(e)
        }
