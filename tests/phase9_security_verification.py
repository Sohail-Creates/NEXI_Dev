"""Explicit Phase 9 proofs (run separately from the protected 53-test baseline)."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import ssl

from cryptography.fernet import Fernet, InvalidToken
import numpy as np
import pytest
import requests

from config.ssl_config import generate_local_certificates
from shared.credential_rotation import SecretPair
from shared.secure_storage import RotatingFernet
from tests.test_phase8_resilience import ROOT, SERVICES


pytestmark = pytest.mark.integration
CURRENT_FERNET = "g2UnTbcWj1lTsK40oN1HOJE_gnm36gjiT25g3J2V1BA="
PREVIOUS_FERNET = "lvl7f3kGOwfy8j52uU6IJ62UupzfeGE22xVGuxBmc9U="


def _wait(process, url, ca_file=None):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        assert process.poll() is None, f"service exited: {process.returncode}"
        try:
            response = requests.get(url, verify=ca_file or True, timeout=15)
            if response.status_code == 200:
                return response
        except requests.RequestException:
            pass
        time.sleep(0.25)
    raise AssertionError(f"service did not bind: {url}")


@pytest.fixture(scope="module")
def live_stack(tmp_path_factory):
    directory = tmp_path_factory.mktemp("phase9-live")
    tls = generate_local_certificates(directory / "tls")
    environment = os.environ.copy()
    environment.update({
        "AUTH_ENFORCEMENT_ENABLED": "true",
        "NEXI_INTERNAL_SERVICE_TOKEN": "phase9-live-service-current",
        "NEXI_JWT_SECRET": "phase9-live-jwt-current-at-least-32-bytes",
        "NEXI_FERNET_KEY": CURRENT_FERNET,
        "NEXI_TLS_ENABLED": "true",
        "NEXI_TLS_CERT_FILE": str(tls.cert_file),
        "NEXI_TLS_KEY_FILE": str(tls.key_file),
        "NEXI_TLS_CA_FILE": str(tls.ca_file),
        "CLOUD_SYNC_ENABLED": "false",
        "CENTRAL_DB_PATH": str(directory / "central.sqlite3"),
        "STORAGE_FILE": str(directory / "knowledge.json"),
        "ENROLLMENT_DATA_DIR": str(directory / "enrollment"),
        "SPEAKER_EMBEDDINGS_FILE": str(directory / "speakers.json"),
    })
    subprocess.run([sys.executable, str(ROOT / "01_central_server/migrate_cloud_sync_outbox.py"),
                    "--database", environment["CENTRAL_DB_PATH"]], env=environment, check=True,
                   capture_output=True, text=True)
    subprocess.run([sys.executable, "-c", "import sys; from pathlib import Path; "
                    "sys.path.insert(0,'05_teachme_service'); from teachme_service.sqlite_store import initialize; "
                    f"initialize(Path({environment['STORAGE_FILE']!r}).with_suffix('.sqlite3'))"],
                   env=environment, cwd=ROOT, check=True, capture_output=True, text=True)
    processes, logs, handles = {}, {}, []
    try:
        for name, app_dir, target, health_path, port in SERVICES:
            log_path = directory / f"{name}.log"
            handle = log_path.open("w", encoding="utf-8")
            handles.append(handle)
            command = [sys.executable, "-m", "uvicorn", target, "--app-dir", str(ROOT / app_dir),
                       "--host", "127.0.0.1", "--port", str(port), "--log-level", "info",
                       "--ssl-certfile", str(tls.cert_file), "--ssl-keyfile", str(tls.key_file)]
            processes[name] = subprocess.Popen(command, cwd=ROOT, env=environment,
                                                stdout=handle, stderr=subprocess.STDOUT)
            logs[name] = log_path
        for name, _, _, health_path, port in SERVICES:
            response = _wait(processes[name], f"https://127.0.0.1:{port}{health_path}", str(tls.ca_file))
            print(f"A_HTTPS service={name} status={response.status_code} body={response.text}")
        yield environment, tls, processes, logs, directory
    finally:
        for process in processes.values():
            if process.poll() is None:
                process.kill()
            process.wait(timeout=15)
        for handle in handles:
            handle.close()


def test_a_https_plaintext_transition_and_bad_ca(live_stack, monkeypatch):
    environment, tls, _, _, directory = live_stack
    for name, _, _, health_path, port in SERVICES:
        with pytest.raises(requests.RequestException):
            requests.get(f"http://127.0.0.1:{port}{health_path}", timeout=3)
        print(f"A_PLAINTEXT_CLOSED service={name} rejected=True")
    wrong = generate_local_certificates(directory / "wrong-ca")
    with pytest.raises(requests.exceptions.SSLError):
        requests.get("https://127.0.0.1:8000/health", verify=str(wrong.ca_file), timeout=3)
    print("A_WRONG_CA rejected=True type=SSLError verification_disabled=False")
    from shared.clients.llm_client import LLMServiceClient
    monkeypatch.setenv("NEXI_TLS_CA_FILE", str(wrong.ca_file))
    actual_client = LLMServiceClient(base_url="https://127.0.0.1:8006")
    assert asyncio.run(actual_client.get_model_info()) is None
    monkeypatch.setenv("NEXI_TLS_CA_FILE", str(tls.ca_file))
    assert asyncio.run(actual_client.get_model_info())["provider"] == "openrouter"
    print("A_INTERSERVICE_CLIENT wrong_ca=REJECT trusted_ca=ACCEPT client=LLMServiceClient")

    transition_env = dict(environment, NEXI_TLS_ALLOW_PLAINTEXT="true")
    log_path = directory / "transition.log"
    with log_path.open("w", encoding="utf-8") as handle:
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--app-dir",
                                    str(ROOT / "01_central_server"), "--host", "127.0.0.1", "--port", "8090"],
                                   cwd=ROOT, env=transition_env, stdout=handle, stderr=subprocess.STDOUT)
        try:
            response = _wait(process, "http://127.0.0.1:8090/health")
            print(f"A_TRANSITION status={response.status_code} body={response.text}")
        finally:
            process.kill()
            process.wait(timeout=15)
    warning = next(line for line in log_path.read_text(encoding="utf-8").splitlines() if "PLAINTEXT_TRANSITION" in line)
    print(warning)
    with pytest.raises(requests.RequestException):
        requests.get("http://127.0.0.1:8090/health", timeout=3)
    print("A_TRANSITION_CLOSED plaintext_listener=8090 rejected=True")


def test_b_biometric_ciphertext_and_round_trips(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXI_FERNET_KEY", CURRENT_FERNET)
    sys.path[:0] = [str(ROOT / "01_central_server"), str(ROOT / "03_audio_service"), str(ROOT / "06_enrollment_service")]
    import sqlite_store
    database = tmp_path / "central.sqlite3"
    sqlite_store.initialize(database)
    monkeypatch.setattr(sqlite_store, "DATABASE", database)
    user = {"user_id": "ciphertext-user", "name": "Ciphertext Biometric User", "voice_embeddings": [[0.125] * 256]}
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO users VALUES (0, ?)", (json.dumps(user),))
    first = sqlite_store.ensure_users_encrypted(database)
    second = sqlite_store.ensure_users_encrypted(database)
    assert sqlite_store.read_records("users") == [user]
    with sqlite3.connect(database) as connection:
        raw = connection.execute("SELECT record FROM users").fetchone()[0]
    assert "Ciphertext Biometric User" not in database.read_bytes().decode("latin1")
    print(f"B_CENTRAL_RAW {raw[:90]} plaintext_user_present=False")
    print(f"B_CENTRAL_ROUND_TRIP PASS first={first} second={second}")

    from audio_service.services import speaker_service
    path = tmp_path / "speakers.json"
    vector = np.linspace(0, 1, 256, dtype=np.float32)
    speaker_service._write_json_store(path, {"ciphertext-user": vector})
    monkeypatch.setitem(speaker_service.SPEAKER_CONFIG, "embeddings_file", path)
    service = speaker_service.SpeakerService()
    assert np.allclose(service.speaker_embeddings["ciphertext-user"], vector)
    assert b"ciphertext-user" not in path.read_bytes()
    print(f"B_AUDIO_RAW {path.read_bytes()[:90]!r} plaintext_user_present=False")
    print(f"B_AUDIO_ROUND_TRIP PASS speakers={service.get_speaker_count()}")

    from app.utils import encryption
    from app.utils.storage_async import AsyncEnrollmentStorage
    monkeypatch.setattr(encryption, "_encryption_manager", None)
    storage = AsyncEnrollmentStorage(str(tmp_path / "enrollment"))
    stored = asyncio.run(storage.save_enrollment("ciphertext-user", {"voice_embeddings": [[0.125] * 256]}))
    loaded = asyncio.run(storage.get_enrollment("ciphertext-user"))
    assert loaded["voice_embeddings"] == [[0.125] * 256]
    assert b"voice_embeddings" not in Path(stored).read_bytes()
    print(f"B_ENROLLMENT_RAW {Path(stored).read_bytes()[:90]!r} plaintext_fields_present=False")
    print("B_ENROLLMENT_ROUND_TRIP PASS mandatory=True")
    with pytest.raises(RuntimeError):
        AsyncEnrollmentStorage(str(tmp_path / "rejected"), enable_encryption=False)


def test_c_local_fernet_jwt_and_service_rotation(monkeypatch):
    from shared.jwt_manager import JWTManager, TokenConfig, TokenType
    from shared.security import INTERNAL_TOKEN_HEADER, is_internal_request
    from starlette.requests import Request
    with pytest.raises(RuntimeError):
        RotatingFernet(SecretPair("", PREVIOUS_FERNET))
    old = RotatingFernet(SecretPair(PREVIOUS_FERNET)).encrypt(b"rotation-record")
    window = RotatingFernet(SecretPair(CURRENT_FERNET, PREVIOUS_FERNET))
    new = window.encrypt(b"rotation-record")
    assert window.decrypt(old) == window.decrypt(new) == b"rotation-record"
    with pytest.raises(InvalidToken):
        RotatingFernet(SecretPair(CURRENT_FERNET)).decrypt(old)
    assert RotatingFernet(SecretPair(CURRENT_FERNET)).decrypt(new) == b"rotation-record"
    rewrapped = window.rotate(old)
    assert RotatingFernet(SecretPair(CURRENT_FERNET)).decrypt(rewrapped) == b"rotation-record"
    print("C_FERNET window_old=ACCEPT window_new=ACCEPT closed_old=REJECT closed_new=ACCEPT")
    print("C_FERNET_REWRAP previous_ciphertext_migrated=True readable_after_window_close=True")

    old_secret, new_secret = "phase9-old-jwt-at-least-32-bytes", "phase9-new-jwt-at-least-32-bytes"
    old_token = JWTManager(TokenConfig(secret_key=old_secret)).create_session_token("user-rotation")["token"]
    window_jwt = JWTManager(TokenConfig(secret_key=new_secret, previous_secret_key=old_secret))
    new_token = window_jwt.create_session_token("user-rotation")["token"]
    for token in (old_token, new_token):
        assert window_jwt.verify_token(token, TokenType.SESSION.value)["sub"] == "user-rotation"
    closed = JWTManager(TokenConfig(secret_key=new_secret, previous_secret_key=""))
    with pytest.raises(Exception):
        closed.verify_token(old_token)
    assert closed.verify_token(new_token)["sub"] == "user-rotation"
    print("C_JWT window_old=ACCEPT window_new=ACCEPT closed_old=REJECT closed_new=ACCEPT")

    monkeypatch.setenv("AUTH_ENFORCEMENT_ENABLED", "true")
    monkeypatch.setenv("NEXI_INTERNAL_SERVICE_TOKEN", "phase9-service-new")
    monkeypatch.setenv("NEXI_INTERNAL_SERVICE_TOKEN_PREVIOUS", "phase9-service-old")
    def request(token):
        return Request({"type": "http", "headers": [(INTERNAL_TOKEN_HEADER.lower().encode(), token.encode())]})
    assert is_internal_request(request("phase9-service-new")) and is_internal_request(request("phase9-service-old"))
    monkeypatch.delenv("NEXI_INTERNAL_SERVICE_TOKEN_PREVIOUS")
    assert not is_internal_request(request("phase9-service-old")) and is_internal_request(request("phase9-service-new"))
    print("C_SERVICE_TRUST window_old=ACCEPT window_new=ACCEPT closed_old=REJECT closed_new=ACCEPT")


def test_c_all_biometric_stores_survive_previous_key_retirement(monkeypatch, tmp_path):
    """Exercise real on-disk store consumers, including legacy Enrollment ciphertext."""
    sys.path[:0] = [str(ROOT / "01_central_server"), str(ROOT / "03_audio_service"), str(ROOT / "06_enrollment_service")]
    import sqlite_store
    from audio_service.services import speaker_service
    from app.utils.encryption import EncryptionManager
    from app.utils import encryption
    from app.utils.storage import EnrollmentStorage

    database = tmp_path / "users.sqlite3"
    sqlite_store.initialize(database)
    monkeypatch.setattr(sqlite_store, "DATABASE", database)
    monkeypatch.setenv("NEXI_FERNET_KEY", PREVIOUS_FERNET)
    user = {"user_id": "rotation-user", "voice_embeddings": [[0.25] * 256]}
    sqlite_store.write_records("users", [user])
    audio_path = tmp_path / "speakers.json"
    vector = np.linspace(0, 1, 256, dtype=np.float32)
    speaker_service._write_json_store(audio_path, {"rotation-user": vector})
    monkeypatch.setitem(speaker_service.SPEAKER_CONFIG, "embeddings_file", audio_path)
    monkeypatch.setattr(encryption, "_encryption_manager", None)
    enrollment = EnrollmentStorage(str(tmp_path / "enrollment"))
    metadata_path = Path(enrollment.save_enrollment("rotation-user", {"voice_embeddings": [[0.25] * 256]}))

    monkeypatch.setenv("NEXI_FERNET_KEY", CURRENT_FERNET)
    monkeypatch.setenv("NEXI_FERNET_PREVIOUS_KEY", PREVIOUS_FERNET)
    assert sqlite_store.read_records("users") == [user]
    migration = sqlite_store.ensure_users_encrypted(database)
    assert migration["encrypted"] == 1
    assert speaker_service.SpeakerService().get_speaker_count() == 1
    enrollment.encryption_manager = EncryptionManager()
    assert enrollment.get_enrollment("rotation-user")["voice_embeddings"] == [[0.25] * 256]
    assert enrollment.encryption_manager.rotate_file(str(metadata_path)) is True
    assert enrollment.encryption_manager.rotate_file(str(metadata_path)) is False

    monkeypatch.delenv("NEXI_FERNET_PREVIOUS_KEY")
    assert sqlite_store.read_records("users") == [user]
    assert speaker_service.SpeakerService().get_speaker_count() == 1
    enrollment.encryption_manager = EncryptionManager()
    assert enrollment.get_enrollment("rotation-user")["voice_embeddings"] == [[0.25] * 256]
    for store in ("central-users", "audio-speakers", "enrollment-metadata"):
        print(f"C_STORE_ROTATION store={store} previous_read=PASS rewrap=PASS closed_current_read=PASS record_parity=1:1")


def test_c_openrouter_rotation_with_https_provider_fixture(monkeypatch, tmp_path):
    """The receiver controls test keys, never claims to issue real provider keys."""
    tls = generate_local_certificates(tmp_path / "provider-tls")
    accepted = {"fixture-openrouter-old", "fixture-openrouter-new"}
    reject_new_once = [False]
    seen = []
    class Provider(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            key = self.headers.get("Authorization", "").removeprefix("Bearer ")
            seen.append(key)
            allowed = key in accepted
            if key == "fixture-openrouter-new" and reject_new_once[0]:
                reject_new_once[0] = False
                allowed = False
            payload = {"choices": [{"message": {"content": "grounded fixture response"}}]} if allowed else {"error": "invalid credential"}
            self.send_response(200 if allowed else 401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())
        def log_message(self, *_args):
            pass
    server = HTTPServer(("127.0.0.1", 0), Provider)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(tls.cert_file, tls.key_file)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        sys.path.insert(0, str(ROOT / "07_llm_service"))
        from llm_service.services import openrouter_client as provider_module
        monkeypatch.setattr(provider_module, "OPENROUTER_BASE_URL", f"https://127.0.0.1:{server.server_port}")
        monkeypatch.setattr(provider_module, "OPENROUTER_MODEL", "fixture/model")
        monkeypatch.setattr(provider_module, "OPENROUTER_API_KEY_ENV", "PHASE9_PROVIDER_KEY")
        monkeypatch.setenv("PHASE9_PROVIDER_KEY", "fixture-openrouter-new")
        monkeypatch.setenv("PHASE9_PROVIDER_KEY_PREVIOUS", "fixture-openrouter-old")
        monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(tls.ca_file))
        client = provider_module.OpenRouterClient()
        assert asyncio.run(client.generate("server-built fixture prompt"))[2] is True
        reject_new_once[0] = True
        assert asyncio.run(client.generate("server-built fixture prompt"))[2] is True
        assert seen[-2:] == ["fixture-openrouter-new", "fixture-openrouter-old"]
        accepted.remove("fixture-openrouter-old")
        monkeypatch.delenv("PHASE9_PROVIDER_KEY_PREVIOUS")
        closed = provider_module.OpenRouterClient()
        assert asyncio.run(closed.generate("server-built fixture prompt"))[2] is True
        old_only = provider_module.OpenRouterClient(api_key="fixture-openrouter-old")
        assert asyncio.run(old_only.generate("server-built fixture prompt"))[2] is False
        assert closed.api_keys.active == ("fixture-openrouter-new",)
        print("C_OPENROUTER window_old=ACCEPT window_new=ACCEPT closed_old=REJECT closed_new=ACCEPT local_https_provider_fixture=True real_provider_keys_rotated=False")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_c_shared_credentials_live_transition_and_close(live_stack):
    environment, tls, processes, logs, _ = live_stack
    from shared.jwt_manager import JWTManager, TokenConfig
    old_service = "phase9-live-service-previous"
    old_jwt_secret = "phase9-live-jwt-previous-at-least-32-bytes"
    old_token = JWTManager(TokenConfig(secret_key=old_jwt_secret, previous_secret_key="")).create_session_token("rotation-user")["token"]
    new_token = JWTManager(TokenConfig(secret_key=environment["NEXI_JWT_SECRET"], previous_secret_key="")).create_session_token("rotation-user")["token"]
    def restart(config):
        processes["central"].kill()
        processes["central"].wait(timeout=15)
        with logs["central"].open("a", encoding="utf-8") as handle:
            processes["central"] = subprocess.Popen([
                sys.executable, "-m", "uvicorn", "main:app", "--app-dir", str(ROOT / "01_central_server"),
                "--host", "127.0.0.1", "--port", "8000", "--ssl-certfile", str(tls.cert_file),
                "--ssl-keyfile", str(tls.key_file),
            ], cwd=ROOT, env=config, stdout=handle, stderr=subprocess.STDOUT)
        _wait(processes["central"], "https://127.0.0.1:8000/health", str(tls.ca_file))
    def service_status(value):
        return requests.get("https://127.0.0.1:8000/resources/status", headers={"X-NEXI-Service-Token": value},
                            verify=str(tls.ca_file), timeout=10).status_code
    def session_status(value):
        return requests.post("https://127.0.0.1:8000/api/v1/rag/query", json={"query": "hello"},
                             headers={"Authorization": f"Bearer {value}"}, verify=str(tls.ca_file), timeout=10).status_code
    window = dict(environment, NEXI_INTERNAL_SERVICE_TOKEN_PREVIOUS=old_service, NEXI_JWT_SECRET_PREVIOUS=old_jwt_secret)
    restart(window)
    assert service_status(old_service) == service_status(environment["NEXI_INTERNAL_SERVICE_TOKEN"]) == 200
    assert session_status(old_token) == session_status(new_token) == 200
    print("C_LIVE_WINDOW HTTPS service_old=200 service_new=200 jwt_old=200 jwt_new=200")
    closed = dict(environment)
    closed.pop("NEXI_INTERNAL_SERVICE_TOKEN_PREVIOUS", None)
    closed.pop("NEXI_JWT_SECRET_PREVIOUS", None)
    restart(closed)
    assert service_status(old_service) == 401 and service_status(environment["NEXI_INTERNAL_SERVICE_TOKEN"]) == 200
    assert session_status(old_token) == 401 and session_status(new_token) == 200
    print("C_LIVE_CLOSED HTTPS service_old=401 service_new=200 jwt_old=401 jwt_new=200")


def test_d_redaction_negative_controls(monkeypatch):
    from shared.utils.logging_setup import install_log_redaction
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("phase9.redaction.proof")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    samples = {
        "credential": "Authorization=Bearer sk-or-v1-0123456789abcdef0123456789abcdef",
        "biometric": "embedding=[0.123456, 0.987654]",
        "transcription": "transcription=My private spoken sentence",
        "production_transcribe": "[AudioClient] transcribe SUCCESS - text: 'My private spoken sentence...'",
        "nested_biometric": "voice_embeddings=[[0.123456,0.987654],[0.654321,0.456789]]",
        "configured_secret": "secret=fixturejwtsecret spacecomponent",
        "multiline_transcription": "transcription=private-first-line\nprivate-second-line",
        "unlabelled_api_key": "diagnostic sk-or-v1-0123456789abcdef0123456789abcdef",
        "unlabelled_fernet_key": f"diagnostic {PREVIOUS_FERNET}",
        "production_transcription_complete": "Transcription complete: text='private-speech', language=en",
        "production_transcribed_language": "Transcribed (en): private-speech...",
        "production_speech_synthesis": "Synthesizing speech (user-a): private-speech...",
        "production_rag_query": "teachme_no_match query='private-question'",
        "production_queue_query": "TeachMe queue full, returning empty results for 'private-question'",
        "production_response_body": 'Response text: {"text":"private-speech","user_id":"private-user"}',
    }
    monkeypatch.setenv("NEXI_JWT_SECRET", "fixturejwtsecret spacecomponent")
    sensitive_fragments = {
        "credential": ["sk-or-v1-0123456789abcdef0123456789abcdef"],
        "biometric": ["0.123456", "0.987654"],
        "transcription": ["My private spoken sentence"],
        "production_transcribe": ["My private spoken sentence"],
        "nested_biometric": ["0.123456", "0.987654", "0.654321", "0.456789"],
        "configured_secret": ["fixturejwtsecret", "spacecomponent"],
        "multiline_transcription": ["private-first-line", "private-second-line"],
        "unlabelled_api_key": ["sk-or-v1-0123456789abcdef0123456789abcdef"],
        "unlabelled_fernet_key": [PREVIOUS_FERNET],
        "production_transcription_complete": ["private-speech"],
        "production_transcribed_language": ["private-speech"],
        "production_speech_synthesis": ["private-speech"],
        "production_rag_query": ["private-question"],
        "production_queue_query": ["private-question"],
        "production_response_body": ["private-speech", "private-user"],
    }
    try:
        for category, sample in samples.items():
            stream.seek(0); stream.truncate(0)
            install_log_redaction(False)
            logger.info("%s", sample)
            plain = stream.getvalue().strip()
            assert sample in plain
            stream.seek(0); stream.truncate(0)
            install_log_redaction(True)
            logger.info("%s", sample)
            masked = stream.getvalue().strip()
            assert "[REDACTED]" in masked and sample not in masked
            assert all(fragment not in masked for fragment in sensitive_fragments[category])
            print(f"D_{category.upper()} OFF={plain!r} ON={masked!r}")
        stream.seek(0); stream.truncate(0)
        logger.info({"request_body": {"user_id": "private-user", "token": "private-token"}})
        assert "private-user" not in stream.getvalue() and "private-token" not in stream.getvalue()
        logger.info({"text": "private-speech", "query": "private-question"})
        assert "private-speech" not in stream.getvalue() and "private-question" not in stream.getvalue()
        handler.setFormatter(logging.Formatter("%(message)s %(embedding)s"))
        logger.info("structured biometric", extra={"embedding": [0.123456, 0.987654]})
        assert "0.123456" not in stream.getvalue()
        handler.setFormatter(logging.Formatter("%(message)s"))
        try:
            raise ValueError("transcription=My private spoken sentence")
        except ValueError:
            logger.exception("forced diagnostic exception")
        assert "My private spoken sentence" not in stream.getvalue()
        print("D_STRUCTURED_BODY_EXTRA_EXCEPTION sensitive_values=REDACTED")
        route_metadata = "REQUEST_END service=audio path=/transcribe status=200 duration_ms=1.0 correlation_id=fixture-id"
        stream.seek(0); stream.truncate(0)
        logger.info(route_metadata)
        assert route_metadata in stream.getvalue()
        print("D_ROUTE_METADATA path=/transcribe status=200 duration_ms=1.0 preserved=True")
        from uvicorn.logging import AccessFormatter
        from shared.utils.trace_context import trace_id_context
        context_token = trace_id_context.set("phase9-access-log")
        try:
            record = logging.getLogRecordFactory()(
                "uvicorn.access", logging.INFO, __file__, 0,
                '%s - "%s %s HTTP/%s" %d',
                ("127.0.0.1:12345", "GET", "/health?api_key=fixture-private-key", "1.1", 200), None,
            )
            access_line = AccessFormatter(
                '%(client_addr)s - "%(request_line)s" %(status_code)s', use_colors=False,
            ).format(record)
            assert "fixture-private-key" not in access_line and "phase9-access-log" in access_line
            assert "200 OK" in access_line
            print(f"D_UVICORN_ACCESS {access_line}")
        finally:
            trace_id_context.reset(context_token)
    finally:
        install_log_redaction(True)
        logger.handlers = []


def test_e_live_correlation_and_all_service_latencies(live_stack):
    environment, tls, _, logs, _ = live_stack
    from shared.jwt_manager import JWTManager, TokenConfig
    user_id = "phase9-trace-user"
    service_headers = {
        "X-NEXI-Service-Token": environment["NEXI_INTERNAL_SERVICE_TOKEN"],
        "X-NEXI-Trusted-User-ID": user_id,
    }
    learned = requests.post("https://127.0.0.1:8004/learn", json={
        "type": "fact", "data": {"subject": "NEXI charging dock", "predicate": "is", "object": "beside the blue sofa"},
        "confidence": 1.0, "tags": ["phase9-trace"],
    }, headers=service_headers, verify=str(tls.ca_file), timeout=30)
    assert learned.status_code == 201, learned.text
    token = JWTManager(TokenConfig(secret_key=environment["NEXI_JWT_SECRET"], previous_secret_key="")).create_session_token(user_id)["token"]
    correlation_id = "phase9-end-to-end-trace"
    response = requests.post("https://127.0.0.1:8000/api/v1/rag/query", json={"query": "Where is NEXI charging dock?"},
                             headers={"Authorization": f"Bearer {token}", "X-Correlation-ID": correlation_id},
                             verify=str(tls.ca_file), timeout=90)
    assert response.status_code in {200, 502}, response.text
    print(f"E_EXTERNAL_RAG status={response.status_code} body={response.text}")
    for name in ("central", "teachme", "llm"):
        matching = [line for line in logs[name].read_text(encoding="utf-8", errors="replace").splitlines()
                    if correlation_id in line and "REQUEST_" in line]
        assert matching, f"missing correlated request logs for {name}"
        for line in matching:
            print(f"E_TRACE {name} {line}")
    for name in logs:
        latency = [line for line in logs[name].read_text(encoding="utf-8", errors="replace").splitlines()
                   if "REQUEST_END" in line and "duration_ms=" in line]
        assert latency, f"missing latency log for {name}"
        print(f"E_LATENCY {name} {latency[-1]}")
    # Observability must also cover requests rejected by the existing auth gate.
    denied_routes = (
        ("central", 8000, "GET", "/resources/status"),
        ("vision", 8001, "POST", "/api/v1/detect/faces"),
        ("audio", 8002, "POST", "/api/v1/process-voice"),
        ("tts", 8003, "POST", "/speak"),
        ("teachme", 8004, "POST", "/learn"),
        ("enrollment", 8005, "GET", "/enrollment/storage/list"),
        ("llm", 8006, "POST", "/api/v1/generate"),
    )
    for name, port, method, path in denied_routes:
        denied_id = f"phase9-denied-{name}"
        denied = requests.request(method, f"https://127.0.0.1:{port}{path}",
                                  json={"query": "fixture"} if method == "POST" else None,
                                  headers={"X-Correlation-ID": denied_id}, verify=str(tls.ca_file), timeout=15)
        assert denied.status_code == 401, denied.text
        assert denied.headers.get("X-Correlation-ID") == denied_id, f"auth rejection bypassed observability: {name}"
        assert denied.headers.get("X-Request-ID") == denied_id
        assert denied.json()["error"]["request_id"] == denied_id
        denied_logs = [line for line in logs[name].read_text(encoding="utf-8", errors="replace").splitlines()
                       if denied_id in line and "REQUEST_END" in line and "status=401" in line]
        assert denied_logs, f"missing rejected-request latency: {name}"
        print(f"E_REJECTED_TRACE {name} {denied_logs[-1]}")


def test_f_auditor_cannot_clear_skipped_packages_or_hide_known_findings(monkeypatch):
    from scripts import scan_dependencies
    result = subprocess.CompletedProcess([], 0, json.dumps({"dependencies": [
        {"name": "unauditable-fixture", "skip_reason": "version not found"},
        {"name": "vulnerable-fixture", "version": "1.0", "vulns": [
            {"id": "FIXTURE-ADVISORY", "fix_versions": ["2.0"]},
            {"id": "FIXTURE-ADVISORY", "fix_versions": ["2.0"]},
        ]},
    ]}), "")
    monkeypatch.setattr(scan_dependencies.subprocess, "run", lambda *_args, **_kwargs: result)
    findings, error = scan_dependencies.audit(ROOT / "requirements.txt")
    assert error and "unauditable-fixture" in error
    assert len(findings) == 1 and findings[0]["id"] == "FIXTURE-ADVISORY"
    assert findings[0]["severity"] == "UNASSESSED_TREATED_AS_HIGH"
    print("F_AUDIT_NEGATIVE_CONTROL skipped_package=FAIL_CLOSED known_finding=PRESERVED duplicate_advisory=DEDUPED severity_not_invented=True")
