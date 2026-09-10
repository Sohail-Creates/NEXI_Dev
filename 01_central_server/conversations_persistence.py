"""
Conversation Persistence Layer - Separate from Users

Manages conversation history storage with:
- Efficient JSON file structure (separate from users.json)
- Automatic cleanup (keeps last 500 conversations per user)
- Query by user_id and date range
- Thread-safe operations
- Atomic writes

Design:
conversations.json = {
    "conversations": [
        {
            "conversation_id": "uuid",
            "user_id": "sara123",
            "timestamp": "2026-03-08T15:45:00Z",
            "user_message": "Tell me about gardening",
            "assistant_response": "Flowers are amazing...",
            "mood": "happy",
            "language": "en",
            "metadata": {}
        },
        ...
    ]
}
"""

from __future__ import annotations

from _thread import RLock
import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import logging
import uuid
from sqlite_store import read_records, write_records, transactional

logger: logging.Logger = logging.getLogger(__name__)

# File paths
DATA_DIR: Path = Path(__file__).resolve().parent / "data"
CONVERSATIONS_FILE: Path = DATA_DIR / "conversations.json"

# Configuration
MAX_CONVERSATIONS_PER_USER: int = 500  # Keep last 500 for each user (reduces file size)
CACHE_TTL_SECONDS: int = 60  # Longer cache TTL for conversations (less frequently accessed)
MAX_CACHE_AGE: timedelta = timedelta(seconds=CACHE_TTL_SECONDS)

# Global thread-safe cache
_cache_lock: RLock = threading.RLock()
_cache: Optional[Dict[str, Any]] = None
_cache_timestamp: Optional[datetime] = None


def _is_cache_valid() -> bool:
    """Check if cache is still valid (not expired)."""
    if _cache is None or _cache_timestamp is None:
        return False
    
    age: timedelta = datetime.now() - _cache_timestamp
    return age < MAX_CACHE_AGE


def load_conversations() -> Dict[str, Any]:
    return {"conversations": read_records("conversations")}


def save_conversations(data: Dict[str, Any]) -> bool:
    write_records("conversations", data["conversations"])
    return True


@transactional
def add_conversation(
    user_id: str,
    user_message: str,
    assistant_response: str,
    mood: Optional[str] = None,
    language: Optional[str] = "en",
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Add a new conversation to the store.
    
    Args:
        user_id: User identifier
        user_message: What the user said
        assistant_response: How NEXI responded
        mood: Detected mood (optional)
        language: Language code (en, ur, etc.)
        metadata: Additional metadata (optional)
        
    Returns:
        True if successfully saved
    """
    try:
        data = load_conversations()
        
        conversation = {
            "conversation_id": f"conv_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "user_message": user_message,
            "assistant_response": assistant_response,
            "mood": mood or "neutral",
            "language": language,
            "metadata": metadata or {}
        }
        
        if "conversations" not in data:
            data["conversations"] = []
        
        data["conversations"].append(conversation)
        
        # Clean up old conversations (keep last N per user)
        _cleanup_old_conversations(data, user_id)
        
        return save_conversations(data)
        
    except Exception as e:
        logger.error(f"Error adding conversation: {e}")
        return False


def get_user_conversations(
    user_id: str,
    limit: int = 10,
    start_timestamp: Optional[str] = None,
    end_timestamp: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get conversations for a specific user.
    
    Args:
        user_id: User identifier
        limit: Max number of conversations to return (0 = all)
        start_timestamp: ISO timestamp for filtering (inclusive)
        end_timestamp: ISO timestamp for filtering (inclusive)
        
    Returns:
        List of conversation dictionaries, most recent first
    """
    try:
        data = load_conversations()
        conversations = data.get("conversations", [])
        
        # Filter by user_id
        user_conversations = [c for c in conversations if c.get("user_id") == user_id]
        
        # Filter by date range if provided
        if start_timestamp:
            user_conversations = [c for c in user_conversations if c.get("timestamp", "") >= start_timestamp]
        if end_timestamp:
            user_conversations = [c for c in user_conversations if c.get("timestamp", "") <= end_timestamp]
        
        # Sort by timestamp (most recent first)
        user_conversations.sort(key=lambda c: c.get("timestamp", ""), reverse=True)
        
        # Apply limit
        if limit > 0:
            user_conversations = user_conversations[:limit]
        
        return user_conversations
        
    except Exception as e:
        logger.error(f"Error getting user conversations: {e}")
        return []


def get_conversation_by_id(conversation_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific conversation by ID."""
    try:
        data = load_conversations()
        conversations = data.get("conversations", [])
        
        for conv in conversations:
            if conv.get("conversation_id") == conversation_id:
                return conv
        
        return None
    except Exception as e:
        logger.error(f"Error getting conversation: {e}")
        return None


@transactional
def delete_user_conversations(user_id: str) -> bool:
    """Delete all conversations for a user."""
    try:
        data = load_conversations()
        conversations = data.get("conversations", [])
        
        # Filter out conversations for this user
        data["conversations"] = [c for c in conversations if c.get("user_id") != user_id]
        
        return save_conversations(data)
    except Exception as e:
        logger.error(f"Error deleting user conversations: {e}")
        return False


def get_conversation_stats() -> Dict[str, Any]:
    """Get statistics about conversations."""
    try:
        data = load_conversations()
        conversations = data.get("conversations", [])
        
        # Count by user
        users = {}
        for conv in conversations:
            user_id = conv.get("user_id", "unknown")
            users[user_id] = users.get(user_id, 0) + 1
        
        # Count by language
        languages = {}
        for conv in conversations:
            lang = conv.get("language", "unknown")
            languages[lang] = languages.get(lang, 0) + 1
        
        return {
            "total_conversations": len(conversations),
            "unique_users": len(users),
            "conversations_per_user": users,
            "by_language": languages,
            "oldest_timestamp": min((c.get("timestamp", "") for c in conversations), default=None),
            "newest_timestamp": max((c.get("timestamp", "") for c in conversations), default=None)
        }
    except Exception as e:
        logger.error(f"Error getting conversation stats: {e}")
        return {
            "total_conversations": 0,
            "error": str(e)
        }


def _cleanup_old_conversations(data: Dict[str, Any], user_id: str) -> None:
    """
    Keep only last N conversations per user.
    
    This prevents the file from growing too large over time.
    """
    try:
        conversations = data.get("conversations", [])
        
        # Find conversations for this user
        user_conversations_indices = [
            i for i, c in enumerate(conversations)
            if c.get("user_id") == user_id
        ]
        
        # If we have more than MAX, delete the oldest ones
        if len(user_conversations_indices) > MAX_CONVERSATIONS_PER_USER:
            # Get indices to delete (oldest ones)
            indices_to_delete = user_conversations_indices[:-MAX_CONVERSATIONS_PER_USER]
            
            # Delete in reverse order to maintain indices
            for idx in sorted(indices_to_delete, reverse=True):
                del conversations[idx]
            
            logger.info(f"Cleaned up {len(indices_to_delete)} old conversations for user {user_id}")
        
    except Exception as e:
        logger.warning(f"Error during cleanup: {e}")


# Initialize conversations file if it doesn't exist
def initialize_conversations_file() -> None:
    """Verify the explicitly migrated store exists; never create a JSON file."""
    read_records("conversations")


# Initialize on import
initialize_conversations_file()
