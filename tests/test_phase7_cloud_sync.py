"""Phase 7 verification fixture: controlled local cloud receiver and tests only."""

from __future__ import annotations

import ast
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import socket
import sqlite3
import sys
import threading
import time
from typing import Iterator

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
import pytest
import requests
import uvicorn


ROOT = Path(__file__).resolve().parents[1]
CENTRAL = ROOT / "01_central_server"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(CENTRAL))

from migrate_cloud_sync_outbox import migrate_outbox
from services.cloud_sync_service import (
    CloudSyncClient,
    CloudSyncService,
    CloudSyncSettings,
    ConversationOutbox,
    ExportableConversation,
    PendingBatch,
    router as sync_router,
)
from shared.api_errors import install_error_handlers


class ReceiverState:
    def __init__(self) -> None:
        self.batches: dict[str, dict] = {}
        self.attempts: dict[str, int] = {}
        self.failures_remaining = 0
        self.drop_ack_after_store_remaining = 0
        self.expected_header = "X-Cloud-Fixture-Key"
        self.expected_token = "fixture-secret"


def create_test_receiver(state: ReceiverState) -> FastAPI:
    """Create the test-only receiver; this is not a product endpoint."""
    app = FastAPI(title="Phase 7 Local Test Receiver")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy", "purpose": "phase7-test-fixture-only"}

    @app.post("/batches")
    async def receive_batch(payload: dict, x_cloud_fixture_key: str | None = Header(None)) -> dict:
        if x_cloud_fixture_key != state.expected_token:
            raise HTTPException(status_code=401, detail="fixture credential required")
        batch_id = payload.get("batch_id")
        records = payload.get("records")
        if not isinstance(batch_id, str) or not isinstance(records, list):
            raise HTTPException(status_code=422, detail="invalid batch")
        state.attempts[batch_id] = state.attempts.get(batch_id, 0) + 1
        if state.failures_remaining:
            state.failures_remaining -= 1
            raise HTTPException(status_code=503, detail="forced receiver failure")
        duplicate = batch_id in state.batches
        if not duplicate:
            state.batches[batch_id] = json.loads(json.dumps(payload))
        if state.drop_ack_after_store_remaining and not duplicate:
            state.drop_ack_after_store_remaining -= 1
            raise HTTPException(status_code=503, detail="forced acknowledgement loss")
        return {"acknowledged": True, "batch_id": batch_id, "duplicate": duplicate}

    return app


@contextmanager
def live_receiver() -> Iterator[tuple[ReceiverState, str]]:
    state = ReceiverState()
    app = create_test_receiver(state)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            if requests.get(f"{base_url}/health", timeout=0.2).status_code == 200:
                break
        except requests.RequestException:
            time.sleep(0.02)
    else:
        server.should_exit = True
        thread.join(timeout=2)
        raise RuntimeError("test receiver did not start")
    try:
        yield state, base_url
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def settings(base_url: str, **overrides) -> CloudSyncSettings:
    value = CloudSyncSettings(
        enabled=True,
        base_url=base_url,
        auth_header="X-Cloud-Fixture-Key",
        auth_token="fixture-secret",
        timeout_seconds=2,
        interval_seconds=60,
        retry_attempts=2,
        retry_initial_delay_seconds=0.05,
        retry_max_delay_seconds=0.05,
        retry_backoff_multiplier=2,
        supervisor_retry_seconds=0.05,
        batch_size=100,
    )
    return replace(value, **overrides)


def sample_record(index: int) -> dict:
    return {
        "conversation_id": f"conv-{index}",
        "user_id": "user-phase7",
        "timestamp": f"2026-09-11T12:00:{index:02d}+00:00",
        "user_message": f"question {index}",
        "assistant_response": f"answer {index}",
        "mood": "neutral",
        "language": "en",
        "metadata": {"local_only_metadata": True},
    }


def database_with_records(path: Path, count: int, *, migrate_schema: bool = True) -> Path:
    from sqlite_store import initialize

    initialize(path)
    with sqlite3.connect(path) as connection:
        connection.executemany(
            "INSERT INTO conversations (position, record) VALUES (?, ?)",
            ((index, json.dumps(sample_record(index))) for index in range(count)),
        )
    if migrate_schema:
        migrate_outbox(path)
    return path


def batch(batch_id: str = "fixed-batch") -> PendingBatch:
    record = ExportableConversation.from_record(sample_record(1))
    return PendingBatch(batch_id=batch_id, records=(record,))


