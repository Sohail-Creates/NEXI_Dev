"""NEXI Sprint 2 live REST-only manual testing console.

This file is an external client. It deliberately imports no NEXI service
package, reads no service database, and implements no application policy. Each
action sends an HTTPS request to an operation published in ``docs/openapi`` and
prints the actual request metadata and response. Start the seven services with
the commands in ``commands.txt`` before using the console.

The filename is retained because it is the established operator entry point;
the former design-reference implementation has been replaced in full.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import threading
import time
from typing import Any, Iterable, Mapping
from urllib.parse import quote
from uuid import uuid4
import wave

import httpx
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=False)

SERVICE_TOKEN_HEADER = "X-NEXI-Service-Token"
CORRELATION_HEADER = "X-Correlation-ID"
DEFAULT_TIMEOUT_SECONDS = float(os.getenv("NEXI_HARNESS_TIMEOUT", "90"))


def _service_url(environment_name: str, port: int) -> str:
    """Read one service URL from configuration and enforce an HTTPS default."""
    return os.getenv(environment_name, f"https://localhost:{port}").rstrip("/")


@dataclass(frozen=True)
class ServiceURLs:
    central: str = field(default_factory=lambda: _service_url("CENTRAL_SERVER_URL", 8000))
    vision: str = field(default_factory=lambda: _service_url("VISION_SERVICE_URL", 8001))
    audio: str = field(default_factory=lambda: _service_url("AUDIO_SERVICE_URL", 8002))
    tts: str = field(default_factory=lambda: _service_url("TTS_SERVICE_URL", 8003))
    teachme: str = field(default_factory=lambda: _service_url("TEACHME_SERVICE_URL", 8004))
    enrollment: str = field(default_factory=lambda: _service_url("ENROLLMENT_SERVICE_URL", 8005))
    llm: str = field(default_factory=lambda: _service_url("LLM_SERVICE_URL", 8006))

    def by_name(self, name: str) -> str:
        return str(getattr(self, name))


HEALTH_OPERATIONS = (
    ("Central Server", "central", "/health"),
    ("Vision Service", "vision", "/health"),
    ("Audio Service", "audio", "/health"),
    ("TTS Service", "tts", "/health"),
    ("TeachMe Service", "teachme", "/health"),
    ("Enrollment Service", "enrollment", "/health"),
    ("LLM Service", "llm", "/api/v1/health"),
)


def _ca_verification() -> str:
    """Mirror the stack's CA-path convention without importing server code."""
    configured = os.getenv("NEXI_TLS_CA_FILE")
    ca_file = (
        Path(configured).expanduser()
        if configured
        else ROOT / "config" / "certificates" / "nexi-local-ca.crt"
    )
    if not ca_file.is_file():
        raise RuntimeError(
            f"TLS CA file does not exist: {ca_file}. Generate/configure certificates per run.txt."
        )
    return str(ca_file.resolve())


def _safe_headers(headers: Mapping[str, str]) -> dict[str, str]:
    sensitive = {"authorization", SERVICE_TOKEN_HEADER.lower()}
    return {
        key: ("<redacted>" if key.lower() in sensitive else value)
        for key, value in headers.items()
    }


def _safe_payload(value: Any, key: str = "") -> Any:
    """Mask credentials and biometric vectors while preserving response shape."""
    normalized = key.lower()
    sensitive_names = {
        "access_token",
        "authorization",
        "api_key",
        "secret",
        "token",
        "voice_embedding",
        "voice_embeddings",
        "face_embedding",
        "face_embeddings",
        "embedding",
        "embeddings",
    }
    if normalized in sensitive_names:
        if isinstance(value, list):
            return f"<redacted list; items={len(value)}>"
        return "<redacted>"
    if isinstance(value, Mapping):
        return {str(child_key): _safe_payload(child, str(child_key)) for child_key, child in value.items()}
    if isinstance(value, list):
        return [_safe_payload(child, key) for child in value]
    return value


def _print_json(value: Any) -> str:
    return json.dumps(_safe_payload(value), indent=2, ensure_ascii=False, default=str)


def _response_message(body: Any, default: str) -> str:
    if not isinstance(body, Mapping):
        return default
    error = body.get("error")
    if isinstance(error, Mapping):
        return str(error.get("message") or default)
    return str(body.get("message") or body.get("detail") or default)


@dataclass
class LiveResponse:
    status_code: int
    headers: dict[str, str]
    body: Any
    raw: bytes

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


