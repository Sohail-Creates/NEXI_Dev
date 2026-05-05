"""LLM integration routes for Central Server."""

import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm", tags=["llm"])


# Request/Response Models
class UserContextModel(BaseModel):
    """User context for LLM."""
    name: Optional[str] = None
    age: Optional[int] = None
    interests: Optional[List[str]] = []


class GenerateRequestModel(BaseModel):
    """Request to generate LLM response."""
    query: str = Field(..., description="User query", min_length=1, max_length=2000)
    user_id: str = Field(..., description="User identifier")
    language: Optional[str] = Field("en", description="Language: 'en' or 'ur'")
    include_vision: bool = Field(True, description="Include visual context")
    include_knowledge: bool = Field(True, description="Include knowledge context")


class GenerateResponseModel(BaseModel):
    """Response from LLM generation."""
    success: bool
    data: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[Dict[str, Any]] = None


def create_llm_routes(llm_client, context_builder, user_storage) -> APIRouter:
    """
    Create LLM integration routes.
    
    Args:
        llm_client: LLM service client
        context_builder: Context builder service
        user_storage: User storage/persistence
    
    Returns:
        Configured APIRouter
    """
    
    @router.post("/generate-response", response_model=GenerateResponseModel)
    async def generate_response(
        request: GenerateRequestModel,
        background_tasks: BackgroundTasks,
    ) -> GenerateResponseModel:
        """
        Generate AI response with full context from NEXI services.
        
        This endpoint orchestrates:
        1. Context gathering (user profile, vision, knowledge, history)
        2. LLM inference
        3. Response storage in conversation history
        """
        try:
            # Validate user exists
            user = user_storage.get_user(request.user_id)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            logger.info(f"Generating response for user {request.user_id}: {request.query[:50]}...")
            
            # Build context from all services
            logger.debug("Building context from NEXI services...")
            context = await context_builder.build_context(
                user_id=request.user_id,
                query=request.query,
                include_vision=request.include_vision,
                include_knowledge=request.include_knowledge,
            )
            
            logger.debug(f"Context summary: {list(context.keys())}")
            
            # Sanitize context
            context = context_builder.sanitize_context(context)
            
            # Call LLM service
            logger.debug("Calling LLM service...")
            success, llm_result = await llm_client.generate_response(
                query=request.query,
                language=request.language,
                user_context=context.get("user_context"),
                vision_context=context.get("vision_context"),
                knowledge_items=context.get("knowledge_items"),
                conversation_history=context.get("conversation_history"),
            )
            
            if not success:
                error_msg = llm_result.get("error", "LLM generation failed")
                logger.error(f"LLM service error: {error_msg}")
                
                return GenerateResponseModel(
                    success=False,
                    error={
                        "code": llm_result.get("error_code", "LLM_ERROR"),
                        "message": error_msg,
                    }
                )
            
            # Extract response
            response_text = llm_result.get("response", "")
            
            # Store in conversation history (background task)
            background_tasks.add_task(
                _store_conversation,
                user_storage,
                request.user_id,
                request.query,
                response_text,
            )
            
            logger.info(f"Response generated successfully ({len(response_text)} chars)")
            
            return GenerateResponseModel(
                success=True,
                data={
                    "response": response_text,
                    "language": request.language,
                    "metadata": llm_result.get("metadata", {}),
                }
            )
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}", exc_info=True)
            
            return GenerateResponseModel(
                success=False,
                error={
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to generate response",
                }
            )
    
    @router.post("/conversation", response_model=Dict[str, Any])
    async def get_conversation_context(
        user_id: str,
    ) -> Dict[str, Any]:
        """
        Get conversation context for a user.
        
        Returns the recent conversation history for UI display.
        """
        try:
            user = user_storage.get_user(user_id)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            history = user.get("conversation_history", [])
            
            return {
                "success": True,
                "user_id": user_id,
                "conversation_count": len(history),
                "recent_turns": history[-5:] if history else [],  # Last 5 turns
            }
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting conversation context: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to retrieve conversation")
    
    @router.delete("/conversation")
    async def clear_conversation(
        user_id: str,
    ) -> Dict[str, Any]:
        """Clear conversation history for a user."""
        try:
            user = user_storage.get_user(user_id)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            user["conversation_history"] = []
            user_storage.save_user(user_id, user)
            
            return {
                "success": True,
                "message": "Conversation history cleared",
            }
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error clearing conversation: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to clear conversation")
    
    @router.get("/health", response_model=Dict[str, Any])
    async def llm_health() -> Dict[str, Any]:
        """Check LLM service health."""
        try:
            is_healthy = await llm_client.health_check()
            
            return {
                "service": "LLM",
                "healthy": is_healthy,
                "status": "ok" if is_healthy else "degraded",
                "circuit_breaker": llm_client.get_circuit_breaker_status(),
            }
        
        except Exception as e:
            logger.error(f"Error checking LLM health: {str(e)}")
            return {
                "service": "LLM",
                "healthy": False,
                "status": "error",
                "error": str(e),
            }
    
    return router


async def _store_conversation(
    user_storage,
    user_id: str,
    user_query: str,
    assistant_response: str,
):
    """
    Store conversation turn in user's history (background task).
    
    Args:
        user_storage: User storage module
        user_id: User identifier
        user_query: User's original query
        assistant_response: Assistant's response
    """
    try:
        user = user_storage.get_user(user_id)
        if not user:
            logger.warning(f"User {user_id} not found when storing conversation")
            return
        
        # Initialize conversation history if needed
        if "conversation_history" not in user:
            user["conversation_history"] = []
        
        # Add new turn
        turn = {
            "user": user_query,
            "assistant": assistant_response,
            "timestamp": datetime.now().isoformat(),
        }
        
        user["conversation_history"].append(turn)
        
        # Keep only last 50 turns to manage storage
        if len(user["conversation_history"]) > 50:
            user["conversation_history"] = user["conversation_history"][-50:]
        
        # Save
        user_storage.save_user(user_id, user)
        
        logger.debug(f"Stored conversation turn for user {user_id}")
    
    except Exception as e:
        logger.error(f"Error storing conversation: {str(e)}", exc_info=True)
