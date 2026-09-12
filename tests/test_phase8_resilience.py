"""Consolidated process-level resilience coverage."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
import requests
from config.ssl_config import generate_local_certificates


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "venv" / "Scripts" / "python.exe"

pytestmark = pytest.mark.resilience


SERVICES = (
    ("central", "01_central_server", "main:app", "/health", 8000),
    ("vision", "02_vision_service", "vision_service.app:app", "/health", 8001),
    ("audio", "03_audio_service", "main:app", "/health", 8002),
    ("tts", "04_tts_service", "tts_service.app:app", "/health", 8003),
    ("teachme", "05_teachme_service", "teachme_service.app:app", "/health", 8004),
    ("enrollment", "06_enrollment_service", "app.main:app", "/health", 8005),
    ("llm", "07_llm_service", "main:app", "/api/v1/health", 8006),
)


def _spawn(app_dir: str, target: str, port: int, environment: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        [
            str(PYTHON), "-m", "uvicorn", target,
            "--app-dir", str(ROOT / app_dir),
            "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning",
            "--ssl-certfile", environment["NEXI_TLS_CERT_FILE"],
            "--ssl-keyfile", environment["NEXI_TLS_KEY_FILE"],
        ],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _ready(process: subprocess.Popen, url: str, ca_file: str, timeout: float = 120.0) -> dict:
    deadline = time.monotonic() + timeout
    last_error = "not started"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"process exited before readiness: exit={process.returncode}")
        try:
            # Vision's honest degraded health probe includes one bounded attempt
            # to contact the camera authority, so allow that probe to complete.
            response = requests.get(url, timeout=15, verify=ca_file)
            if response.status_code == 200:
                return response.json()
            last_error = f"HTTP {response.status_code}: {response.text[:200]}"
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise AssertionError(f"readiness timeout for {url}: {last_error}")


def _kill(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.kill()
    process.wait(timeout=15)


def test_resilience_all_seven_services_forced_kill_and_restart(tmp_path) -> None:
    tls = generate_local_certificates(tmp_path / "tls")
    environment = os.environ.copy()
    environment.update(
        {
            "AUTH_ENFORCEMENT_ENABLED": "true",
            "NEXI_INTERNAL_SERVICE_TOKEN": "phase8-resilience-service-token",
            "NEXI_JWT_SECRET": "phase8-resilience-jwt-secret-at-least-32-bytes",
            "NEXI_FERNET_KEY": "g2UnTbcWj1lTsK40oN1HOJE_gnm36gjiT25g3J2V1BA=",
            "NEXI_TLS_ENABLED": "true",
            "NEXI_TLS_CERT_FILE": str(tls.cert_file),
            "NEXI_TLS_KEY_FILE": str(tls.key_file),
            "NEXI_TLS_CA_FILE": str(tls.ca_file),
            "CLOUD_SYNC_ENABLED": "false",
            "CENTRAL_DB_PATH": str(tmp_path / "central.sqlite3"),
            "STORAGE_FILE": str(tmp_path / "knowledge.json"),
            "ENROLLMENT_DATA_DIR": str(tmp_path / "enrollment"),
            "SPEAKER_EMBEDDINGS_FILE": str(tmp_path / "speakers.json"),
        }
    )
    subprocess.run(
        [
            str(PYTHON),
            str(ROOT / "01_central_server" / "migrate_cloud_sync_outbox.py"),
            "--database",
            environment["CENTRAL_DB_PATH"],
        ],
        cwd=ROOT,
        env=environment,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        [
            str(PYTHON),
            "-c",
            (
                "import os,sys; from pathlib import Path; "
                f"sys.path.insert(0, {str(ROOT / '05_teachme_service')!r}); "
                "from teachme_service.sqlite_store import initialize; "
                "initialize(Path(os.environ['STORAGE_FILE']).with_suffix('.sqlite3'))"
            ),
        ],
        cwd=ROOT,
        env=environment,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    processes = {
        name: _spawn(app_dir, target, port, environment)
        for name, app_dir, target, _health_path, port in SERVICES
    }
    restarted = 0
    try:
        health = {}
        for name, _app_dir, _target, health_path, port in SERVICES:
            health[name] = _ready(processes[name], f"https://127.0.0.1:{port}{health_path}", str(tls.ca_file))
        smoke = subprocess.run(
            [str(PYTHON), str(ROOT / "scripts" / "health_check_all.py")],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=90,
        )
        print(smoke.stdout.strip())
        assert smoke.returncode == 0 and "ALL SERVICES RESPONSIVE (7/7)" in smoke.stdout
        print("RESILIENCE_COLD_START_SMOKE PASS services=7 HTTP200=7")

        for name, app_dir, target, health_path, port in SERVICES:
            first = processes[name]
            first_pid = first.pid
            _kill(first)
            assert first.returncode is not None
            restart_target = target
            if os.getenv("PHASE8_FAULT") == "resilience_restart" and name == "central":
                restart_target = "phase8_missing_app:app"
            second = _spawn(app_dir, restart_target, port, environment)
            processes[name] = second
            after = _ready(second, f"https://127.0.0.1:{port}{health_path}", str(tls.ca_file))
            assert second.pid != first_pid
            restarted += 1
            print(
                f"RESILIENCE_RESTART {name:10} forced_kill=True old_pid={first_pid} "
                f"new_pid={second.pid} HTTP=200 status={after.get('status', after.get('service', 'running'))}"
            )
            assert isinstance(health[name], dict) and isinstance(after, dict)
    finally:
        for process in processes.values():
            if process.poll() is None:
                _kill(process)
    assert restarted == 7
    print("RESILIENCE_FORCED_KILL_RESTART_RESULT PASS services=7 restarted=7 manual_intervention=0")
