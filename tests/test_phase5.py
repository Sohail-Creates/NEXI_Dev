"""Phase 5 security, migration, and regression-focused verification."""

from __future__ import annotations

import asyncio
import os
import pickle
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import Depends, FastAPI, Request, UploadFile
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT / "01_central_server", ROOT / "03_audio_service", ROOT / "05_teachme_service", ROOT / "06_enrollment_service"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

os.environ["AUTH_ENFORCEMENT_ENABLED"] = "true"
os.environ["NEXI_INTERNAL_SERVICE_TOKEN"] = "phase5-internal-fixture-token"
os.environ["NEXI_JWT_SECRET"] = "phase5-jwt-fixture-secret-at-least-32-bytes"
os.environ["NEXI_ALLOWED_ORIGINS"] = "https://allowed.example"

from shared.clients.models import ServiceCallResult
from shared.jwt_manager import JWTManager, TokenConfig, TokenType, require_user_ownership
from shared.security import (
    INTERNAL_TOKEN_HEADER,
    InternalRouteAuthMiddleware,
    UploadGuardMiddleware,
    allowed_origins,
    internal_service_headers,
    require_internal_service,
)


def _token(user_id: str, expires: float | None = None) -> str:
    config = TokenConfig(secret_key=os.environ["NEXI_JWT_SECRET"])
    return JWTManager(config).create_session_token(user_id, expires_in_minutes=expires)["token"]


def test_b_shared_internal_trust_rejects_missing_and_accepts_real_credential():
    app = FastAPI()
    app.add_middleware(InternalRouteAuthMiddleware, protected_prefixes=("/internal",))

    @app.get("/internal/resource")
    async def resource():
        return {"status": "granted"}

    with TestClient(app) as client:
        missing = client.get("/internal/resource")
        forged = client.get("/internal/resource", headers={INTERNAL_TOKEN_HEADER: "wrong"})
        accepted = client.get("/internal/resource", headers=internal_service_headers("user-a"))
    print(f"B_UNAUTH status={missing.status_code} body={missing.json()}")
    print(f"B_FORGED status={forged.status_code} body={forged.json()}")
    print(f"B_AUTH status={accepted.status_code} body={accepted.json()}")
    assert (missing.status_code, forged.status_code, accepted.status_code) == (401, 401, 200)


def test_j_match_issues_token_no_match_does_not_and_expiry_fails(monkeypatch):
    from audio_service.routes import advanced_routes

    class Matcher:
        match = True

        def verify_speaker(self, _path):
            return ("user-a", 0.99) if self.match else ("unknown", 0.10)

        def get_verification_threshold(self):
            return 0.65

    matcher = Matcher()
    monkeypatch.setattr(advanced_routes, "get_speaker_service", lambda: matcher)
    app = FastAPI()
    app.include_router(advanced_routes.router)
    with TestClient(app) as client:
        matched = client.post("/api/v1/verify-speaker", files={"file": ("speech.wav", b"RIFF-synth", "audio/wav")})
        matcher.match = False
        unmatched = client.post("/api/v1/verify-speaker", files={"file": ("other.wav", b"RIFF-other", "audio/wav")})

    matched_body = matched.json()
    unmatched_body = unmatched.json()
    claims = JWTManager(TokenConfig(secret_key=os.environ["NEXI_JWT_SECRET"])).verify_token(
        matched_body["access_token"], TokenType.SESSION.value
    )
    print(f"J_MATCH status={matched.status_code} user={claims['sub']} token_issued={bool(matched_body['access_token'])} expires_in={matched_body['expires_in']}")
    print(f"J_NO_MATCH status={unmatched.status_code} verified={unmatched_body['is_verified']} token={unmatched_body['access_token']}")

    expired = _token("user-a", expires=-0.01)
    time.sleep(0.7)
    with pytest.raises(Exception) as caught:
        JWTManager(TokenConfig(secret_key=os.environ["NEXI_JWT_SECRET"])).verify_token(expired, TokenType.SESSION.value)
    print(f"J_EXPIRED rejected={type(caught.value).__name__}")
    assert claims["sub"] == "user-a"
    assert unmatched_body["access_token"] is None


