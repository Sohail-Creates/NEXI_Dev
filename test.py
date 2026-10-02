
from __future__ import annotations

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import platform
import queue
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
CONSOLE_OUTPUT_MODES = ("narrative", "trace", "debug")
KNOWLEDGE_PREVIEW_LIMIT = 3
SESSION_END_PROMPT = ROOT / "04_tts_service" / "voices" / "session_end_normal.wav"
SESSION_END_TEXT = "Goodbye!"
VOICE_DIR = ROOT / "04_tts_service" / "voices"
# Text is used only when a recorded prompt is missing; ordinary playback uses the WAV.
CACHED_PROMPTS = {
    "profile_setup_start": ("profile_setup_start.wav", "Welcome to Nexi. Let's set up your profile."),
    "session_start": ("session_start.wav", "Welcome, how can I help you today?"),
    "teach_mode_start": ("teach_mode_start.wav", "Teaching mode activated. What would you like to teach me today?"),
    "verification_failed": ("verification_failed.wav", "I don't recognize your voice. Please try again or enroll if you're a new user."),
    "non_english_input": ("non_english_input.wav", "I currently only understand English."),
    "no_knowledge": ("no_knowledge.wav", "I'm not familiar with this yet. Could you teach me?"),
    "session_end_idle": ("session_end_idle.wav", "I haven't heard anything in a while, so I'm ending our conversation."),
    "system_status_check": ("system_status_check.wav", "Nexi is checking its system status."),
    "video_call_starting": ("video_call_starting.wav", "A video call is starting. I'll pause for a moment."),
    "video_call_ended": ("video_call_ended.wav", "The call has ended. Let's continue."),
    "object_taught_confirmation": ("object_taught_confirmation.wav", "I've learned that."),
}


def _service_url(environment_name: str, port: int) -> str:
    """Read one service URL from configuration and enforce an HTTPS default."""
    url = os.getenv(environment_name, f"https://127.0.0.1:{port}").rstrip("/")
    # The local stack binds IPv4 and its certificate covers 127.0.0.1.
    # On Windows a fresh localhost connection can wait for IPv6 first.
    if url.lower().startswith("https://localhost:"):
        url = "https://127.0.0.1:" + url[len("https://localhost:"):]
    return url


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


def _error_details(body: Any, status_code: int) -> tuple[str, str]:
    """Read the shared error envelope without exposing raw response bodies."""
    if isinstance(body, Mapping):
        error = body.get("error")
        envelope = error if isinstance(error, Mapping) else body
        code = str(envelope.get("code") or envelope.get("error_code") or "HTTP_ERROR")
        message = str(envelope.get("message") or envelope.get("detail") or "Request failed")
        message = " ".join(message.split())
        return code, message
    return "HTTP_ERROR", f"Request failed with HTTP status {status_code}"


def _operation_name(path: str) -> str:
    """Convert a route path to a short, human-readable operation label."""
    normalized = path.rstrip("/").lower()
    known = {
        "/health": "Health check",
        "/api/v1/health": "Health check",
        "/api/v1/record-until-silence/audio": "Audio recording",
        "/api/v1/verify-speaker": "Speaker verification",
        "/api/v1/transcribe": "Speech transcription",
        "/api/v1/rag/query": "Restricted RAG query",
        "/speak": "Speech synthesis",
        "/enrollment/enroll": "User enrollment",
        "/knowledge/facts": "Fact list",
        "/knowledge/objects": "Object list",
        "/users/list": "Enrolled-user list",
        "/resources/status": "Resource status",
        "/camera/status": "Camera status",
        "/sync/status": "Cloud-sync status",
    }
    if normalized in known:
        return known[normalized]
    leaf = normalized.rsplit("/", 1)[-1].replace("-", " ").replace("_", " ")
    return leaf[:1].upper() + leaf[1:] if leaf else "Service request"


def _knowledge_item_line(item: Mapping[str, Any], item_type: str) -> str:
    """Render a compact, user-facing preview without embedding metadata."""
    data = item.get("data") if isinstance(item.get("data"), Mapping) else {}
    item_id = str(item.get("id") or "").strip()

    if item_type == "fact":
        subject = " ".join(str(data.get("subject") or "Fact").split())
        predicate = " ".join(str(data.get("predicate") or "").split())
        value = " ".join(str(data.get("object") or "").split())
        summary = f"{subject}: {predicate}".rstrip(": ")
        if value:
            summary += f" ({value})" if predicate else f": {value}"
        return f"[{item_id}] {summary}" if item_id else summary

    name = " ".join(str(data.get("name") or item.get("name") or "Object").split())
    description = " ".join(str(data.get("description") or "").split())
    identity = f" [{item_id}]" if item_id else ""
    return f"{name}{identity}" + (f": {description}" if description else "")