@pytest.mark.asyncio
async def test_a_provider_agnostic_client_deduplicates_and_swaps_config(monkeypatch) -> None:
    with live_receiver() as (first, first_url), live_receiver() as (second, second_url):
        monkeypatch.setenv("CLOUD_SYNC_ENABLED", "true")
        monkeypatch.setenv("CLOUD_SYNC_AUTH_HEADER", "X-Cloud-Fixture-Key")
        monkeypatch.setenv("CLOUD_SYNC_AUTH_TOKEN", "fixture-secret")
        monkeypatch.setenv("CLOUD_SYNC_RETRY_INITIAL_DELAY_SECONDS", "0.01")
        monkeypatch.setenv("CLOUD_SYNC_RETRY_MAX_DELAY_SECONDS", "0.01")
        monkeypatch.setenv("CLOUD_SYNC_BASE_URL", first_url)
        first_client = CloudSyncClient(CloudSyncSettings.from_env())
        initial = await first_client.send_batch(batch())
        duplicate = await first_client.send_batch(batch())
        assert len(first.batches) == 1 and duplicate["duplicate"] is True

        monkeypatch.setenv("CLOUD_SYNC_BASE_URL", second_url)
        second_client = CloudSyncClient(CloudSyncSettings.from_env())
        swapped = await second_client.send_batch(batch("config-swapped-batch"))
        assert len(second.batches) == 1 and swapped["acknowledged"] is True
        print(
            "TASK_A_DEDUPE=PASS "
            f"url={first_client.settings.base_url} deliveries={first.attempts['fixed-batch']} "
            f"stored_batches={len(first.batches)} first_duplicate={initial['duplicate']} "
            f"second_duplicate={duplicate['duplicate']}"
        )
        print(
            "TASK_A_CONFIG_SWAP=PASS "
            f"old_url={first_client.settings.base_url} new_url={second_client.settings.base_url} "
            "code_changes=0 stored_on_new_receiver=1"
        )


@pytest.mark.asyncio
async def test_b_shared_retry_failure_then_recovery_timing() -> None:
    with live_receiver() as (receiver, base_url):
        receiver.failures_remaining = 1
        client = CloudSyncClient(settings(base_url))
        started = time.perf_counter()
        result = await client.send_batch(batch("retry-batch"))
        elapsed = time.perf_counter() - started
        assert result["acknowledged"] is True
        assert receiver.attempts["retry-batch"] == 2
        assert elapsed >= 0.045
        print(
            "TASK_B_RETRY=PASS mechanism=shared.retry_handler.RetryHandler "
            f"attempts=2 configured_backoff_s=0.050 measured_elapsed_s={elapsed:.3f} recovered=true"
        )


def test_c_outbox_migration_twice_and_conversation_round_trip(tmp_path, monkeypatch) -> None:
    database = database_with_records(
        tmp_path / "central.sqlite3", 3, migrate_schema=False
    )
    first = migrate_outbox(database)
    second = migrate_outbox(database)
    assert first["before"] == first["after"] == 3
    assert second["before"] == second["after"] == 3
    assert first["added"] == [
        "synced", "batch_id", "sync_attempted_at", "sync_succeeded_at"
    ]
    assert second["added"] == []

    import sqlite_store
    import conversations_persistence

    monkeypatch.setattr(sqlite_store, "DATABASE", database)
    outbox = ConversationOutbox(database)
    acknowledged_batch = outbox.acquire_pending_batch(1)
    assert acknowledged_batch is not None
    assert outbox.acknowledge(acknowledged_batch.batch_id, datetime.now(timezone.utc)) == 1
    assert conversations_persistence.add_conversation(
        "user-phase7", "live write", "live read", language="en"
    )
    conversations = conversations_persistence.get_user_conversations("user-phase7", limit=0)
    assert any(item["user_message"] == "live write" for item in conversations)
    with sqlite3.connect(database) as connection:
        count = int(connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0])
        synced = int(
            connection.execute("SELECT COUNT(*) FROM conversations WHERE synced=1").fetchone()[0]
        )
        pending = int(
            connection.execute("SELECT COUNT(*) FROM conversations WHERE synced=0").fetchone()[0]
        )
    assert count == 4 and synced == 1 and pending == 3
    print(
        "TASK_C_MIGRATION=PASS "
        "run1_before=3 run1_after=3 "
        "run1_added=synced,batch_id,sync_attempted_at,sync_succeeded_at "
        "run2_before=3 run2_after=3 run2_added=none parity=true"
    )
    print(
        "TASK_C_CONVERSATION_ROUND_TRIP=PASS write=true read=true "
        f"records={count} previously_synced_preserved={synced} pending={pending}"
    )


