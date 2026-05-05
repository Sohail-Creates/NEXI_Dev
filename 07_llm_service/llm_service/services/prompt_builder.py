"""Prompt builder for LLM service - constructs system and user prompts with context."""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class PromptBuilder:
    """Builds system and user prompts with context information."""
    
    def __init__(self, config):
        """
        Initialize prompt builder.
        
        Args:
            config: Service configuration with system prompts
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def build_full_prompt(
        self,
        user_query: str,
        language: str = "en",
        user_context: Optional[Dict[str, Any]] = None,
        vision_context: Optional[Dict[str, Any]] = None,
        knowledge_items: Optional[List[Dict[str, Any]]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        token_counter: Optional[callable] = None,
    ) -> tuple[str, Dict[str, int]]:
        """
        Build complete prompt with context.

        Args:
            user_query: User's question or statement
            language: 'en' for English, 'ur' for Urdu
            user_context: User profile data {name, age, mood, interests, etc}
            vision_context: Current visual information {objects, mood, etc}
            knowledge_items: Relevant knowledge from TeachMe service
            conversation_history: Previous conversation turns
            token_counter: Function to estimate token count

        Returns:
            Tuple of (complete_prompt, token_breakdown)
        """
        token_breakdown = {}
        
        # Extract context for system prompt adaptation
        age = None
        mood = None
        question_type = self._detect_question_type(user_query)
        
        if user_context:
            age = user_context.get("age")
            mood_data = user_context.get("mood")
            
            # Extract mood string from dict if needed
            if isinstance(mood_data, dict):
                mood = mood_data.get("state") or mood_data.get("emotion") or None
            elif isinstance(mood_data, str):
                mood = mood_data
        
        # Get system prompt with context awareness
        system_prompt = self.config.get_system_prompt(
            language=language,
            age=age,
            mood=mood,
            question_type=question_type,
        )
        system_tokens = self._rough_token_count(system_prompt)
        token_breakdown["system_prompt"] = system_tokens
        
        # Build context section
        context_section = self._build_context_section(
            language,
            user_context,
            vision_context,
            knowledge_items,
        )
        context_tokens = self._rough_token_count(context_section)
        token_breakdown["context"] = context_tokens
        
        # Build conversation history section
        history_section = self._build_history_section(language, conversation_history)
        history_tokens = self._rough_token_count(history_section)
        token_breakdown["history"] = history_tokens
        
        # Build final prompt
        if language.lower() in ["ur", "urdu", "اردو"]:
            prompt = f"""{system_prompt}

=== معلومات ===
{context_section}

{history_section}

صارف کی سوال: {user_query}

NEXI (معاون): """
        else:
            prompt = f"""{system_prompt}

=== Context ===
{context_section}

{history_section}

User: {user_query}

