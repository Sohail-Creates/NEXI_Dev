"""Configuration for LLM Service."""

import os
from typing import Optional, Dict, Any
from dataclasses import dataclass

# Service Configuration
HOST = os.getenv("LLM_HOST", "0.0.0.0")
PORT = int(os.getenv("LLM_PORT", "8006"))
DEBUG = os.getenv("LLM_DEBUG", "False").lower() == "true"

# Inference Configuration
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.6"))
TOP_P = float(os.getenv("LLM_TOP_P", "0.85"))

@dataclass
class InferenceConfig:
    """Configuration for inference."""
    temperature: float = TEMPERATURE
    top_p: float = TOP_P

def detect_language(text: str) -> str:
    """Detect if text contains Urdu/Arabic characters."""
    if not text:
        return "en"
    URDU_CHAR_RANGE = (0x0600, 0x06FF)
    for char in text:
        code = ord(char)
        if URDU_CHAR_RANGE[0] <= code <= URDU_CHAR_RANGE[1]:
            return "ur"
    return "en"

