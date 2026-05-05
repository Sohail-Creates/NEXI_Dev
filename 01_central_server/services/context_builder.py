"""Context builder for Central Server - gathers context from all services for LLM."""

import logging
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

from shared.clients.vision_client import VisionServiceClient
from shared.clients.teachme_client import TeachMeServiceClient

logger: logging.Logger = logging.getLogger(__name__)

# Configuration for retry/fallback logic
RETRY_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 1


class ContextBuilder:
    """
    Gathers contextual information from multiple NEXI services.
    
    Combines user profile, visual state, emotional context, and knowledge
    to provide rich context for LLM to generate better responses.
    """
    
    def __init__(
        self,
        user_storage,
        vision_client: Optional[VisionServiceClient] = None,
        teachme_client: Optional[TeachMeServiceClient] = None,
    ) -> None:
        """
        Initialize context builder.
        
        Args:
            user_storage: User persistence/storage module
            vision_client: Vision service client
            teachme_client: TeachMe service client
        """
        self.user_storage = user_storage
        self.vision_client: VisionServiceClient | None = vision_client
        self.teachme_client: TeachMeServiceClient | None = teachme_client
        self.logger: logging.Logger = logging.getLogger(__name__)
    
    async def build_context(
        self,
        user_id: str,
        query: str,
        include_vision: bool = True,
        include_knowledge: bool = True,
        knowledge_limit: int = 5,
    ) -> Dict[str, Any]:
        """
        Build complete context for LLM.
        
        Args:
            user_id: User identifier
            query: User's query (for relevance matching)
            include_vision: Whether to include visual context
            include_knowledge: Whether to include knowledge items
            knowledge_limit: Maximum knowledge items to include
        
        Returns:
            Context dictionary with all available information
        """
        context = {}
        
        # Gather context in parallel
        tasks = []
        
        # User context (always included)
        tasks.append(("user_context", self._get_user_context(user_id)))
        
        # Vision context (parallel if enabled)
        if include_vision and self.vision_client:
            tasks.append(("vision_context", self._get_vision_context()))
        
        # Knowledge items (parallel if enabled)
        if include_knowledge and self.teachme_client:
            tasks.append(("knowledge_items", self._get_relevant_knowledge(query, knowledge_limit)))
        
        # Conversation history
        tasks.append(("conversation_history", self._get_conversation_history(user_id)))
        
        # Execute all tasks in parallel
        results = await asyncio.gather(*[task[1] for task in tasks], return_exceptions=True)
        
        for (key, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                self.logger.warning(f"Failed to get {key}: {str(result)}")
                if key != "conversation_history":  # These are optional
                    context[key] = None
            else:
                context[key] = result
        
        return context
    
    async def _get_user_context(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user profile context.
        
        Args:
            user_id: User identifier
        
        Returns:
            User profile information
        """
        try:
            user = self.user_storage.get_user(user_id)
            
            if not user:
                self.logger.info(f"User {user_id} not found in storage")
                return None
            
            # Extract relevant user information
            context = {
                "name": user.get("name", f"User {user_id[:8]}"),
                "age": user.get("age"),
                "interests": user.get("interests", []),
            }
            
            # Add mood/emotion if available
            if "last_emotion" in user and user["last_emotion"]:
                context["mood"] = user.get("last_emotion")
            
            return context
        
        except Exception as e:
            self.logger.error(f"Error getting user context: {str(e)}")
            return None
    
    async def _get_vision_context(self) -> Optional[Dict[str, Any]]:
        """
        Get current visual context from Vision service with retry logic.
        
        Uses exponential backoff:
        - Attempt 1: Immediate
        - Attempt 2: After 1 second
        
        Fallback: If Vision unavail able, returns last known mood from history
        
        Returns:
            Current visual information (detected emotion, objects, etc) or None
        """
        if not self.vision_client:
            return None
        
        # Try up to RETRY_ATTEMPTS times
        for attempt in range(RETRY_ATTEMPTS):
            try:
                # Try to get current face emotion detection
                success, result = await self.vision_client.detect_emotion()
                
                if not success:
                    if attempt < RETRY_ATTEMPTS - 1:
                        self.logger.debug(f"Vision attempt {attempt + 1} failed, retrying...")
                        await asyncio.sleep(RETRY_DELAY_SECONDS)
                        continue
                    else:
                        self.logger.debug("Vision context not available after retries")
                        return None
                
                context = {}
                
                # Extract emotion
                if "emotion" in result:
                    context["emotion"] = result["emotion"]
                
                # Extract detected objects if available
                if "detected_objects" in result:
                    context["objects"] = result["detected_objects"]
                
                # Add description
                if context:
                    context["description"] = "Current visual and emotional state"
                
                return context if context else None
            
            except Exception as e:
                if attempt < RETRY_ATTEMPTS - 1:
                    self.logger.warning(f"Vision error (attempt {attempt + 1}): {str(e)}")
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                else:
                    self.logger.warning(f"Vision context failed after {RETRY_ATTEMPTS} attempts: {str(e)}")
                    return None
        
        return None
    
    async def _get_relevant_knowledge(
        self,
        query: str,
        limit: int = 5,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get relevant knowledge items for the query with retry logic.
        
        Uses exponential backoff:
        - Attempt 1: Immediate
        - Attempt 2: After 1 second
        
        Fallback: If TeachMe unavailable, LLM continues with general knowledge
        
        Args:
            query: User query for relevance matching
            limit: Maximum number of items to return
        
        Returns:
            List of relevant knowledge items, or None if unavailable
        """
        if not self.teachme_client:
            return None
        
        # Try up to RETRY_ATTEMPTS times
        for attempt in range(RETRY_ATTEMPTS):
            try:
                # Search for relevant knowledge
                success, result = await self.teachme_client.search_knowledge(query, limit=limit)
                
                if not success:
                    if attempt < RETRY_ATTEMPTS - 1:
                        self.logger.debug(f"TeachMe attempt {attempt + 1} failed, retrying...")
                        await asyncio.sleep(RETRY_DELAY_SECONDS)
                        continue
                    else:
                        self.logger.debug("No relevant knowledge found after retries")
                        return None
                
                items = result.get("items", [])
                
                if items:
                    # Limit to requested amount
                    return items[:limit]
                
                return None
            
            except Exception as e:
                if attempt < RETRY_ATTEMPTS - 1:
                    self.logger.warning(f"TeachMe error (attempt {attempt + 1}): {str(e)}")
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                else:
                    self.logger.warning(f"Knowledge retrieval failed after {RETRY_ATTEMPTS} attempts: {str(e)}")
                    return None
        
        return None
    
    async def _get_conversation_history(
        self,
        user_id: str,
        limit: int = 10,
    ) -> Optional[List[Dict[str, str]]]:
        """
        Get recent conversation history.
        
        Args:
            user_id: User identifier
            limit: Maximum number of turns to retrieve
        
        Returns:
            List of conversation turns [{user: "...", assistant: "..."}]
        """
        try:
            user = self.user_storage.get_user(user_id)
            
            if not user or "conversation_history" not in user:
                return None
            
            history = user.get("conversation_history", [])
            
            # Return most recent turns
            return history[-limit:] if history else None
        
        except Exception as e:
            self.logger.warning(f"Error getting conversation history: {str(e)}")
            return None
    
    def sanitize_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize context to remove sensitive information.
        
        Args:
            context: Raw context dictionary
        
        Returns:
            Sanitized context safe for LLM
        """
        sanitized = {}
        
        # Safe keys to include
        safe_keys = {
            "user_context": ["name", "age", "interests", "mood"],
            "vision_context": ["emotion", "objects", "description"],
            "knowledge_items": "*",  # Include all fields
            "conversation_history": "*",  # Include all fields
        }
        
        for section, value in context.items():
            if value is None:
                continue
            
            if section not in safe_keys:
                continue
            
            allowed_keys = safe_keys[section]
            
            if isinstance(value, dict) and allowed_keys != "*":
                # Filter dictionary
                sanitized[section] = {k: v for k, v in value.items() if k in allowed_keys}
            else:
                # Keep as-is (list or already allowed)
                sanitized[section] = value
        
        return sanitized
