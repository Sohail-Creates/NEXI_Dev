"""Shared photo reuse and REST-only numbered retake orchestration."""

from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "06_enrollment_service"))

from app.services.photo_validation import PhotoValidation
from app.services.enrollment_service import EnrollmentService
from config.settings import settings
from fastapi import UploadFile
import test as console_module

pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_final_photo_uses_exact_early_result_and_changed_photo_is_revalidated(tmp_path):
    client = SimpleNamespace(get_face_embedding=AsyncMock(return_value={"embedding": [0.1] * 128, "confidence": 0.9, "face_detected": True}))
    validator = PhotoValidation(client)
    early, final = tmp_path / "early.jpg", tmp_path / "final.jpg"
    early.write_bytes(b"same photo")
    final.write_bytes(early.read_bytes())
    first = await validator.get_face_embedding(str(early))
    second = await validator.get_face_embedding(str(final))
    assert second == first
    client.get_face_embedding.assert_awaited_once()
    second["embedding"][0] = 999
    assert (await validator.get_face_embedding(str(final)))["embedding"][0] == 0.1
    final.write_bytes(b"changed photo")
    await validator.get_face_embedding(str(final))
    assert client.get_face_embedding.await_count == 2
    validator.clear()
    await validator.get_face_embedding(str(final))
    assert client.get_face_embedding.await_count == 3


@pytest.mark.asyncio
async def test_failed_checks_are_not_cached_and_cache_is_bounded(tmp_path, monkeypatch):
    from fastapi import HTTPException
    client = SimpleNamespace(get_face_embedding=AsyncMock(side_effect=HTTPException(400, "No face detected in image")))
    validator = PhotoValidation(client)
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"photo")
    for _ in range(2):
        with pytest.raises(HTTPException):
            await validator.get_face_embedding(str(photo))
    assert client.get_face_embedding.await_count == 2
    client.get_face_embedding.side_effect = None
    client.get_face_embedding.return_value = {"embedding": [0.1], "confidence": 0.9, "face_detected": True}
    monkeypatch.setattr(settings, "photo_validation_cache_max_items", 1)
    await validator.get_face_embedding(str(photo))
    other = tmp_path / "other.jpg"
    other.write_bytes(b"other")
    await validator.get_face_embedding(str(other))
    assert len(validator._cache) == 1
    monkeypatch.setattr(settings, "photo_validation_cache_ttl_seconds", 0)
    await validator.get_face_embedding(str(other))
    assert client.get_face_embedding.await_count == 5


def test_capture_does_not_wait_and_only_failed_number_is_retaken(tmp_path, monkeypatch, capsys):
    all_captured = threading.Event()
    rounds, checks = [], []

    def capture(output_dir, count, photo_numbers, on_capture, guidance):
        rounds.append(list(photo_numbers))
        paths = []
        for number in photo_numbers:
            path = output_dir / f"face_{number}-round{len(rounds)}.jpg"
            paths.append(path)
            on_capture(number, path)
        all_captured.set()
        return paths

    def validate(path):
        assert all_captured.wait(timeout=2), "camera blocked waiting for validation"
        checks.append(path.name)
        failed = path.name == "face_3-round1.jpg"
        return console_module.LiveResponse(status_code=400 if failed else 200, headers={}, raw=b"",
                                           body={"error": {"message": "No face detected in image"}} if failed else {"valid": True})

    monkeypatch.setattr(console_module, "_capture_face_samples", capture)
    paths = console_module._capture_validated_face_samples(SimpleNamespace(validate_photo=validate), tmp_path)
    assert rounds == [[1, 2, 3, 4, 5], [3]]
    assert len(checks) == 6
    assert paths[2].name == "face_3-round2.jpg"
    assert all("round1" in path.name for index, path in enumerate(paths) if index != 2)
    assert "Photo 3: No face detected in image" in capsys.readouterr().out


def test_background_request_is_quiet_and_normal_error_reporting_is_preserved(capsys):
    client = console_module.LiveRESTClient.__new__(console_module.LiveRESTClient)
    client.urls = console_module.ServiceURLs()
    client.output_mode = "narrative"
    client.internal_token = "test-token"
    client._client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(400, json={"error": {"message": "No face detected in image"}})))
    try:
        response = client.request("enrollment", "POST", "/enrollment/validate-photo", quiet=True)
        assert response.status_code == 400
        assert capsys.readouterr().out == ""
        client.request("enrollment", "POST", "/enrollment/validate-photo")
        assert "No face detected in image" in capsys.readouterr().out
    finally:
        client.close()


