"""Bounded temporary reference context through Central's actual orchestration."""
import sys
import time
import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01_central_server"))
import conversation_context as context
import restricted_rag as rag


def test_sliding_window_ttl_and_restart(monkeypatch):
    window = context.ConversationContext()
    counts = []
    for i in range(5):
        window.append(f"query {i}", f"answer {i}", (str(i),), ("My blue camera",))
        counts.append(len(window.snapshot()))
    assert counts == [1, 2, 3, 3, 3]
    assert [turn.user_query for turn in window.turns] == ["query 2", "query 3", "query 4"]
    assert not context.ConversationContext().snapshot()
    assert not window.snapshot(window.last_activity + context.CONTEXT_TTL_SECONDS)
    assert window.reset_reason == "ttl_expired"
    assert window.resolve("Why?") == ("Why?", ())


@pytest.mark.parametrize("query,expected", [
    ("Why?", "why about My blue camera?"),
    ("What about it?", "What about My blue camera?"),
    ("Where is it?", "Where is My blue camera?"),
    ("Tell me more", "Tell me more about My blue camera?"),
])
def test_reference_resolution(query, expected):
    window = context.ConversationContext()
    window.append("Tell me about my camera", "Your blue camera.", ("camera",), ("My blue camera",))
    resolved, turns = window.resolve(query)
    assert resolved == expected and len(turns) == 1


def test_explicit_topic_and_unknown_topic_do_not_inherit_prior_topic():
    window = context.ConversationContext()
    window.append("My camera", "Your camera", ("camera",), ("My camera",))
    assert window.resolve("What about my desk?") == ("Tell me about my desk", ())
    assert window.resolve("Tell me about that desk") == ("Tell me about that desk", ())
    window.append("My desk", "Unknown", (), ())
    assert window.resolve("Why?") == ("Why?", ())


def test_ordinals_require_unambiguous_grounded_topics():
    window = context.ConversationContext()
    window.append("My camera and my desk", "Camera and desk", ("c", "d"), ("My camera", "My desk"))
    assert window.resolve("What about the second one?")[0] == "Tell me about My desk"
    assert window.resolve("Why?") == ("Why?", ())
    window.append("My camera", "Camera", ("c",), ("My camera",))
    assert window.resolve("What about the other one?") == ("What about the other one?", ())


def test_current_explicit_query_is_not_truncated_by_history_limits():
    window = context.ConversationContext()
    window.append("My camera", "Camera", ("c",), ("My camera",))
    topic = "detailed " * 100
    resolved, history = window.resolve("What about my " + topic)
    assert resolved == "Tell me about my " + topic.strip()
    assert not history


def test_shortened_named_reference_must_be_unique_within_window():
    window = context.ConversationContext()
    window.append("My camera", "Your blue camera", ("c",), ("My blue camera",))
    window.append("My desk", "Your desk", ("d",), ("My desk",))
    assert window.resolve("Tell me again about the camera.")[0] == "Tell me about My blue camera"
    window.append("My second camera", "Your red camera", ("r",), ("My red camera",))
    assert window.resolve("Tell me again about the camera.") == ("Tell me again about the camera.", ())


def test_text_is_bounded_and_context_is_not_serialized_with_vectors():
    window = context.ConversationContext()
    window.append(" x " * 3000, " y " * 3000, ("c",), ("My camera",))
    turn = window.snapshot()[0]
    assert len(turn.user_query) <= 512 and len(turn.nexi_response) <= 512
    prompt = context.expression_context("Why?", window.snapshot())
    assert "NEVER as factual evidence" in prompt
    assert "retrieved_record_ids" not in prompt and "c" not in turn.user_query


class Store:
    def __init__(self):
        self.queries = []
        self.available = True

    async def search_by_embedding(self, **kwargs):
        self.queries.append(kwargs)
        return {"results": ([{"id": "camera", "type": "object", "similarity": .99,
                              "data": {"name": "My blue camera"}}] if self.available else [])}


