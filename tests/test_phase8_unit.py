"""Fast direct-object tests for the Phase 8 unit layer."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from types import MethodType

import pytest


ROOT = Path(__file__).resolve().parents[1]
CENTRAL = ROOT / "01_central_server"
sys.path[:0] = [str(ROOT), str(CENTRAL)]

import restricted_rag
from migrate_cloud_sync_outbox import migrate_outbox
from resource_authority import PriorityLevel, ResourceAuthority, ResourceType
from services.cloud_sync_service import ConversationOutbox
from shared.jwt_manager import JWTManager, TokenConfig, TokenValidator


pytestmark = pytest.mark.unit


def _fault(name: str) -> bool:
    """Opt-in negative control used only by Phase 8 verification commands."""
    return os.getenv("PHASE8_FAULT") == name


def test_unit_resource_authority_grant_priority_and_release(monkeypatch) -> None:
    started = time.perf_counter()
    authority = ResourceAuthority(release_ack_timeout=5.0)
    low = authority.request_resource(ResourceType.CAMERA, "background", PriorityLevel.BACKGROUND)
    assert low.state == "reserved"
    assert authority.acknowledge_grant(low.lease_id)
    high = authority.request_resource(ResourceType.CAMERA, "teachme", PriorityLevel.ACTIVE_TEACHME)
    assert low.state == "revoking" and high.state == "queued"
    if _fault("unit_resource"):
        monkeypatch.setattr(authority, "release_resource", MethodType(lambda self, lease_id: True, authority))
    assert authority.release_resource(low.lease_id)
    assert authority.check_lease_status(low.lease_id) is None
    assert authority.check_lease_status(high.lease_id)["state"] == "reserved"
    authority.release_resource(high.lease_id)
    elapsed = time.perf_counter() - started
    assert elapsed < 1.0
    print(f"UNIT_RESOURCE PASS preempted=background next=teachme released=True elapsed={elapsed:.4f}s")


def test_unit_rag_grounding_containment_rejects_extra_claims(monkeypatch) -> None:
    started = time.perf_counter()
    if _fault("unit_grounding"):
        monkeypatch.setattr(restricted_rag, "is_grounded", lambda response, facts: True)
    fact = "NEXI's charging dock is beside the blue sofa."
    assert restricted_rag.is_grounded("The charging dock is beside the blue sofa.", [fact])
    assert not restricted_rag.is_grounded(
        "The charging dock is beside the blue sofa and it was built in Paris.", [fact]
    )
    elapsed = time.perf_counter() - started
    assert elapsed < 1.0
    print(f"UNIT_GROUNDING PASS contained=True extra_claim=False elapsed={elapsed:.4f}s")


def test_unit_jwt_session_validation_preserves_subject(monkeypatch) -> None:
    started = time.perf_counter()
    manager = JWTManager(TokenConfig(secret_key="phase8-unit-jwt-secret-at-least-32-bytes"))
    validator = TokenValidator(manager)
    token = manager.create_session_token("user-unit")["token"]
    if _fault("unit_jwt"):
        original = manager.verify_token

        def wrong_subject(value, token_type=None):
            claims = original(value, token_type)
            return {**claims, "sub": "user-other"}

        monkeypatch.setattr(manager, "verify_token", wrong_subject)
    claims = validator.validate_session_token(token)
    assert claims["sub"] == "user-unit"
    assert claims["type"] == "session"
    elapsed = time.perf_counter() - started
    assert elapsed < 1.0
    print(f"UNIT_JWT PASS subject={claims['sub']} type={claims['type']} elapsed={elapsed:.4f}s")


def test_unit_outbox_acknowledgement_transitions_state(monkeypatch, tmp_path) -> None:
    started = time.perf_counter()
    database = tmp_path / "outbox.sqlite3"
    migrate_outbox(database)
    record = {
        "conversation_id": "conversation-unit",
        "user_id": "user-unit",
        "timestamp": "2026-09-11T00:00:00+00:00",
        "user_message": "Where is the dock?",
        "assistant_response": "Beside the blue sofa.",
        "language": "en",
    }
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO conversations(position, record) VALUES (?, ?)",
            (0, json.dumps(record)),
        )
    outbox = ConversationOutbox(database)
    batch = outbox.acquire_pending_batch(10)
    assert batch is not None and len(batch.records) == 1
    attempted = datetime(2026, 9, 11, tzinfo=timezone.utc)
    outbox.mark_attempted(batch.batch_id, attempted)
    if _fault("unit_outbox"):
        monkeypatch.setattr(
            outbox,
            "acknowledge",
            MethodType(lambda self, batch_id, succeeded_at: 0, outbox),
        )
    assert outbox.acknowledge(batch.batch_id, attempted) == 1
    status = outbox.status()
    assert status["pending_records"] == 0
    assert status["last_successful_sync"] == "2026-09-11T00:00:00+00:00"
    elapsed = time.perf_counter() - started
    assert elapsed < 1.0
    print(f"UNIT_OUTBOX PASS pending=0 acknowledged=1 elapsed={elapsed:.4f}s")
