"""Configuration-only provider selection behind the existing generation REST API."""

import logging
import os
from llm_service.config import ExpressionSettings
from llm_service.services.providers import HTTPProvider, GroqProvider, GeminiProvider
from shared.credential_rotation import SecretPair

logger = logging.getLogger(__name__)


def get_llm_provider(settings: ExpressionSettings) -> HTTPProvider:
    factories = {
        "openrouter": (HTTPProvider, "https://openrouter.ai/api/v1"),
        "groq": (GroqProvider, "https://api.groq.com/openai/v1"),
        "gemini": (GeminiProvider, "https://generativelanguage.googleapis.com/v1beta"),
    }
    if settings.provider not in factories:
        raise ValueError("unsupported_provider")
    adapter, base_url = factories[settings.provider]
    base_url = os.getenv(f"{settings.provider.upper()}_BASE_URL", base_url)
    keys = SecretPair.from_env(settings.key_env, f"{settings.key_env}_PREVIOUS", required=False)
    return adapter(settings.model, base_url, keys, settings.timeout)


class ExpressionService:
    def __init__(self, settings: ExpressionSettings | None = None):
        self.settings = settings or ExpressionSettings.from_env()
        self.model = self.settings.model
        self.provider = self.settings.provider
        self.client = None
        self.last_error = self.settings.error or ("llm_disabled" if not self.settings.enabled else "")
        if self.settings.enabled and not self.settings.error:
            self.client = get_llm_provider(self.settings)
        logger.info("llm enabled=%s provider=%s reason=%s", self.settings.enabled,
                    self.provider, self.settings.error or "configured")

    async def generate(self, prompt: str, max_tokens: int | None = None,
                       temperature: float | None = None) -> tuple[str, dict, bool]:
        if self.client is None:
            return "", {"error": self.settings.error or "llm_disabled", "fallback_ready": True}, False
        result = await self.client.generate(
            prompt, min(max_tokens or self.settings.max_tokens, self.settings.max_tokens),
            self.settings.temperature if temperature is None else temperature)
        self.last_error = "" if result[2] else result[1].get("error", "provider_unavailable")
        return result

    def is_healthy(self) -> bool:
        return bool(self.client and self.client.is_healthy())

    def status(self) -> dict:
        return {"enabled": self.settings.enabled, "provider": self.provider, "model": self.model,
                "available": self.is_healthy(), "fallback_ready": True,
                "reason": self.last_error}
