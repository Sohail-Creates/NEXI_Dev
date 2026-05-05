"""
Conversation State Manager

Manages the state of the audio service conversation mode.
Ensures safe transitions between IDLE and CONVERSATION_ACTIVE states.
"""

from enum import Enum
from threading import Lock
import logging

logger = logging.getLogger(__name__)


class ConversationState(Enum):
    """Possible conversation states."""
    IDLE = "idle"
    CONVERSATION_ACTIVE = "conversation_active"


class ConversationStateManager:
    """Manages conversation state transitions."""
    
    def __init__(self):
        """Initialize the manager with IDLE state."""
        self._state = ConversationState.IDLE
        self._lock = Lock()
        logger.info("ConversationStateManager initialized with IDLE state")
    
    def transition_to(self, new_state: ConversationState) -> bool:
        """
        Transition to a new state.
        
        Args:
            new_state: The target ConversationState
            
        Returns:
            True if transition was successful, False otherwise
        """
        if not isinstance(new_state, ConversationState):
            logger.warning(f"Invalid state transition attempt: {new_state}")
            return False
        
        with self._lock:
            old_state = self._state
            self._state = new_state
            logger.info(f"State transitioned: {old_state.value} → {new_state.value}")
            return True
    
    def get_state(self) -> ConversationState:
        """
        Get the current state.
        
        Returns:
            The current ConversationState
        """
        with self._lock:
            return self._state
    
    def is_in_conversation(self) -> bool:
        """
        Check if currently in conversation mode.
        
        Returns:
            True if state is CONVERSATION_ACTIVE, False otherwise
        """
        with self._lock:
            return self._state == ConversationState.CONVERSATION_ACTIVE
