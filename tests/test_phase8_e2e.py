"""One deterministic full journey across the production route boundaries."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest


ROOT = Path(__file__).resolve().parents[1]
CENTRAL = ROOT / "01_central_server"
AUDIO = ROOT / "03_audio_service"
sys.path[:0] = [str(ROOT), str(CENTRAL), str(AUDIO)]

os.environ.setdefault("AUTH_ENFORCEMENT_ENABLED", "true")
os.environ.setdefault("NEXI_INTERNAL_SERVICE_TOKEN", "phase8-e2e-service-token")
os.environ.setdefault("NEXI_JWT_SECRET", "phase8-e2e-jwt-secret-at-least-32-bytes")

import conversations_persistence
import main as central_main
from migrate_cloud_sync_outbox import migrate_outbox
import restricted_rag
import sqlite_store
import teachme_routes
from audio_service.routes import advanced_routes
from shared.clients.models import ServiceCallResult


pytestmark = pytest.mark.e2e


class _SynthesizedSpeakerMatcher:
    def __init__(self, user_id: str):
        self.user_id = user_id

    def verify_speaker(self, _audio_file_path: str):
        return self.user_id, 0.99

    def get_verification_threshold(self):
        return 0.65


class _MemoryTeachMe:
    def __init__(self):
        self.items: list[dict] = []
        self.search_users: list[str | None] = []

    async def learn_item(self, item_type, data, tags=None, confidence=1.0):
        item = {"id": "fact-e2e", "type": item_type, "data": data, "tags": tags or [], "confidence": confidence}
        self.items.append(item)
        return {"success": True, "item_id": item["id"], "type": item_type, "timestamp": "2026-09-11T00:00:00Z"}

    async def search_by_embedding(self, query, k=3, threshold=0.55, user_id=None):
        self.search_users.append(user_id)
        return {"results": [{**self.items[0], "similarity": 0.99}] if self.items else []}


class _GroundedLLM:
    def __init__(self):
        self.calls = 0
        self.prompts: list[str] = []

    async def generate_response(self, prompt, **_kwargs):
        self.calls += 1
        self.prompts.append(prompt)
        if os.getenv("PHASE8_FAULT") == "e2e_journey":
            return True, {"response": "The dock is on Mars."}
        return True, {"response": "NEXI charging dock is beside the blue sofa"}


def test_e2e_enroll_verify_grounded_answer_persist_and_sync_eligible(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CLOUD_SYNC_ENABLED", "false")
    database = tmp_path / "central-e2e.sqlite3"
    migrate_outbox(database)
    monkeypatch.setattr(sqlite_store, "DATABASE", database)
    monkeypatch.setattr(central_main, "DATABASE", database)
    central_app = central_main.create_app()

    teachme = _MemoryTeachMe()
    llm = _GroundedLLM()
    monkeypatch.setattr(teachme_routes, "get_teachme_connector", lambda: teachme)
    monkeypatch.setattr(restricted_rag, "get_teachme_connector", lambda: teachme)
    monkeypatch.setattr(restricted_rag, "_llm_client", llm)

    audio_app = FastAPI()
    audio_app.include_router(advanced_routes.router)
    service_headers = {"X-NEXI-Service-Token": os.environ["NEXI_INTERNAL_SERVICE_TOKEN"]}

    with TestClient(central_app) as central, TestClient(audio_app) as audio:
        enrolled = central.post(
            "/users",
            headers=service_headers,
            json={
                "name": "Phase Eight User",
                "face_embeddings": [[0.1, 0.2]],
                "voice_embeddings": [[0.3, 0.4]],
                "enrollment_timestamp": "2026-09-11T00:00:00Z",
            },
        )
        assert enrolled.status_code == 200, enrolled.text
        user_id = enrolled.json()["user_id"]
        print(f"E2E_STAGE_1_ENROLL HTTP=200 user_id={user_id} persisted=True")

        monkeypatch.setattr(advanced_routes, "get_speaker_service", lambda: _SynthesizedSpeakerMatcher(user_id))
        verified = audio.post(
            "/api/v1/verify-speaker",
            files={"file": ("synthesized.wav", b"RIFF-synthesized-speech-WAVE", "audio/wav")},
        )
        assert verified.status_code == 200, verified.text
        verified_body = verified.json()
        assert verified_body["is_verified"] and verified_body["user_id"] == user_id
        token = verified_body["access_token"]
        assert token
        print(
            f"E2E_STAGE_2_VERIFY HTTP=200 method=synthesized-speech "
            f"user_id={user_id} confidence={verified_body['confidence']} token_issued=True"
        )

        taught = central.post(
            "/teachme/learn",
            json={
                "type": "fact",
                "data": {"subject": "NEXI charging dock", "predicate": "is", "object": "beside the blue sofa"},
                "tags": ["phase8-e2e"],
                "confidence": 1.0,
            },
        )
        assert taught.status_code == 200 and taught.json()["success"], taught.text
        print(f"E2E_STAGE_3_TEACH HTTP=200 item_id={taught.json()['item_id']} type=fact")

        user_headers = {"Authorization": f"Bearer {token}"}
        answered = central.post(
            "/api/v1/rag/query",
            headers=user_headers,
            json={"query": "Where is the NEXI charging dock?"},
        )
        assert answered.status_code == 200, answered.text
        answer = answered.json()
        assert answer["source"] == "teachme_grounded"
        assert answer["response"] == "NEXI charging dock is beside the blue sofa"
        assert llm.calls == 1 and teachme.search_users == [user_id]
        assert "FACTS:" in llm.prompts[0] and "beside the blue sofa" in llm.prompts[0]
        print(
            f"E2E_STAGE_4_RAG HTTP=200 source={answer['source']} llm_calls={llm.calls} "
            f"trusted_user={teachme.search_users[0]} response={answer['response']!r}"
        )

        durable = central.get(f"/users/{user_id}/conversations", headers=user_headers)
        assert durable.status_code == 200 and durable.json()["count"] == 1, durable.text
        record = durable.json()["conversations"][0]
        assert record["assistant_response"] == answer["response"]
        assert record["metadata"] == {"source": "teachme_grounded", "automatic": True}
        print(
            f"E2E_STAGE_5_DURABILITY auto_persisted=True GET=200 "
            f"conversation_id={record['conversation_id']} count={durable.json()['count']}"
        )

        no_match = _MemoryTeachMe()
        monkeypatch.setattr(restricted_rag, "get_teachme_connector", lambda: no_match)
        fallback = central.post(
            "/api/v1/rag/query",
            headers=user_headers,
            json={"query": "What is the orbital period of Neptune?"},
        )
        assert fallback.status_code == 200, fallback.text
        assert fallback.json() == {
            "success": True,
            "response": "I don't know this yet. Please teach me.",
            "source": "no_match",
        }
        after_fallback = central.get(f"/users/{user_id}/conversations", headers=user_headers)
        assert after_fallback.status_code == 200 and after_fallback.json()["count"] == 2
        newest = after_fallback.json()["conversations"][0]
        assert newest["user_message"] == "What is the orbital period of Neptune?"
        assert newest["metadata"] == {"source": "no_match", "automatic": True}
        print(
            f"E2E_STAGE_5B_NO_MATCH auto_persisted=True GET=200 "
            f"conversation_id={newest['conversation_id']} count={after_fallback.json()['count']}"
        )

        sync = central.get("/sync/status", headers=service_headers)
        assert sync.status_code == 200, sync.text
        assert sync.json()["pending_records"] == 2
        print(
            f"E2E_STAGE_6_SYNC_ELIGIBILITY HTTP=200 pending_records={sync.json()['pending_records']} "
            f"synced=0 conversation_ids={record['conversation_id']},{newest['conversation_id']}"
        )

    print("E2E_RESULT PASS stages=6 physical_hardware=False synthesized_speech=True")
