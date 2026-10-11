"""Intent/evidence policies exercise production helpers, never copied scoring."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01_central_server"))
from answerability import build_answer_plan
import restricted_rag as rag


@pytest.mark.parametrize("query,relation", [
    ("Where is my camera?", "location"), ("Why about my camera?", "reason"),
    ("When did I buy my camera?", "time"), ("Who made my camera?", "person"),
    ("Which camera?", "identity"), ("What is my camera?", "description"),
    ("How does my camera work?", "method"),
])
def test_generic_relations_and_missing_evidence(query, relation):
    records = [{"type": "object", "data": {"name": "My blue camera"}}]
    plan = build_answer_plan(query, records, subject_referenced=True)
    assert plan.requested_relation == relation
    assert plan.requested_relation_known == (relation in {"identity", "description"})
    if relation not in {"identity", "description"}:
        assert "haven't taught me" in plan.missing_response()


def test_explicit_relation_evidence_and_unknown_subject():
    records = [{"type": "object", "data": {"name": "My camera", "description": "It is kept on the shelf."}}]
    assert build_answer_plan("Where is my camera?", records, subject_referenced=True).requested_relation_known
    assert build_answer_plan("Where is my drone?", records, subject_referenced=False).missing_response() is None
    assert not build_answer_plan("Where is my drone?", [], subject_referenced=False).subject_known


def test_fact_value_types_are_not_guessed_from_domain_labels():
    records = [{"type": "fact", "data": {"subject": "My destination", "predicate": "is", "object": "Quito"}}]
    assert build_answer_plan("Where is my destination?", records, subject_referenced=True).requested_relation_known is None


def test_free_text_relations_are_not_declared_missing_by_keyword_absence():
    records = [{"type": "object", "data": {"name": "My camera", "description": "I prefer it for its comfortable grip."}}]
    plan = build_answer_plan("Why is my camera my favorite?", records, subject_referenced=True)
    assert plan.requested_relation_known is None and plan.missing_response() is None
    assert "can't confirm" in plan.missing_response(unavailable=True)


@pytest.mark.parametrize("response", [
    "I remember you told me your destination is Quito.",
    "You told me that your destination is Quito.",
])
def test_bounded_attribution_paraphrase_keeps_claims(response):
    assert rag.is_grounded(response, ["My destination is Quito."])


def test_unsupported_detail_cannot_hide_in_a_long_grounded_response():
    facts = ["My destination is Quito Ecuador.", "My personal favorite camera is blue stainless steel."]
    assert not rag.is_grounded("Your destination is Quito Ecuador and your personal favorite camera is beautiful blue stainless steel.", facts)


def test_simple_claim_bindings_cannot_swap_stored_values():
    assert not rag.is_grounded("Your camera is red and your desk is blue.",
                               ["My camera is blue.", "My desk is red."])


async def test_supported_relation_survives_provider_failure():
    class Store:
        async def search_by_embedding(self, **kwargs):
            return {"results": [{"id": "camera", "type": "fact", "similarity": .99,
                                 "data": {"subject": "My camera", "predicate": "is located in", "object": "Helsinki"}}]}
    class Failure:
        async def generate_response(self, prompt, **kwargs):
            return False, {"failure_reason": "timeout"}
    result = await rag.RestrictedRAGPipeline(Store(), Failure()).answer("Where is my camera?")
    assert result.response == "Your camera is located in Helsinki."
    assert result.fallback_reason == "timeout" and result.requested_relation_known is True


async def test_verified_runtime_identity_is_session_only(monkeypatch):
    from fastapi import FastAPI
    import httpx
    from shared.security import require_internal_service
    monkeypatch.setattr(rag, "require_bearer_session_claims", lambda request: {"sub": "bridge-user"})
    monkeypatch.setattr(rag, "require_session_claims", lambda request: {"sub": request.headers.get("x-user", "bridge-user")})
    monkeypatch.setattr(rag, "get_teachme_connector", lambda: object())
    app = FastAPI()
    app.state.db = {"users": {"bridge-user": {"name": "Alex"}}}
    app.include_router(rag.router)
    app.dependency_overrides[require_internal_service] = lambda: "test-service"
    sid = None
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
            sid = (await client.post("/api/v1/rag/sessions")).json()["session_id"]
            body = {"session_id": sid, "query": "Do you recognize me?"}
            response = await client.post("/api/v1/rag/query", json=body)
            assert response.json()["response"] == "Yes, I recognized you as Alex."
            assert response.json()["source"] == "session_identity"
            assert response.json()["llm_latency_ms"] is None
            assert (await client.post("/api/v1/rag/query", json=body, headers={"x-user": "other-user"})).status_code == 403
            await client.delete("/api/v1/rag/sessions/" + sid)
            assert sid not in rag._rag_sessions
    finally:
        if sid: rag._rag_sessions.pop(sid, None)
