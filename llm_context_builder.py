"""
LLM Context Builder for Test Suite

Properly formats context JSON for LLM service calls with all necessary information:
- User metadata (id, age, name, mood)
- Vision context (emotion scores, face data)
- Knowledge base context (learned objects, facts)
- Conversation history
- Language and parameters

This ensures LLM receives complete context for informed responses.
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
import json
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

@dataclass
class UserContext:
    """User profile context."""
    user_id: str
    name: str = ""
    age: Optional[int] = None
    gender: Optional[str] = None
    mood: str = "neutral"
    language: str = "en"
    enrolled_timestamp: Optional[str] = None
    last_interaction: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary, excluding None values."""
        data = asdict(self)
        return {k: v for k, v in data.items() if v is not None}


@dataclass
class VisionContext:
    """Vision/emotion context."""
    face_detected: bool = False
    mood: str = "neutral"
    emotion_scores: Dict[str, float] = None
    confidence: float = 0.0
    face_count: int = 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "face_detected": self.face_detected,
            "mood": self.mood,
            "emotion_scores": self.emotion_scores or {},
            "confidence": self.confidence,
            "face_count": self.face_count,
        }


@dataclass
class KnowledgeItem:
    """Single knowledge base item."""
    query: str
    answer: str
    label: Optional[str] = None
    embeddings: Optional[List[float]] = None
    category: Optional[str] = None
    created_timestamp: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            k: v for k, v in asdict(self).items() if v is not None
        }


class ConversationHistory:
    """Manages conversation history."""
    
    def __init__(self, max_turns: int = 50):
        self.turns: List[Dict[str, Any]] = []
        self.max_turns = max_turns
    
    def add_turn(self, user_message: str, assistant_response: str):
        """Add a conversation turn."""
        self.turns.append({
            "user": user_message,
            "assistant": assistant_response,
            "timestamp": datetime.now().isoformat(),
        })
        
        # Keep only recent turns
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]
    
    def get_recent(self, num_turns: int = 5) -> List[Dict]:
        """Get recent conversation turns."""
        return self.turns[-num_turns:] if self.turns else []
    
    def to_list(self) -> List[Dict]:
        """Get all conversation history."""
        return self.turns.copy()