@dataclass
class LiveResponse:
    status_code: int
    headers: dict[str, str]
    body: Any
    raw: bytes

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


class ManualRequestCancelled(RuntimeError):
    """Raised when SPACE cancels an in-flight manual-mode HTTP request."""


@dataclass
class ConversationCallCounts:
    record: int = 0
    verify_speaker: int = 0
    transcribe: int = 0
    rag: int = 0
    speak: int = 0
    playback: int = 0

    def snapshot(self) -> dict[str, int]:
        return {
            "record": self.record,
            "verify_speaker": self.verify_speaker,
            "transcribe": self.transcribe,
            "rag": self.rag,
            "speak": self.speak,
            "playback": self.playback,
        }


class SpaceSessionStop:
    """Watch SPACE without owning any application behavior."""

    def __init__(self, on_stop, *, message: str = "SPACE received: ending the whole conversation session...") -> None:
        self.requested = threading.Event()
        self._closed = threading.Event()
        self._on_stop = on_stop
        self._message = message
        self.reason = "space"
        self._stop_lock = threading.Lock()
        self._keys: queue.Queue[str] = queue.Queue()
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
                if msvcrt.kbhit():
                    key = msvcrt.getwch()
                    if key == " ":
                        self._stop()
                        return
                    if key not in {"\x00", "\xe0"}:
                        self._keys.put(key)
                time.sleep(0.03)
            return

        import select

        while not self._closed.is_set():
            readable, _, _ = select.select([sys.stdin], [], [], 0.1)
            if readable:
                key = sys.stdin.read(1)
                if key == " ":
                    self._stop()
                    return
                self._keys.put(key)

    def wait_for_enter(self, prompt: str) -> bool:
        """Wait for ENTER while the same key watcher can still observe SPACE."""
        print(prompt, end="", flush=True)
        while not self.requested.is_set():
            try:
                key = self._keys.get(timeout=0.1)
            except queue.Empty:
                continue
            if key in {"\r", "\n"}:
                print()
                return True
        return False

    def _stop(self) -> None:
        self.request_stop()

    def request_stop(self, *, reason: str = "space", message: str | None = None) -> None:
        with self._stop_lock:
            if self.requested.is_set():
                return
            self.reason = reason
            self.requested.set()
        print("\n" + (message or self._message))
        try:
            self._on_stop()
        except Exception as exc:
            print(f"Audio interrupt warning: {type(exc).__name__}: {exc}")


