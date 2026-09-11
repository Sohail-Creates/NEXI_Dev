"""
Conversation Routes - Professional REST API for Conversation Storage

Endpoints:
- POST /users/{user_id}/conversations - Store new conversation
- GET /users/{user_id}/conversations - Retrieve user's conversations
- DELETE /users/{user_id}/conversations - Delete all user conversations
- GET /conversations/{conversation_id} - Get specific conversation
- GET /conversations/admin/stats - Analytics about conversations
"""

from fastapi import APIRouter, HTTPException, Query, Request
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging
import asyncio
from shared.jwt_manager import require_user_ownership
from shared.security import require_internal_service

from conversations_persistence import (
    add_conversation,
    get_user_conversations,
    get_conversation_by_id,
    delete_user_conversations,
    get_conversation_stats
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Conversations"])


@router.post("/users/{user_id}/conversations")
async def store_user_conversation(
    user_id: str,
    request: Request
) -> Dict[str, Any]:
    """
    Store a new conversation for a user.
    
    POST /users/{user_id}/conversations
    
    Expected JSON payload:
    {
        "user_message": "Tell me about gardening",
        "assistant_response": "Flowers are amazing...",
        "mood": "happy",
        "language": "en",
        "metadata": {}  // optional
    }
    
    Response:
    {
        "status": "success",
        "user_id": "sara123",
        "timestamp": "2026-03-08T15:45:00Z"
    }
    """
    try:
        require_user_ownership(request, user_id)
        # Parse request body
        body = await request.json()
        
        # Validate required fields
        user_message = body.get("user_message", "").strip()
        assistant_response = body.get("assistant_response", "").strip()
        
        if not user_message or not assistant_response:
            raise HTTPException(
                status_code=400,
                detail="Both 'user_message' and 'assistant_response' are required"
            )
        
        # Get optional fields
        mood = body.get("mood", "neutral")
        language = body.get("language", "en")
        metadata = body.get("metadata", {})
        
        # Store conversation
        success = await asyncio.to_thread(add_conversation,
            user_id=user_id,
            user_message=user_message,
            assistant_response=assistant_response,
            mood=mood,
            language=language,
            metadata=metadata
        )
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to store conversation"
            )
        
        logger.info(f"[CONVERSATION] Stored for user {user_id} (mood: {mood}, lang: {language})")
        
        return {
            "status": "success",
            "message": f"Conversation stored for user {user_id}",
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error storing conversation: {e}")
        raise HTTPException(status_code=500, detail=f"Error storing conversation: {str(e)}")


@router.get("/users/{user_id}/conversations")
async def get_user_conversations_endpoint(
    user_id: str,
    limit: int = Query(10, ge=1, le=500),
    start_date: Optional[str] = Query(None),  # ISO timestamp
    end_date: Optional[str] = Query(None),    # ISO timestamp
    request: Request = None
) -> Dict[str, Any]:
    """
    Retrieve conversations for a user.
    
    GET /users/{user_id}/conversations?limit=10&start_date=...&end_date=...
    
    Query parameters:
    - limit: Number of conversations to return (1-500, default 10)
    - start_date: ISO timestamp for filtering (inclusive)
    - end_date: ISO timestamp for filtering (inclusive)
    
    Returns most recent conversations first.
    
    Response:
    {
        "user_id": "sara123",
        "conversations": [...],
        "count": 5,
        "limit": 10
    }
    """
    try:
        require_user_ownership(request, user_id)
        conversations = await asyncio.to_thread(get_user_conversations,
            user_id=user_id,
            limit=limit,
            start_timestamp=start_date,
            end_timestamp=end_date
        )
        
        logger.info(f"[CONVERSATION] Retrieved {len(conversations)} conversations for user {user_id}")
        
        return {
            "user_id": user_id,
            "conversations": conversations,
            "count": len(conversations),
            "limit": limit,
            "start_date": start_date,
            "end_date": end_date
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving conversations: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving conversations: {str(e)}")


@router.get("/conversations/{conversation_id}")
async def get_single_conversation(
    conversation_id: str,
    request: Request = None
) -> Dict[str, Any]:
    """
    Retrieve a specific conversation by ID.
    
    GET /conversations/{conversation_id}
    
    Response: Single conversation object with all details
    """
    try:
        conversation = await asyncio.to_thread(get_conversation_by_id, conversation_id)
        
        if not conversation:
            raise HTTPException(
                status_code=404,
                detail=f"Conversation '{conversation_id}' not found"
            )
        require_user_ownership(request, conversation.get("user_id", ""))
        
        return conversation
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving conversation: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving conversation: {str(e)}")


@router.delete("/users/{user_id}/conversations")
async def delete_all_user_conversations(
    user_id: str,
    request: Request = None
) -> Dict[str, Any]:
    """
    Delete all conversations for a user (e.g., for privacy/account deletion).
    
    DELETE /users/{user_id}/conversations
    
    Response:
    {
        "status": "deleted",
        "user_id": "sara123",
        "message": "All conversations deleted for user sara123"
    }
    """
    try:
        require_user_ownership(request, user_id)
        success = await asyncio.to_thread(delete_user_conversations, user_id)
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to delete conversations"
            )
        
        logger.info(f"[CONVERSATION] Deleted all conversations for user {user_id}")
        
        return {
            "status": "deleted",
            "user_id": user_id,
            "message": f"All conversations deleted for user {user_id}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting conversations: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting conversations: {str(e)}")


@router.get("/admin/stats")
async def get_conversation_statistics(request: Request = None) -> Dict[str, Any]:
    """
    Get analytics about all conversations (admin endpoint).
    
    Response:
    {
        "total_conversations": 1542,
        "unique_users": 25,
        "conversations_per_user": {"sara123": 45, "ali456": 23, ...},
        "by_language": {"en": 900, "ur": 642},
        "oldest_timestamp": "2026-02-15T10:00:00Z",
        "newest_timestamp": "2026-03-08T15:45:00Z"
    }
    """
    try:
        await require_internal_service(request)
        stats = await asyncio.to_thread(get_conversation_stats)
        
        logger.info(f"[CONVERSATION] Stats retrieved: {stats.get('total_conversations')} total conversations")
        
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting stats: {str(e)}")