@dataclass
class ConversationCallCounts:
    record: int = 0
    verify_speaker: int = 0
    transcribe: int = 0
    rag: int = 0
    speak: int = 0
    playback: int = 0


class SpaceSessionStop:
    """Watch SPACE without owning any application behavior."""

    def __init__(self, on_stop) -> None:
        self.requested = threading.Event()
        self._closed = threading.Event()
        self._on_stop = on_stop
        self._thread = threading.Thread(target=self._watch, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._closed.set()
        self._thread.join(timeout=0.5)

    def _watch(self) -> None:
        if platform.system() == "Windows":
            import msvcrt

            while not self._closed.is_set():
                if msvcrt.kbhit() and msvcrt.getwch() == " ":
                    self._stop()
                    return
                time.sleep(0.03)
            return

        import select

        while not self._closed.is_set():
            readable, _, _ = select.select([sys.stdin], [], [], 0.1)
            if readable and sys.stdin.read(1) == " ":
                self._stop()
                return

    def _stop(self) -> None:
        self.requested.set()
        print("\nSPACE received: ending the whole conversation session...")
        try:
            self._on_stop()
        except Exception as exc:
            print(f"Audio interrupt warning: {type(exc).__name__}: {exc}")


class LiveRESTClient:
    """The single networking boundary used by every console action."""

    def __init__(self, urls: ServiceURLs | None = None) -> None:
        self.urls = urls or ServiceURLs()
        self.internal_token = os.getenv("NEXI_INTERNAL_SERVICE_TOKEN", "").strip()
        self._client = httpx.Client(
            verify=_ca_verification(),
            timeout=httpx.Timeout(DEFAULT_TIMEOUT_SECONDS),
            follow_redirects=False,
        )

    def close(self) -> None:
        self._client.close()

    def request(
        self,
        service: str,
        method: str,
        path: str,
        *,
        internal: bool = False,
        bearer: str | None = None,
        params: Mapping[str, Any] | None = None,
        json_body: Any | None = None,
        data: Mapping[str, Any] | None = None,
        files: Any | None = None,
        display: bool = True,
    ) -> LiveResponse:
        url = f"{self.urls.by_name(service)}{path}"
        if not url.lower().startswith("https://"):
            raise RuntimeError(f"Refusing plaintext service URL: {url}")
        headers = {CORRELATION_HEADER: f"manual-{uuid4().hex}"}
        if internal:
            if not self.internal_token:
                raise RuntimeError("NEXI_INTERNAL_SERVICE_TOKEN is required for this operation")
            headers[SERVICE_TOKEN_HEADER] = self.internal_token
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"

        request_summary: dict[str, Any] = {
            "method": method.upper(),
            "url": url,
            "headers": _safe_headers(headers),
        }
        if params:
            request_summary["params"] = dict(params)
        if json_body is not None:
            request_summary["json"] = json_body
        if data:
            request_summary["form"] = dict(data)
        if files:
            iterable = files if isinstance(files, list) else list(files.items())
            request_summary["files"] = [
                {"field": field_name, "filename": value[0]}
                for field_name, value in iterable
            ]
        if display:
            print("\nREQUEST")
            print(_print_json(request_summary))

        response = self._client.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json_body,
            data=data,
            files=files,
        )
        content_type = response.headers.get("content-type", "")
        try:
            body: Any = response.json() if "json" in content_type else None
        except ValueError:
            body = None
        if body is None:
            if content_type.startswith("text/"):
                body = response.text
            else:
                body = f"<{len(response.content)} bytes; content-type={content_type or 'unknown'}>"
        result = LiveResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            body=body,
            raw=response.content,
        )
        if display:
            print("RESPONSE")
            print(_print_json({"status": result.status_code, "body": result.body}))
        return result


@dataclass
class Session:
    token: str | None = None
    user_id: str | None = None
    expires_at: float = 0.0
    voice_fixture: Path | None = None
    active_call_id: str | None = None

    def valid(self) -> bool:
        return bool(self.token and self.user_id and time.time() < self.expires_at - 5)

    def accept_token(self, body: Mapping[str, Any], voice_fixture: Path | None = None) -> bool:
        token = body.get("access_token")
        user_id = body.get("user_id")
        if not token or not user_id:
            return False
        expires_in = int(body.get("expires_in") or 1800)
        self.token = str(token)
        self.user_id = str(user_id)
        self.expires_at = time.time() + expires_in
        if voice_fixture is not None:
            self.voice_fixture = voice_fixture
        return True