class LLMContextBuilder:
    """
    Builds comprehensive context for LLM service calls.
    
    Assembles all necessary context information and formats it properly
    for LLM inference with full metadata including user, vision, knowledge, and history.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def build_context(
        self,
        query: str,
        user_id: str,
        user_name: str = "",
        user_age: Optional[int] = None,
        mood: str = "neutral",
        emotion_scores: Optional[Dict[str, float]] = None,
        language: str = "en",
        knowledge_items: Optional[List[Dict]] = None,
        conversation_history: Optional[List[Dict]] = None,
        additional_metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Build complete context for LLM call.
        
        Args:
            query: User's question/command
            user_id: User identifier
            user_name: User's name
            user_age: User's age
            mood: Detected mood (happy, sad, angry, etc.)
            emotion_scores: Full emotion confidence scores
            language: Language ('en' or 'ur')
            knowledge_items: Items from knowledge base
            conversation_history: Previous conversation turns
            additional_metadata: Any other metadata
        
        Returns:
            Complete context dictionary formatted for LLM service
        """
        try:
            # Build user context
            user_ctx = UserContext(
                user_id=user_id,
                name=user_name,
                age=user_age,
                mood=mood,
                language=language,
            )
            
            # Build vision context
            vision_ctx = VisionContext(
                face_detected=mood != "neutral",
                mood=mood,
                emotion_scores=emotion_scores,
                confidence=max(emotion_scores.values()) if emotion_scores else 0.0,
            )
            
            # Prepare knowledge items
            knowledge_list = knowledge_items if knowledge_items else []
            
            # Prepare conversation history
            history_list = conversation_history if conversation_history else []
            
            # Build comprehensive context
            context = {
                "query": query,
                "language": language,
                "user_context": user_ctx.to_dict(),
                "vision_context": vision_ctx.to_dict(),
                "knowledge_items": knowledge_list,
                "conversation_history": history_list,
                "metadata": {
                    "query_type": self._classify_query(query),
                    "context_timestamp": datetime.now().isoformat(),
                    "has_emotion_data": bool(emotion_scores),
                    "knowledge_base_size": len(knowledge_list),
                    "conversation_turns": len(history_list),
                }
            }
            
            # Add additional metadata if provided
            if additional_metadata:
                context["metadata"].update(additional_metadata)
            
            self.logger.debug(f"Context built for user {user_id}: mood={mood}, "
                            f"knowledge_items={len(knowledge_list)}, "
                            f"history_turns={len(history_list)}")
            
            return context
            
        except Exception as e:
            self.logger.error(f"Error building context: {e}")
            # Return minimal context on error
            return {
                "query": query,
                "language": language,
                "user_context": {"user_id": user_id},
                "metadata": {"error": str(e)},
            }
    
    def _classify_query(self, query: str) -> str:
        """Classify query type for better LLM routing."""
        query_lower = query.lower()
        
        if any(word in query_lower for word in ["how", "what", "why", "where", "when", "who"]):
            return "question"
        elif any(word in query_lower for word in ["help", "please", "sorry", "sad", "angry"]):
            return "emotional_support"
        elif any(word in query_lower for word in ["create", "make", "build", "imagine", "invent"]):
            return "creative"
        elif any(word in query_lower for word in ["teach", "learn", "explain", "understand"]):
            return "learning"
        else:
            return "general"
    
    def format_for_direct_llm(
        self,
        context: Dict[str, Any],
        max_response_tokens: int = 150,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """
        Format context for direct LLM service call (port 8006).
        
        Args:
            context: Context dict from build_context()
            max_response_tokens: Max tokens for response
            temperature: Sampling temperature
        
        Returns:
            JSON payload for LLM service /api/v1/generate endpoint
        """
        return {
            "query": context.get("query", ""),
            "language": context.get("language", "en"),
            "user_context": context.get("user_context"),
            "vision_context": context.get("vision_context"),
            "knowledge_items": context.get("knowledge_items", []),
            "conversation_history": context.get("conversation_history", []),
            "max_response_tokens": max_response_tokens,
            "temperature": temperature,
        }
    
    def format_for_central_server(
        self,
        context: Dict[str, Any],
        include_vision: bool = True,
        include_knowledge: bool = True,
    ) -> Dict[str, Any]:
        """
        Format context for Central Server /llm/generate-response call.
        
        Args:
            context: Context dict from build_context()
            include_vision: Include vision context
            include_knowledge: Include knowledge items
        
        Returns:
            JSON payload for Central Server
        """
        return {
            "user_id": context.get("user_context", {}).get("user_id", ""),
            "query": context.get("query", ""),
            "language": context.get("language", "en"),
            "include_vision": include_vision,
            "include_knowledge": include_knowledge,
            # Optional: Send metadata for enhanced context (Central Server can extract from user DB)
            "metadata": context.get("metadata", {}),
        }


def create_sample_context() -> Dict[str, Any]:
    """Create a sample context for testing."""
    builder = LLMContextBuilder()
    
    context = builder.build_context(
        query="What is a cat?",
        user_id="user_123",
        user_name="Sara",
        user_age=12,
        mood="happy",
        emotion_scores={
            "happy": 0.85,
            "neutral": 0.10,
            "sad": 0.03,
            "angry": 0.02,
        },
        language="en",
        knowledge_items=[
            {
                "query": "animal",
                "answer": "Cats are domesticated felines",
                "category": "animals",
            }
        ],
        conversation_history=[
            {
                "user": "Hello",
                "assistant": "Hello! How can I help?",
            }
        ],
    )
    
    return context


if __name__ == "__main__":
    # Test context builder
    builder = LLMContextBuilder()
    context = create_sample_context()
    
    print("\n" + "=" * 70)
    print("SAMPLE LLM CONTEXT")
    print("=" * 70)
    print(json.dumps(context, indent=2))
    
    print("\n" + "=" * 70)
    print("FOR DIRECT LLM SERVICE:")
    print("=" * 70)
    llm_payload = builder.format_for_direct_llm(context)
    print(json.dumps(llm_payload, indent=2))
    
    print("\n" + "=" * 70)
    print("FOR CENTRAL SERVER:")
    print("=" * 70)
    server_payload = builder.format_for_central_server(context)
    print(json.dumps(server_payload, indent=2))
