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
from contextlib import ExitStack
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import time
from typing import Any, Iterable, Mapping
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


@dataclass
class LiveResponse:
    status_code: int
    headers: dict[str, str]
    body: Any
    raw: bytes

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


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
        if len(photo_paths) != 5 or len(voice_paths) != 5:
            raise ValueError("Enrollment requires exactly five photos and five voice samples")
        with ExitStack() as stack:
            files = [
                ("photos", (path.name, stack.enter_context(path.open("rb")), "image/jpeg"))
                for path in photo_paths
            ] + [
                ("voice_samples", (path.name, stack.enter_context(path.open("rb")), "audio/wav"))
                for path in voice_paths
            ]
            form: dict[str, Any] = {"user_name": name}
            if age is not None:
                form["age"] = age
            if relation is not None:
                form["relation"] = relation
            response = self.client.request(
                "enrollment",
                "POST",
                "/enrollment/enroll",
                internal=True,
                data=form,
                files=files,
                display=False,
            )
        if isinstance(response.body, Mapping):
            self.session.accept_token(response.body, voice_paths[0])
        if response.ok:
            print(f"{name} enrolled successfully with 5 photos and 5 audio samples.")
        else:
            message = "Enrollment request failed"
            if isinstance(response.body, Mapping):
                message = str(response.body.get("message") or response.body.get("detail") or message)
            print(f"Enrollment failed (HTTP {response.status_code}): {message}")
        return response

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
        if voice is None:
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
        path = "/knowledge/facts" if item_type == "fact" else "/knowledge/objects"
        return self.client.request("teachme", "GET", path, internal=True)

    def ask(self, question: str) -> LiveResponse:
        self._require_session()
        return self.client.request(
            "central",
            "POST",
            "/api/v1/rag/query",
            bearer=self.session.token,
            json_body={"query": question},
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

    def vision_camera_analysis(self) -> LiveResponse:
        return self.client.request("vision", "POST", "/api/v1/analyze/complete", internal=True)

    def vision_face_upload(self, image: Path) -> LiveResponse:
        with image.open("rb") as handle:
            return self.client.request(
                "vision",
                "POST",
                "/api/v1/detect/faces/upload",
                internal=True,
                files={"file": (image.name, handle, "image/jpeg")},
            )

    def speak_jenny(self, text: str, output: Path | None = None) -> LiveResponse:
        response = self.client.request(
            "tts",
            "POST",
            "/speak",
            internal=True,
            json_body={"text": text, "voice_id": "jenny", "language": "en"},
        )
        if response.ok and output is not None and response.raw:
            output.write_bytes(response.raw)
            print(f"Audio response saved to {output.resolve()}")
        return response

    def manual_voice_fallback(self) -> tuple[LiveResponse, LiveResponse]:
        """Use spacebar controls while Audio owns recording and lease logic."""
        _wait_for_spacebar("Press SPACE to start the direct-voice fallback")
        started = self.client.request(
            "audio", "POST", "/api/v1/wake-word/start", internal=True
        )
        if not started.ok:
            return started, started
        try:
            _wait_for_spacebar("Press SPACE to stop and release the microphone")
        finally:
            stopped = self.client.request(
                "audio", "POST", "/api/v1/wake-word/stop", internal=True
            )
        return started, stopped


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
 1  Seven-service health dashboard
 2  Enroll user (live camera + microphone; five samples each)
 3  Voice login / refresh session
 4  Teach fact
 5  Teach object
 6  List taught facts or objects
 7  Ask through restricted RAG
 8  Read authenticated conversation history
 9  Cloud-sync status
10  Resource status
11  Camera status
12  Start simulated video call
13  End simulated video call
14  Vision camera object/face analysis
15  Vision face detection from uploaded image
16  Synthesize English speech with Jenny
17  Manual direct-voice fallback (SPACE starts/stops)
 0  Exit
"""


def _interactive(console: Sprint2Console) -> int:
    actions = {
        "1": lambda: console.health_dashboard(),
        "2": lambda: _interactive_enrollment(console),
        "3": lambda: console.voice_login(
            _existing_file(input("Synthesized-speech WAV path: ").strip(), "voice fixture")
        ),
        "4": lambda: console.teach(
            "fact",
            {
                "subject": input("Subject: ").strip(),
                "predicate": input("Predicate: ").strip(),
                "object": input("Object/value: ").strip(),
                "context": {},
            },
        ),
        "5": lambda: console.teach(
            "object",
            {
                "name": input("Object name: ").strip(),
                "category": input("Category (optional): ").strip() or None,
                "description": input("Description (optional): ").strip() or None,
                "attributes": {},
            },
        ),
        "6": lambda: console.list_knowledge(input("Type [fact/object]: ").strip().lower()),
        "7": lambda: console.ask(input("Question: ").strip()),
        "8": lambda: console.conversation_history(),
        "9": lambda: console.sync_status(),
        "10": lambda: console.resource_status(),
        "11": lambda: console.camera_status(),
        "12": lambda: console.call_start(input("Call ID (blank=generated): ").strip() or None),
        "13": lambda: console.call_end(input("Call ID (blank=current): ").strip() or None),
        "14": lambda: console.vision_camera_analysis(),
        "15": lambda: console.vision_face_upload(
            _existing_file(input("Image path: ").strip(), "image")
        ),
        "16": lambda: console.speak_jenny(
            input("Text: ").strip(), ROOT / "manual-jenny-output.wav"
        ),
        "17": lambda: console.manual_voice_fallback(),
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
