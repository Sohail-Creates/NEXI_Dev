"""Optional expression layer: real adapter serialization, bounded failures, no retrieval changes."""

import asyncio
import sys
from pathlib import Path
import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "07_llm_service"))
from llm_service.config import ExpressionSettings
from llm_service.services.expression_service import ExpressionService, get_llm_provider
from shared.clients.llm_client import LLMServiceClient


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "1")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_MODEL", "fixture-chat")
    monkeypatch.setenv("GROQ_API_KEY", "fixture-secret")
    return monkeypatch


async def test_disabled_calls_neither_rest_nor_provider(configured):
    configured.setenv("LLM_ENABLED", "0")
    configured.delenv("GROQ_API_KEY")
    settings = ExpressionSettings.from_env()
    assert not settings.error
    service = ExpressionService(settings)
    assert service.client is None
    assert not (await service.generate("approved memory"))[2]
    ok, result = await LLMServiceClient().generate_response("approved memory")
    assert not ok and result["error"] == "llm_disabled"
    assert service.status()["fallback_ready"]


@pytest.mark.parametrize("variable,value,error", [
    ("GROQ_API_KEY", "", "missing_api_key"),
    ("GROQ_MODEL", "", "missing_model"),
    ("LLM_PROVIDER", "unknown", "unsupported_provider"),
    ("LLM_TIMEOUT_SECONDS", "nan", "invalid_generation_settings"),
    ("LLM_ENABLED", "maybe", "invalid_llm_enabled"),
])
async def test_invalid_configuration_degrades_without_crashing(configured, variable, value, error):
    configured.setenv(variable, value)
    service = ExpressionService()
    assert service.settings.error == error
    assert not (await service.generate("approved memory"))[2]
    assert not service.status()["available"]


@pytest.mark.parametrize("provider", ["groq", "gemini", "openrouter"])
async def test_provider_wire_contract_and_success(configured, provider):
    configured.setenv("LLM_PROVIDER", provider)
    configured.setenv(f"{provider.upper()}_MODEL", "fixture-chat")
    configured.setenv(f"{provider.upper()}_API_KEY", "fixture-secret")
    calls = []

    def post(session, url, **kwargs):
        calls.append((url, kwargs))
        response = requests.Response()
        response.status_code = 200
        response.json = lambda: ({"candidates": [{"content": {"parts": [{"text": "Your color is blue."}]}}]}
                                if provider == "gemini" else
                                {"choices": [{"message": {"content": "Your color is blue."}}]})
        return response

    configured.setattr(requests.Session, "post", post)
    service = ExpressionService()
    text, metadata, ok = await service.generate("Only memory: My color is blue.", 100, 0.2)
    assert ok and text == "Your color is blue." and metadata["source"] == provider
    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url.startswith("https://") and kwargs["timeout"] <= service.settings.timeout
    payload = kwargs["json"]
    if provider == "gemini":
        assert kwargs["headers"]["x-goog-api-key"] == "fixture-secret"
        assert payload["generationConfig"]["maxOutputTokens"] == 100
        assert "generateContent" in url
    else:
        assert kwargs["headers"]["Authorization"] == "Bearer fixture-secret"
        assert payload["messages"] == [{"role": "user", "content": "Only memory: My color is blue."}]
        assert payload["max_tokens"] == 100
    assert service.status()["available"]
    assert "fixture-secret" not in str(service.status())


@pytest.mark.parametrize("failure", ["http", "timeout", "empty", "malformed", "offline"])
async def test_provider_failure_is_bounded_and_degraded(configured, failure):
    calls = []
    def post(session, url, **kwargs):
        calls.append(url)
        if failure == "timeout":
            raise requests.Timeout()
        if failure == "offline":
            raise requests.ConnectionError()
        response = requests.Response()
        response.status_code = 429 if failure == "http" else 200
        response.json = lambda: ({} if failure == "malformed" else {"choices": [{"message": {"content": ""}}]})
        return response
    configured.setattr(requests.Session, "post", post)
    service = ExpressionService()
    assert not (await service.generate("approved memory"))[2]
    assert len(calls) == 1 and not service.status()["available"]


async def test_shared_client_disabled_rag_still_returns_memory(configured):
    configured.setenv("LLM_ENABLED", "0")
    sys.path.insert(0, str(ROOT / "01_central_server"))
    from restricted_rag import RestrictedRAGPipeline
    class Store:
        async def search_by_embedding(self, **kwargs):
            return {"results": [{"id": "color", "type": "fact", "similarity": .99,
                                 "data": {"subject": "My color", "predicate": "is", "object": "blue"}}]}
    result = await RestrictedRAGPipeline(Store(), LLMServiceClient()).answer("Tell me about my color")
    assert result.response == "Your color is blue."


def test_runtime_boundaries_remain_provider_free():
    for path in [ROOT / "test.py", ROOT / "01_central_server/restricted_rag.py"]:
        source = path.read_text(encoding="utf-8")
        assert "api.groq.com" not in source and "generativelanguage.googleapis.com" not in source
        assert "openrouter.ai" not in source


@pytest.mark.parametrize("response", ["", "   ", None, 123])
async def test_invalid_formatter_output_retains_approved_knowledge(response):
    sys.path.insert(0, str(ROOT / "01_central_server"))
    from restricted_rag import RestrictedRAGPipeline
    class Store:
        async def search_by_embedding(self, **kwargs):
            return {"results": [{"id": "color", "type": "fact", "similarity": .99,
                                 "data": {"subject": "My color", "predicate": "is", "object": "blue"}}]}
    class InvalidFormatter:
        async def generate_response(self, *args, **kwargs):
            return True, {"response": response}
    result = await RestrictedRAGPipeline(Store(), InvalidFormatter()).answer("Tell me about my color")
    assert result.response == "Your color is blue."
