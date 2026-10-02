"""Photo error propagation through Enrollment's real Vision REST client."""

from pathlib import Path
import sys
from unittest.mock import AsyncMock, Mock
import asyncio
import io
from types import SimpleNamespace
from contextlib import contextmanager
from starlette.datastructures import Headers

import httpx
import pytest
from fastapi import FastAPI, File, UploadFile
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "06_enrollment_service"))

from app.clients import vision_client as vision_module
from app.services import enrollment_service as enrollment_module
from shared.api_errors import install_error_handlers


pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_failed_upload_write_removes_partial_file(monkeypatch, tmp_path):
    from app.utils import file_handler
    real_open = open

    @contextmanager
    def interrupted_write(path, mode):
        with real_open(path, mode) as handle:
            def fail(content):
                handle.write(content[:1])
                raise OSError("Simulated disk-full write")
            yield SimpleNamespace(write=fail)

    monkeypatch.setattr(file_handler, "open", interrupted_write, raising=False)
    upload = UploadFile(filename="photo.jpg", file=io.BytesIO(b"photo"),
                        headers=Headers({"content-type": "image/jpeg"}))
    with pytest.raises(OSError, match="Simulated disk-full"):
        await file_handler.save_uploaded_file(upload, str(tmp_path), ["image/jpeg"], 1024)
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["process_enrollment", "improve_training", "update_model"])
async def test_cancelled_enrollment_removes_all_temporary_uploads(monkeypatch, tmp_path, operation):
    """Cancellation is BaseException, so ordinary exception handlers are insufficient."""
    service = enrollment_module.EnrollmentService.__new__(enrollment_module.EnrollmentService)
    service.upload_dir = str(tmp_path)
    service.max_photo_size = enrollment_module.EnrollmentValidator.MAX_PHOTO_SIZE
    service.max_voice_size = enrollment_module.EnrollmentValidator.MAX_AUDIO_SIZE
    service.storage = SimpleNamespace(get_enrollment_smart=AsyncMock(return_value={"user_id": "existing"}))
    service.photo_validation = SimpleNamespace(
        get_face_embedding=AsyncMock(side_effect=asyncio.CancelledError()), clear=Mock())
    monkeypatch.setattr(enrollment_module.EnrollmentValidator, "validate_all_photos", AsyncMock())
    monkeypatch.setattr(enrollment_module.EnrollmentValidator, "validate_all_audio", AsyncMock())

    async def save(upload, *args):
        path = tmp_path / upload.filename
        path.write_bytes(await upload.read())
        return str(path)

    monkeypatch.setattr(enrollment_module, "save_uploaded_file", save)
    photos = [UploadFile(filename=f"photo_{i}.jpg", file=io.BytesIO(b"photo")) for i in range(5)]
    voices = [UploadFile(filename=f"voice_{i}.wav", file=io.BytesIO(b"voice")) for i in range(5)]
    with pytest.raises(asyncio.CancelledError):
        await getattr(service, operation)("Existing User" if operation == "process_enrollment" else "existing", photos, voices)
    assert not list(tmp_path.iterdir())
    service.photo_validation.clear.assert_called_once()


def vision_client(monkeypatch, handler):
    monkeypatch.setenv("VISION_SERVICE_URL", "https://vision.test")
    monkeypatch.setenv("NEXI_INTERNAL_SERVICE_TOKEN", "photo-error-test-token")
    original = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(vision_module.httpx, "AsyncClient", lambda **kwargs: original(transport=transport, **kwargs))
    client = vision_module.VisionClient()
    client.max_retries = 1
    return client


