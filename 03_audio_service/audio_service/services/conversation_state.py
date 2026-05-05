"""
Conversation State Management for NEXI Audio Service.
Tracks and manages the conversational state of the system.

Features:
- State machine for conversation flow (IDLE → CONVERSATION_ACTIVE → EXITING)
- Thread-safe state transitions
- Timeout management for inactive conversations
- State change callbacks for subscribers
"""

import logging
import threading
from enum import Enum
from datetime import datetime
from typing import Optional, Callable, Dict, List

logger = logging.getLogger(__name__)


class ConversationState(Enum):
    """
    Enumeration of conversation states.
    
    IDLE: Waiting for wake word, stop word detector inactive
    CONVERSATION_ACTIVE: In conversation, stop word detector active, wake word detector inactive
    PROCESSING_QUERY: Currently processing user query (sub-state of CONVERSATION_ACTIVE)
    EXITING: Gracefully exiting conversation mode
    """
    IDLE = "idle"
    CONVERSATION_ACTIVE = "conversation_active"
    PROCESSING_QUERY = "processing_query"
    EXITING = "exiting"


class ConversationStateManager:
    """
    Manages conversation state transitions and timeouts.
    Thread-safe state management for continuous conversation mode.
    
    Attributes:
        current_state: Current conversation state
        state_lock: Thread lock for thread-safe state changes
        conversation_start_time: When conversation started (datetime or None)
        last_user_speech_time: When user last spoke (datetime or None)
        timeout_seconds: Timeout duration for continuous conversation
        state_change_callbacks: Dict mapping state to list of callback functions
    """
    
    def __init__(self, timeout_seconds: int = 120):
        """
        Initialize conversation state manager.
        
        Args:
            timeout_seconds: Timeout for continuous conversation (default 120 seconds)
        """
        self.current_state = ConversationState.IDLE
        self.state_lock = threading.RLock()
        self.conversation_start_time: Optional[datetime] = None
        self.last_user_speech_time: Optional[datetime] = None
        self.timeout_seconds = timeout_seconds
        self.state_change_callbacks: Dict[ConversationState, List[Callable]] = {
            state: [] for state in ConversationState
        }
        
        logger.info(f"ConversationStateManager initialized (timeout: {timeout_seconds}s)")
    
    def get_state(self) -> ConversationState:
        """
        Get current conversation state (thread-safe).
        
        Returns:
            Current ConversationState
        """
        with self.state_lock:
            return self.current_state
    
    def transition_to(self, new_state: ConversationState):
        """
        Transition to a new conversation state (thread-safe).
        Updates timing information and calls registered callbacks.
        
        Args:
            new_state: Target ConversationState
        """
        with self.state_lock:
            old_state = self.current_state
            
            if old_state == new_state:
                logger.debug(f"Already in state {new_state.value}, no transition")
                return
            
            # Log transition
            logger.info(f"Conversation state transition: {old_state.value} → {new_state.value}")
            
            # Update state
            self.current_state = new_state
            
            # Update timing based on new state
            if new_state == ConversationState.CONVERSATION_ACTIVE:
                # Starting conversation
                self.conversation_start_time = datetime.now()
                self.last_user_speech_time = datetime.now()
                logger.info("Conversation started")
            
            elif new_state == ConversationState.IDLE:
                # Ended conversation
                if self.conversation_start_time:
                    duration = (datetime.now() - self.conversation_start_time).total_seconds()
                    logger.info(f"Conversation ended (duration: {duration:.1f}s)")
                
                self.conversation_start_time = None
                self.last_user_speech_time = None
            
            elif new_state == ConversationState.PROCESSING_QUERY:
                # Processing query (update speech time)
                self.last_user_speech_time = datetime.now()
            
            # Call registered callbacks for this state
            self._invoke_callbacks(new_state)
    
    def update_last_speech_time(self):
        """
        Update last user speech time to current time.
        Resets conversation timeout.
        """
        with self.state_lock:
            if self.current_state == ConversationState.CONVERSATION_ACTIVE:
                self.last_user_speech_time = datetime.now()
                logger.debug("Updated last speech time (timeout reset)")
    
    def check_timeout(self) -> bool:
        """
        Check if conversation has exceeded timeout duration.
        
        Returns:
            True if timeout exceeded, False otherwise
        """
        with self.state_lock:
            # Not in conversation mode
            if self.current_state != ConversationState.CONVERSATION_ACTIVE:
                return False
            
            # No speech time recorded
            if self.last_user_speech_time is None:
                return False
            
            # Calculate seconds since last user speech
            elapsed = (datetime.now() - self.last_user_speech_time).total_seconds()
            
            # Check against timeout
            if elapsed > self.timeout_seconds:
                logger.warning(f"Conversation timeout: {elapsed:.1f}s > {self.timeout_seconds}s")
                return True
            
            return False
    
    def get_conversation_duration(self) -> float:
        """
        Get duration of current conversation in seconds.
        
        Returns:
            Duration in seconds, or 0 if not in conversation
        """
        with self.state_lock:
            if self.current_state == ConversationState.CONVERSATION_ACTIVE and self.conversation_start_time:
                return (datetime.now() - self.conversation_start_time).total_seconds()
            return 0.0
    
    def get_elapsed_since_speech(self) -> float:
        """
        Get elapsed time since user last spoke.
        
        Returns:
            Elapsed seconds since speech, or 0 if no speech yet
        """
        with self.state_lock:
            if self.last_user_speech_time:
                return (datetime.now() - self.last_user_speech_time).total_seconds()
            return 0.0
    
    def register_callback(
        self,
        state: ConversationState,
        callback: Callable
    ):
        """
        Register callback function to be called on state transition.
        
        Args:
            state: State to trigger callback on
            callback: Callable to invoke
        """
        with self.state_lock:
            if callback not in self.state_change_callbacks[state]:
                self.state_change_callbacks[state].append(callback)
                logger.debug(f"Registered callback for state: {state.value}")
    
    def unregister_callback(
        self,
        state: ConversationState,
        callback: Callable
    ):
        """
        Unregister callback function.
        
        Args:
            state: State to remove callback from
            callback: Callable to remove
        """
        with self.state_lock:
            if callback in self.state_change_callbacks[state]:
                self.state_change_callbacks[state].remove(callback)
                logger.debug(f"Unregistered callback for state: {state.value}")
    
    def _invoke_callbacks(self, state: ConversationState):
        """
        Invoke all registered callbacks for a given state.
        
        Args:
            state: State whose callbacks should be invoked
        """
        callbacks = self.state_change_callbacks.get(state, [])
        
        for callback in callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in state callback {callback.__name__}: {e}")
    
    def get_status(self) -> dict:
        """
        Get detailed status information.
        
        Returns:
            Dict with current state and timing information
        """
        with self.state_lock:
            return {
                "current_state": self.current_state.value,
                "in_conversation": self.current_state == ConversationState.CONVERSATION_ACTIVE,
                "conversation_duration_s": self.get_conversation_duration(),
                "elapsed_since_speech_s": self.get_elapsed_since_speech(),
                "timeout_exceeded": self.check_timeout(),
                "timeout_seconds": self.timeout_seconds
            }
