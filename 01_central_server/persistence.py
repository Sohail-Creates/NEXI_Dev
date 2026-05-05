"""
User Persistence Layer with  In-Memory Caching

Provides fast user data access with 30-second TTL caching:
- First read: ~1-5ms (memory cache hit)
- Cache miss: ~10-50ms (disk read)
- Writes: Atomic with backup

Usage:
  from persistence import load_users, save_users
"""

from __future__ import annotations

from _thread import RLock
import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import logging

logger: logging.Logger = logging.getLogger(__name__)

# File paths
DATA_DIR: Path = Path(__file__).resolve().parent / "data"
USERS_FILE: Path = DATA_DIR / "users.json"

# Cache configuration
CACHE_TTL_SECONDS = 30  # Cache valid for 30 seconds - balance between freshness and speed
MAX_CACHE_AGE = timedelta(seconds=CACHE_TTL_SECONDS)

# Global thread-safe cache
_cache_lock: RLock = threading.RLock()
_cache: Optional[List[Dict[str, Any]]] = None
_cache_timestamp: Optional[datetime] = None


def _is_cache_valid() -> bool:
    """Check if cache is still valid (not expired)."""
    if _cache is None or _cache_timestamp is None:
        return False
    
    age: timedelta = datetime.now() - _cache_timestamp
    return age < MAX_CACHE_AGE


def load_users() -> List[Dict[str, Any]]:
    """
    Load users from cache or disk.
    
    Performance:
    - Cache hit: ~1-5ms
    - Cache miss: ~10-50ms (disk read)
    
    Returns:
        List of user dictionaries from users.json
    """
    global _cache, _cache_timestamp
    
    # Check if cached data is still valid (avoid lock on common case)
    if _is_cache_valid() and _cache is not None:
        return _cache
    
    # Cache miss or expired - load from disk with lock
    with _cache_lock:
        # Double-check after acquiring lock
        if _is_cache_valid() and _cache is not None:
            return _cache
        
        try:
            if not USERS_FILE.exists():
                _cache = []
                _cache_timestamp = datetime.now()
                return []
            
            # Read from disk and parse JSON
            data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
            
            # Update cache
            _cache = data if isinstance(data, list) else []
            _cache_timestamp = datetime.now()
            
            return _cache if _cache else []
            
        except Exception as e:
            logger.error(f"Error loading users from disk: {e}")
            return []


def save_users(users: List[Dict[str, Any]]) -> None:
    """
    Save users to disk atomically and update cache.
    
    Atomic write operation:
    1. Write to temporary file
    2. Atomic rename (ACID on most filesystems)
    3. Update in-memory cache
    
    Args:
        users: List of user dictionaries to persist
    
    Note:
        Thread-safe. Multiple threads can call simultaneously.
    """
    global _cache, _cache_timestamp
    
    with _cache_lock:
        try:
            # Create output directory
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            
            # Create backup of existing file (non-critical, so errors ignored)
            if USERS_FILE.exists():
                try:
                    backup_file: Path = USERS_FILE.with_suffix(".json.backup")
                    existing_data: bytes = USERS_FILE.read_bytes()
                    backup_file.write_bytes(existing_data)
                except Exception:
                    pass  # Backup is best-effort
            
            # Write to temporary file first (atomic operation pattern)
            tmp_file: Path = USERS_FILE.with_suffix(".tmp")
            tmp_file.write_text(json.dumps(users, indent=2), encoding="utf-8")
            
            # Atomic rename (works across filesystems on most systems)
            tmp_file.replace(USERS_FILE)
            
            # Update in-memory cache after successful disk write
            _cache = users
            _cache_timestamp = datetime.now()
            
            logger.debug(f"Saved {len(users)} users to {USERS_FILE}")
            
        except Exception as e:
            logger.error(f"Failed to save users: {e}")
            raise


def clear_cache() -> None:
    """
    Manually clear the in-memory cache.
    
    Useful for testing or forcing a fresh disk read.
    After calling this, the next load_users() will read from disk.
    """
    global _cache, _cache_timestamp
    
    with _cache_lock:
        _cache = None
        _cache_timestamp = None


def get_cache_stats() -> Dict[str, Any]:
    """
    Get cache statistics for monitoring.
    
    Returns:
        Dictionary with cache status info
    """
    with _cache_lock:
        if _cache_timestamp is None:
            age_seconds = None
        else:
            age_seconds: float = (datetime.now() - _cache_timestamp).total_seconds()
        
        return {
            "cache_size": len(_cache) if _cache else 0,
            "cache_age_seconds": age_seconds,
            "cache_valid": _is_cache_valid(),
            "ttl_seconds": CACHE_TTL_SECONDS,
        }