def _existing_file(raw: str, label: str) -> Path:
    path = Path(raw).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"{label} does not exist: {path}")
    return path


def _prompt_files(label: str, count: int) -> list[Path]:
    print(f"Enter {count} {label} paths. Each file is uploaded unchanged to the service.")
    return [_existing_file(input(f"  {label} {index + 1}: ").strip(), label) for index in range(count)]


def _capture_face_samples(output_dir: Path, count: int = 5) -> list[Path]:
    """Capture enrollment photos locally; Vision still owns all face processing."""
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required for interactive face capture") from exc

    selector = os.getenv("VISION_CAMERA_DEVICE", "0").strip()
    try:
        device_index = int(selector)
    except ValueError as exc:
        raise RuntimeError(
            "Interactive capture requires VISION_CAMERA_DEVICE to be a numeric camera index"
        ) from exc

    camera = cv2.VideoCapture(device_index)
    if not camera.isOpened():
        camera.release()
        raise RuntimeError(f"Cannot open camera device {device_index}")

    prompts = ("front", "slightly left", "slightly right", "slightly up", "slightly down")
    captured: list[Path] = []
    window_name = "NEXI enrollment - SPACE capture, ESC cancel"
    try:
        while len(captured) < count:
            ok, frame = camera.read()
            if not ok or frame is None:
                raise RuntimeError("Camera stopped returning frames")
            preview = frame.copy()
            direction = prompts[len(captured)] if len(captured) < len(prompts) else "new angle"
            cv2.putText(
                preview,
                f"Photo {len(captured) + 1}/{count}: {direction} - press SPACE",
                (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )
            cv2.imshow(window_name, preview)
            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                raise RuntimeError("Face capture cancelled")
            if key != 32:
                continue
            path = output_dir / f"face_{len(captured) + 1}.jpg"
            if not cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95]):
                raise RuntimeError(f"Failed to save captured image: {path}")
            captured.append(path)
            print(f"Captured photo {len(captured)}/{count}: {path.name}")
    finally:
        camera.release()
        cv2.destroyAllWindows()
    return captured


def _capture_voice_samples(
    output_dir: Path, count: int = 5, duration_seconds: float = 5.0
) -> list[Path]:
    """Record WAV inputs locally; Audio still owns embeddings and verification."""
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError("numpy and sounddevice are required for voice capture") from exc

    configured = os.getenv("AUDIO_INPUT_DEVICE", "").strip()
    device: int | str | None
    if not configured:
        device = None
    else:
        try:
            device = int(configured)
        except ValueError:
            device = configured

    try:
        device_info = sd.query_devices(device, "input")
    except Exception as exc:
        raise RuntimeError(f"Cannot resolve audio input device {configured or '<system default>'}") from exc
    sample_rate = int(round(float(device_info["default_samplerate"])))
    if sample_rate <= 0:
        raise RuntimeError("Selected microphone reports an invalid sample rate")
    print(
        f"Microphone: {device_info['name']} | sample rate: {sample_rate} Hz | "
        f"duration: {duration_seconds:.1f}s per sample"
    )

    enrollment_phrases = (
        "Hello NEXI, this is my natural speaking voice.",
        "I am registering my voice for secure access.",
        "Please recognize me when I speak clearly.",
        "My voice confirms that I am present.",
        "NEXI can now verify my identity by voice.",
    )
    captured: list[Path] = []
    for index in range(count):
        phrase = enrollment_phrases[index % len(enrollment_phrases)]
        print(f'Voice sample {index + 1}/{count}: "{phrase}"')
        input("Press ENTER when you are ready to speak...")
        print(f'Recording now - say: "{phrase}"')
        try:
            recording = sd.rec(
                int(sample_rate * duration_seconds),
                samplerate=sample_rate,
                channels=1,
                dtype="int16",
                device=device,
                blocking=True,
            )
        except Exception as exc:
            raise RuntimeError(f"Microphone recording failed: {exc}") from exc
        samples = np.asarray(recording, dtype=np.int16).reshape(-1)
        peak = int(np.max(np.abs(samples.astype(np.int32)))) if samples.size else 0
        if samples.size == 0 or peak == 0:
            raise RuntimeError(f"Voice sample {index + 1} is empty or silent; enrollment cancelled")
        path = output_dir / f"voice_{index + 1}.wav"
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(samples.tobytes())
        captured.append(path)
        print(f"Captured voice sample {index + 1}/{count}: {duration_seconds:.1f}s, peak={peak}")
    return captured


