"""Configuration for LLM Service - SmolLM2-1.7B-Instruct."""

import os
from typing import Optional, Dict, Any
from dataclasses import dataclass

# Import flexible system prompt manager
from llm_service.system_prompts import get_prompt_manager

# Model Configuration
MODEL_NAME = "HuggingFaceTB/SmolLM2-1.7B-Instruct"
MODEL_PATH = os.getenv("LLM_MODEL_PATH", "./model")
DEVICE = os.getenv("LLM_DEVICE", "cpu")  # "cpu" or "cuda"

# Service Configuration
HOST = os.getenv("LLM_HOST", "0.0.0.0")
PORT = int(os.getenv("LLM_PORT", "8006"))
DEBUG = os.getenv("LLM_DEBUG", "False").lower() == "true"

# Model Inference Configuration
MAX_CONTEXT_TOKENS = int(os.getenv("LLM_MAX_CONTEXT_TOKENS", "16384"))  # Increased to support full context + history
MAX_RESPONSE_TOKENS = int(os.getenv("LLM_MAX_RESPONSE_TOKENS", "128"))  # Optimal balance for speed/quality
INFERENCE_TIMEOUT = float(os.getenv("LLM_INFERENCE_TIMEOUT", "80.0"))  # CPU inference fallback: 80s timeout (reasonable limit)
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.6"))  # Reduced from 0.7 for faster deterministic inference
TOP_P = float(os.getenv("LLM_TOP_P", "0.85"))  # Reduced from 0.9 for faster inference
REPETITION_PENALTY = float(os.getenv("LLM_REPETITION_PENALTY", "1.2"))  # Increase to avoid repetition


# Token Budget Allocation
TOKEN_BUDGET = {
    "system_prompt": 400,
    "user_profile": 200,
    "vision_context": 200,
    "knowledge_items": 400,
    "conversation_history": 3000,
    "user_query": 200,
    "response": 150,
    "buffer": 1642,
}

# Language Detection (Unicode Ranges)
URDU_CHAR_RANGE = (0x0600, 0x06FF)  # Arabic/Urdu Unicode range


@dataclass
class ModelLoadConfig:
    """Configuration for model loading."""
    model_name: str = MODEL_NAME
    model_path: str = MODEL_PATH
    device: str = DEVICE
    dtype: Optional[str] = None  # "float32" or "float16" for quantization
    low_memory: bool = True  # Use memory-efficient loading


@dataclass
class InferenceConfig:
    """Configuration for inference."""
    max_context_tokens: int = MAX_CONTEXT_TOKENS
    max_response_tokens: int = MAX_RESPONSE_TOKENS
    temperature: float = TEMPERATURE
    top_p: float = TOP_P
    repetition_penalty: float = REPETITION_PENALTY
    timeout: float = INFERENCE_TIMEOUT


def get_system_prompt(
    language: str = "en",
    age: Optional[int] = None,
    mood: Optional[str] = None,
    question_type: Optional[str] = None,
    custom_context: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Get system prompt adapted to user context.
    
    Uses the flexible system prompt manager to generate context-aware prompts.
    
    Args:
        language: "en" for English, "ur" for Urdu
        age: User age (optional)
        mood: User mood/emotional state (optional)
        question_type: Type of question being asked (optional)
        custom_context: Additional context fields (optional)
    
    Returns:
        System prompt adapted to all provided context
    """
    prompt_manager = get_prompt_manager()
    return prompt_manager.get_system_prompt(
        language=language,
        age=age,
        mood=mood,
        question_type=question_type,
        custom_context=custom_context,
    )


def detect_language(text: str) -> str:
    """
    Detect if text contains Urdu/Arabic characters.
    Returns 'ur' for Urdu, 'en' for English.
    """
    if not text:
        return "en"
    
    for char in text:
        code = ord(char)
        if URDU_CHAR_RANGE[0] <= code <= URDU_CHAR_RANGE[1]:
            return "ur"
    
    return "en"