@pytest.mark.parametrize("status,body,message", [
    (200, {"faces": []}, "Failed to process photo 2: No face detected in image"),
    (500, {"error": {"message": "Embedding runtime unavailable", "code": "EMBEDDING_FAILED"}},
     "Failed to process photo 2: Face inference failed; check server logs"),
])
def test_second_photo_error_reaches_rest_caller_with_traceback(monkeypatch, tmp_path, status, body, message):
    calls = []

    def respond(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json={"faces": [{"embedding": [0.1] * 128, "confidence": 0.9}]})
        return httpx.Response(status, json=body)

    service = enrollment_module.EnrollmentService.__new__(enrollment_module.EnrollmentService)
    traceback_logger = Mock(wraps=enrollment_module.logger.exception)
    monkeypatch.setattr(enrollment_module.logger, "exception", traceback_logger)
    service.vision_client = vision_client(monkeypatch, respond)
    from app.services.photo_validation import PhotoValidation
    service.photo_validation = PhotoValidation(service.vision_client)
    service.upload_dir = str(tmp_path)
    service.max_photo_size = enrollment_module.EnrollmentValidator.MAX_PHOTO_SIZE
    service.max_voice_size = enrollment_module.EnrollmentValidator.MAX_AUDIO_SIZE
    monkeypatch.setattr(enrollment_module.EnrollmentValidator, "validate_all_photos", AsyncMock())
    monkeypatch.setattr(enrollment_module.EnrollmentValidator, "validate_all_audio", AsyncMock())

    async def save(upload, *args):
        path = tmp_path / upload.filename
        path.write_bytes(await upload.read())
        return str(path)

    monkeypatch.setattr(enrollment_module, "save_uploaded_file", save)
    app = FastAPI()
    install_error_handlers(app, "enrollment-photo-test")

    @app.post("/enrollment/enroll")
    async def enroll(photos: list[UploadFile] = File(...), voice_samples: list[UploadFile] = File(...)):
        return await service.process_enrollment("Photo Test", photos, voice_samples)

    files = [("photos", (f"photo_{i}.jpg", f"test photo {i}".encode(), "image/jpeg")) for i in range(1, 6)]
    files += [("voice_samples", (f"voice_{i}.wav", b"test voice", "audio/wav")) for i in range(1, 6)]
    with TestClient(app) as client:
        response = client.post("/enrollment/enroll", files=files)

    assert response.status_code == 400
    assert response.json()["error"]["message"] == message
    assert len(calls) == 2
    assert all(str(request.url) == "https://vision.test/api/v1/detect/faces/upload" for request in calls)
    traceback_logger.assert_called_once_with("Enrollment face processing failed for photo %d", 2)
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize("error,expected", [
    (httpx.ReadTimeout(""), "Vision Service timed out; try again"),
    (httpx.ConnectError(""), "Cannot reach Vision Service; check service readiness"),
])
async def test_empty_transport_exception_still_has_actionable_detail(monkeypatch, tmp_path, error, expected):
    def fail(request):
        raise error

    client = vision_client(monkeypatch, fail)
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"photo")
    with pytest.raises(vision_module.HTTPException) as caught:
        await client.get_face_embedding(str(photo))
    assert caught.value.detail["message"] == expected
    assert caught.value.detail["reason"] == "REQUEST_FAILURE"
    assert caught.value.__cause__ is error


@pytest.mark.asyncio
@pytest.mark.parametrize("status,body,reason", [
    (200, {"faces": []}, "NO_FACE_DETECTED"),
    (400, {"detail": "Invalid image file"}, "INVALID_IMAGE"),
    (503, {"detail": {"code": "FACE_MODEL_UNAVAILABLE", "message": "private/path/model"}}, "MODEL_NOT_READY"),
    (500, {"detail": "C:/private/model.py traceback"}, "INFERENCE_ERROR"),
    (200, {"faces": [{"embedding": [0.0] * 128}]}, "INFERENCE_ERROR"),
    (200, {"faces": [{"embedding": [float('nan')]}]}, "INFERENCE_ERROR"),
])
async def test_distinct_reasons_and_no_fabricated_or_leaked_face(monkeypatch, tmp_path, status, body, reason):
    # NaN cannot be encoded by httpx JSON; use raw JSON for malformed upstream data.
    import json
    client = vision_client(monkeypatch, lambda request: httpx.Response(status, content=json.dumps(body)))
    photo = tmp_path / "face.jpg"
    photo.write_bytes(b"image")
    with pytest.raises(vision_module.HTTPException) as caught:
        await client.get_face_embedding(str(photo))
    detail = caught.value.detail
    assert detail["reason"] == reason
    assert detail["embedding_generated"] is False
    assert "private" not in detail["message"] and "traceback" not in detail["message"]
