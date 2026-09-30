#!/usr/bin/env python3
"""Live HTTPS contract smoke checks for the Vision service."""

from __future__ import annotations

import sys
from pathlib import Path

import requests
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from config.ssl_config import client_verify  # noqa: E402
from shared.security import internal_service_headers  # noqa: E402


BASE_URL = "https://127.0.0.1:8001"
TIMEOUT = 30
CLIENT = requests.Session()
CLIENT.headers.update(internal_service_headers())
CLIENT.verify = client_verify(BASE_URL)


def check(name: str, method) -> bool:
    try:
        detail = method()
        print(f"[PASS] {name}{': ' + detail if detail else ''}")
        return True
    except Exception as exc:
        print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
        return False


def require_success(response: requests.Response) -> None:
    if not response.ok:
        raise AssertionError(f"HTTP {response.status_code}: {response.text}")


def test_health() -> str:
    response = CLIENT.get(f"{BASE_URL}/health", timeout=5)
    require_success(response)
    data = response.json()
    assert data.get("camera") == "not_checked", data
    assert data.get("face_model") in {"loaded", "unavailable"}, data
    assert data.get("object_model") in {"loaded", "unavailable", "disabled"}, data
    assert data.get("status") in {"healthy", "degraded"}, data
    return f"{data['status']}; face={data['face_model']}; object={data['object_model']}"


def test_face_detection() -> str:
    response = CLIENT.post(
        f"{BASE_URL}/api/v1/detect/faces",
        params={"detector_backend": "opencv", "model_name": "Facenet"},
        timeout=TIMEOUT,
    )
    require_success(response)
    data = response.json()
    assert data.get("status") in {"success", "no_face_detected"}, data
    assert data.get("faces_detected") == len(data.get("faces", [])), data
    if data["status"] == "no_face_detected":
        assert data["faces"] == [], data
    return f"{data['status']}; faces={data['faces_detected']}"


def test_complete_analysis_contract() -> str:
    response = CLIENT.post(
        f"{BASE_URL}/api/v1/analyze/complete",
        params={"detector_backend": "opencv", "model_name": "Facenet"},
        timeout=TIMEOUT,
    )
    require_success(response)
    data = response.json()
    assert data.get("status") in {"success", "no_face_detected"}, data
    assert data.get("faces_detected") == len(data.get("faces", [])), data
    assert data.get("objects_detected") == len(data.get("objects", [])), data
    return f"{data['status']}; faces={data['faces_detected']}; objects={data['objects_detected']}"


def test_camera_controls() -> str:
    paused = CLIENT.post(f"{BASE_URL}/camera/pause", timeout=5)
    require_success(paused)
    assert paused.json().get("status") == "paused", paused.text
    resumed = CLIENT.post(f"{BASE_URL}/camera/resume", timeout=5)
    require_success(resumed)
    assert resumed.json().get("status") == "active", resumed.text
    return "pause/resume acknowledged"


def test_live_ui() -> str:
    response = CLIENT.get(f"{BASE_URL}/live", timeout=5)
    require_success(response)
    assert "html" in response.headers.get("content-type", "").lower(), response.headers
    return "HTML response"


def main() -> int:
    print(f"Vision HTTPS contract checks: {BASE_URL}")
    checks = [
        ("Health and model readiness", test_health),
        ("Face detection response contract", test_face_detection),
        ("Combined analysis response contract", test_complete_analysis_contract),
        ("Camera control contract", test_camera_controls),
        ("Authenticated live UI", test_live_ui),
    ]
    outcomes = [check(name, fn) for name, fn in checks]
    print(f"Summary: {sum(outcomes)}/{len(outcomes)} passed")
    return 0 if all(outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
