"""Bounded compound parsing regressions; scoring remains in the production pipeline."""
import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01_central_server"))
import restricted_rag as rag


@pytest.mark.parametrize("query,expected", [
    ("My favorite color and my travel mug.", ["My favorite color", "my travel mug"]),
    ("Tell me naturally what you remember about my favorite color and my travel mug.",
     ["my favorite color", "my travel mug"]),
    ("What do you remember about my favorite color and the travel mug I taught you about?",
     ["my favorite color", "the travel mug"]),
    ("Can you tell me what you know about my favorite color and my travel mug?",
     ["my favorite color", "my travel mug"]),
    ("What do you know about my travel mug and my favorite color?",
     ["my travel mug", "my favorite color"]),
    ("Tell me about both my favorite color and my travel mug", ["my favorite color", "my travel mug"]),
    ("Both favorite color and travel mug", ["favorite color", "travel mug"]),
    ("My favorite color as well as my travel mug", ["My favorite color", "my travel mug"]),
    ("My favorite color also my travel mug", ["My favorite color", "my travel mug"]),
])
def test_compound_request_grammar(query, expected):
    assert rag._retrieval_clauses(rag.normalize_retrieval_query(query)) == expected


@pytest.mark.parametrize("query", ["My travel mug.", "What do you remember about my color?",
                                        "My bread and butter dish"])
def test_single_topic_is_not_rewritten_or_split(query):
    assert rag._retrieval_clauses(query) == [query]


def test_clause_limit_uses_existing_top_k(monkeypatch):
    monkeypatch.setattr(rag, "RAG_TOP_K", 2)
    assert len(rag._retrieval_clauses("my color and my mug and my pet")) == 2
    monkeypatch.setattr(rag, "RAG_TOP_K", 1)
    query = "my color and my mug"
    assert rag._retrieval_clauses(query) == [query]


FACT = {"id": "color", "type": "fact", "similarity": .50,
        "data": {"subject": "My favorite color", "predicate": "is", "object": "blue"}}
OBJECT = {"id": "mug", "type": "object", "similarity": .98,
          "data": {"name": "My travel mug"}}


class Search:
    def __init__(self, responses):
        self.responses, self.calls = responses, []

    async def search_by_embedding(self, **kwargs):
        self.calls.append(kwargs)
        return {"results": self.responses.get(kwargs["query"].casefold(), [])}


class Expression:
    def __init__(self):
        self.calls = 0

    async def generate_response(self, prompt, **kwargs):
        self.calls += 1
        self.prompt = prompt
        return False, {"failure_reason": "test_unavailable"}


@pytest.mark.parametrize("query,expected_ids,search_count", [
    ("Tell me naturally what you remember about my favorite color and my travel mug.", {"color", "mug"}, 2),
    ("My travel mug and my favorite color", {"color", "mug"}, 2),
    ("My favorite color and my unknown animal", {"color"}, 2),
    ("My unknown animal and my unknown vehicle", set(), 2),
    ("Tell me about my favorite color", {"color"}, 1),
    ("My favorite color and my favorite color", {"color"}, 2),
])
async def test_independent_relevance_merge_and_one_expression_call(monkeypatch, query, expected_ids, search_count):
    monkeypatch.setattr(rag, "require_english", lambda query: None)
    search = Search({"my favorite color": [FACT], "my travel mug": [OBJECT]})
    expression = Expression()
    result = await rag.RestrictedRAGPipeline(search, expression).answer(query)
    assert set(result.retrieved_record_ids) == expected_ids
    assert len(search.calls) == search_count
    assert expression.calls == bool(expected_ids)
    if expected_ids == {"color"}:
        assert result.response.count("blue") == 1
    if "unknown" in query and expected_ids:
        assert rag.PARTIAL_KNOWLEDGE_NOTICE in result.response
    assert all(call["threshold"] == min(rag.RAG_CANDIDATE_THRESHOLD, rag.RAG_MATCH_THRESHOLD)
               for call in search.calls)


def test_parser_has_no_domain_specific_keywords():
    source = inspect.getsource(rag._clean_compound_clause) + inspect.getsource(rag._retrieval_clauses)
    assert not any(word in source.lower() for word in ("hometown", "bottle", "university", "phone"))
