"""Cached-voice wiring checks; REST calls are intercepted, not reimplemented."""

from __future__ import annotations

import threading
import time
import io
import importlib.util
from pathlib import Path
import wave

import pytest

import test as console_module


def test_local_service_url_uses_ipv4_without_rewriting_remote_hosts(monkeypatch):
    monkeypatch.setenv("AUDIO_SERVICE_URL", "https://localhost:8002")
    assert console_module.ServiceURLs().audio == "https://127.0.0.1:8002"
    monkeypatch.setenv("AUDIO_SERVICE_URL", "https://audio.example.test:8002")
    assert console_module.ServiceURLs().audio == "https://audio.example.test:8002"


def test_audio_playback_reuses_preopened_device_and_closes_on_shutdown(monkeypatch):
    module_path = Path(__file__).resolve().parents[1] / "03_audio_service/audio_service/services/playback_manager.py"
    spec = importlib.util.spec_from_file_location("audio_playback_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    streams = []

    class FakeStream:
        def __init__(self, **kwargs):
            self.format = (kwargs["samplerate"], kwargs["channels"])
            self.starts = 0
            self.writes = 0
            self.closed = False
            streams.append(self)

        def start(self):
            self.starts += 1

        def write(self, chunk):
            self.writes += len(chunk)

        def stop(self):
            pass

        def close(self):
            self.closed = True

    monkeypatch.setattr(module.sd, "OutputStream", FakeStream)

    def wav_bytes(sample_rate):
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as recording:
            recording.setnchannels(1)
            recording.setsampwidth(2)
            recording.setframerate(sample_rate)
            recording.writeframes(b"\x01\x00" * (sample_rate // 10))
        return buffer.getvalue()

    manager = module.PlaybackManager()
    assert len(streams) == 1  # Device is ready before the first menu action.
    assert manager.play_audio_bytes(wav_bytes(22050))["success"]
    assert manager.play_audio_bytes(wav_bytes(22050))["success"]
    assert len(streams) == 1 and streams[0].starts == 2
    assert streams[0].writes == 4410
    assert manager.play_audio_bytes(wav_bytes(16000))["success"]
    assert len(streams) == 2 and streams[0].closed
    assert streams[1].format == (16000, 1)
    manager.close()
    assert streams[1].closed


class RecordingClient:
    output_mode = "narrative"

    def __init__(self):
        self.calls = []

    def request(self, service, method, path, **kwargs):
        self.calls.append((service, method, path, kwargs, time.perf_counter()))
        if path == "/speak":
            return console_module.LiveResponse(200, {}, None, b"RIFFfallback")
        return console_module.LiveResponse(200, {}, {"success": True}, b"")


def test_every_cached_prompt_uses_existing_audio_playback_endpoint():
    client = RecordingClient()
    console = console_module.Sprint2Console(client)
    for prompt_id in console_module.CACHED_PROMPTS:
        assert console._play_cached_prompt(prompt_id).ok
    playbacks = [call for call in client.calls if call[2] == "/api/v1/playback/start"]
    assert len(playbacks) == len(console_module.CACHED_PROMPTS)
    assert not any(call[2] == "/speak" for call in client.calls)
    for prompt_id, call in zip(console_module.CACHED_PROMPTS, playbacks):
        filename, _ = console_module.CACHED_PROMPTS[prompt_id]
        assert call[3]["files"]["file"][1] == (console_module.VOICE_DIR / filename).read_bytes()


def test_missing_prompt_uses_live_tts_then_same_audio_player(monkeypatch, tmp_path):
    monkeypatch.setattr(console_module, "VOICE_DIR", tmp_path)
    client = RecordingClient()
    console = console_module.Sprint2Console(client)
    assert console._play_cached_prompt("no_knowledge").ok
    assert [call[2] for call in client.calls] == ["/speak", "/api/v1/playback/start"]
    assert client.calls[0][3]["json_body"]["text"] == console_module.CACHED_PROMPTS["no_knowledge"][1]


def test_missing_prompt_rejects_success_without_wav(monkeypatch, tmp_path):
    monkeypatch.setattr(console_module, "VOICE_DIR", tmp_path)

    class BadSpeechClient(RecordingClient):
        def request(self, service, method, path, **kwargs):
            if path == "/speak":
                self.calls.append((service, method, path, kwargs, time.perf_counter()))
                return console_module.LiveResponse(200, {}, {}, b"not audio")
            return super().request(service, method, path, **kwargs)

    client = BadSpeechClient()
    response = console_module.Sprint2Console(client)._play_cached_prompt("no_knowledge")
    assert response.status_code == 502
    assert [call[2] for call in client.calls] == ["/speak"]


def test_background_prompt_starts_before_health_check_finishes():
    started = threading.Event()
    release = threading.Event()

    class SlowClient(RecordingClient):
        def request(self, service, method, path, **kwargs):
            if path == "/api/v1/playback/start":
                started.set()
                release.wait(timeout=2)
            return super().request(service, method, path, **kwargs)

    client = SlowClient()
    console = console_module.Sprint2Console(client)
    console._start_cached_prompt("system_status_check")
    assert started.wait(timeout=2)
    first_health = console.client.request("central", "GET", "/health")
    assert first_health.ok and not release.is_set()
    release.set()
    console._wait_for_background_prompts()


def test_background_playbacks_never_overlap():
    first_started = threading.Event()
    release_first = threading.Event()
    active = 0
    peak = 0
    gate = threading.Lock()

    class BlockingClient(RecordingClient):
        def request(self, service, method, path, **kwargs):
            nonlocal active, peak
            if path == "/api/v1/playback/start":
                with gate:
                    active += 1
                    peak = max(peak, active)
                    first_started.set()
                release_first.wait(timeout=2)
                with gate:
                    active -= 1
            return super().request(service, method, path, **kwargs)

    console = console_module.Sprint2Console(BlockingClient())
    console._start_cached_prompt("system_status_check")
    assert first_started.wait(timeout=2)
    console._start_cached_prompt("video_call_starting")
    time.sleep(0.05)
    release_first.set()
    console._wait_for_background_prompts()
    assert peak == 1
    assert sum(call[2] == "/api/v1/playback/start" for call in console.client.calls) == 2


def test_object_confirmation_only_after_successful_teach():
    class TeachClient(RecordingClient):
        def __init__(self, success):
            super().__init__()
            self.success = success

        def request(self, service, method, path, **kwargs):
            if path == "/teachme/learn":
                self.calls.append((service, method, path, kwargs, time.perf_counter()))
                return console_module.LiveResponse(200 if self.success else 500, {}, {}, b"")
            return super().request(service, method, path, **kwargs)

    for success in (False, True):
        client = TeachClient(success)
        console = console_module.Sprint2Console(client)
        console.teach("object", {"name": "test"})
        console._wait_for_background_prompts()
        paths = [call[2] for call in client.calls]
        assert paths == (["/teachme/learn", "/api/v1/playback/start"] if success else ["/teachme/learn"])


def test_menu_trigger_points_play_before_interaction(monkeypatch):
    client = RecordingClient()
    console = console_module.Sprint2Console(client)
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    with pytest.raises(ValueError, match="User name"):
        console_module._interactive_enrollment(console)
    with pytest.raises(ValueError, match="fact or object"):
        console_module._interactive_teach(console)
    clips = [call[3]["files"]["file"][1] for call in client.calls]
    assert clips == [
        (console_module.VOICE_DIR / "profile_setup_start.wav").read_bytes(),
        (console_module.VOICE_DIR / "teach_mode_start.wav").read_bytes(),
    ]


def test_video_call_prompts_start_at_rest_invocation():
    client = RecordingClient()
    console = console_module.Sprint2Console(client)
    assert console.call_start("test-call").ok
    assert console.call_end().ok
    console._wait_for_background_prompts()
    paths = [call[2] for call in client.calls]
    assert paths.count("/api/v1/playback/start") == 2
    assert "/calls/start" in paths and "/calls/end" in paths


class _NoKeyboardStop:
    def __init__(self, _on_stop, **_kwargs):
        self.requested = threading.Event()
        self.reason = "space"

    def start(self):
        pass

    def close(self):
        pass

    def wait_for_enter(self, _prompt):
        return True


class TurnClient(RecordingClient):
    def __init__(self, scenario):
        super().__init__()
        self.scenario = scenario
        self.records = 0

    def request_cancellable(self, *args, **kwargs):
        return self.request(*args, **kwargs)

    def request(self, service, method, path, **kwargs):
        self.calls.append((service, method, path, kwargs, time.perf_counter()))
        reply = console_module.LiveResponse
        if path == "/api/v1/record-until-silence/audio":
            self.records += 1
            if self.records > 1:
                return reply(204, {"x-nexi-recording-end-reason": "cancelled"}, None, b"")
            return reply(200, {"x-nexi-recording-end-reason": "speech_end"}, None, b"RIFFclip")
        if path == "/api/v1/verify-speaker":
            return reply(200, {}, {"is_verified": self.scenario != "verification_failed",
                                   "user_id": "user-one", "access_token": "token"}, b"")
        if path == "/api/v1/rag/sessions":
            return reply(200, {}, {"session_id": "session-one"}, b"")
        if path == "/api/v1/transcribe":
            return reply(200, {}, {"text": "A short query"}, b"")
        if path == "/api/v1/rag/commands/stop":
            return reply(200, {}, {"is_stop_command": False}, b"")
        if path == "/api/v1/rag/query":
            if self.scenario == "non_english_input":
                return reply(422, {}, {"error": {"code": "english_only", "message": "English-only input required"}}, b"")
            if self.scenario == "no_knowledge":
                return reply(200, {}, {"source": "no_match", "response": "I don't know this yet. Please teach me."}, b"")
            return reply(200, {}, {"source": "teachme_grounded", "response": "A grounded answer."}, b"")
        if path == "/api/v1/conversation-state":
            return reply(200, {}, {"state": "idle"}, b"")
        if path == "/speak":
            return reply(200, {}, None, b"RIFFspeech")
        return reply(200, {}, {"success": True}, b"")


@pytest.mark.parametrize("scenario,prompt_id", [
    ("verification_failed", "verification_failed"),
    ("non_english_input", "non_english_input"),
    ("no_knowledge", "no_knowledge"),
    ("session_end_idle", "session_end_idle"),
])
def test_conversation_branch_plays_its_clip(monkeypatch, scenario, prompt_id):
    monkeypatch.setattr(console_module, "SpaceSessionStop", _NoKeyboardStop)
    monkeypatch.setattr(console_module, "_wait_for_spacebar", lambda _prompt: None)
    client = TurnClient(scenario)
    console_module.Sprint2Console(client).return_user("manual")
    played = [call[3]["files"]["file"][1] for call in client.calls
              if call[2] == "/api/v1/playback/start"]
    assert played[0] == (console_module.VOICE_DIR / "session_start.wav").read_bytes()
    assert (console_module.VOICE_DIR / console_module.CACHED_PROMPTS[prompt_id][0]).read_bytes() in played
