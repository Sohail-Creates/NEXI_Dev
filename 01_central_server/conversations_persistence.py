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
    """
    Load conversations from cache or disk.
    
    Returns:
        Dictionary with 'conversations' key containing list of conversation objects
    """
    global _cache, _cache_timestamp
    
    # Check if cached data is still valid
    if _is_cache_valid() and _cache is not None:
        return _cache
    
    # Cache miss or expired - load from disk with lock
    with _cache_lock:
        # Double-check after acquiring lock
        if _is_cache_valid() and _cache is not None:
            return _cache
        
        try:
            if not CONVERSATIONS_FILE.exists():
                _cache = {"conversations": []}
                _cache_timestamp = datetime.now()
                return _cache
            
            # Read from disk and parse JSON
            data = json.loads(CONVERSATIONS_FILE.read_text(encoding="utf-8"))
            
            # Validate structure
            if not isinstance(data, dict) or "conversations" not in data:
                data = {"conversations": []}
            
            # Update cache
            _cache = data
            _cache_timestamp = datetime.now()
            
            return _cache
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error in conversations.json: {e}")
            return {"conversations": []}
        except Exception as e:
            logger.error(f"Error loading conversations from disk: {e}")
            return {"conversations": []}


def save_conversations(data: Dict[str, Any]) -> bool:
    """
    Save conversations to disk atomically.
    
    Uses atomic write pattern:
    1. Write to temporary file
    2. Atomic rename (ACID on most filesystems)
    3. Update cache
    
    Args:
        data: Dictionary with 'conversations' key
        
    Returns:
        True if successful, False otherwise
    """
    global _cache, _cache_timestamp
    
    try:
        # Ensure data directory exists
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        # Validate structure
        if not isinstance(data, dict) or "conversations" not in data:
            logger.error("Invalid data structure - must have 'conversations' key")
            return False
        
        # Create backup before write
        if CONVERSATIONS_FILE.exists():
            backup_path = CONVERSATIONS_FILE.with_suffix('.backup')
            try:
                import shutil
                shutil.copy2(CONVERSATIONS_FILE, backup_path)
            except Exception as e:
                logger.warning(f"Could not create backup: {e}")
        
        # Atomic write: write to temp file first, then rename
        temp_file = CONVERSATIONS_FILE.with_suffix('.tmp')
        
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        # Atomic rename
        temp_file.replace(CONVERSATIONS_FILE)
        
        # Update cache after successful write
        with _cache_lock:
            _cache = data
            _cache_timestamp = datetime.now()
        
        logger.debug(f"[PERSIST] Saved {len(data.get('conversations', []))} conversations")
        return True
        
    except Exception as e:
        logger.error(f"Error saving conversations: {e}")
        return False


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
    """Ensure conversations file exists with proper structure."""
    try:
        if not CONVERSATIONS_FILE.exists():
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            initial_data = {"conversations": []}
            save_conversations(initial_data)
            logger.info("Conversations file initialized")
    except Exception as e:
        logger.error(f"Error initializing conversations file: {e}")


# Initialize on import
initialize_conversations_file()