def _module_path(name: str) -> Path | None:
    candidate = ROOT.joinpath(*name.split(".")).with_suffix(".py")
    if candidate.exists():
        return candidate
    candidate = CENTRAL.joinpath(*name.split(".")).with_suffix(".py")
    return candidate if candidate.exists() else None


def boundary_violations(entrypoint: Path) -> list[str]:
    """AST import-graph and SQL-table allowlist for the sync boundary."""
    violations: list[str] = []
    queued = [entrypoint]
    visited: set[Path] = set()
    while queued:
        path = queued.pop()
        if path in visited:
            continue
        visited.add(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [
                    ".".join(part for part in (node.module or "", alias.name) if part)
                    for alias in node.names
                ]
            for name in names:
                lowered = name.lower()
                if "teachme" in lowered or "user_route" in lowered or "user_router" in lowered:
                    violations.append(f"disallowed import: {name}")
                module_name = name.rsplit(".", 1)[0] if "." in name else name
                dependency = _module_path(module_name)
                if dependency is not None:
                    queued.append(dependency)
        if path == entrypoint:
            for literal in (
                node.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
            ):
                if not re.search(r"\b(?:SELECT|INSERT|UPDATE|CREATE)\b", literal, re.I):
                    continue
                matches = list(re.finditer(
                    r"\b(?:FROM|JOIN|INTO)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                    literal, flags=re.IGNORECASE,
                ))
                matches.extend(re.finditer(
                    r"^\s*UPDATE\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                    literal, flags=re.IGNORECASE | re.MULTILINE,
                ))
                for match in matches:
                    if match.group(1).lower() not in {"conversations", "sync_state"}:
                        violations.append(f"disallowed SQL table: {match.group(1)}")
    return sorted(set(violations))


def test_d_static_boundary_negative_control_then_clean(tmp_path) -> None:
    source = CENTRAL / "services" / "cloud_sync_service.py"
    clean = boundary_violations(source)
    assert clean == []
    broken = tmp_path / "cloud_sync_service.py"
    broken.write_text(
        source.read_text(encoding="utf-8") + "\nfrom routes import user_router\n",
        encoding="utf-8",
    )
    detected = boundary_violations(broken)
    assert "disallowed import: routes.user_router" in detected
    repaired = boundary_violations(source)
    assert repaired == []
    print(f"TASK_D_NEGATIVE_CONTROL=EXPECTED_FAIL violations={detected}")
    print("TASK_D_REPAIRED_BASELINE=PASS violations=[] import_graph=clean sql_tables=allowlisted")


class FailOnceClient:
    def __init__(self) -> None:
        self.calls = 0

    async def send_batch(self, value: PendingBatch) -> dict:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("forced scheduled-run exception")
        return {"acknowledged": True, "batch_id": value.batch_id, "duplicate": False}


@pytest.mark.asyncio
async def test_e_supervision_survives_and_restart_uses_persisted_time(tmp_path) -> None:
    database = database_with_records(tmp_path / "central.sqlite3", 1)
    outbox = ConversationOutbox(database)
    client = FailOnceClient()
    config = settings(
        "http://unused.invalid",
        interval_seconds=0.5,
        supervisor_retry_seconds=0.05,
        retry_attempts=1,
    )
    service = CloudSyncService(outbox, client, config)
    started = datetime.now(timezone.utc)
    service.start()
    deadline = time.monotonic() + 2
    while outbox.status()["last_successful_sync"] is None and time.monotonic() < deadline:
        await asyncio_sleep(0.01)
    assert client.calls == 2 and service.running
    success = outbox.status()["last_successful_sync"]
    await service.stop()

    restarted = CloudSyncService(outbox, FailOnceClient(), config)
    delay = restarted.seconds_until_next_run()
    assert 0 < delay <= config.interval_seconds
    print(
        "TASK_E_EXCEPTION_SURVIVAL=PASS "
        f"first_run={started.isoformat()} forced_exception=true next_run_calls={client.calls} "
        f"next_run_success={success} task_alive_before_stop=true"
    )
    print(
        "TASK_E_RESTART_TIMING=PASS "
        f"persisted_last_success={success} interval_s={config.interval_seconds:.3f} "
        f"computed_next_run_in_s={delay:.3f} immediate=false doubled_wait=false"
    )


async def asyncio_sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


@pytest.mark.asyncio
async def test_f_ten_batches_failure_retry_and_duplicate_delivery(tmp_path) -> None:
    database = database_with_records(tmp_path / "central.sqlite3", 10)
    with live_receiver() as (receiver, base_url):
        receiver.drop_ack_after_store_remaining = 2
        config = settings(base_url, batch_size=1, retry_initial_delay_seconds=0.02,
                          retry_max_delay_seconds=0.02)
        service = CloudSyncService(
            ConversationOutbox(database), CloudSyncClient(config), config
        )
        results = [await service.run_once() for _ in range(10)]
        with sqlite3.connect(database) as connection:
            synced = int(
                connection.execute("SELECT COUNT(*) FROM conversations WHERE synced=1").fetchone()[0]
            )
        assert synced == 10 and len(receiver.batches) == 10
        assert sum(receiver.attempts.values()) == 12
        assert sum(result["records_synced"] for result in results) == 10

        with sqlite3.connect(database) as connection:
            connection.execute(
                "INSERT INTO conversations (position, record) VALUES (?, ?)",
                (10, json.dumps(sample_record(10))),
            )
        receiver.failures_remaining = config.retry_attempts
        with pytest.raises(Exception, match="HTTP 503"):
            await service.run_once()
        failed_status = service.outbox.status()
        with sqlite3.connect(database) as connection:
            failed_row = connection.execute(
                """SELECT synced, batch_id, sync_attempted_at FROM conversations
                   WHERE position=10"""
            ).fetchone()
        assert failed_row[0] == 0 and failed_row[1] and failed_row[2]
        receiver.failures_remaining = 0
        recovered = await service.run_once()
        final_status = service.outbox.status()
        assert recovered["batch_id"] == failed_row[1]
        assert final_status["pending_records"] == 0
        assert len(receiver.batches) == 11
        print(
            "TASK_F_FULL_CYCLE=PASS local_batches=10 local_records_synced=10 "
            "receiver_batches=10 receiver_records=10"
        )
        dedupe_hits = sum(bool(result["receiver_duplicate"]) for result in results)
        print(
            "TASK_F_DUPLICATE_DELIVERY=PASS forced_ack_losses=2 "
            f"receiver_delivery_attempts=12 receiver_batches=10 dedupe_hits={dedupe_hits} "
            "local_double_count=0"
        )
        print(
            "TASK_F_FAILURE_RETRY=PASS "
            f"failed_synced={failed_row[0]} attempted_at={failed_row[2]} "
            f"retry_batch_same={recovered['batch_id'] == failed_row[1]} "
            f"final_pending={final_status['pending_records']} receiver_batches={len(receiver.batches)}"
        )


def test_g_status_endpoint_is_accurate_and_internally_authenticated(tmp_path, monkeypatch) -> None:
    database = database_with_records(tmp_path / "central.sqlite3", 1)
    outbox = ConversationOutbox(database)
    last_success = datetime(2026, 9, 11, 12, 34, 56, tzinfo=timezone.utc)
    outbox.record_empty_success(last_success)
    config = settings("http://unused.invalid", enabled=False)
    service = CloudSyncService(outbox, CloudSyncClient(config), config)

    app = FastAPI()
    app.state.cloud_sync_service = service
    app.include_router(sync_router)
    install_error_handlers(app, "phase7-status-fixture")
    monkeypatch.setenv("AUTH_ENFORCEMENT_ENABLED", "true")
    monkeypatch.setenv("NEXI_INTERNAL_SERVICE_TOKEN", "phase7-service-token")
    with TestClient(app) as client:
        rejected = client.get("/sync/status")
        accepted = client.get(
            "/sync/status", headers={"X-NEXI-Service-Token": "phase7-service-token"}
        )
    assert rejected.status_code == 401 and set(rejected.json()) == {"error"}
    assert accepted.status_code == 200
    assert accepted.json()["pending_records"] == 1
    assert accepted.json()["last_successful_sync"] == last_success.isoformat()
    print(
        "TASK_G_UNAUTHORIZED "
        f"HTTP={rejected.status_code} body={json.dumps(rejected.json(), separators=(',', ':'))}"
    )
    print(
        "TASK_G_AUTHORIZED "
        f"HTTP={accepted.status_code} body={json.dumps(accepted.json(), separators=(',', ':'))} "
        "actual_outbox_pending=1"
    )