def _interactive_enrollment(console: "Sprint2Console") -> LiveResponse:
    name = input("User name: ").strip()
    if not name:
        raise ValueError("User name is required")
    age_text = input("Age (optional): ").strip()
    try:
        age = int(age_text) if age_text else None
    except ValueError as exc:
        raise ValueError("Age must be a whole number") from exc
    relation = input("Relation (optional): ").strip() or None

    with tempfile.TemporaryDirectory(prefix="nexi-enrollment-") as temporary:
        capture_dir = Path(temporary)
        print("Camera preview will open. Press SPACE once for each requested angle.")
        photos = _capture_face_samples(capture_dir)
        print("Next, record five independent five-second voice samples.")
        voices = _capture_voice_samples(capture_dir)
        return console.enroll(name, photos, voices, age=age, relation=relation)


def _interactive_training(console: "Sprint2Console", *, replace: bool) -> LiveResponse:
    user_id = input("Enrolled user ID: ").strip()
    if not user_id:
        raise ValueError("User ID is required")
    with tempfile.TemporaryDirectory(prefix="nexi-training-") as temporary:
        capture_dir = Path(temporary)
        print("Press SPACE in the camera preview for each of five photos.")
        photos = _capture_face_samples(capture_dir)
        print("Record five independent five-second voice samples.")
        voices = _capture_voice_samples(capture_dir)
        if replace:
            return console.reenroll(user_id, photos, voices)
        return console.improve_training(user_id, photos, voices)


def _interactive_teach(console: "Sprint2Console") -> LiveResponse:
    item_type = input("Teach [fact/object]: ").strip().lower()
    if item_type == "fact":
        data = {
            "subject": input("Subject: ").strip(),
            "predicate": input("Predicate: ").strip(),
            "object": input("Object/value: ").strip(),
            "context": {},
        }
    elif item_type == "object":
        data = {
            "name": input("Object name: ").strip(),
            "category": input("Category (optional): ").strip() or None,
            "description": input("Description (optional): ").strip() or None,
            "attributes": {},
        }
    else:
        raise ValueError("Choose fact or object")
    return console.teach(item_type, data)


def _confirmed_delete(label: str) -> bool:
    return input(f"Type DELETE to remove {label}: ").strip() == "DELETE"


def _interactive_delete_object(console: "Sprint2Console") -> LiveResponse | None:
    item_id = input("Taught object item ID: ").strip()
    if not item_id:
        raise ValueError("Item ID is required")
    if not _confirmed_delete(item_id):
        print("Deletion cancelled")
        return None
    return console.delete_object(item_id)


def _interactive_delete_user(console: "Sprint2Console") -> LiveResponse | None:
    user_name = input("Enrolled user name: ").strip()
    if not user_name:
        raise ValueError("User name is required")
    if not _confirmed_delete(user_name):
        print("Deletion cancelled")
        return None
    return console.delete_user(user_name)


