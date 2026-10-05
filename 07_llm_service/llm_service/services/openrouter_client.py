"""Import-compatible OpenRouter adapter using the shared HTTP implementation."""

from typing import Optional
from llm_service.config import OPENROUTER_MODEL, OPENROUTER_BASE_URL, OPENROUTER_API_KEY_ENV
from llm_service.services.providers import HTTPProvider
from shared.credential_rotation import SecretPair


class OpenRouterClient(HTTPProvider):
    provider = "openrouter"

    def __init__(self, api_key: Optional[str] = None, timeout: float = 8.0):
        keys = SecretPair(api_key) if api_key else SecretPair.from_env(
            OPENROUTER_API_KEY_ENV, f"{OPENROUTER_API_KEY_ENV}_PREVIOUS", required=False)
        super().__init__(OPENROUTER_MODEL, OPENROUTER_BASE_URL, keys, timeout)