class LiveRESTClient:
    """The single networking boundary used by every console action."""

    def __init__(self, urls: ServiceURLs | None = None, output_mode: str | None = None) -> None:
        self.urls = urls or ServiceURLs()
        selected_output = output_mode or os.getenv("NEXI_CONSOLE_OUTPUT", "narrative")
        if selected_output not in CONSOLE_OUTPUT_MODES:
            raise ValueError(
                f"NEXI_CONSOLE_OUTPUT must be one of: {', '.join(CONSOLE_OUTPUT_MODES)}"
            )
        self.output_mode = selected_output
        self.internal_token = os.getenv("NEXI_INTERNAL_SERVICE_TOKEN", "").strip()
        self._client = httpx.Client(
            verify=_ca_verification(),
            timeout=httpx.Timeout(DEFAULT_TIMEOUT_SECONDS),
            follow_redirects=False,
        )

    def close(self) -> None:
        self._client.close()

    def _request(
        self,
        service: str,
        method: str,
        path: str,
        *,
        cancel_event: threading.Event | None = None,
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
        if self.output_mode == "debug":
            print("\nREQUEST")
            print(_print_json(request_summary))

        started_at = time.perf_counter()
        try:
            if cancel_event is None:
                response = self._client.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json_body,
                    data=data,
                    files=files,
                )
            else:
                async def send() -> httpx.Response:
                    async with httpx.AsyncClient(
                        verify=_ca_verification(),
                        timeout=httpx.Timeout(DEFAULT_TIMEOUT_SECONDS),
                        follow_redirects=False,
                    ) as client:
                        task = asyncio.create_task(client.request(
                            method, url, headers=headers, params=params, json=json_body,
                            data=data, files=files,
                        ))
                        while not task.done():
                            if cancel_event.is_set():
                                task.cancel()
                                try:
                                    await task
                                except asyncio.CancelledError:
                                    pass
                                raise ManualRequestCancelled("SPACE cancelled the in-flight request")
                            await asyncio.sleep(0.025)
                        if cancel_event.is_set():
                            raise ManualRequestCancelled("SPACE cancelled the in-flight request")
                        return await task

                response = asyncio.run(send())
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            if isinstance(exc, ManualRequestCancelled):
                if self.output_mode == "trace":
                    print(
                        f"[{service.title()}] {method.upper()} {path} -> CANCELLED "
                        f"({elapsed_ms:.0f} ms) | SPACE cancelled the request"
                    )
                elif self.output_mode == "debug":
                    print("RESPONSE")
                    print(_print_json({"status": "cancelled", "message": "SPACE cancelled the request"}))
                else:
                    print("Audio request cancelled by SPACE; no response was received.")
            else:
                self._report_failure(service, method, path, 0, "TRANSPORT_ERROR", str(exc), elapsed_ms)
            raise
        result = self._live_response(response)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        if self.output_mode == "debug":
            print("RESPONSE")
            print(_print_json({"status": result.status_code, "body": result.body}))
            if not result.ok:
                code, message = _error_details(result.body, result.status_code)
                self._report_failure(service, method, path, result.status_code, code, message, elapsed_ms)
        elif self.output_mode == "trace":
            self._report_trace(service, method, path, result, elapsed_ms)
        elif not result.ok:
            code, message = _error_details(result.body, result.status_code)
            self._report_failure(service, method, path, result.status_code, code, message, elapsed_ms)
        elif display or path.rstrip("/").endswith("/verify-speaker"):
            self._report_narrative(service, method, path, result)
        return result

    def _report_trace(
        self, service: str, method: str, path: str, response: LiveResponse, elapsed_ms: float
    ) -> None:
        prefix = f"[{service.title()}] {method.upper()} {path} -> {response.status_code} ({elapsed_ms:.0f} ms)"
        if not response.ok:
            code, message = _error_details(response.body, response.status_code)
            prefix += f" | {code}: {' '.join(message.split())}"
        print(prefix)

    def _report_failure(
        self, service: str, method: str, path: str, status_code: int,
        code: str, message: str, elapsed_ms: float,
    ) -> None:
        line = (
            f"{service.title()} request failed (HTTP {status_code}; {code}): {' '.join(message.split())}."
        )
        if self.output_mode == "trace":
            self._report_trace(
                service, method, path,
                LiveResponse(status_code, {}, {"code": code, "message": message}, b""),
                elapsed_ms,
            )
        elif self.output_mode == "narrative":
            print(line + " (run with --output debug for the full exchange)")
        else:
            print(line)

    def _report_narrative(self, service: str, method: str, path: str, response: LiveResponse) -> None:
        body = response.body if isinstance(response.body, Mapping) else {}
        if path.rstrip("/").endswith("/verify-speaker"):
            confidence = body.get("confidence")
            threshold = body.get("threshold")
            user_id = body.get("user_id")
            verified = bool(body.get("is_verified"))
            confidence_text = f"{float(confidence):.2f}" if confidence is not None else "not reported"
            threshold_text = f"{float(threshold):.2f}" if threshold is not None else "not reported"
            if response.ok and verified:
                print(f"Speaker verified as {user_id} (confidence {confidence_text}; threshold {threshold_text}).")
            else:
                message = f"Speaker not recognized (confidence {confidence_text}; threshold {threshold_text})."
                if confidence is not None and float(confidence) == 0.0:
                    message += " Please enroll or re-enroll this speaker."
                print(message)
            return

        # Manual-mode narration below reports these stages with richer, concise
        # context (end reason, duration, transcript, RAG source, or playback).
        if path.endswith("/record-until-silence/audio") or path.endswith("/api/v1/transcribe"):
            return

        service_name = str(body.get("service") or service).replace("_", " ").replace("-", " ").title()
        reported_status = str(body.get("status") or "").strip().lower()
        operation = _operation_name(path)
        if "health" in path and reported_status:
            print(f"{service_name} health: {reported_status} (HTTP {response.status_code}).")
            return
        if path.endswith("/knowledge/facts") or path.endswith("/knowledge/objects"):
            item_type = "fact" if path.endswith("/facts") else "object"
            items_key = "facts" if item_type == "fact" else "objects"
            items = body.get(items_key)
            items = [item for item in items if isinstance(item, Mapping)] if isinstance(items, list) else []
            count = body.get("count")
            count = count if isinstance(count, int) and count >= 0 else len(items)
            preview = [
                _knowledge_item_line(item, item_type)
                for item in items[:KNOWLEDGE_PREVIEW_LIMIT]
            ]
            if count > len(preview):
                preview.append(f"+{count - len(preview)} more")
            summary = f"{operation}: {count}"
            if not items:
                summary += f" (none taught)"
            elif preview:
                summary += " — " + "; ".join(preview)
            print(summary + ".")
            return
        if path.endswith("/users/list"):
            users = body.get("users", [])
            print(f"{operation}: retrieved {len(users)} enrolled users (HTTP {response.status_code}).")
            return
        message = body.get("message")
        if message:
            print(f"{operation}: {message} (HTTP {response.status_code}).")
            return
        print(f"{operation} completed successfully (HTTP {response.status_code}).")

    def request(
        self,
        service: str,
        method: str,
        path: str,
        *,
        cancel_event: threading.Event | None = None,
        internal: bool = False,
        bearer: str | None = None,
        params: Mapping[str, Any] | None = None,
        json_body: Any | None = None,
        data: Mapping[str, Any] | None = None,
        files: Any | None = None,
        display: bool = True,
    ) -> LiveResponse:
        return self._request(
            service, method, path, cancel_event=cancel_event, internal=internal,
            bearer=bearer, params=params, json_body=json_body, data=data,
            files=files, display=display,
        )

    @staticmethod
    def _live_response(response: httpx.Response) -> LiveResponse:
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
        return LiveResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            body=body,
            raw=response.content,
        )

    def request_cancellable(
        self,
        service: str,
        method: str,
        path: str,
        *,
        cancel_event: threading.Event | None = None,
        internal: bool = False,
        bearer: str | None = None,
        params: Mapping[str, Any] | None = None,
        json_body: Any | None = None,
        data: Mapping[str, Any] | None = None,
        files: Any | None = None,
        display: bool = True,
    ) -> LiveResponse:
        """Use the shared request path, optionally aborting the HTTP task on SPACE."""
        return self._request(
            service, method, path, cancel_event=cancel_event, internal=internal,
            bearer=bearer, params=params, json_body=json_body, data=data,
            files=files, display=display,
        )


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
    console._play_cached_prompt("profile_setup_start")
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
    console._play_cached_prompt("teach_mode_start")
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
        observation = console.client.request(
            "vision", "POST", "/api/v1/detect/objects", internal=True, display=False
        )
        detections = (
            observation.body.get("detections", [])
            if observation.ok and isinstance(observation.body, Mapping) else []
        )
        if detections:
            print("Detected objects:")
            for index, detected in enumerate(detections, 1):
                print(f"  {index}. {detected.get('class_name', 'object')} "
                      f"({detected.get('confidence', 0):.2f})")
            choice = input("Object number to teach (ENTER skips selection): ").strip()
            if choice:
                if not choice.isdecimal() or not 1 <= int(choice) <= len(detections):
                    raise ValueError("Choose a listed object number")
                data["vision_observation"] = detections[int(choice) - 1]
        else:
            print("No object selected; TeachMe will use its existing capture path.")
    else:
        raise ValueError("Choose fact or object")
    return console.teach(item_type, data)