class Formatter:
    def __init__(self):
        self.prompts = []
        self.response = "Your blue camera."
        self.success = True

    async def generate_response(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return self.success, {"response": self.response, "failure_reason": "timeout"}


@pytest.fixture
def service(monkeypatch):
    store, formatter = Store(), Formatter()
    monkeypatch.setattr(rag, "require_session_claims", lambda request: {"sub": request.headers["x-user"]})
    monkeypatch.setattr(rag, "get_teachme_connector", lambda: store)
    monkeypatch.setattr(rag, "_llm_client", formatter)
    monkeypatch.setattr(rag, "add_conversation", lambda **kwargs: True)
    app = FastAPI()
    app.include_router(rag.router)
    yield app, store, formatter
    for sid, state in list(rag._rag_sessions.items()):
        if state.user_id and state.user_id.startswith("context-test-"):
            rag._rag_sessions.pop(sid).context.clear("test_cleanup")


async def send(client, session, query, user="context-test-A"):
    return await client.post("/api/v1/rag/query", json={"query": query, "session_id": session},
                             headers={"x-user": user})


async def test_rest_sliding_goodbye_and_new_session(service):
    app, store, formatter = service
    sid, state = rag.create_rag_session("context-test-A")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        counts = []
        for query in ["Tell me about my camera", "Why?", "What about it?", "Tell me more", "Tell me about my blue camera"]:
            result = await send(client, sid, query)
            assert result.status_code == 200, result.text
            counts.append(result.json()["context_turn_count"])
        assert counts == [1, 2, 3, 3, 3]
        assert "My blue camera" in store.queries[1]["query"]
        assert len(formatter.prompts) == 5
        assert "Recent conversation" in formatter.prompts[1]
        result = await send(client, sid, "Goodbye")
        assert result.json()["context_turn_count"] == 0
        assert result.json()["context_reset_reason"] == "goodbye"
        assert sid not in rag._rag_sessions and not state.context.turns
        assert len(formatter.prompts) == 5
        new_sid, _ = rag.create_rag_session("context-test-A")
        result = await send(client, new_sid, "Why?")
        assert result.json()["source"] == "no_match"
        assert not result.json()["context_used"] and len(formatter.prompts) == 5


async def test_user_and_session_isolation_and_invalidation(service):
    app, store, formatter = service
    sid, state = rag.create_rag_session("context-test-A")
    other, _ = rag.create_rag_session("context-test-B")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        await send(client, sid, "Tell me about my blue camera")
        assert (await send(client, sid, "Why?", "context-test-B")).status_code == 403
        response = await send(client, other, "Why?", "context-test-B")
        assert not response.json()["context_used"] and response.json()["source"] == "no_match"
        assert rag.delete_rag_sessions_for_user("context-test-A") == 1
        assert not state.context.turns


async def test_ttl_context_expiry_does_not_require_session_expiry(service, monkeypatch):
    app, _, formatter = service
    monkeypatch.setattr(context, "CONTEXT_TTL_SECONDS", 1)
    sid, state = rag.create_rag_session("context-test-A")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        await send(client, sid, "Tell me about my blue camera")
        state.context.last_activity = time.monotonic() - 2
        result = await send(client, sid, "Why?")
        assert result.json()["context_reset_reason"] == "ttl_expired"
        assert not result.json()["context_used"] and len(formatter.prompts) == 1


async def test_context_requeries_memory_and_cannot_ground_historical_claims(service):
    app, store, formatter = service
    sid, state = rag.create_rag_session("context-test-A")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        await send(client, sid, "Tell me about my blue camera")
        state.context.append("My blue camera", "Your blue camera is in Paris.", ("camera",), ("My blue camera",))
        formatter.response = "Your blue camera is in Paris."
        result = (await send(client, sid, "Where is it?")).json()
        assert result["fallback_reason"] == "grounding_rejected"
        assert "Paris" not in result["response"]
        assert len(store.queries) == 2 and len(formatter.prompts) == 2
        store.available = False  # Deleted knowledge cannot survive in context.
        result = (await send(client, sid, "What about it?")).json()
        assert result["source"] == "no_match" and len(formatter.prompts) == 2


async def test_unknown_property_and_provider_failure_remain_safe(service):
    app, _, formatter = service
    sid, _ = rag.create_rag_session("context-test-A")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        await send(client, sid, "Tell me about my blue camera")
        formatter.response = rag.NOT_ANSWERABLE_MARKER
        result = (await send(client, sid, "Why?")).json()
        assert result["response"].endswith(rag.PARTIAL_KNOWLEDGE_NOTICE)
        formatter.success = False
        result = (await send(client, sid, "What about it?")).json()
        assert result["fallback_reason"] == "timeout" and result["response"] == "Your blue camera."


async def test_disabled_and_failed_context_do_not_break_rag(service, monkeypatch):
    app, _, formatter = service
    sid, state = rag.create_rag_session("context-test-A")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        monkeypatch.setattr(rag, "CONTEXT_ENABLED", False)
        result = (await send(client, sid, "Tell me about my blue camera")).json()
        assert not result["context_enabled"] and not state.context.turns
        monkeypatch.setattr(rag, "CONTEXT_ENABLED", True)
        def fail(*args):
            raise RuntimeError("context fixture failure")
        monkeypatch.setattr(state.context, "resolve", fail)
        result = (await send(client, sid, "Tell me about my blue camera")).json()
        assert result["source"] == "teachme_grounded" and not result["context_used"]
        assert len(formatter.prompts) == 2


def test_client_has_no_conversation_context_logic():
    source = (Path(__file__).resolve().parents[1] / "test.py").read_text(encoding="utf-8")
    assert "ConversationContext" not in source
    assert "CONTEXT_TTL_SECONDS" not in source
    assert "expression_context" not in source


async def test_session_serialization_and_close_during_inference(service):
    app, store, formatter = service
    sid, state = rag.create_rag_session("context-test-A")
    entered, release = asyncio.Event(), asyncio.Event()
    original = formatter.generate_response
    async def delayed(prompt, **kwargs):
        entered.set()
        await release.wait()
        return await original(prompt, **kwargs)
    formatter.generate_response = delayed
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        first = asyncio.create_task(send(client, sid, "Tell me about my camera"))
        await entered.wait()
        second = asyncio.create_task(send(client, sid, "Why?"))
        await asyncio.sleep(.02)
        assert len(store.queries) == 1
        rag.delete_rag_sessions_for_user("context-test-A")
        release.set()
        assert (await first).status_code == 200
        assert (await second).status_code == 410
        assert not state.context.turns and sid not in rag._rag_sessions


async def test_optional_context_failures_in_expiry_and_prompt_are_safe(service, monkeypatch):
    app, _, formatter = service
    sid, state = rag.create_rag_session("context-test-A")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        await send(client, sid, "Tell me about my camera")
        def fail(*args):
            raise RuntimeError("context fixture failure")
        monkeypatch.setattr(rag, "expression_context", fail)
        result = (await send(client, sid, "What about it?")).json()
        assert result["source"] == "teachme_grounded"
        monkeypatch.setattr(state.context, "snapshot", fail)
        result = (await send(client, sid, "Tell me about my camera")).json()
        assert result["source"] == "teachme_grounded" and len(formatter.prompts) == 3


async def test_compound_topic_order_is_query_order_not_similarity_order():
    class TwoTopics:
        async def search_by_embedding(self, **kwargs):
            return {"results": [
                {"id": "desk", "type": "fact", "similarity": .99,
                 "data": {"subject": "My desk", "predicate": "is", "object": "brown"}},
                {"id": "camera", "type": "object", "similarity": .90,
                 "data": {"name": "My blue camera"}},
            ]}
    result = await rag.RestrictedRAGPipeline(TwoTopics(), Formatter()).answer("Tell me about my camera and my desk")
    assert result.context_topics == ("My blue camera", "My desk")
