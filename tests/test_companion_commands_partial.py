"""Generic companion behavior through the authoritative command/RAG paths."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01_central_server"))
import basic_commands
import restricted_rag as rag


class Store:
    async def search_by_embedding(self, **kwargs):
        return {"results": [{"id": "camera", "type": "object", "similarity": .99,
                             "data": {"name": "My blue camera"}}]}


class Formatter:
    def __init__(self, text):
        self.text, self.calls = text, 0

    async def generate_response(self, prompt, **kwargs):
        self.calls += 1
        return True, {"response": self.text}


@pytest.mark.parametrize("query", ["Goodbye", "Goodbye.", "good bye", "Goodbye goodbye.",
                                  "Okay, goodbye.", "Bye.", "good bye good bye"])
async def test_farewells_bypass_language_retrieval_and_llm(query, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("command entered language/retrieval processing")
    monkeypatch.setattr(rag, "require_english", forbidden)
    formatter = Formatter("unused")
    result = await rag.RestrictedRAGPipeline(object(), formatter).answer(query)
    assert result.source == "basic_command" and result.response == "Goodbye!"
    assert basic_commands.is_stop_command(query, rag.RAG_FAREWELL_PHRASES)
    assert formatter.calls == 0


@pytest.mark.parametrize("query", ["Don't say goodbye", "Say goodbye to my friend", "goodbye camera",
                                  "Okay goodbye and tell me about my camera"])
def test_mentions_do_not_terminate(query):
    assert not basic_commands.is_stop_command(query, rag.RAG_FAREWELL_PHRASES)
    assert basic_commands.classify_basic_command(query) is None


@pytest.mark.parametrize("query", ["Okay", "Cool", "Thanks", "Hello"])
async def test_bounded_social_inputs_bypass_llm(query):
    formatter = Formatter("unused")
    result = await rag.RestrictedRAGPipeline(object(), formatter).answer(query)
    assert result.source == "basic_command" and formatter.calls == 0


async def test_single_known_entity_missing_property_keeps_known_information():
    text = "This is your blue camera. " + rag.PARTIAL_KNOWLEDGE_NOTICE
    formatter = Formatter(text)
    result = await rag.RestrictedRAGPipeline(Store(), formatter).answer("Where is my blue camera?")
    assert result.response == text and result.response_source == "llm"
    assert result.retrieved_record_ids == ("camera",) and formatter.calls == 1


async def test_missing_property_notice_cannot_hide_unsupported_claim():
    formatter = Formatter("Your blue camera is in Paris. " + rag.PARTIAL_KNOWLEDGE_NOTICE)
    result = await rag.RestrictedRAGPipeline(Store(), formatter).answer("Where is my blue camera?")
    assert result.fallback_reason == "grounding_rejected"
    assert "Paris" not in result.response
    assert result.response.endswith(rag.PARTIAL_KNOWLEDGE_NOTICE)
    assert formatter.calls == 1
