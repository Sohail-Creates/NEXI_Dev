"""Direct voice fallback; the legacy name preserves the existing import contract."""

import logging
import os
import threading
import time
from enum import Enum
from typing import Callable

import requests
from shared.security import internal_service_headers
from config.ssl_config import client_verify

try:
    from shared.focus_mode import FocusModeClient
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parents[3]))
    from shared.focus_mode import FocusModeClient

from audio_service.config import CONVERSATION_CONFIG, VAD_RECORDER_CONFIG
from audio_service.services.vad_recorder import VADRecorder
from audio_service.utils.audio_utils import AudioRecorderError

logger = logging.getLogger(__name__)


class DirectVoiceSessionState(Enum):
    IDLE = "idle"
    ACQUIRING_MICROPHONE = "acquiring_microphone"
    RECORDING = "recording"
    ENDED = "ended"
    FAILED = "failed"


class MicrophoneLeaseClient:
    """Fail-closed HTTP client for Central's Phase 2 microphone authority."""

    def __init__(self, central_url=None, timeout=2.0):
        self.central_url = (central_url or os.getenv(
            "CENTRAL_SERVER_URL", "https://localhost:8000"
        )).rstrip("/")
        self.timeout = timeout

    def acquire(self):
        response = requests.post(
            self.central_url + "/resources/request",
            params={
                "resource_type": "microphone",
                "service_name": "audio_direct_voice",
                "priority": "ACTIVE_CONVERSATION",
                "timeout_seconds": max(30, int(CONVERSATION_CONFIG["timeout_seconds"] + 5)),
            },
            headers=internal_service_headers(),
            timeout=self.timeout,
            verify=client_verify(self.central_url),
        )
        response.raise_for_status()
        payload = response.json()
        lease_id = payload.get("lease_id")
        if not lease_id or payload.get("state") != "reserved":
            if lease_id:
                self.release(lease_id)
            raise RuntimeError("Microphone authority did not reserve a lease")
        acknowledgement = requests.post(
            self.central_url + "/resources/acknowledge/" + lease_id,
            headers=internal_service_headers(),
            timeout=self.timeout,
            verify=client_verify(self.central_url),
        )
        acknowledgement.raise_for_status()
        if acknowledgement.json().get("granted") is not True:
            self.release(lease_id)
            raise RuntimeError("Microphone authority did not acknowledge the grant")
        return lease_id

    def release(self, lease_id):
        response = requests.post(
            self.central_url + "/resources/release/" + lease_id,
            headers=internal_service_headers(),
            timeout=self.timeout,
            verify=client_verify(self.central_url),
        )
        return response.status_code in (200, 404)

    def status(self, lease_id):
        response = requests.get(
            self.central_url + "/resources/status/" + lease_id,
            headers=internal_service_headers(),
            timeout=self.timeout,
            verify=client_verify(self.central_url),
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json().get("lease")


class DirectVoiceSession:
    """One wake-failure session with explicit lease and terminal state."""

    def __init__(self, recorder, lease_client=None, callback=None):
        self.recorder = recorder
        self.lease_client = lease_client or MicrophoneLeaseClient()
        self.callback = callback
        self.stop_event = threading.Event()
        self.state = DirectVoiceSessionState.IDLE
        self.end_reason = None
        self.lease_id = None
        self.last_released_lease_id = None

    def run(self, timeout=30.0):
        self.stop_event.clear()
        self.end_reason = None
        self.state = DirectVoiceSessionState.ACQUIRING_MICROPHONE
        started = time.monotonic()
        try:
            self.lease_id = self.lease_client.acquire()
            self.state = DirectVoiceSessionState.RECORDING
            self.recorder.max_recording_seconds = max(
                timeout, CONVERSATION_CONFIG["timeout_seconds"] + 1
            )
            result = self.recorder.record_until_silence(stop_event=self.stop_event)
            if not result.get("success"):
                raise AudioRecorderError(result.get("error", "Direct voice recording failed"))
            self.end_reason = (
                "manual_stop" if self.stop_event.is_set() else result.get("stopped_by")
            )
            if self.end_reason != "manual_stop" and result.get("audio_file") and self.callback:
                self.callback(result["audio_file"], 0.0)
            self.state = DirectVoiceSessionState.ENDED
            return {
                **result,
                "keyword": "direct_voice",
                "detection_time": time.monotonic() - started,
                "end_reason": self.end_reason,
                "lease_id": self.lease_id,
            }
        except Exception:
            self.state = DirectVoiceSessionState.FAILED
            raise
        finally:
            if self.lease_id is not None:
                lease_id = self.lease_id
                if not self.lease_client.release(lease_id):
                    self.state = DirectVoiceSessionState.FAILED
                    raise RuntimeError("Microphone lease release was not acknowledged")
                self.last_released_lease_id = lease_id
                self.lease_id = None


    def manual_stop(self):
        self.stop_event.set()


class KeyboardWakeWordListener:
    """Capture spoken queries without a wake word or keyboard input."""

    def __init__(self, callback: Callable, focus_mode_client=None):
        self.callback = callback
        self._stop_event = threading.Event()
        self._thread = None
        self.error = None
        self.focus_mode_client = focus_mode_client or FocusModeClient()
        self.recorder = VADRecorder(
            sample_rate=VAD_RECORDER_CONFIG["sample_rate"],
            chunk_size=VAD_RECORDER_CONFIG["chunk_size"],
            silence_threshold_ms=int(CONVERSATION_CONFIG["timeout_seconds"] * 1000),
            max_duration_seconds=max(
                VAD_RECORDER_CONFIG["max_recording_seconds"],
                int(CONVERSATION_CONFIG["timeout_seconds"] + 1),
            ),
        )
        self.vad = self.recorder.vad_instance
        self.session = DirectVoiceSession(self.recorder, callback=self.callback)

    def record_once(self, timeout: float = 30.0) -> dict:
        """Record bounded microphone windows until one contains speech."""
        result = self.session.run(timeout=timeout)
        result["status"] = "success"
        result["confidence"] = 0.0
        return result

    def start(self):
        """Start background recording; microphone failures remain observable."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self.error = None
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def _listen(self):
        try:
            while not self._stop_event.is_set():
                self.cooperate_with_focus()
                if self._stop_event.is_set():
                    break
                try:
                    result = self.record_once()
                except TimeoutError:
                    continue
                # DirectVoiceSession invokes the callback before releasing its lease.
        except InterruptedError:
            if not self._stop_event.is_set():
                raise
        except Exception as exc:
            self.error = exc
            logger.exception("Direct voice fallback failed")

    def cooperate_with_focus(self):
        """Throttle one idle-listening poll while TeachMe owns focus."""
        return self.focus_mode_client.defer_if_needed("background")

    def stop(self):
        """Stop after the current bounded microphone recording completes."""
        self._stop_event.set()
        self.session.manual_stop()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=VAD_RECORDER_CONFIG["max_recording_seconds"] + 1.0)