def _confirmed_delete(label: str) -> bool:
    return input(f"Type DELETE to remove {label}: ").strip() == "DELETE"


def _interactive_delete_knowledge(console: "Sprint2Console") -> LiveResponse | None:
    item_type = input("Delete taught [fact/object]: ").strip().lower()
    if item_type not in {"fact", "object"}:
        raise ValueError("Choose fact or object")
    item_id = input(f"Taught {item_type} ID: ").strip()
    if not item_id:
        raise ValueError("Item ID is required")
    if not _confirmed_delete(item_id):
        print("Deletion cancelled")
        return None
    return console.delete_knowledge_item(item_id)


def _interactive_delete_user(console: "Sprint2Console") -> LiveResponse | None:
    listing = console.list_users()
    if not listing.ok:
        return listing
    users = listing.body.get("users", []) if isinstance(listing.body, Mapping) else []
    available = {
        str(user.get("user_id")): user
        for user in users
        if isinstance(user, Mapping) and user.get("user_id")
    }
    if not available:
        print("No enrolled users found.")
        return listing

    user_id = input("User ID to delete: ").strip()
    selected = available.get(user_id)
    if selected is None:
        print("That ID is not in the enrolled-user list; nothing was deleted.")
        return None
    user_name = selected.get("user_name") or selected.get("name") or "user"
    if not _confirmed_delete(user_id):
        print("Deletion cancelled")
        return None
    response = console.delete_user(user_id)
    if response.ok:
        print(f"User {user_name} ({user_id}) deleted successfully.")
    return response