class Sprint2Console:
    def __init__(self, client: LiveRESTClient) -> None:
        self.client = client
        self.session = Session()

    def health_dashboard(self) -> list[LiveResponse]:
        results: list[LiveResponse] = []
        rows: list[tuple[str, str, int, str | None]] = []
        for label, service, path in HEALTH_OPERATIONS:
            try:
                response = self.client.request(service, "GET", path, display=False)
                results.append(response)
                reported = ""
                if isinstance(response.body, Mapping):
                    reported = str(response.body.get("status", "")).strip().lower()
                if not response.ok:
                    state = "UNHEALTHY"
                elif reported in {"degraded", "unavailable", "unhealthy", "error"}:
                    state = reported.upper()
                else:
                    state = "HEALTHY"
                rows.append((label, state, response.status_code, None))
            except httpx.HTTPError as exc:
                body = {"service": service, "status": "unreachable", "error": str(exc)}
                results.append(LiveResponse(status_code=0, headers={}, body=body, raw=b""))
                rows.append((label, "UNREACHABLE", 0, str(exc)))

        print("\n" + "=" * 62)
        print("NEXI SEVEN-SERVICE HEALTH DASHBOARD")
        print("=" * 62)
        for label, state, status_code, _error in rows:
            http_text = f"HTTP {status_code}" if status_code else "NO RESPONSE"
            print(f"{label:<22} : {state:<11} ({http_text})")
        responsive = sum(response.status_code == 200 for response in results)
        healthy = sum(state == "HEALTHY" for _, state, _, _ in rows)
        print("-" * 62)
        print(f"Responsive: {responsive}/7 | Healthy: {healthy}/7")
        print("=" * 62)
        return results

    def enroll(
        self,
        name: str,
        photos: Iterable[Path],
        voices: Iterable[Path],
        *,
        age: int | None = None,
        relation: str | None = None,
    ) -> LiveResponse:
        photo_paths, voice_paths = list(photos), list(voices)
        form: dict[str, Any] = {"user_name": name}
        if age is not None:
            form["age"] = age
        if relation is not None:
            form["relation"] = relation
        response = self._with_resource_trace(
            lambda: self._upload_samples(
                "/enrollment/enroll", photo_paths, voice_paths, "photos", "voice_samples", form
            )
        )
        if isinstance(response.body, Mapping):
            self.session.accept_token(response.body, voice_paths[0])
        if response.ok:
            print(f"{name} enrolled successfully with 5 photos and 5 audio samples.")
        else:
            print(
                f"Enrollment failed (HTTP {response.status_code}): "
                f"{_response_message(response.body, 'Enrollment request failed')}"
            )
        return response

    def _upload_samples(
        self, path: str, photos: Iterable[Path], voices: Iterable[Path],
        photo_field: str, voice_field: str, form: Mapping[str, Any] | None = None,
        *, authenticated: bool = False,
    ) -> LiveResponse:
        photo_paths, voice_paths = list(photos), list(voices)
        if len(photo_paths) != 5 or len(voice_paths) != 5:
            raise ValueError("Five photos and five voice samples are required")
        with ExitStack() as stack:
            files = [
                (photo_field, (path.name, stack.enter_context(path.open("rb")), "image/jpeg"))
                for path in photo_paths
            ] + [
                (voice_field, (path.name, stack.enter_context(path.open("rb")), "audio/wav"))
                for path in voice_paths
            ]
            return self.client.request(
                "enrollment", "POST", path, internal=not authenticated,
                bearer=self.session.token if authenticated else None, data=form, files=files,
            )

    def _with_resource_trace(self, action):
        print("Resource status BEFORE:")
        self.resource_status()
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                result = executor.submit(action)
                print("Resource status DURING request:")
                self.resource_status()
                return result.result()
        finally:
            print("Resource status AFTER:")
            self.resource_status()

    def improve_training(self, user_id: str, photos: Iterable[Path], voices: Iterable[Path]) -> LiveResponse:
        self._require_session()
        if user_id != self.session.user_id:
            raise ValueError("Training user ID must match the authenticated session")
        return self._upload_samples(
            f"/enrollment/improve-training/{quote(user_id, safe='')}",
            photos, voices, "additional_photos", "additional_voice_samples",
            authenticated=True,
        )

    def reenroll(self, user_id: str, photos: Iterable[Path], voices: Iterable[Path]) -> LiveResponse:
        self._require_session()
        if user_id != self.session.user_id:
            raise ValueError("Re-enrollment user ID must match the authenticated session")
        return self._upload_samples(
            f"/enrollment/update-model/{quote(user_id, safe='')}",
            photos, voices, "new_photos", "new_voice_samples",
            authenticated=True,
        )

    def voice_login(self, voice: Path) -> LiveResponse:
        with voice.open("rb") as handle:
            response = self.client.request(
                "central",
                "POST",
                "/users/session/voice",
                files={"file": (voice.name, handle, "audio/wav")},
            )
        if isinstance(response.body, Mapping):
            self.session.accept_token(response.body, voice)
        return response

    def _require_session(self) -> None:
        if self.session.valid():
            return
        print("Session is missing or expired; biometric re-authentication is required.")
        voice = self.session.voice_fixture
        if voice is None or not voice.is_file():
            voice = _existing_file(input("Synthesized-speech WAV path: ").strip(), "voice fixture")
        response = self.voice_login(voice)
        if not response.ok or not self.session.valid():
            raise RuntimeError("Voice verification did not issue a valid session token")

    def teach(self, item_type: str, data: Mapping[str, Any]) -> LiveResponse:
        return self.client.request(
            "central",
            "POST",
            "/teachme/learn",
            internal=True,
            json_body={"type": item_type, "data": dict(data), "confidence": 1.0, "tags": ["manual-console"]},
        )

    def list_knowledge(self, item_type: str) -> LiveResponse:
        if item_type not in {"fact", "object"}:
            raise ValueError("Choose fact or object")
        path = "/knowledge/facts" if item_type == "fact" else "/knowledge/objects"
        return self.client.request("teachme", "GET", path, internal=True)

    def delete_object(self, item_id: str) -> LiveResponse:
        return self.client.request(
            "teachme", "DELETE", f"/forget/{quote(item_id, safe='')}", internal=True
        )

    def list_users(self) -> LiveResponse:
        response = self.client.request("central", "GET", "/users/list", internal=True, display=False)
        users = response.body.get("users", []) if isinstance(response.body, Mapping) else []
        print(f"GET /users/list -> HTTP {response.status_code}; enrolled users: {len(users)}")
        for user in users:
            if isinstance(user, Mapping):
                print(f"  {user.get('user_id', '?')}: {user.get('name') or user.get('user_name') or '?'}")
        if not response.ok:
            print(_print_json(response.body))
        return response

    def delete_user(self, user_name: str) -> LiveResponse:
        self._require_session()
        return self.client.request(
            "enrollment", "DELETE", f"/enrollment/delete-user/{quote(user_name, safe='')}",
            bearer=self.session.token,
        )

    def conversation_history(self) -> LiveResponse:
        self._require_session()
        return self.client.request(
            "central",
            "GET",
            f"/users/{self.session.user_id}/conversations",
            bearer=self.session.token,
            params={"limit": 20},
        )

    def sync_status(self) -> LiveResponse:
        return self.client.request("central", "GET", "/sync/status", internal=True)

    def resource_status(self) -> LiveResponse:
        return self.client.request("central", "GET", "/resources/status", internal=True)

    def camera_status(self) -> LiveResponse:
        return self.client.request("central", "GET", "/camera/status", internal=True)

    def call_start(self, call_id: str | None = None) -> LiveResponse:
        selected = call_id or f"manual-{uuid4().hex[:10]}"
        response = self.client.request(
            "central", "POST", "/calls/start", internal=True, json_body={"call_id": selected}
        )
        if response.ok:
            self.session.active_call_id = selected
        return response

    def call_end(self, call_id: str | None = None) -> LiveResponse:
        selected = call_id or self.session.active_call_id
        if not selected:
            raise ValueError("No active call ID; start a call or supply its ID")
        response = self.client.request(
            "central", "POST", "/calls/end", internal=True, json_body={"call_id": selected}
        )
        if response.ok:
            self.session.active_call_id = None
        return response

    def video_call(self, call_id: str | None = None, *, wait_for_end: bool = True) -> LiveResponse:
        print("Resource status BEFORE video call:")
        self.resource_status()
        started = self.call_start(call_id)
        print("Resource status DURING video call:")
        self.resource_status()
        if not started.ok:
            return started
        if wait_for_end:
            input("Press ENTER to end the video call... ")
        ended = self.call_end()
        print("Resource status AFTER video call:")
        self.resource_status()
        return ended

    def return_user(self, mode: str = "manual") -> LiveResponse:
        """Drive Audio's wake or manual conversation surface over REST."""
        if mode == "wake":
            started = self.client.request("audio", "POST", "/api/v1/wake-word/start", internal=True)
            if not started.ok:
                return started
            try:
                _wait_for_spacebar("Press SPACE after speaking to stop the wake/direct-voice listener")
                return self.client.request("audio", "GET", "/api/v1/orchestration/health")
            finally:
                self.client.request("audio", "POST", "/api/v1/wake-word/stop", internal=True)
        if mode != "manual":
            raise ValueError("Mode must be manual or wake")
        return self._manual_conversation_loop()

    def _manual_conversation_loop(self) -> LiveResponse:
        """Run a verify-once multi-turn session using service APIs only."""
        _wait_for_spacebar("Press SPACE to start the manual conversation session")
        input("Press ENTER to record your first query... ")

        counts = ConversationCallCounts()
        last_response = LiveResponse(0, {}, {"message": "Session ended before capture"}, b"")
        conversation_started = False

        def interrupt_audio() -> None:
            self.client.request(
                "audio", "POST", "/api/v1/interrupt-playback", internal=True, display=False
            )

        stopper = SpaceSessionStop(interrupt_audio)
        stopper.start()
        try:
            first_turn = True
            while not stopper.requested.is_set():
                print("\nAudio is recording. Speak naturally; recording stops when you finish speaking.")
                recording = self.client.request(
                    "audio", "POST", "/api/v1/record-until-silence/audio",
                    internal=True, display=False,
                )
                counts.record += 1
                last_response = recording
                if stopper.requested.is_set():
                    break
                if not recording.ok or not recording.raw.startswith(b"RIFF"):
                    print(
                        "Audio recording failed: "
                        f"{_response_message(recording.body, 'microphone capture unavailable')}"
                    )
                    return recording
                duration = recording.headers.get("x-nexi-recording-duration")
                print(f"Audio recording completed{f' ({duration}s)' if duration else ''}.")

                if first_turn:
                    print("Verifying the speaker...")
                    verification = self.client.request(
                        "audio", "POST", "/api/v1/verify-speaker", internal=True,
                        files={"file": ("conversation.wav", recording.raw, "audio/wav")},
                        display=False,
                    )
                    counts.verify_speaker += 1
                    last_response = verification
                    body = verification.body if isinstance(verification.body, Mapping) else {}
                    if not verification.ok or not body.get("is_verified"):
                        print("User not enrolled — please enroll first")
                        return verification
                    if not self.session.accept_token(body):
                        raise RuntimeError("Speaker verification succeeded without a session token")
                    print(
                        f"Speaker verified as {self.session.user_id} "
                        f"(confidence {float(body.get('confidence', 0.0)):.2f})."
                    )
                    started = self.client.request(
                        "audio", "POST", "/api/v1/conversation/start",
                        bearer=self.session.token, params={"user_id": self.session.user_id},
                        display=False,
                    )
                    last_response = started
                    if not started.ok:
                        print(
                            "Conversation session could not start: "
                            f"{_response_message(started.body, 'unknown error')}"
                        )
                        return started
                    conversation_started = True
                    first_turn = False

                print("Transcribing the recorded speech...")
                transcription = self.client.request(
                    "audio", "POST", "/api/v1/transcribe", internal=True,
                    params={"language": "auto"},
                    files={"file": ("conversation.wav", recording.raw, "audio/wav")},
                    display=False,
                )
                counts.transcribe += 1
                last_response = transcription
                transcript = (
                    transcription.body.get("text", "").strip()
                    if transcription.ok and isinstance(transcription.body, Mapping)
                    else ""
                )
                if not transcript:
                    print("No clear speech was transcribed. Listening for the next query.")
                    continue
                print(f'Transcribed text: "{transcript}"')

                print("Sending the transcribed query through restricted RAG...")
                rag = self.client.request(
                    "central", "POST", "/api/v1/rag/query", bearer=self.session.token,
                    json_body={"query": transcript},
                    display=False,
                )
                counts.rag += 1
                last_response = rag
                query_tokens = rag.headers.get("x-nexi-query-tokens")
                retrieval_terms = rag.headers.get("x-nexi-retrieval-terms")
                best_similarity = rag.headers.get("x-nexi-best-similarity")
                if query_tokens is not None:
                    print(f"Normalized query tokens: {[token for token in query_tokens.split(',') if token]}")
                if retrieval_terms is not None:
                    print(f"RAG search terms: {[term for term in retrieval_terms.split(',') if term]}")
                if best_similarity is not None:
                    print(f"Best knowledge similarity: {float(best_similarity):.4f}")
                if not rag.ok or not isinstance(rag.body, Mapping):
                    print(f"RAG request failed: {_response_message(rag.body, 'unknown error')}")
                    continue

                answer = str(rag.body.get("response") or "")
                metadata = rag.body.get("metadata")
                metadata_source = metadata.get("source") if isinstance(metadata, Mapping) else None
                source = str(rag.body.get("source") or metadata_source or "")
                if source == "no_match":
                    print("No matching taught knowledge was found.")
                    print(f"NEXI: {answer}")
                    print("TTS was skipped. Listening for the next query...")
                    continue
                if source == "grounding_failure":
                    print("A relevant knowledge candidate was retrieved, but the generated answer failed grounding validation.")
                    print("No answer was spoken. Try a more direct question or rephrase the stored fact.")
                    continue
                if source != "teachme_grounded":
                    print(f"RAG did not return a speakable grounded answer (source={source or 'missing'}).")
                    print(f"NEXI: {answer}")
                    print("TTS was skipped. Listening for the next query...")
                    continue

                print("Matching taught knowledge was found.")
                print(f"Grounded response: {answer}")
                print("Converting the grounded response to Jenny speech...")
                speech = self.client.request(
                    "tts", "POST", "/speak", internal=True,
                    json_body={"text": answer, "language": "en", "voice_id": "jenny"},
                    display=False,
                )
                counts.speak += 1
                last_response = speech
                if stopper.requested.is_set():
                    break
                if not speech.ok or not speech.raw.startswith(b"RIFF"):
                    print("Speech synthesis failed; playback was skipped.")
                    continue
                print("Speech synthesis completed. Playing the response...")
                playback = self.client.request(
                    "audio", "POST", "/api/v1/playback/start", internal=True,
                    files={"file": ("nexi-response.wav", speech.raw, "audio/wav")},
                    display=False,
                )
                counts.playback += 1
                last_response = playback
                if playback.ok:
                    print("Playback completed. Listening for the next query...")
                else:
                    print(
                        "Playback failed: "
                        f"{_response_message(playback.body, 'audio output unavailable')}"
                    )

            return last_response
        finally:
            stopper.close()
            if conversation_started and self.session.token and self.session.user_id:
                self.client.request(
                    "audio", "POST", "/api/v1/conversation/end", bearer=self.session.token,
                    params={"user_id": self.session.user_id},
                    display=False,
                )
            print("Conversation session ended.")

    def audio_status(self) -> tuple[LiveResponse, LiveResponse]:
        print("Audio service circuit breaker and orchestration health (not general settings):")
        breaker = self.client.request("audio", "GET", "/api/v1/stt/circuit-breaker-status")
        orchestration = self.client.request("audio", "GET", "/api/v1/orchestration/health")
        return breaker, orchestration

