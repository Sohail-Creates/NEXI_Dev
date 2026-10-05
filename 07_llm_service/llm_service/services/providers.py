"""Small provider contract and HTTP adapters; no retrieval or knowledge decisions."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Protocol
from urllib.parse import quote

import requests
from shared.credential_rotation import SecretPair

logger = logging.getLogger(__name__)


class LLMProvider(Protocol):
    model: str

    async def generate(self, prompt: str, max_tokens: int, temperature: float) -> tuple[str, dict, bool]: ...


class HTTPProvider:
    """One bounded request; existing credential rotation retries auth rejection only."""

    provider = "openrouter"

    def __init__(self, model: str, base_url: str, api_keys: SecretPair, timeout: float = 8.0):
        self.model = model
        self.base_url = base_url.strip().rstrip("/")
        self.api_keys = api_keys
        self.api_key = api_keys.current
        self.timeout = timeout
        self.is_available = bool(model and self.api_key)

    def request(self, prompt: str, max_tokens: int, temperature: float, key: str) -> tuple[str, dict, dict]:
        return (f"{self.base_url}/chat/completions",
                {"Authorization": f"Bearer {key}"},
                {"model": self.model, "messages": [{"role": "user", "content": prompt}],
                 "max_tokens": max_tokens, "temperature": temperature, "top_p": 0.9})

    def parse(self, data: dict[str, Any]) -> str:
        return data["choices"][0]["message"]["content"]

    def _generate(self, prompt: str, max_tokens: int, temperature: float, timeout: float) -> tuple[str, dict, bool]:
        start = time.monotonic()
        metadata = {"model": self.model, "source": self.provider}
        try:
            with requests.Session() as session:
                for key in self.api_keys.active:
                    remaining = timeout - (time.monotonic() - start)
                    if remaining <= 0:
                        raise requests.Timeout()
                    url, headers, payload = self.request(prompt, max_tokens, temperature, key)
                    response = session.post(url, json=payload, headers=headers, timeout=remaining)
                    if response.status_code not in {401, 403}:
                        break
                response.raise_for_status()
                text = self.parse(response.json())
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("empty_response")
                metadata["tokens_generated"] = len(text.split())
                return text.strip(), metadata, True
        except requests.Timeout:
            metadata["error"] = "timeout"
        except requests.HTTPError as exc:
            metadata["error"] = f"http_{exc.response.status_code}"
        except requests.RequestException:
            metadata["error"] = "provider_unavailable"
        except (ValueError, KeyError, IndexError, TypeError):
            metadata["error"] = "invalid_response"
        finally:
            metadata["elapsed_seconds"] = time.monotonic() - start
            logger.info("llm provider=%s model=%s latency=%.3f success=%s",
                        self.provider, self.model, metadata["elapsed_seconds"], "error" not in metadata)
        return "", metadata, False

    async def generate(self, prompt: str, max_tokens: int = 128, temperature: float = 0.2,
                       timeout: float | None = None) -> tuple[str, dict, bool]:
        if not self.api_key or not self.model:
            return "", {"error": "provider_not_configured"}, False
        limit = timeout or self.timeout
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._generate, prompt, max_tokens, temperature, limit), limit)
            self.is_available = result[2]
            return result
        except asyncio.TimeoutError:
            self.is_available = False
            return "", {"error": "timeout"}, False

    def is_healthy(self) -> bool:
        # Capability status, not a costly per-health-check provider request.
        return self.is_available


class GroqProvider(HTTPProvider):
    provider = "groq"


class GeminiProvider(HTTPProvider):
    provider = "gemini"

    def request(self, prompt: str, max_tokens: int, temperature: float, key: str) -> tuple[str, dict, dict]:
        return (f"{self.base_url}/models/{quote(self.model, safe='')}:generateContent",
                {"x-goog-api-key": key},
                {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                 "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature}})

    def parse(self, data: dict[str, Any]) -> str:
        return "".join(part["text"] for part in data["candidates"][0]["content"]["parts"]
                       if not part.get("thought", False))
