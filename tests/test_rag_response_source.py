"""Composition provenance does not change retrieval or grounded answers."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01_central_server"))
from restricted_rag import RestrictedRAGPipeline


class Store:
    def __init__(self, records):
        self.records = records

    async def search_by_embedding(self, **kwargs):
        return {"results": self.records}


FACT = {"id": "color", "type": "fact", "similarity": .99,
        "data": {"subject": "My color", "predicate": "is", "object": "blue"}}
OBJECT = {"id": "mug", "type": "object", "similarity": .98,
          "data": {"name": "My travel mug"}}


class Formatter:
    def __init__(self, text, success=True):
        self.text, self.success, self.calls = text, success, 0

    async def generate_response(self, *args, **kwargs):
        self.calls += 1
        return self.success, {"response": self.text, "failure_reason": "timeout",
                              "metadata": {"source": "fixture", "model": "configured-model",
                                           "elapsed_seconds": 1.72}}


@pytest.mark.parametrize("records,query,text", [
    ([FACT], "Tell me about my favorite color", "Your color is blue."),
    ([OBJECT], "Tell me about my travel mug", "This is your travel mug."),
    ([FACT, OBJECT], "My color and my travel mug", "Your color is blue. This is your travel mug."),
])
async def test_llm_provenance_for_approved_answers(records, query, text):
    formatter = Formatter(text)
    result = await RestrictedRAGPipeline(Store(records), formatter).answer(query)
    assert result.response == text and result.response_source == "llm"
    assert not result.fallback_used and result.fallback_reason is None
    assert result.llm_provider == "fixture" and result.llm_model == "configured-model"
    assert result.llm_latency_ms == 1720
    assert set(result.retrieved_record_ids) == {item["id"] for item in records}
    assert formatter.calls == 1


@pytest.mark.parametrize("text,success,reason", [
    ("", False, "timeout"), ("", True, "empty_response"),
    ("Your color is red and your mug is titanium.", True, "grounding_rejected"),
])
async def test_fallback_provenance(text, success, reason):
    result = await RestrictedRAGPipeline(Store([FACT]), Formatter(text, success)).answer("Tell me about my favorite color")
    assert result.response_source == "deterministic" and result.fallback_used
    assert result.fallback_reason == reason
    assert result.response == "Your color is blue."
    assert result.llm_provider is None


@pytest.mark.parametrize("query,records", [("Unknown spacecraft", []), ("Goodbye", [FACT]),
                                         ("Thank you.", [FACT])])
async def test_unknown_and_command_never_call_expression_layer(query, records):
    formatter = Formatter("must not be used")
    result = await RestrictedRAGPipeline(Store(records), formatter).answer(query)
    assert formatter.calls == 0 and result.response_source == "deterministic"
    assert not result.fallback_used