def _wait_for_spacebar(prompt: str) -> None:
    """Console-only input handling; all application work remains REST-owned."""
    print(prompt)
    if platform.system() == "Windows":
        import msvcrt

        while msvcrt.getwch() != " ":
            pass
        print()
        return
    while input("Type one space and press Enter: ") != " ":
        pass


MENU = """
NEXI live REST console
 1  Service status (seven live health endpoints)
 2  New user (five photos + five voice samples)
 3  Improve training
 4  Re-enrollment (replace biometric samples)
 5  Return user (record, verify, RAG, Jenny, playback)
 6  Teach fact or object
 7  View taught facts and objects
 8  Delete taught object
 9  List enrolled users
10  Delete enrolled user
11  Video call (start/end and resource trace)
12  Resource and camera status
13  Cloud-sync status
14  Audio circuit breaker and orchestration health
 0  Exit
"""


def _interactive(console: Sprint2Console) -> int:
    actions = {
        "1": lambda: console.health_dashboard(),
        "2": lambda: _interactive_enrollment(console),
        "3": lambda: _interactive_training(console, replace=False),
        "4": lambda: _interactive_training(console, replace=True),
        "5": lambda: console.return_user(input("Trigger [manual/wake]: ").strip().lower() or "manual"),
        "6": lambda: _interactive_teach(console),
        "7": lambda: (console.list_knowledge("fact"), console.list_knowledge("object")),
        "8": lambda: _interactive_delete_object(console),
        "9": lambda: console.list_users(),
        "10": lambda: _interactive_delete_user(console),
        "11": lambda: console.video_call(input("Call ID (blank=generated): ").strip() or None),
        "12": lambda: (console.resource_status(), console.camera_status()),
        "13": lambda: console.sync_status(),
        "14": lambda: console.audio_status(),
    }
    while True:
        print(MENU)
        choice = input("Choose an action: ").strip()
        if choice == "0":
            return 0
        action = actions.get(choice)
        if action is None:
            print("Unknown action")
            continue
        try:
            action()
        except (httpx.HTTPError, OSError, RuntimeError, ValueError) as exc:
            print(f"ACTION FAILED: {type(exc).__name__}: {exc}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--health",
        action="store_true",
        help="Run the non-interactive seven-service health dashboard and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    client = LiveRESTClient()
    try:
        console = Sprint2Console(client)
        if args.health:
            responses = console.health_dashboard()
            return 0 if all(response.status_code == 200 for response in responses) else 1
        return _interactive(console)
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