class Sprint2Console:
    def __init__(self, client: LiveRESTClient) -> None:
        self.client = client
        self.session = Session()
        self._playback_gate = threading.Lock()
        self._background_prompts: list[threading.Thread] = []

    def health_dashboard(self, *, announce: bool = True) -> list[LiveResponse]:
        if announce:
            self._start_cached_prompt("system_status_check")
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
        response = self.client.request(
            "central",
            "POST",
            "/teachme/learn",
            internal=True,
            json_body={"type": item_type, "data": dict(data), "confidence": 1.0, "tags": ["manual-console"]},
        )
        if item_type == "object" and response.ok:
            self._start_cached_prompt("object_taught_confirmation")
        return response

    def list_knowledge(self, item_type: str) -> LiveResponse:
        if item_type not in {"fact", "object"}:
            raise ValueError("Choose fact or object")
        path = "/knowledge/facts" if item_type == "fact" else "/knowledge/objects"
        return self.client.request("teachme", "GET", path, internal=True)

    def delete_knowledge_item(self, item_id: str) -> LiveResponse:
        return self.client.request(
            "teachme", "DELETE", f"/forget/{quote(item_id, safe='')}", internal=True
        )

    def list_users(self) -> LiveResponse:
        response = self.client.request("central", "GET", "/users/list", internal=True, display=False)
        users = response.body.get("users", []) if isinstance(response.body, Mapping) else []
        print(f"Enrolled users: {len(users)}.")
        for user in users:
            if isinstance(user, Mapping):
                print(f"  {user.get('user_id', '?')}: {user.get('name') or user.get('user_name') or '?'}")
        return response

    def delete_user(self, user_id: str) -> LiveResponse:
        return self.client.request(
            "enrollment", "DELETE", f"/enrollment/delete-user/{quote(user_id, safe='')}",
            internal=True, display=False,
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
        self._start_cached_prompt("video_call_starting")
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
        self._start_cached_prompt("video_call_ended")
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
            return self._wake_conversation()
        if mode != "manual":
            raise ValueError("Mode must be manual or wake")
        return self._conversation_loop(mode="manual")

    def _wake_conversation(self) -> LiveResponse:
        """Wait for Audio's opt-in wake event, then use the ordinary REST turn loop."""
        started = self.client.request(
            "audio", "POST", "/api/v1/wake-word/start",
            internal=True, params={"event_mode": True},
        )
        if not started.ok:
            return started
        listener_stop = SpaceSessionStop(
            lambda: None, message="SPACE received: cancelling the wake listener..."
        )
        listener_stop.start()
        detected = False
        try:
            print("Listening for the wake word (SPACE cancels the listener).")
            while not listener_stop.requested.is_set():
                event = self.client.request_cancellable(
                    "audio", "GET", "/api/v1/wake-word/events",
                    internal=True, params={"timeout": 0.5},
                    cancel_event=listener_stop.requested, display=False,
                )
                if not event.ok:
                    return event
                if isinstance(event.body, Mapping) and event.body.get("event_detected"):
                    detected = True
                    break
        except ManualRequestCancelled:
            pass
        finally:
            listener_stop.close()
            self.client.request("audio", "POST", "/api/v1/wake-word/stop", internal=True)
        if not detected or listener_stop.requested.is_set():
            return self.client.request("audio", "GET", "/api/v1/orchestration/health")
        print("Wake word detected. Speak your first query now.")
        return self._conversation_loop(mode="wake")

    def _play_audio_bytes(self, audio: bytes, *, request_fn=None) -> LiveResponse:
        """One Audio-owned playback path, including its existing echo guard."""
        send = request_fn or self.client.request
        with self._playback_gate:
            return send(
                "audio", "POST", "/api/v1/playback/start", internal=True,
                files={"file": ("nexi-response.wav", audio, "audio/wav")}, display=False,
            )

    def _play_cached_prompt(self, prompt_id: str, *, request_fn=None) -> LiveResponse:
        """Use farewell's Audio playback path; synthesize only if the WAV is absent."""
        filename, text = CACHED_PROMPTS[prompt_id]
        send = request_fn or self.client.request
        path = VOICE_DIR / filename
        if path.is_file():
            audio = path.read_bytes()
        else:
            speech = send(
                "tts", "POST", "/speak", internal=True, display=False,
                json_body={"text": text, "language": "en", "voice_id": "jenny"},
            )
            if not speech.ok:
                return speech
            if not speech.raw.startswith(b"RIFF"):
                return LiveResponse(502, {}, {"message": "TTS returned no WAV audio"}, b"")
            audio = speech.raw
        return self._play_audio_bytes(audio, request_fn=send)

    def _start_cached_prompt(self, prompt_id: str) -> None:
        """Start a menu prompt while the real REST operation proceeds."""
        def play() -> None:
            try:
                response = self._play_cached_prompt(prompt_id)
                if not response.ok:
                    print(f"{prompt_id.replace('_', ' ')} audio could not play.")
            except Exception as exc:
                print(f"{prompt_id.replace('_', ' ')} audio failed: {type(exc).__name__}: {exc}")

        worker = threading.Thread(target=play, daemon=True)
        self._background_prompts = [item for item in self._background_prompts if item.is_alive()]
        self._background_prompts.append(worker)
        worker.start()

    def _wait_for_background_prompts(self) -> None:
        for worker in self._background_prompts:
            worker.join()
        self._background_prompts.clear()

    def _play_session_farewell(self) -> LiveResponse:
        """Use the recorded Jenny clip; retain /speak as a missing-cache fallback."""
        if SESSION_END_PROMPT.is_file():
            audio = SESSION_END_PROMPT.read_bytes()
        else:
            speech = self.client.request(
                "tts", "POST", "/speak", internal=True, display=False,
                json_body={"text": SESSION_END_TEXT, "language": "en", "voice_id": "jenny"},
            )
            if not speech.ok or not speech.raw.startswith(b"RIFF"):
                return speech
            audio = speech.raw
        return self._play_audio_bytes(audio)

    def _end_conversation_session(
        self, conversation_started: bool, rag_session_id: str | None, *, idle_end: bool = False
    ) -> None:
        """The shared manual/wake teardown; speak once before existing cleanup calls."""
        if conversation_started:
            farewell_stop = SpaceSessionStop(
                lambda: self.client.request(
                    "audio", "POST", "/api/v1/interrupt-playback", internal=True, display=False
                ),
                message="SPACE received: interrupting farewell playback...",
            )
            farewell_stop.start()
            try:
                farewell = (self._play_cached_prompt("session_end_idle") if idle_end
                            else self._play_session_farewell())
                if not farewell.ok:
                    print("Farewell playback failed; ending the session anyway.")
            except Exception as exc:
                print(f"Farewell playback failed: {type(exc).__name__}: {exc}")
            finally:
                farewell_stop.close()
        if conversation_started and self.session.token and self.session.user_id:
            self.client.request(
                "audio", "POST", "/api/v1/conversation/end", bearer=self.session.token,
                params={"user_id": self.session.user_id}, display=False,
            )
        if rag_session_id:
            self.client.request(
                "central", "DELETE", f"/api/v1/rag/sessions/{quote(rag_session_id, safe='')}",
                internal=True, display=False,
            )
        if conversation_started or rag_session_id:
            print("Conversation session ended.")

    def _conversation_loop(self, *, mode: str) -> LiveResponse:
        """Run the same verify-once REST conversation turns for either trigger."""
        if mode == "manual":
            _wait_for_spacebar("Press SPACE to start the manual conversation session")
        counts = ConversationCallCounts()
        last_response = LiveResponse(0, {}, {"message": "Session ended before capture"}, b"")
        conversation_started = False
        rag_session_id: str | None = None
        idle_timeout_seconds = None
        idle_end = False

        def interrupt_audio() -> None:
            self.client.request(
                "audio", "POST", "/api/v1/interrupt-playback", internal=True, display=False
            )

        stopper = SpaceSessionStop(interrupt_audio)
        stopper.start()
        if mode == "manual":
            print("Manual capture ready. No Central session exists until speaker verification succeeds.")
        stop_poll = threading.Event()
        stop_thread: threading.Thread | None = None

        def watch_stop_word() -> None:
            while not stop_poll.is_set() and not stopper.requested.is_set():
                try:
                    event = self.client.request(
                        "audio", "GET", "/api/v1/poll-stop-word", internal=True,
                        params={"timeout": 0.5}, display=False,
                    )
                    if stop_poll.is_set():
                        return
                    if not event.ok:
                        print("Stop-word detection is unavailable; use SPACE to end this session.")
                        return
                    if isinstance(event.body, Mapping) and event.body.get("event_detected"):
                        stopper.request_stop(
                            reason="stop_word", message="Stop NEXI detected: ending the conversation session..."
                        )
                        return
                except Exception as exc:
                    print(f"Stop-word polling failed: {type(exc).__name__}: {exc}")
                    return
        turn_number = 0
        prior_counts = counts.snapshot()
        try:
            self._wait_for_background_prompts()
            opening = self._play_cached_prompt("session_start")
            if not opening.ok:
                print("Session-start audio could not play; continuing to capture.")
            if stopper.requested.is_set():
                return last_response
            if mode == "manual" and not stopper.wait_for_enter("Press ENTER to record your first query (SPACE cancels): "):
                return last_response

            def request(service: str, method: str, path: str, **kwargs) -> LiveResponse:
                kwargs.setdefault("display", False)
                return self.client.request_cancellable(
                    service, method, path,
                    cancel_event=stopper.requested,
                    **kwargs,
                )

            def report_counts(turn_number: int, previous: Mapping[str, int]) -> None:
                if self.client.output_mode != "debug":
                    return
                current = counts.snapshot()
                delta = {name: current[name] - previous[name] for name in current}
                print(
                    f"Turn {turn_number} REST calls: "
                    + ", ".join(f"{name}={value}" for name, value in delta.items())
                )

            first_turn = True
            while not stopper.requested.is_set():
                prior_counts = counts.snapshot()
                turn_number += 1
                if conversation_started and not first_turn:
                    audio_state = self.client.request(
                        "audio", "GET", "/api/v1/conversation-state", internal=True,
                        display=False,
                    )
                    state_body = audio_state.body if isinstance(audio_state.body, Mapping) else {}
                    if audio_state.ok and str(state_body.get("state", "")).casefold() == "idle":
                        idle_end = True
                        print(
                            "Central's idle timeout ended the Audio session automatically"
                            + (f" after {idle_timeout_seconds}s without a RAG turn." if idle_timeout_seconds else ".")
                        )
                        break
                print("\nAudio is recording. Speak naturally; recording stops when you finish speaking.")
                self._wait_for_background_prompts()
                counts.record += 1
                recording = request(
                    "audio", "POST", "/api/v1/record-until-silence/audio",
                    internal=True,
                )
                last_response = recording
                if stopper.requested.is_set():
                    break
                end_reason = recording.headers.get("x-nexi-recording-end-reason", "unknown")
                if recording.status_code == 204 and end_reason in {"no_speech", "cancelled"}:
                    print(f"Capture ended: {end_reason}. STT was skipped.")
                    report_counts(turn_number, prior_counts)
                    if end_reason == "cancelled":
                        break
                    continue
                if not recording.ok or not recording.raw.startswith(b"RIFF"):
                    print(
                        "Audio recording failed: "
                        f"{_response_message(recording.body, 'microphone capture unavailable')}"
                    )
                    report_counts(turn_number, prior_counts)
                    return recording
                duration = recording.headers.get("x-nexi-recording-duration")
                print(f"Audio recording completed: end_reason={end_reason}" + (f", {duration}s." if duration else "."))

                if first_turn:
                    print("Verifying the speaker...")
                    counts.verify_speaker += 1
                    verification = request(
                        "audio", "POST", "/api/v1/verify-speaker", internal=True,
                        files={"file": ("conversation.wav", recording.raw, "audio/wav")},
                    )
                    last_response = verification
                    if stopper.requested.is_set():
                        break
                    body = verification.body if isinstance(verification.body, Mapping) else {}
                    if not verification.ok or not body.get("is_verified"):
                        self._play_cached_prompt("verification_failed", request_fn=request)
                        report_counts(turn_number, prior_counts)
                        return verification
                    if not self.session.accept_token(body):
                        raise RuntimeError("Speaker verification succeeded without a session token")
                    created = request(
                        "central", "POST", "/api/v1/rag/sessions",
                        internal=True, bearer=self.session.token, display=False,
                    )
                    last_response = created
                    if not created.ok:
                        report_counts(turn_number, prior_counts)
                        return created
                    if not isinstance(created.body, Mapping) or not created.body.get("session_id"):
                        print(f"Could not create Central session: {_response_message(created.body, 'unknown error')}")
                        report_counts(turn_number, prior_counts)
                        return created
                    rag_session_id = str(created.body["session_id"])
                    idle_timeout_seconds = created.body.get("idle_timeout_seconds")
                    print(
                        f"Central session created for verified user {self.session.user_id}; "
                        "idle timeout starts now"
                        + (f" ({idle_timeout_seconds}s)." if idle_timeout_seconds else ".")
                    )
                    if stopper.requested.is_set():
                        break
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
                        report_counts(turn_number, prior_counts)
                        return started
                    conversation_started = True
                    first_turn = False
                    if mode == "wake":
                        stop_thread = threading.Thread(target=watch_stop_word, daemon=True)
                        stop_thread.start()

                print("Transcribing the recorded speech...")
                counts.transcribe += 1
                transcription = request(
                    "audio", "POST", "/api/v1/transcribe", internal=True,
                    params={"language": "auto"},
                    files={"file": ("conversation.wav", recording.raw, "audio/wav")},
                )
                last_response = transcription
                if stopper.requested.is_set():
                    break
                transcript = (
                    transcription.body.get("text", "").strip()
                    if transcription.ok and isinstance(transcription.body, Mapping)
                    else ""
                )
                if not transcript:
                    print("No clear speech was transcribed. Listening for the next query.")
                    report_counts(turn_number, prior_counts)
                    continue
                print(f'Transcribed text: "{transcript}"')

                print("Sending the transcribed query through restricted RAG...")
                counts.rag += 1
                rag = request(
                    "central", "POST", "/api/v1/rag/query", bearer=self.session.token,
                    json_body={"query": transcript, "session_id": rag_session_id},
                )
                last_response = rag
                if stopper.requested.is_set():
                    break
                best_similarity = rag.headers.get("x-nexi-best-similarity")
                if best_similarity is not None:
                    print(f"Semantic similarity diagnostic: {float(best_similarity):.4f}")
                if not rag.ok or not isinstance(rag.body, Mapping):
                    code, _ = _error_details(rag.body, rag.status_code)
                    if code == "english_only":
                        self._play_cached_prompt("non_english_input", request_fn=request)
                    print(f"RAG request failed: {_response_message(rag.body, 'unknown error')}")
                    report_counts(turn_number, prior_counts)
                    continue

                answer = str(rag.body.get("response") or "")
                idle_timeout_seconds = rag.headers.get(
                    "x-nexi-session-idle-timeout", idle_timeout_seconds
                )
                metadata = rag.body.get("metadata")
                metadata_source = metadata.get("source") if isinstance(metadata, Mapping) else None
                source = str(rag.body.get("source") or metadata_source or "")
                if source in {"no_match", "not_answerable"}:
                    print("No matching taught knowledge was found.")
                    print(f"NEXI: {CACHED_PROMPTS['no_knowledge'][1]}")
                    self._play_cached_prompt("no_knowledge", request_fn=request)
                    print("Listening for the next query...")
                    report_counts(turn_number, prior_counts)
                    continue
                if source == "no_speech":
                    print("No speech detected by Central; no language validation or answer generation was run.")
                    report_counts(turn_number, prior_counts)
                    continue
                if source == "grounding_failure":
                    print("A relevant knowledge candidate was retrieved, but the generated answer failed grounding validation.")
                    print("No answer was spoken. Try a more direct question or rephrase the stored fact.")
                    report_counts(turn_number, prior_counts)
                    continue
                is_basic_command = source == "basic_command"
                if source != "teachme_grounded" and not is_basic_command:
                    print(f"RAG did not return a speakable grounded answer (source={source or 'missing'}).")
                    print(f"NEXI: {answer}")
                    print("TTS was skipped. Listening for the next query...")
                    report_counts(turn_number, prior_counts)
                    continue

                print("Basic command response:" if is_basic_command else "Matching taught knowledge was found.")
                print(f"NEXI: {answer}")
                if rag.headers.get("x-nexi-session-ended", "false").casefold() == "true":
                    print("Farewell command received; playing the recorded goodbye before teardown.")
                    report_counts(turn_number, prior_counts)
                    break
                print("Converting the response to Jenny speech...")
                counts.speak += 1
                speech = request(
                    "tts", "POST", "/speak", internal=True,
                    json_body={"text": answer, "language": "en", "voice_id": "jenny"},
                )
                last_response = speech
                if stopper.requested.is_set():
                    break
                if not speech.ok or not speech.raw.startswith(b"RIFF"):
                    print("Speech synthesis failed; playback was skipped.")
                    report_counts(turn_number, prior_counts)
                    continue
                print("Speech synthesis completed. Playing the response...")
                counts.playback += 1
                playback = self._play_audio_bytes(speech.raw, request_fn=request)
                last_response = playback
                if stopper.requested.is_set():
                    break
                if playback.ok:
                    print("Playback completed; echo guard elapsed before the next capture.")
                else:
                    print(
                        "Playback failed: "
                        f"{_response_message(playback.body, 'audio output unavailable')}"
                    )
                report_counts(turn_number, prior_counts)

            return last_response
        except ManualRequestCancelled:
            print(
                "SPACE cancelled the active REST request; downstream steps were not started."
                if stopper.reason == "space" else
                "Stop word cancelled the active REST request; downstream steps were not started."
            )
            if turn_number:
                report_counts(turn_number, prior_counts)
            return last_response
        finally:
            stop_poll.set()
            if stop_thread is not None:
                stop_thread.join(timeout=1.0)
            stopper.close()
            self._end_conversation_session(conversation_started, rag_session_id, idle_end=idle_end)

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
 8  Delete taught fact or object
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
        "8": lambda: _interactive_delete_knowledge(console),
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
        except Exception as exc:
            print(f"Action failed: {type(exc).__name__}: {exc}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--health",
        action="store_true",
        help="Run the non-interactive seven-service health dashboard and exit",
    )
    parser.add_argument(
        "--output",
        choices=CONSOLE_OUTPUT_MODES,
        default=None,
        help="Console output detail (default: NEXI_CONSOLE_OUTPUT or narrative)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    client = LiveRESTClient(output_mode=args.output)
    console = Sprint2Console(client)
    try:
        if args.health:
            responses = console.health_dashboard(announce=False)
            return 0 if all(response.status_code == 200 for response in responses) else 1
        return _interactive(console)
    finally:
        console._wait_for_background_prompts()
        client.close()


if __name__ == "__main__":
    sys.exit(main())
