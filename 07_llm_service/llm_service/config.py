"""Configuration for LLM Service."""

import os
from typing import Optional, Dict, Any
from dataclasses import dataclass

# Service Configuration
HOST = os.getenv("LLM_HOST", "0.0.0.0")
PORT = int(os.getenv("LLM_PORT", "8006"))
DEBUG = os.getenv("LLM_DEBUG", "False").lower() == "true"

# Online provider configuration; the model is selected by deployment config.
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_API_KEY_ENV = os.getenv("OPENROUTER_API_KEY_ENV", "OpenRouter_API_Key")

# Inference Configuration
TEMPERATURE = 0.2
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


@dataclass(frozen=True)
class ExpressionSettings:
    """Read once at service construction; invalid settings degrade capability."""
    enabled: bool
    provider: str
    model: str
    key_env: str
    temperature: float = 0.2
    max_tokens: int = 160
    timeout: float = 8.0
    error: str = ""

    @classmethod
    def from_env(cls):
        provider = os.getenv("LLM_PROVIDER", "openrouter").strip().lower()
        enabled_raw = os.getenv("LLM_ENABLED", "1").strip().lower()
        enabled = enabled_raw in {"1", "true"}
        model = os.getenv(f"{provider.upper()}_MODEL", "").strip()
        key_env = f"{provider.upper()}_API_KEY"
        if provider == "openrouter" and not os.getenv(key_env):
            key_env = os.getenv("OPENROUTER_API_KEY_ENV", "OpenRouter_API_Key")
        error = ""
        temperature, max_tokens, timeout = 0.2, 160, 8.0
        try:
            temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))
            max_tokens = int(os.getenv("LLM_MAX_TOKENS", "160"))
            timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "8"))
            if not (0 <= temperature <= 1.5 and 1 <= max_tokens <= 512 and 0 < timeout <= 120):
                raise ValueError()
        except ValueError:
            error = "invalid_generation_settings"
        if enabled_raw not in {"0", "1", "true", "false"}:
            error = "invalid_llm_enabled"
        elif provider not in {"groq", "gemini", "openrouter"}:
            error = "unsupported_provider"
        elif enabled and not model:
            error = "missing_model"
        elif enabled and not os.getenv(key_env):
            error = "missing_api_key"
        return cls(enabled, provider, model, key_env, temperature, max_tokens, timeout, error)