NEXI (Assistant): """
        
        total_tokens = self._rough_token_count(prompt)
        token_breakdown["total"] = total_tokens
        
        return prompt, token_breakdown
    
    def _build_context_section(
        self,
        language: str,
        user_context: Optional[Dict[str, Any]],
        vision_context: Optional[Dict[str, Any]],
        knowledge_items: Optional[List[Dict[str, Any]]],
    ) -> str:
        """Build context section of prompt - optimized for character budget (max ~2000 chars for safe margin)."""
        sections = []
        
        # User profile context (only if non-empty)
        if user_context and any(user_context.values()):
            sections.append(self._format_user_context(language, user_context))
        
        # Vision/mood context (only if non-empty)
        if vision_context and any(vision_context.values()):
            sections.append(self._format_vision_context(language, vision_context))
        
        # Knowledge items - FIXED: Reduced from 3 to 2 items limit for additional character savings
        if knowledge_items:
            sections.append(self._format_knowledge_items(language, knowledge_items[:2]))
        
        return "\n\n".join(sections) if sections else ""
    
    def _format_user_context(self, language: str, user_context: Dict[str, Any]) -> str:
        """Format user profile information."""
        if language.lower() in ["ur", "urdu", "اردو"]:
            lines = ["=== صارف کی معلومات ==="]
            
            if "name" in user_context:
                lines.append(f"نام: {user_context['name']}")
            if "age" in user_context:
                lines.append(f"عمر: {user_context['age']}")
            if "interests" in user_context:
                lines.append(f"دلچسپیاں: {', '.join(user_context['interests'])}")
            if "mood" in user_context and user_context.get("mood"):
                mood = user_context["mood"]
                # Handle both dict formats: {"state": "happy"} and {"emotion": "happy"}
                if isinstance(mood, dict):
                    mood_str = mood.get('state') or mood.get('emotion') or 'neutral'
                else:
                    mood_str = str(mood)
                lines.append(f"موڈ: {mood_str}")
            
            return "\n".join(lines)
        else:
            lines = ["=== User Profile ==="]
            
            if "name" in user_context:
                lines.append(f"Name: {user_context['name']}")
            if "age" in user_context:
                lines.append(f"Age: {user_context['age']}")
            if "interests" in user_context:
                lines.append(f"Interests: {', '.join(user_context['interests'])}")
            if "mood" in user_context and user_context.get("mood"):
                mood = user_context["mood"]
                # Handle both dict formats: {"state": "happy"} and {"emotion": "happy"}
                if isinstance(mood, dict):
                    mood_str = mood.get('state') or mood.get('emotion') or 'neutral'
                    confidence = mood.get("confidence", 0)
                    lines.append(f"Current Mood: {mood_str} (confidence: {confidence:.1%})")
                else:
                    lines.append(f"Current Mood: {mood}")
            
            return "\n".join(lines)
    
    def _format_vision_context(self, language: str, vision_context: Dict[str, Any]) -> str:
        """Format visual information."""
        if language.lower() in ["ur", "urdu", "اردو"]:
            lines = ["=== موجودہ ماحول ==="]
            
            if "objects" in vision_context and vision_context["objects"]:
                objects_list = ", ".join(vision_context["objects"])
                lines.append(f"دیکھے جانے والے اشیاء: {objects_list}")
            
            if "emotion" in vision_context:
                lines.append(f"جذبات: {vision_context['emotion']}")
            
            if "description" in vision_context:
                lines.append(f"نوٹ: {vision_context['description']}")
            
            return "\n".join(lines)
        else:
            lines = ["=== Current Environment ==="]
            
            if "objects" in vision_context and vision_context["objects"]:
                objects_list = ", ".join(vision_context["objects"])
                lines.append(f"Visible objects: {objects_list}")
            
            if "emotion" in vision_context:
                lines.append(f"Emotional context: {vision_context['emotion']}")
            
            if "description" in vision_context:
                lines.append(f"Note: {vision_context['description']}")
            
            return "\n".join(lines)
    
    def _format_knowledge_items(
        self,
        language: str,
        knowledge_items: List[Dict[str, Any]]
    ) -> str:
        """Format relevant knowledge items - FIXED: 4 items→2, descriptions 200→80 chars to reduce token size."""
        if not knowledge_items:
            return ""
        
        if language.lower() in ["ur", "urdu", "اردو"]:
            lines = ["=== متعلقہ معلومات ==="]
            
            for item in knowledge_items[:2]:  # FIXED: Reduced from 4 to 2 items to save ~240 chars per knowledge item
                if "name" in item:
                    lines.append(f"• {item['name']}")
                if "description" in item:
                    lines.append(f"  {item['description'][:80]}")  # FIXED: Reduced from 200 to 80 chars per item
            
            return "\n".join(lines)
        else:
            lines = ["=== Relevant Knowledge ==="]
            
            for item in knowledge_items[:2]:  # FIXED: Reduced from 4 to 2 items to save ~240 chars per knowledge item
                if "name" in item:
                    lines.append(f"• {item['name']}")
                if "description" in item:
                    lines.append(f"  {item['description'][:80]}")  # FIXED: Reduced from 200 to 80 chars per item
            
            return "\n".join(lines)
    
    def _build_history_section(
        self,
        language: str,
        conversation_history: Optional[List[Dict[str, str]]],
        max_tokens: int = 3000,
    ) -> str:
        """Build conversation history section - FIXED: 10→5 exchanges, responses 150→100 chars to reduce token size."""
        if not conversation_history:
            return ""
        
        lines = []
        
        if language.lower() in ["ur", "urdu", "اردو"]:
            lines.append("=== حالیہ گفتگو ===")
            
            for exchange in conversation_history[-5:]:  # FIXED: Reduced from 10 to 5 exchanges to save ~500 chars
                if "user" in exchange:
                    lines.append(f"صارف: {exchange['user']}")
                if "assistant" in exchange:
                    lines.append(f"NEXI: {exchange['assistant'][:100]}")  # FIXED: Reduced from 150 to 100 chars per response
        else:
            lines.append("=== Recent Conversation ===")
            
            for exchange in conversation_history[-5:]:  # FIXED: Reduced from 10 to 5 exchanges to save ~500 chars
                if "user" in exchange:
                    lines.append(f"User: {exchange['user']}")
                if "assistant" in exchange:
                    lines.append(f"NEXI: {exchange['assistant'][:100]}")  # FIXED: Reduced from 150 to 100 chars per response
        
        return "\n".join(lines)
    
    def _rough_token_count(self, text: str) -> int:
        """
        Rough token count estimate.
        
        Assumes 1 token ≈ 4 characters for English,
        1 token ≈ 1.5 characters for Urdu.
        """
        if not text:
            return 0
        
        # Check if text contains Urdu characters
        urdu_chars = sum(1 for char in text if 0x0600 <= ord(char) <= 0x06FF)
        english_chars = len(text) - urdu_chars
        
        # Estimate tokens
        english_tokens = english_chars / 4
        urdu_tokens = urdu_chars / 1.5
        
        return int(english_tokens + urdu_tokens + 10)  # Add 10 for special tokens
    
    def _detect_question_type(self, query: str) -> Optional[str]:
        """
        Detect the type of question being asked.
        
        Args:
            query: User's question/query
        
        Returns:
            Question type: technical, emotional_support, creative, learning, social, or None
        """
        query_lower = query.lower()
        
        # Technical indicators
        technical_keywords = [
            "code", "program", "python", "javascript", "html", "css", "algorithm",
            "function", "variable", "debug", "error", "how to code", "how do i",
            "what is", "explain", "math", "science", "physics", "chemistry",
            "equation", "formula", "calculate", "compute"
        ]
        
        # Emotional support indicators
        emotional_keywords = [
            "feel", "feeling", "sad", "happy", "angry", "scared", "lonely",
            "friend", "friendship", "love", "heartbreak", "depression", "anxiety",
            "stressed", "worried", "help me", "what do i do", "advice", ""
        ]
        
        # Creative indicators
        creative_keywords = [
            "story", "write", "poem", "art", "draw", "music", "song", "create",
            "creative", "imagine", "idea", "inspiration", "design", "color",
            "character", "plot", "scene"
        ]
        
        # Learning indicators
        learning_keywords = [
            "learn", "study", "homework", "assignment", "project", "lesson",
            "teach", "explain", "understand", "how to", "tutorial", "guide",
            "practice", "exercise", "example"
        ]
        
        # Social indicators
        social_keywords = [
            "friend", "people", "social", "relationship", "talk", "say",
            "mean", "understand", "help with", "what should i", "how do i",
            "bullying", "peer", "group"
        ]
        
        # Check keywords
        for keyword in technical_keywords:
            if keyword in query_lower:
                return "technical"
        
        for keyword in emotional_keywords:
            if keyword in query_lower:
                return "emotional_support"
        
        for keyword in creative_keywords:
            if keyword in query_lower:
                return "creative"
        
        for keyword in learning_keywords:
            if keyword in query_lower:
                return "learning"
        
        for keyword in social_keywords:
            if keyword in query_lower:
                return "social"
        
        return None
    
    
    def sanitize_context(
        self,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Sanitize context to remove sensitive information.
        
        Args:
            context: Context dictionary to sanitize
        
        Returns:
            Sanitized context
        """
        sanitized = {}
        
        # Safe keys to include
        safe_keys = [
            "name",
            "age",
            "interests",
            "mood",
            "emotion",
            "objects",
            "description",
        ]
        
        for key, value in context.items():
            if key in safe_keys:
                sanitized[key] = value
        
        return sanitized
