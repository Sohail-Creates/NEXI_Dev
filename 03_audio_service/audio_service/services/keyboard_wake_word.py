"""Direct voice fallback; the legacy name preserves the existing import contract."""

import logging
import threading
import time
from typing import Callable

from scipy.io import wavfile

from audio_service.config import VAD_RECORDER_CONFIG
from audio_service.services.vad_recorder import VADRecorder
from audio_service.utils.audio_utils import AudioRecorderError

logger = logging.getLogger(__name__)


class KeyboardWakeWordListener:
    """Capture spoken queries without a wake word or keyboard input."""

    def __init__(self, callback: Callable):
        self.callback = callback
        self._stop_event = threading.Event()
        self._thread = None
        self.error = None
        self.recorder = VADRecorder(
            sample_rate=VAD_RECORDER_CONFIG["sample_rate"],
            chunk_size=VAD_RECORDER_CONFIG["chunk_size"],
            silence_threshold_ms=VAD_RECORDER_CONFIG["silence_threshold_ms"],
            max_duration_seconds=VAD_RECORDER_CONFIG["max_recording_seconds"],
        )
        self.vad = self.recorder.vad_instance

    def record_once(self, timeout: float = 30.0) -> dict:
        """Record bounded microphone windows until one contains speech."""
        started = time.monotonic()
        frames_processed = 0
        frame_length = int(self.recorder.sample_rate * self.vad.frame_duration_ms / 1000)
        while not self._stop_event.is_set():
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError("No direct speech received before timeout")
            self.recorder.max_recording_seconds = min(
                VAD_RECORDER_CONFIG["max_recording_seconds"], remaining
            )
            recording = self.recorder.record_until_silence()
            if not recording["success"]:
                raise AudioRecorderError(recording["error"])
            if self._stop_event.is_set():
                break
            sample_rate, audio = wavfile.read(recording["audio_file"])
            pcm = audio.flatten()
            speech_frames = 0
            for offset in range(0, len(pcm) - frame_length + 1, frame_length):
                is_speech, _ = self.vad.is_speech(
                    pcm[offset:offset + frame_length], use_webrtc=True
                )
                speech_frames += int(is_speech)
                frames_processed += 1
            if speech_frames:
                return {
                    "status": "success",
                    "keyword": "direct_voice",
                    "detection_time": time.monotonic() - started,
                    "frames_processed": frames_processed,
                    "speech_frames": speech_frames,
                    "audio_file": recording["audio_file"],
                    "confidence": 0.0,  # No wake-word confidence was measured.
                }
        raise InterruptedError("Direct voice recording stopped")

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
                try:
                    result = self.record_once()
                except TimeoutError:
                    continue
                self.callback(result["audio_file"], result["confidence"])
        except InterruptedError:
            if not self._stop_event.is_set():
                raise
        except Exception as exc:
            self.error = exc
            logger.exception("Direct voice fallback failed")

    def stop(self):
        """Stop after the current bounded microphone recording completes."""
        self._stop_event.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=VAD_RECORDER_CONFIG["max_recording_seconds"] + 1.0)