@pytest.mark.asyncio
async def test_prevalidation_removes_upload_and_returns_metadata_only(tmp_path):
    import io
    from starlette.datastructures import Headers
    service = EnrollmentService.__new__(EnrollmentService)
    service.upload_dir = str(tmp_path)
    service.max_photo_size = 1024
    service.photo_validation = SimpleNamespace(get_face_embedding=AsyncMock(
        return_value={"embedding": [0.1] * 128, "confidence": 0.9, "face_detected": True}))
    photo = UploadFile(io.BytesIO(b"\xff\xd8photo"), filename="face.jpg", headers=Headers({"content-type": "image/jpeg"}))
    result = await service.validate_photo(photo)
    assert result == {"valid": True, "confidence": 0.9, "face_detected": True, "embedding_generated": True, "reason": None}
    assert "embedding" not in result
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_cache_version_change_invalidates_same_bytes(tmp_path, monkeypatch):
    client = SimpleNamespace(get_face_embedding=AsyncMock(return_value={"embedding": [0.1] * 128, "confidence": 0.9, "face_detected": True}))
    validator = PhotoValidation(client)
    photo = tmp_path / "face.jpg"
    photo.write_bytes(b"same bytes")
    await validator.get_face_embedding(str(photo))
    monkeypatch.setattr(settings, "photo_validation_version", "changed-model-policy")
    await validator.get_face_embedding(str(photo))
    assert client.get_face_embedding.await_count == 2


def test_multiple_failed_slots_out_of_order_completion_cannot_replace_retakes(tmp_path, monkeypatch):
    import time
    rounds = []
    completed = []

    def capture(output_dir, count, photo_numbers, on_capture, guidance):
        # Previous futures must be drained before a new round can begin.
        if rounds:
            assert len(completed) == 5
        rounds.append(list(photo_numbers))
        paths = []
        for number in photo_numbers:
            path = output_dir / f"{number}-{len(rounds)}.jpg"
            paths.append(path)
            on_capture(number, path)
        return paths

    def validate(path):
        number, generation = map(int, path.stem.split("-"))
        time.sleep(0.02 if number == 1 else 0.001)
        completed.append(path.name)
        failed = generation == 1 and number in (2, 4)
        return console_module.LiveResponse(status_code=400 if failed else 200, headers={}, raw=b"",
            body={"error": {"message": "No face detected in image"}} if failed else {"valid": True})

    monkeypatch.setattr(settings, "photo_validation_concurrency", 2)
    monkeypatch.setattr(console_module, "_capture_face_samples", capture)
    paths = console_module._capture_validated_face_samples(SimpleNamespace(validate_photo=validate), tmp_path)
    assert rounds == [[1, 2, 3, 4, 5], [2, 4]]
    assert completed[0] != "1-1.jpg"
    assert [path.name for path in paths] == ["1-1.jpg", "2-2.jpg", "3-1.jpg", "4-2.jpg", "5-1.jpg"]


def test_capture_evidence_default_off_and_opt_in_is_restricted(tmp_path):
    from shared.face_diagnostics import DIAGNOSTIC_ROOT, diagnostic_directory
    console = SimpleNamespace(enrollment_evidence_dir=None)
    with console_module._enrollment_capture_directory(console) as path:
        temporary = path
        assert path.is_dir()
    assert not temporary.exists()
    with pytest.raises(ValueError, match="logs/face-validation"):
        diagnostic_directory(tmp_path)
    assert diagnostic_directory(DIAGNOSTIC_ROOT / "private-run").parent == DIAGNOSTIC_ROOT.resolve()


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [b"", b"not an image"])
async def test_bad_input_reuses_existing_validator_without_inference(tmp_path, content):
    import io
    from fastapi import HTTPException
    from starlette.datastructures import Headers
    service = EnrollmentService.__new__(EnrollmentService)
    service.upload_dir = str(tmp_path)
    service.max_photo_size = 1024
    service.photo_validation = SimpleNamespace(get_face_embedding=AsyncMock())
    photo = UploadFile(io.BytesIO(content), filename="face.jpg", headers=Headers({"content-type": "image/jpeg"}))
    with pytest.raises(HTTPException) as caught:
        await service.validate_photo(photo)
    assert caught.value.detail["reason"] == "INVALID_IMAGE"
    service.photo_validation.get_face_embedding.assert_not_awaited()
