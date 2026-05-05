"""
Speaker State Management for NEXI TTS Service.
Manages intelligent speaker lifecycle: loaded, idle, unloaded.

Features:
- Jenny as default speaker (always loaded on startup)
- Smart speaker switching (load new, unload old default)
- Idle state for available speakers (e.g., Shahid)
- Resource optimization (don't load all speakers)
- Thread-safe operations for concurrent requests
"""

import logging
import threading
from enum import Enum
from typing import Dict, Optional, Set, List
from datetime import datetime

logger = logging.getLogger(__name__)


class SpeakerState(Enum):
    """Speaker lifecycle states."""
    LOADED = "loaded"          # Model is in memory, ready to use
    IDLE = "idle"              # Available but not loaded (saves memory)
    UNLOADED = "unloaded"      # Not available in this session


class SpeakerManager:
    """
    Manages speaker lifecycle and resource optimization.
    
    Responsibilities:
    1. Track speaker states (loaded, idle, unloaded)
    2. Load default speaker on startup (Jenny)
    3. Smart switching: unload old default, load new default
    4. Keep non-default speakers idle (save resources)
    5. Auto-cleanup of rarely used speakers
    """
    
    # Map speakers to their properties
    SPEAKER_CONFIG = {
        "jenny": {
            "language": "english",
            "default": True,
            "preload_on_startup": True,
            "description": "Female English voice (British accent) - DEFAULT"
        },
        "ryan": {
            "language": "english",
            "default": False,
            "preload_on_startup": False,
            "description": "Male English voice"
        },
        "shahid": {
            "language": "urdu",
            "default": False,
            "preload_on_startup": False,
            "description": "Male Urdu voice"
        }
    }
    
    def __init__(self, model_cache):
        """
        Initialize speaker manager.
        
        Args:
            model_cache: UnifiedModelCache instance for managing models
        """
        self.model_cache = model_cache
        self._states: Dict[str, SpeakerState] = {}
        self._load_times: Dict[str, datetime] = {}
        self._access_counts: Dict[str, int] = {}
        self._lock = threading.RLock()
        self._current_default = None
        
        # Initialize all speakers as idle
        for speaker_id in self.SPEAKER_CONFIG.keys():
            self._states[speaker_id] = SpeakerState.IDLE
            self._access_counts[speaker_id] = 0
        
        logger.info("SpeakerManager initialized")
    
    def initialize_default_speaker(self):
        """
        Load default speaker on service startup.
        This is called during FastAPI lifespan startup.
        Jenny is preloaded for fast response times.
        """
        with self._lock:
            try:
                # Load Jenny (default speaker)
                logger.info("Loading default speaker: jenny...")
                self.model_cache.get_model("jenny")
                
                self._states["jenny"] = SpeakerState.LOADED
                self._load_times["jenny"] = datetime.now()
                self._current_default = "jenny"
                self._access_counts["jenny"] += 1
                
                logger.info("✓ Default speaker loaded: jenny")
                
            except Exception as e:
                logger.error(f"Failed to load default speaker jenny: {e}")
                raise RuntimeError(f"Cannot load default speaker: {e}")
    
    def get_speaker_state(self, speaker_id: str) -> SpeakerState:
        """
        Get current state of a speaker.
        
        Args:
            speaker_id: Speaker identifier
            
        Returns:
            SpeakerState enum value
        """
        with self._lock:
            return self._states.get(speaker_id, SpeakerState.UNLOADED)
    
    def is_speaker_loaded(self, speaker_id: str) -> bool:
        """Check if speaker model is currently loaded."""
        return self.get_speaker_state(speaker_id) == SpeakerState.LOADED
    
    def get_all_speakers_status(self) -> Dict[str, dict]:
        """
        Get status of all speakers.
        Returns: Dict with speaker details including state, load time, access count.
        """
        with self._lock:
            status = {}
            for speaker_id, config in self.SPEAKER_CONFIG.items():
                state = self._states[speaker_id]
                status[speaker_id] = {
                    "id": speaker_id,
                    "name": config.get("description", speaker_id),
                    "language": config.get("language"),
                    "state": state.value,
                    "is_default": self._current_default == speaker_id,
                    "is_loaded": state == SpeakerState.LOADED,
                    "access_count": self._access_counts[speaker_id],
                    "load_time": self._load_times.get(speaker_id, None),
                }
            return status
    
    def switch_speaker(self, new_speaker_id: str) -> Dict[str, str]:
        """
        Switch default speaker intelligently.
        
        Behavior:
        1. Load new speaker if not already loaded
        2. Unload old default speaker (if it's not the same)
        3. Set new speaker as default
        4. Keep other speakers idle for resource optimization
        
        Args:
            new_speaker_id: Speaker to set as new default
            
        Returns:
            Dict with operation results
            
        Raises:
            ValueError: If speaker_id is invalid
            RuntimeError: If speaker loading fails
        """
        if new_speaker_id not in self.SPEAKER_CONFIG:
            raise ValueError(f"Invalid speaker_id: {new_speaker_id}")
        
        with self._lock:
            # If already default, no-op
            if self._current_default == new_speaker_id and \
               self._states[new_speaker_id] == SpeakerState.LOADED:
                logger.info(f"Speaker '{new_speaker_id}' already set as default (loaded)")
                return {
                    "status": "already_default",
                    "current_default": new_speaker_id
                }
            
            old_default = self._current_default
            unloaded = []
            
            try:
                # Step 1: Load new speaker
                logger.info(f"Loading speaker: {new_speaker_id}...")
                self.model_cache.get_model(new_speaker_id)
                self._states[new_speaker_id] = SpeakerState.LOADED
                self._load_times[new_speaker_id] = datetime.now()
                self._access_counts[new_speaker_id] += 1
                
                # Step 2: Unload old default (but keep it idle)
                if old_default and old_default != new_speaker_id:
                    logger.info(f"Unloading previous default speaker: {old_default}...")
                    try:
                        self.model_cache.unload_model(old_default)
                        self._states[old_default] = SpeakerState.IDLE
                        unloaded.append(old_default)
                        logger.info(f"✓ Unloaded: {old_default} (now idle)")
                    except Exception as e:
                        logger.warning(f"Could not unload {old_default}: {e}")
                        # Continue anyway - model will be evicted by LRU if needed
                
                # Step 3: Set as new default
                self._current_default = new_speaker_id
                
                logger.info(f"✓ Default speaker changed to: {new_speaker_id}")
                
                return {
                    "status": "switched",
                    "old_default": old_default,
                    "new_default": new_speaker_id,
                    "unloaded": unloaded,
                    "current_state": {
                        "loaded": new_speaker_id,
                        "idle": [s for s in self.SPEAKER_CONFIG.keys() 
                                if s != new_speaker_id and self._states[s] == SpeakerState.IDLE]
                    }
                }
            
            except Exception as e:
                error_msg = f"Failed to switch to {new_speaker_id}: {e}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
    
    def get_current_default(self) -> str:
        """Get currently set default speaker."""
        with self._lock:
            return self._current_default or "jenny"
    
    def record_speaker_usage(self, speaker_id: str):
        """
        Record speaker usage for monitoring.
        Updates access count and last access time.
        
        Args:
            speaker_id: Speaker that was used
        """
        with self._lock:
            if speaker_id in self._access_counts:
                self._access_counts[speaker_id] += 1
    
    def get_resource_stats(self) -> Dict:
        """
        Get resource usage statistics.
        Returns memory usage info, cache status, etc.
        """
        with self._lock:
            loaded_speakers = [sid for sid, state in self._states.items() 
                             if state == SpeakerState.LOADED]
            idle_speakers = [sid for sid, state in self._states.items() 
                           if state == SpeakerState.IDLE]
            
            return {
                "current_default": self._current_default,
                "loaded_speakers": loaded_speakers,
                "idle_speakers": idle_speakers,
                "num_loaded": len(loaded_speakers),
                "num_idle": len(idle_speakers),
                "total_speakers": len(self.SPEAKER_CONFIG),
                "access_counts": dict(self._access_counts),
                "memory_optimized": f"Loaded {len(loaded_speakers)} of {len(self.SPEAKER_CONFIG)} speakers"
            }


# Global singleton speaker manager
_speaker_manager: Optional[SpeakerManager] = None


def get_speaker_manager(model_cache=None) -> SpeakerManager:
    """
    Get or create global speaker manager.
    
    Args:
        model_cache: UnifiedModelCache instance (required on first call)
        
    Returns:
        Singleton SpeakerManager instance
    """
    global _speaker_manager
    if _speaker_manager is None:
        if model_cache is None:
            raise RuntimeError("model_cache required for first initialization")
        _speaker_manager = SpeakerManager(model_cache)
    return _speaker_manager
