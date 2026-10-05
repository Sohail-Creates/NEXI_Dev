"""Presentation-only regressions against the existing RAG pipeline."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01_central_server"))
from restricted_rag import (
    NOT_ANSWERABLE_MARKER, PARTIAL_KNOWLEDGE_NOTICE, NEXI_MEMORY_INSTRUCTION, RestrictedRAGPipeline,
    build_grounded_prompt,
)


FACT = {"id": "private-fact-id", "type": "fact", "similarity": 0.95,
        "data": {"subject": "My hometown", "predicate": "is", "object": "Quito"}}
OBJECT = {"id": "private-object-id", "type": "object", "similarity": 0.96,
          "data": {"name": "My travel mug", "attributes": {"secret": "private-metadata"}},
          "visual_embedding": [12345.0]}
COLOR = {"id": "private-color-id", "type": "fact", "similarity": 0.94,
         "data": {"subject": "My favorite color", "predicate": "is", "object": "blue"}}


class Retrieval:
    def __init__(self, records):
        self.records = records

    async def search_by_embedding(self, **kwargs):
        return {"results": self.records}


class Formatter:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    async def generate_response(self, prompt, **kwargs):
        self.calls += 1
        self.prompt = prompt
        return True, {"response": self.response}


@pytest.mark.parametrize("records,query,response", [
    ([FACT, OBJECT], "Tell me about my hometown and my travel mug.",
     "This is your travel mug, and your hometown is Quito."),
    ([FACT, COLOR], "Tell me about my hometown and my favorite color.",
     "Your hometown is Quito, and your favorite color is blue."),
])
async def test_natural_combined_response_and_one_formatting_call(records, query, response):
    llm = Formatter(response)
    result = await RestrictedRAGPipeline(Retrieval(records), llm).answer(query)
    assert result.source == "teachme_grounded"
    assert result.response == response
    assert llm.calls == 1
    assert "connect them smoothly" in llm.prompt
    assert "Preserve the supplied order and meaningful phrases" in llm.prompt
    assert "at most two short sentences" in llm.prompt
    assert not any(value in llm.prompt for value in (
        "private-fact-id", "private-object-id", "private-metadata", "12345", "0.95", "0.96"))
    assert "Fact:" not in result.response and "Object:" not in result.response


@pytest.mark.parametrize("record,query,response", [
    (FACT, "My hometown", "Your hometown is Quito."),
    (OBJECT, "Tell me about my travel mug", "This is your travel mug."),
])
async def test_single_record_prompt_and_behavior_unchanged(record, query, response):
    prompt, facts = build_grounded_prompt(query, [record])
    object_guidance = (
        "For object records, the stored personal label is itself taught knowledge "
        "about that object. Answer label questions from that label even if no "
        "description exists; do not invent uses or locations. Keep the answer "
        "concise using the stored wording. " if record["type"] == "object" else ""
    )
    text = facts[0] if record["type"] == "fact" else "[object] " + facts[0]
    assert prompt == (
        NEXI_MEMORY_INSTRUCTION +
        "Answer the question strictly and only from the facts below. "
        "Do not add outside knowledge, assumptions, or new claims. "
        + object_guidance + "If these facts do not contain what is needed to answer the question, "
        + f"reply with exactly this marker and nothing else: {NOT_ANSWERABLE_MARKER}\n"
        + f"FACTS:\n- {text}\nQUESTION:\n{query}"
    )
    llm = Formatter(response)
    result = await RestrictedRAGPipeline(Retrieval([record]), llm).answer(query)
    assert result.response == response and result.source == "teachme_grounded"
    assert llm.calls == 1


@pytest.mark.parametrize("response", [
    "Your hometown is Quito. " + PARTIAL_KNOWLEDGE_NOTICE,
    "Your hometown is Quito, and " + PARTIAL_KNOWLEDGE_NOTICE.lower(),
])
async def test_partial_answer_has_fixed_notice_and_only_known_information(response):
    llm = Formatter(response)
    result = await RestrictedRAGPipeline(Retrieval([FACT]), llm).answer(
        "Tell me about my hometown and my favorite animal.")
    assert result.source == "teachme_grounded"
    assert result.response == response
    assert "Do not guess the missing information" in llm.prompt
    assert "Never repeat or name an unknown topic" in llm.prompt
    assert llm.calls == 1


@pytest.mark.parametrize("response", [
    "Your hometown is Paris, and your travel mug is made from titanium.",
    "Your hometown is Paris. " + PARTIAL_KNOWLEDGE_NOTICE,
    PARTIAL_KNOWLEDGE_NOTICE,
])
async def test_composition_cannot_bypass_factual_grounding(response):
    llm = Formatter(response)
    result = await RestrictedRAGPipeline(Retrieval([FACT, OBJECT]), llm).answer(
        "Tell me about my hometown and my travel mug.")
    assert result.source == "grounding_failure"
    assert result.response != response


def test_presentation_order_follows_question_without_mutating_retrieved_records():
    records = [OBJECT, FACT]
    prompt, texts = build_grounded_prompt("Tell me about my hometown and my travel mug", records)
    assert texts == ["My hometown is Quito", "My travel mug"]
    assert records == [OBJECT, FACT]
    assert prompt.index("My hometown is Quito") < prompt.index("[object] My travel mug")


class UnavailableFormatter(Formatter):
    async def generate_response(self, prompt, **kwargs):
        self.calls += 1
        return False, {"error": "unavailable"}


@pytest.mark.parametrize("records,query,expected", [
    ([FACT], "My hometown", "Your hometown is Quito."),
    ([FACT, OBJECT], "My hometown and my travel mug", "Your hometown is Quito. Your travel mug."),
])
async def test_provider_failure_preserves_approved_memory(records, query, expected):
    llm = UnavailableFormatter("")
    result = await RestrictedRAGPipeline(Retrieval(records), llm).answer(query)
    assert result.response == expected
    assert result.source == "teachme_grounded" and llm.calls == 1


async def test_partial_provider_failure_does_not_invent_unknown_topic():
    class PartialRetrieval:
        async def search_by_embedding(self, **kwargs):
            return {"results": [FACT] if "hometown" in kwargs["query"] else []}
    llm = UnavailableFormatter("")
    result = await RestrictedRAGPipeline(PartialRetrieval(), llm).answer(
        "My hometown and my spacecraft engine")
    assert result.response == "Your hometown is Quito. " + PARTIAL_KNOWLEDGE_NOTICE
    assert llm.calls == 1
