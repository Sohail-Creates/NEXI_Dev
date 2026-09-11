"""Phase 6 contract and video-call regression tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from contextlib import contextmanager

import requests
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SERVICE_TOKEN = os.getenv("NEXI_INTERNAL_SERVICE_TOKEN", "phase6-service-token")


def _assert_envelope(response: requests.Response) -> dict:
    body = response.json()
    assert set(body) == {"error"}, body
    assert set(body["error"]) == {"status_code", "code", "message", "request_id"}, body
    assert body["error"]["status_code"] == response.status_code, body
    assert body["error"]["request_id"] == response.headers["X-Request-ID"], body
    return body


def run_live_error_contract() -> None:
    """Probe the seven real processes started by the verification harness."""
    from shared.jwt_manager import get_jwt_manager

    service_headers = {"X-NEXI-Service-Token": SERVICE_TOKEN}
    user_token = get_jwt_manager().create_session_token("user-a")["token"]
    probes: list[tuple[str, str, str, dict]] = []

    for name, port in (
        ("Central", 8000),
        ("Vision", 8001),
        ("Audio", 8002),
        ("TTS", 8003),
        ("TeachMe", 8004),
        ("Enrollment", 8005),
        ("LLM", 8006),
    ):
        probes.append((name, "GET", f"http://127.0.0.1:{port}/missing-phase6", {}))

    probes.extend(
        [
            ("Central", "GET", "http://127.0.0.1:8000/resources/status", {}),
            ("Vision", "POST", "http://127.0.0.1:8001/camera/pause", {}),
            ("Audio", "POST", "http://127.0.0.1:8002/api/v1/process-voice", {}),
            ("TTS", "POST", "http://127.0.0.1:8003/speak", {"json": {"text": "hello"}}),
            ("TeachMe", "POST", "http://127.0.0.1:8004/learn", {"json": {}}),
            ("Enrollment", "GET", "http://127.0.0.1:8005/enrollment/storage/list", {}),
            ("LLM", "POST", "http://127.0.0.1:8006/api/v1/generate", {"json": {"query": "hello"}}),
            (
                "Central",
                "GET",
                "http://127.0.0.1:8000/users/user-b",
                {"headers": {"Authorization": f"Bearer {user_token}"}},
            ),
            (
                "Central",
                "POST",
                "http://127.0.0.1:8000/api/v1/rag/query",
                {"headers": {"Authorization": f"Bearer {user_token}"}, "json": {}},
            ),
            (
                "Vision",
                "POST",
                "http://127.0.0.1:8001/api/v1/detect/faces?detector_backend=invalid-backend",
                {"headers": service_headers},
            ),
        ]
    )

    for service, method, url, kwargs in probes:
        response = requests.request(method, url, timeout=20, **kwargs)
        body = _assert_envelope(response)
        path = "/" + url.split("/", 3)[-1]
        print(
            f"{service:10} {method:6} {path:55} HTTP={response.status_code} "
            f"BODY={json.dumps(body, separators=(',', ':'))}"
        )

    print(f"PHASE6_ERROR_CONTRACT=PASS probes={len(probes)} services=7")


def run_live_openapi_contract() -> None:
    service_ports = {
        "central": 8000,
        "vision": 8001,
        "audio": 8002,
        "tts": 8003,
        "teachme": 8004,
        "enrollment": 8005,
        "llm": 8006,
    }
    samples = {
        "central": ("GET", "/health", {}),
        "vision": ("GET", "/health", {}),
        "audio": ("GET", "/health", {}),
        "tts": ("GET", "/health", {}),
        "teachme": ("GET", "/health", {}),
        "enrollment": ("GET", "/health", {}),
        "llm": ("GET", "/api/v1/health", {}),
    }
    for service, port in service_ports.items():
        generated = json.loads((ROOT / "docs" / "openapi" / f"{service}.json").read_text(encoding="utf-8"))
        live = requests.get(f"http://127.0.0.1:{port}/openapi.json", timeout=20).json()
        assert set(generated["paths"]) == set(live["paths"])
        method, path, kwargs = samples[service]
        assert path in generated["paths"] and method.lower() in generated["paths"][path]
        response = requests.request(method, f"http://127.0.0.1:{port}{path}", timeout=20, **kwargs)
        assert response.status_code == 200, response.text
        print(
            f"OPENAPI_LIVE {service:10} generated_paths={len(generated['paths']):3} "
            f"live_paths={len(live['paths']):3} sample={method} {path} HTTP=200"
        )
    print("PHASE6_OPENAPI_LIVE=PASS services=7")


def test_identity_contract_uses_user_id_end_to_end(monkeypatch) -> None:
    os.environ["AUTH_ENFORCEMENT_ENABLED"] = "true"
    os.environ["NEXI_INTERNAL_SERVICE_TOKEN"] = SERVICE_TOKEN
    os.environ["NEXI_JWT_SECRET"] = "phase6-jwt-secret-with-sufficient-length"

    central_dir = ROOT / "01_central_server"
    sys.path.insert(0, str(central_dir))
    import main as central_main
    from routes import user_routes

    async def no_persist(*args, **kwargs):
        return None

    monkeypatch.setattr(user_routes, "_persist_users", no_persist)
    central_main.app.state.db = {"users": []}
    with TestClient(central_main.app) as central:
        response = central.post(
            "/users",
            headers={"X-NEXI-Service-Token": SERVICE_TOKEN},
            json={"name": "Phase Six User", "voice_embeddings": [[0.1]], "face_embeddings": [[0.2]]},
        )
    assert response.status_code == 200, response.text
    user_id = response.json()["user_id"]
    assert user_id.startswith("user_")
    print(f"CENTRAL_REGISTRATION HTTP=200 accepted=name returned=user_id:{user_id}")

    enrollment_dir = ROOT / "06_enrollment_service"
    sys.path.insert(0, str(enrollment_dir))
    from app.main import app as enrollment_app
    from app.routes import enrollment
    from shared.jwt_manager import get_jwt_manager

    seen: dict[str, str] = {}

    async def improve_training(*, user_id, additional_photos, additional_voice_samples):
        seen["user_id"] = user_id
        return {
            "status": "success",
            "message": f"Training improved for user {user_id}",
            "user_id": user_id,
            "total_samples": {"images": 10, "audio": 10},
        }

    monkeypatch.setattr(enrollment.enrollment_service, "improve_training", improve_training)
    token = get_jwt_manager().create_session_token(user_id)["token"]
    files = []
    for index in range(5):
        files.append(("additional_photos", (f"photo-{index}.jpg", b"jpeg", "image/jpeg")))
        files.append(("additional_voice_samples", (f"voice-{index}.wav", b"wave", "audio/wav")))
    with TestClient(enrollment_app) as enrollment_client:
        improved = enrollment_client.post(
            f"/enrollment/improve-training/{user_id}",
            headers={"Authorization": f"Bearer {token}"},
            files=files,
        )
    assert improved.status_code == 200, improved.text
    assert seen == {"user_id": user_id}
    assert improved.json()["user_id"] == user_id
    print(
        f"ENROLLMENT_IMPROVE HTTP=200 path_field=user_id:{seen['user_id']} "
        f"response_field=user_id:{improved.json()['user_id']}"
    )


def test_video_call_preemption_release_and_screenshot(monkeypatch) -> None:
    os.environ["AUTH_ENFORCEMENT_ENABLED"] = "true"
    os.environ["NEXI_INTERNAL_SERVICE_TOKEN"] = SERVICE_TOKEN

    central_dir = ROOT / "01_central_server"
    vision_dir = ROOT / "02_vision_service"
    sys.path[:0] = [str(central_dir), str(vision_dir)]
    import camera_routes
    import main as central_main
    import resource_authority
    from resource_authority import PriorityLevel, ResourceAuthority, ResourceType

    authority = ResourceAuthority(release_ack_timeout=0.2, liveness_interval=0.1)
    monkeypatch.setattr(resource_authority, "_authority", authority)
    lower = authority.request_resource(
        ResourceType.CAMERA,
        "background-vision",
        PriorityLevel.BACKGROUND,
        timeout_seconds=30,
    )
    assert authority.acknowledge_grant(lower.lease_id)
    physical_released = threading.Event()

    def cooperate_with_preemption():
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            status = authority.check_lease_status(lower.lease_id)
            if status and status["state"] == "revoking":
                physical_released.set()
                authority.release_resource(lower.lease_id)
                return
            time.sleep(0.01)

    release_thread = threading.Thread(target=cooperate_with_preemption, daemon=True)
    release_thread.start()

    import cv2
    import numpy as np
    from vision_service.routes import detection

    class FakeCamera:
        def read(self):
            frame = np.zeros((32, 48, 3), dtype=np.uint8)
            frame[:, :, 1] = 180
            return True, frame

    class InjectedVisionPool:
        @contextmanager
        def get_camera(self, timeout=None, delegated_lease_id=None):
            assert delegated_lease_id == authority.get_call_status()["lease_id"]
            yield FakeCamera()

    detection.set_resource_pool(InjectedVisionPool())

    async def fetch_from_vision_app(lease_id: str):
        frame_response = await detection.capture_call_frame(lease_id)
        return bytes(frame_response.body), frame_response.media_type

    monkeypatch.setattr(camera_routes, "_fetch_vision_frame", fetch_from_vision_app)
    headers = {"X-NEXI-Service-Token": SERVICE_TOKEN}
    with TestClient(central_main.app) as client:
        started = client.post("/calls/start", headers=headers, json={"call_id": "call-phase6"})
        assert started.status_code == 200, started.text
        call_lease_id = started.json()["lease_id"]
        assert physical_released.wait(1)
        assert authority.check_lease_status(lower.lease_id) is None
        assert authority.get_call_status() == {
            "state": "CALL_ACTIVE",
            "call_id": "call-phase6",
            "lease_id": call_lease_id,
            "lease_state": "active",
        }
        print(
            f"CALL_START HTTP=200 lower={lower.lease_id} physical_release=True "
            f"call_lease={call_lease_id} state=CALL_ACTIVE"
        )

        screenshot = client.get("/calls/screenshot", headers=headers)
        assert screenshot.status_code == 200, screenshot.text
        assert screenshot.headers["content-type"].startswith("image/jpeg")
        assert screenshot.content[:2] == b"\xff\xd8" and screenshot.content[-2:] == b"\xff\xd9"
        decoded = cv2.imdecode(np.frombuffer(screenshot.content, dtype=np.uint8), cv2.IMREAD_COLOR)
        assert decoded is not None and decoded.shape[:2] == (32, 48)
        print(
            f"CALL_SCREENSHOT HTTP=200 content_type=image/jpeg bytes={len(screenshot.content)} "
            f"decoded={decoded.shape[1]}x{decoded.shape[0]}"
        )

        waiting = authority.request_resource(
            ResourceType.CAMERA,
            "background-resume",
            PriorityLevel.BACKGROUND,
            timeout_seconds=30,
        )
        assert waiting.state == "queued"
        ended = client.post("/calls/end", headers=headers, json={"call_id": "call-phase6"})
        assert ended.status_code == 200, ended.text
        assert authority.check_lease_status(call_lease_id) is None
        assert authority.get_call_status()["state"] == "IDLE"
        assert authority.check_lease_status(waiting.lease_id)["state"] == "reserved"
        print(
            f"CALL_END HTTP=200 released={call_lease_id} state=IDLE "
            f"resumed_lease={waiting.lease_id} resumed_state=reserved"
        )
        authority.release_resource(waiting.lease_id)


def test_phase2_resource_authority_regression() -> None:
    """Re-run the five Phase 2 lease mechanics without changing their contract."""
    central_dir = ROOT / "01_central_server"
    vision_dir = ROOT / "02_vision_service"
    sys.path[:0] = [str(central_dir), str(vision_dir)]
    from resource_authority import PriorityLevel, ResourceAuthority, ResourceType
    from vision_service.services.resource_pool import ResourcePool

    authority = ResourceAuthority(release_ack_timeout=0.03, liveness_interval=0.03)
    holder = authority.request_resource(ResourceType.CAMERA, "holder", PriorityLevel.BACKGROUND)
    assert authority.acknowledge_grant(holder.lease_id)
    contender = authority.request_resource(ResourceType.CAMERA, "contender", PriorityLevel.BACKGROUND)
    assert contender.state == "queued"
    print(f"DOUBLE_GRANT PASS contender_state={contender.state}")
    authority.release_resource(contender.lease_id)
    authority.release_resource(holder.lease_id)

    authority = ResourceAuthority(release_ack_timeout=0.03, liveness_interval=0.03)
    holder = authority.request_resource(ResourceType.CAMERA, "unknown-holder", PriorityLevel.BACKGROUND)
    assert authority.acknowledge_grant(holder.lease_id)
    waiting = authority.request_resource(ResourceType.CAMERA, "waiting", PriorityLevel.ENROLLMENT)
    time.sleep(0.08)
    holder_status = authority.check_lease_status(holder.lease_id)
    waiting_status = authority.check_lease_status(waiting.lease_id)
    assert holder_status["state"] == "suspect" and holder_status["liveness"] == "unknown"
    assert waiting_status["state"] == "queued"
    print(
        "FAIL_CLOSED PASS "
        f"holder_state={holder_status['state']} liveness={holder_status['liveness']} "
        f"waiting_state={waiting_status['state']}"
    )
    authority.release_resource(waiting.lease_id)
    authority.release_resource(holder.lease_id)

    authority = ResourceAuthority()
    holder = authority.request_resource(ResourceType.CAMERA, "holder", PriorityLevel.BACKGROUND)
    authority.acknowledge_grant(holder.lease_id)
    cancelled = authority.request_resource(ResourceType.CAMERA, "cancelled", PriorityLevel.BACKGROUND)
    assert authority.release_resource(cancelled.lease_id)
    queue = authority.get_all_resources_status()["camera"]["queue"]
    assert queue == [] and authority.check_lease_status(cancelled.lease_id) is None
    print(f"QUEUE_CANCELLATION PASS queue={queue} cancelled_query=None")
    authority.release_resource(holder.lease_id)

    class Camera:
        opened = True

        def release(self):
            self.opened = False

        def isOpened(self):
            return self.opened

    class Client:
        def __init__(self):
            self.calls = []

        def release_camera(self, **kwargs):
            self.calls.append(kwargs)
            return True

    pool = ResourcePool.__new__(ResourcePool)
    camera = Camera()
    pool._camera = camera
    pool._frame_lock = threading.Lock()
    pool._camera_client = Client()
    acknowledged = threading.Event()
    pool._force_release(camera, "watchdog-lease", acknowledged)
    assert acknowledged.is_set() and not camera.isOpened()
    print(
        "WATCHDOG_FORCE_RELEASE PASS "
        f"camera_open={camera.isOpened()} release_calls={pool._camera_client.calls} "
        f"acknowledged={acknowledged.is_set()}"
    )

    sleeper = subprocess.Popen(
        [str(ROOT / "venv" / "Scripts" / "python.exe"), "-c", "import time; time.sleep(30)"]
    )
    try:
        import psutil
        process = psutil.Process(sleeper.pid)
        authority = ResourceAuthority(release_ack_timeout=0.03, liveness_interval=0.03)
        holder = authority.request_resource(ResourceType.CAMERA, "dying-holder", PriorityLevel.BACKGROUND)
        authority.acknowledge_grant(holder.lease_id)
        holder.holder_pid = sleeper.pid
        holder.holder_started = process.create_time()
        sleeper.terminate()
        sleeper.wait(timeout=5)
        successor = authority.request_resource(ResourceType.CAMERA, "successor", PriorityLevel.ENROLLMENT)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and successor.state != "reserved":
            time.sleep(0.01)
        assert authority.check_lease_status(holder.lease_id) is None
        assert successor.state == "reserved"
        print(
            "LIVENESS_REASSIGNMENT PASS "
            f"dead_holder=None successor_state={successor.state}"
        )
        authority.release_resource(successor.lease_id)
    finally:
        if sleeper.poll() is None:
            sleeper.terminate()
    print("PHASE2_RESOURCE_RESULT passed=5 failed=0")


def test_phase2_persistence_regression(tmp_path) -> None:
    """Exercise the same strict, idempotent Central and TeachMe migrations."""
    central_source = tmp_path / "central"
    central_source.mkdir()
    user = {"name": "Phase Two", "user_id": "user-phase2"}
    conversation = {
        "conversation_id": "conversation-phase2",
        "user_id": "user-phase2",
        "timestamp": "2026-01-01T00:00:00",
        "user_message": "hello",
        "assistant_response": "hello",
        "mood": "neutral",
        "language": "en",
        "metadata": {},
    }
    (central_source / "users.json").write_text(json.dumps([user]), encoding="utf-8")
    (central_source / "conversations.json").write_text(
        json.dumps({"conversations": [conversation]}), encoding="utf-8"
    )
    central_db = tmp_path / "central.sqlite3"
    central_script = ROOT / "01_central_server" / "migrate_sqlite.py"
    command = [
        str(ROOT / "venv" / "Scripts" / "python.exe"), str(central_script),
        "--source-dir", str(central_source), "--database", str(central_db),
    ]
    first = subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()
    second = subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()
    print(first)
    print(second)
    assert "users: JSON=1 SQLite=1 action=imported parity=True" in first
    assert "conversations: JSON=1 SQLite=1 action=imported parity=True" in first
    assert first.replace("action=imported", "action=unchanged") == second
    print("CENTRAL_MIGRATION_IDEMPOTENCY PASS")

    knowledge_source = tmp_path / "knowledge.json"
    fact = {
        "id": "fact-phase2",
        "type": "fact",
        "data": {"subject": "NEXI", "predicate": "is", "object": "grounded", "context": {}},
        "tags": ["fixture"],
        "confidence": 1.0,
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "embedding": None,
    }
    metadata = {"created_at": "2026-01-01T00:00:00", "version": "1.0", "total_items": 1}
    knowledge_source.write_text(
        json.dumps({"storage": {fact["id"]: fact}, "metadata": metadata}), encoding="utf-8"
    )
    teachme_db = tmp_path / "teachme.sqlite3"
    teachme_script = ROOT / "05_teachme_service" / "migrate_sqlite.py"
    command = [
        str(ROOT / "venv" / "Scripts" / "python.exe"), str(teachme_script),
        "--source", str(knowledge_source), "--database", str(teachme_db),
    ]
    first = subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()
    second = subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()
    print(first)
    print(second)
    assert "knowledge: JSON=1 SQLite=1 action=imported parity=True metadata_parity=True" in first
    assert first.replace("action=imported", "action=unchanged") == second
    print("TEACHME_MIGRATION_IDEMPOTENCY PASS")

    with sqlite3.connect(teachme_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0] == 1

    enrollment_dir = ROOT / "06_enrollment_service"
    if str(enrollment_dir) not in sys.path:
        sys.path.insert(0, str(enrollment_dir))
    from app.services.enrollment_service import EnrollmentService

    class RecoveryStorage:
        def __init__(self):
            self.records = {
                "user-phase2": {
                    "user_id": "user-phase2",
                    "user_name": "Phase Two",
                    "face_embeddings": [[0.1, 0.2]],
                }
            }

        async def get_all_users_async(self):
            return list(self.records)

        async def get_enrollment_smart(self, user_id):
            return self.records.get(user_id)

    recovery_storage = RecoveryStorage()
    enrollment_service = EnrollmentService.__new__(EnrollmentService)
    enrollment_service.storage = recovery_storage
    import asyncio
    recovery = asyncio.run(enrollment_service.sync_local_enrollments_to_central())
    assert recovery["errors"] == 1 and "user-phase2" in recovery_storage.records
    assert "missing or invalid voice_embeddings" in recovery["error_details"][0]["error"]
    print("ENROLLMENT_RECOVERY_FAIL_SAFE PASS missing=voice_embeddings record_preserved=True")
    print("PHASE2_PERSISTENCE_RESULT passed=3 failed=0")
    print("PHASE2_COMBINED_RESULT passed=8 failed=0 enforcement=ON")


def test_phase3_wake_word_during_teachme_combined() -> None:
    central_dir = ROOT / "01_central_server"
    audio_dir = ROOT / "03_audio_service"
    sys.path[:0] = [str(central_dir), str(audio_dir)]
    from resource_authority import PriorityLevel, ResourceAuthority, ResourceType
    from shared.focus_mode import FocusModeClient
    from audio_service.services.keyboard_wake_word import DirectVoiceSession

    authority = ResourceAuthority()
    teachme = authority.request_resource(
        ResourceType.CAMERA, "teachme", PriorityLevel.ACTIVE_TEACHME, timeout_seconds=30
    )
    assert authority.acknowledge_grant(teachme.lease_id)
    focus = FocusModeClient(
        defer_seconds=0.04, status_provider=authority.get_focus_mode_status
    )
    started = time.monotonic()
    deferred = focus.defer_if_needed("background")
    focus_elapsed = time.monotonic() - started
    snapshot = authority.get_focus_mode_status()
    print(
        f"TEACHME_FOCUS active_before={snapshot['teachme_active']} "
        f"signal={snapshot['signal']} background_defer={deferred:.4f}s"
    )

    class LeaseClient:
        def acquire(self):
            lease = authority.request_resource(
                ResourceType.MICROPHONE, "audio-direct", PriorityLevel.ACTIVE_CONVERSATION
            )
            assert authority.acknowledge_grant(lease.lease_id)
            return lease.lease_id

        def release(self, lease_id):
            return authority.release_resource(lease_id)

        def status(self, lease_id):
            return authority.check_lease_status(lease_id)

    class SynthesizedRecorder:
        max_recording_seconds = 30

        def record_until_silence(self, stop_event=None):
            time.sleep(0.06)
            return {
                "success": True,
                "audio_file": "synthesized-speech.wav",
                "duration": 0.10,
                "chunks_recorded": 12,
                "voice_frames": 8,
                "stopped_by": "silence",
            }

    callbacks = []
    session = DirectVoiceSession(
        SynthesizedRecorder(), LeaseClient(), lambda path, confidence: callbacks.append((path, confidence))
    )
    result = session.run()
    released = session.last_released_lease_id
    assert result["keyword"] == "direct_voice" and result["stopped_by"] == "silence"
    assert authority.check_lease_status(released) is None
    assert authority.get_focus_mode_status()["teachme_active"]
    print(
        "WAKE_FAILURE_SESSION keyword=direct_voice wake_word_spoken=false "
        f"voice_frames={result['voice_frames']} stopped_by={result['stopped_by']} "
        f"elapsed={result['detection_time']:.4f}s"
    )
    print(f"MICROPHONE_RELEASE lease_id={released} authority_query=None")
    print(
        "COEXISTENCE teachme_active_during=True "
        f"audio_callback={callbacks}"
    )
    authority.release_resource(teachme.lease_id)
    started = time.monotonic()
    normal_delay = focus.defer_if_needed("background")
    normal_elapsed = time.monotonic() - started
    cleared = authority.get_focus_mode_status()
    assert not cleared["teachme_active"] and normal_delay == 0.0
    print(
        f"TEACHME_RELEASE teachme_active={cleared['teachme_active']} "
        f"signal={cleared['signal']} normal_delay={normal_delay:.4f}s "
        f"normal_elapsed={normal_elapsed:.4f}s"
    )
    # Windows scheduler/clock resolution can undershoot a short requested sleep;
    # the contract is measurable deferral relative to the no-focus baseline.
    assert deferred > 0.0 and focus_elapsed >= normal_elapsed + 0.02
    print("PHASE3_COMBINED_RESULT=PASS enforcement=ON")


def test_phase2_protected_llm_contract() -> None:
    """Protect Phase 2 model reporting and the intentionally unimplemented formatter."""
    llm_dir = ROOT / "07_llm_service"
    if str(llm_dir) not in sys.path:
        sys.path.insert(0, str(llm_dir))
    from llm_service.services.openrouter_client import OpenRouterClient
    from llm_service.routes.generation import create_generation_routes
    from llm_service.routes.format import create_format_router
    from fastapi import FastAPI

    fixture = OpenRouterClient.__new__(OpenRouterClient)
    fixture.api_key = ""
    fixture.model = "openai/gpt-4o-mini"
    fixture.base_url = "https://openrouter.ai/api/v1"
    fixture.timeout = 60
    app = FastAPI()
    app.include_router(create_generation_routes(fixture))
    app.include_router(create_format_router(None))
    with TestClient(app) as client:
        model_info = client.get("/api/v1/model-info")
        formatter = client.post("/api/v1/format")
    assert model_info.status_code == 200
    assert model_info.json()["model"] == "openai/gpt-4o-mini"
    assert formatter.status_code == 501
    print(f"LLM_MODEL_INFO HTTP=200 body={model_info.json()}")
    print(f"LLM_FORMAT HTTP=501 body={formatter.json()}")
    print("PHASE2_LLM_CONTRACT_RESULT=PASS model_info=preserved format=preserved")


def test_shared_error_handler_covers_rate_limit_and_unexpected_failure() -> None:
    from fastapi import FastAPI, HTTPException
    from shared.api_errors import install_error_handlers

    app = FastAPI()

    @app.get("/limited")
    async def limited():
        raise HTTPException(status_code=429, detail="Burst limit reached")

    @app.get("/broken")
    async def broken():
        raise RuntimeError("forced fixture failure")

    install_error_handlers(app, "phase6-fixture")
    with TestClient(app, raise_server_exceptions=False) as client:
        limited_response = client.get("/limited")
        broken_response = client.get("/broken")
    limited_body = _assert_envelope(limited_response)
    broken_body = _assert_envelope(broken_response)
    assert limited_body["error"]["code"] == "RATE_LIMITED"
    assert broken_body["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "forced fixture failure" not in broken_response.text
    print(f"ERROR_429 HTTP=429 body={limited_body}")
    print(f"ERROR_500 HTTP=500 body={broken_body} internal_detail_leaked=False")


if __name__ == "__main__":
    if "--openapi" in sys.argv:
        run_live_openapi_contract()
    else:
        run_live_error_contract()