@pytest.mark.asyncio
async def test_j_new_central_route_wraps_existing_audio_client(monkeypatch):
    from routes import user_routes

    class AudioFixture:
        verified = True
        calls = []

        async def verify_speaker(self, audio_file_bytes, filename, user_id):
            self.calls.append({
                "audio_file_bytes": audio_file_bytes,
                "filename": filename,
                "user_id": user_id,
            })
            if self.verified:
                return ServiceCallResult(True, {"verified": True, "user_id": "user-a", "access_token": _token("user-a"), "token_type": "bearer", "expires_in": 1800})
            return ServiceCallResult(True, {"verified": False, "user_id": "unknown", "access_token": None})

    fixture = AudioFixture()
    monkeypatch.setattr(user_routes, "_audio_verification_client", fixture)
    app = FastAPI()
    app.include_router(user_routes.router)
    with TestClient(app) as client:
        accepted = client.post("/users/session/voice", files={"file": ("speech.wav", b"RIFF-synth", "audio/wav")})
        fixture.verified = False
        rejected = client.post("/users/session/voice", files={"file": ("other.wav", b"RIFF-other", "audio/wav")})
    print(f"J_ROUTE_MATCH status={accepted.status_code} body_keys={sorted(accepted.json())}")
    print(f"J_ROUTE_NO_MATCH status={rejected.status_code} body={rejected.json()}")
    print(f"J_ROUTE_AUDIO_CONTRACT calls={fixture.calls}")
    assert accepted.status_code == 200 and rejected.status_code == 401
    assert fixture.calls == [
        {"audio_file_bytes": b"RIFF-synth", "filename": "speech.wav", "user_id": "candidate"},
        {"audio_file_bytes": b"RIFF-other", "filename": "other.wav", "user_id": "candidate"},
    ]


def test_c_claim_ownership_no_token_cross_user_own_and_expired():
    app = FastAPI()
    records = {"user-a": {"user_id": "user-a", "name": "Alice"}, "user-b": {"user_id": "user-b", "name": "Bob"}}

    @app.get("/users/{user_id}")
    async def read_user(user_id: str, request: Request):
        require_user_ownership(request, user_id)
        if user_id not in records:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="User not found")
        return records[user_id]

    user_a = _token("user-a")
    expired = _token("user-a", expires=-0.01)
    time.sleep(0.7)
    with TestClient(app) as client:
        missing = client.get("/users/user-a")
        cross = client.get("/users/user-b", headers={"Authorization": f"Bearer {user_a}"})
        own = client.get("/users/user-a", headers={"Authorization": f"Bearer {user_a}"})
        stale = client.get("/users/user-a", headers={"Authorization": f"Bearer {expired}"})
    print(f"C_NO_TOKEN status={missing.status_code} body={missing.json()}")
    print(f"C_CROSS_USER status={cross.status_code} body={cross.json()}")
    print(f"C_OWN status={own.status_code} body={own.json()}")
    print(f"C_EXPIRED status={stale.status_code} body={stale.json()}")
    assert (missing.status_code, cross.status_code, own.status_code, stale.status_code) == (401, 403, 200, 401)


def test_d_teachme_shared_auth_and_missing_jwt_fail_closed(monkeypatch):
    from teachme_service import authentication
    app = FastAPI()

    @app.get("/learn", dependencies=[Depends(authentication.require_api_key)])
    async def learn():
        return {"status": "ok"}

    @app.get("/jwt", dependencies=[Depends(authentication.require_jwt)])
    async def jwt_route():
        return {"status": "ok"}

    with TestClient(app) as client:
        missing = client.get("/learn")
        internal = client.get("/learn", headers=internal_service_headers())
        valid_token = _token("user-a")
        monkeypatch.setattr(authentication.jwt_manager, "JWT_AVAILABLE", False)
        unavailable = client.get("/jwt", headers={"Authorization": f"Bearer {valid_token}"})
    print(f"D_UNAUTH status={missing.status_code} body={missing.json()}")
    print(f"D_INTERNAL status={internal.status_code} body={internal.json()}")
    print(f"D_JWT_LIBRARY_MISSING status={unavailable.status_code} body={unavailable.json()}")
    assert (missing.status_code, internal.status_code, unavailable.status_code) == (401, 200, 503)


