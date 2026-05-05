"""
Thread-safe service configuration module.
Manages runtime configuration that can be modified by endpoints.
PHASE 1.3: Eliminates race conditions on global variables.
"""

import threading
from typing import Optional


class ServiceConfig:
    """
    Thread-safe runtime configuration for TTS service.
    Replaces global variables with atomic operations.
    """
    
    # Valid voice IDs
    VALID_VOICES = {"ryan", "jenny", "shahid"}
    
    def __init__(self, default_voice: str = "ryan"):
        """
        Initialize service configuration.
        
        Args:
            default_voice: Default voice to use for synthesis
        """
        self._default_voice = default_voice
        self._lock = threading.RLock()
        
        if default_voice not in self.VALID_VOICES:
            raise ValueError(f"Invalid default voice: {default_voice}")
    
    @property
    def default_voice(self) -> str:
        """
        Get default voice (thread-safe).
        
        Returns:
            Current default voice ID
        """
        with self._lock:
            return self._default_voice
    
    @default_voice.setter
    def default_voice(self, voice_id: str) -> None:
        """
        Set default voice atomically (thread-safe).
        
        Args:
            voice_id: New default voice ID
            
        Raises:
            ValueError: If voice_id is invalid
        """
        if voice_id not in self.VALID_VOICES:
            raise ValueError(
                f"Invalid voice_id: {voice_id}. Valid: {self.VALID_VOICES}"
            )
        
        with self._lock:
            self._default_voice = voice_id
    
    def set_default_voice_atomic(self, voice_id: str) -> bool:
        """
        Atomically set default voice with validation.
        Returns False if validation fails (non-throwing).
        
        Args:
            voice_id: New default voice ID
            
        Returns:
            True if successful, False if invalid voice_id
        """
        if voice_id not in self.VALID_VOICES:
            return False
        
        try:
            self.default_voice = voice_id
            return True
        except (ValueError, Exception):
            return False


# Global singleton configuration
_service_config: Optional[ServiceConfig] = None


def get_service_config() -> ServiceConfig:
    """
    Get or create global service configuration.
    
    Returns:
        Singleton ServiceConfig instance
    """
    global _service_config
    if _service_config is None:
        _service_config = ServiceConfig(default_voice="jenny")
    return _service_config