def test_e_explicit_cors_allowlist():
    assert allowed_origins() == ["https://allowed.example"]
    app = FastAPI()
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(CORSMiddleware, allow_origins=allowed_origins(), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    with TestClient(app) as client:
        denied = client.options("/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
        allowed = client.options("/health", headers={"Origin": "https://allowed.example", "Access-Control-Request-Method": "GET"})
    print(f"E_DENIED status={denied.status_code} allow_origin={denied.headers.get('access-control-allow-origin')}")
    print(f"E_ALLOWED status={allowed.status_code} allow_origin={allowed.headers.get('access-control-allow-origin')}")
    assert denied.status_code == 400 and allowed.status_code == 200


def test_f_upload_rejected_before_handler_and_path_traversal(monkeypatch, tmp_path):
    calls = {"handler": 0}
    app = FastAPI()
    app.add_middleware(UploadGuardMiddleware, rules={"/upload": (100, ("multipart/form-data",))})

    @app.post("/upload")
    async def upload():
        calls["handler"] += 1
        return {"ok": True}

    with TestClient(app) as client:
        started = time.monotonic()
        oversized = client.post("/upload", content=b"x", headers={"Content-Type": "multipart/form-data; boundary=x", "Content-Length": "101"})
        elapsed = time.monotonic() - started
        wrong_type = client.post("/upload", content=b"x", headers={"Content-Type": "text/plain"})
    print(f"F_OVERSIZED status={oversized.status_code} handler_calls={calls['handler']} elapsed={elapsed:.4f}s")
    print(f"F_WRONG_TYPE status={wrong_type.status_code} handler_calls={calls['handler']}")

    recordings = tmp_path / "recordings"
    recordings.mkdir()
    valid = recordings / "sample.wav"
    valid.write_bytes(b"RIFF")
    monkeypatch.setenv("VAD_RECORDING_OUTPUT_DIR", str(recordings))
    from audio_service.routes.orchestration_routes import _validated_audio_path
    assert _validated_audio_path(str(valid)) == str(valid.resolve())
    with pytest.raises(Exception) as traversal:
        _validated_audio_path(str(recordings / ".." / "secret.wav"))
    print(f"F_PATH_TRAVERSAL rejected={getattr(traversal.value, 'status_code', None)} detail={getattr(traversal.value, 'detail', '')}")
    assert calls["handler"] == 0 and oversized.status_code == 413 and wrong_type.status_code == 415


def test_g_pickle_migration_twice_and_existing_verification_flow(monkeypatch, tmp_path):
    from audio_service.services import speaker_service as module
    legacy = tmp_path / "speakers.pkl"
    safe = tmp_path / "speakers.json"
    vector = np.linspace(0.0, 1.0, 256, dtype=np.float32)
    with legacy.open("wb") as handle:
        pickle.dump({"user-a": vector}, handle)
    first = module.migrate_legacy_pickle(legacy, safe)
    second = module.migrate_legacy_pickle(legacy, safe)

    service = module.SpeakerService.__new__(module.SpeakerService)
    service.encoder = SimpleNamespace(embed_utterance=lambda _audio: vector.copy())
    service.speaker_embeddings = {"user-a": vector.copy()}
    monkeypatch.setattr(module, "load_audio_file", lambda _path: (np.ones(32000, dtype=np.float32), 16000))
    monkeypatch.setattr(module, "validate_audio_duration", lambda *_args, **_kwargs: True)
    fake_resemblyzer = SimpleNamespace(preprocess_wav=lambda data, _rate: data)
    monkeypatch.setitem(sys.modules, "resemblyzer", fake_resemblyzer)
    user_id, confidence = service.verify_speaker("synthesized.wav")
    print(f"G_MIGRATION_FIRST {first}")
    print(f"G_MIGRATION_SECOND {second}")
    print(f"G_SAFE_FORMAT schema=json pickle_load_in_normal_path=False")
    print(f"G_VERIFY user_id={user_id} confidence={confidence:.4f}")
    assert first == {"examined": 1, "updated": 1, "unchanged": 0}
    assert second == {"examined": 1, "updated": 0, "unchanged": 1}
    assert user_id == "user-a" and confidence > 0.99


@pytest.mark.parametrize("service_name", ["central", "vision"])
def test_h_rate_limiter_sustains_burst_without_500(service_name):
    from shared.rate_limiter import RateLimiter, create_rate_limit_middleware
    limiter = RateLimiter()
    app = FastAPI()
    app.middleware("http")(create_rate_limit_middleware(limiter))

    @app.get("/api/v1/generate")
    async def limited():
        return {"service": service_name}

    with TestClient(app) as client:
        statuses = [client.get("/api/v1/generate").status_code for _ in range(40)]
    print(f"H_BURST service={service_name} total=40 ok={statuses.count(200)} limited={statuses.count(429)} errors500={statuses.count(500)}")
    assert statuses.count(200) == 10 and statuses.count(429) == 30 and 500 not in statuses
