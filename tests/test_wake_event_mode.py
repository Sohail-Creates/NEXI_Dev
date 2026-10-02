"""Focused checks for the opt-in wake event and shared console lifecycle."""

from __future__ import annotations

import asyncio
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "03_audio_service"))
import test as console_module
from audio_service.routes import advanced_routes


def _request(token: bytes | None = None) -> Request:
    headers = [(b"x-nexi-service-token", token)] if token else []
    return Request({"type": "http", "headers": headers})


def test_default_wake_start_keeps_server_callback(monkeypatch):
    callbacks = []
    turns = []

    async def turn(_user, audio_file):
        turns.append(audio_file)
        return SimpleNamespace(error=None, user_id="verified")

    monkeypatch.setitem(sys.modules, "main", SimpleNamespace(
        orchestrator=SimpleNamespace(process_conversation_turn=turn)
    ))
    monkeypatch.setattr(advanced_routes.wake_word_service, "start_listening", lambda detection_callback: callbacks.append(detection_callback))

    async def exercise():
        await advanced_routes.start_wake_word_detection(_request())
        callbacks[0]("legacy.wav", 0.8)
        await asyncio.sleep(0.01)

    asyncio.run(exercise())
    assert turns == ["legacy.wav"]


def test_opt_in_wake_event_never_calls_server_turn(monkeypatch):
    callbacks = []
    monkeypatch.setenv("AUTH_ENFORCEMENT_ENABLED", "true")
    monkeypatch.setenv("NEXI_INTERNAL_SERVICE_TOKEN", "wake-test-token")
    monkeypatch.setattr(advanced_routes.wake_word_service, "start_listening", lambda detection_callback: callbacks.append(detection_callback))
    monkeypatch.setitem(sys.modules, "main", SimpleNamespace(orchestrator=None))

    async def exercise():
        await advanced_routes.start_wake_word_detection(_request(b"wake-test-token"), event_mode=True)
        callbacks[0]("event-only.wav", 0.8)
        return await advanced_routes.poll_wake_word_event(timeout=0.1)

    event = asyncio.run(exercise())
    assert event == {"event_detected": True, "event": {"event": "wake_word_detected", "confidence": 0.8}}
    assert advanced_routes._wake_events.empty()


def test_opt_in_wake_event_is_consumed_over_authenticated_rest(monkeypatch):
    callbacks = []
    monkeypatch.setenv("AUTH_ENFORCEMENT_ENABLED", "true")
    monkeypatch.setenv("NEXI_INTERNAL_SERVICE_TOKEN", "wake-test-token")
    monkeypatch.setattr(advanced_routes.wake_word_service, "start_listening", lambda detection_callback: callbacks.append(detection_callback))
    app = FastAPI()
    app.include_router(advanced_routes.router)
    with TestClient(app) as client:
        headers = {"X-NEXI-Service-Token": "wake-test-token"}
        assert client.post("/api/v1/wake-word/start?event_mode=true", headers=headers).status_code == 200
        callbacks[0]("injected.wav", 0.9)
        reply = client.get("/api/v1/wake-word/events?timeout=0.1", headers=headers)
        assert reply.status_code == 200
        assert reply.json()["event"] == {"event": "wake_word_detected", "confidence": 0.9}
        assert client.get("/api/v1/wake-word/events?timeout=0.1").status_code == 401


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

    def request_stop(self, *, reason, message):
        self.reason = reason
        self.requested.set()


class _RESTFixture:
    output_mode = "narrative"

    def __init__(self, *, stop_word=False):
        self.calls = []
        self.stop_word = stop_word
        self.playbacks = 0

    def request_cancellable(self, *args, **kwargs):
        return self.request(*args, **kwargs)

    def request(self, service, method, path, **kwargs):
        self.calls.append((service, method, path, kwargs))
        response = console_module.LiveResponse
        if path == "/api/v1/wake-word/events":
            return response(200, {}, {"event_detected": True}, b"")
        if path == "/api/v1/poll-stop-word":
            time.sleep(0.02)
            return response(200, {}, {"event_detected": self.stop_word and self.playbacks > 1}, b"")
        if path == "/api/v1/record-until-silence/audio":
            if self.stop_word and self.playbacks:
                time.sleep(0.05)
            return response(200, {"x-nexi-recording-end-reason": "speech_end"}, None, b"RIFFclip")
        if path == "/api/v1/verify-speaker":
            return response(200, {}, {"is_verified": True, "user_id": "user-one", "access_token": "token"}, b"")
        if path == "/api/v1/rag/sessions":
            return response(200, {}, {"session_id": "session-one"}, b"")
        if path == "/api/v1/transcribe":
            return response(200, {}, {"text": "Goodbye"}, b"")
        if path == "/api/v1/rag/commands/stop":
            return response(200, {}, {"is_stop_command": True}, b"")
        if path == "/api/v1/rag/query":
            if self.stop_word:
                return response(200, {}, {"response": "A grounded answer.", "source": "teachme_grounded"}, b"")
            return response(200, {"x-nexi-session-ended": "true"}, {"response": "Goodbye!", "source": "basic_command"}, b"")
        if path == "/speak":
            return response(200, {}, None, b"RIFFspeech")
        if path == "/api/v1/playback/start":
            self.playbacks += 1
        return response(200, {}, {"success": True, "state": "active"}, b"")


def test_manual_and_wake_share_turn_loop_and_cached_farewell(monkeypatch):
    monkeypatch.setattr(console_module, "SpaceSessionStop", _NoKeyboardStop)
    monkeypatch.setattr(console_module, "_wait_for_spacebar", lambda _prompt: None)
    for mode in ("manual", "wake"):
        client = _RESTFixture()
        console = console_module.Sprint2Console(client)
        console.return_user(mode)
        paths = [call[2] for call in client.calls]
        assert paths.count("/api/v1/record-until-silence/audio") == 1
        assert paths.count("/api/v1/verify-speaker") == 1
        assert paths.count("/api/v1/transcribe") == 1
        assert paths.count("/api/v1/rag/query") == (0 if mode == "manual" else 1)
        assert paths.count("/api/v1/playback/start") == (1 if mode == "manual" else 2)
        assert paths.index("/api/v1/playback/start") < paths.index("/api/v1/record-until-silence/audio")
        assert "/speak" not in paths
        assert paths.index("/api/v1/playback/start") < paths.index("/api/v1/conversation/end")
        if mode == "wake":
            assert paths.index("/api/v1/wake-word/stop") < paths.index("/api/v1/record-until-silence/audio")


def test_stop_word_ends_wake_session_through_same_farewell(monkeypatch):
    monkeypatch.setattr(console_module, "SpaceSessionStop", _NoKeyboardStop)
    client = _RESTFixture(stop_word=True)
    console_module.Sprint2Console(client).return_user("wake")
    paths = [call[2] for call in client.calls]
    assert paths.count("/api/v1/verify-speaker") == 1
    assert paths.count("/api/v1/rag/query") == 1
    assert paths.count("/api/v1/playback/start") == 3  # opening, answer, farewell
    assert paths.index("/api/v1/conversation/end") > max(i for i, path in enumerate(paths) if path == "/api/v1/playback/start")


def test_space_before_wake_event_only_stops_listener(monkeypatch):
    class AlreadyCancelled(_NoKeyboardStop):
        def start(self):
            self.requested.set()

    monkeypatch.setattr(console_module, "SpaceSessionStop", AlreadyCancelled)
    client = _RESTFixture()
    console_module.Sprint2Console(client).return_user("wake")
    paths = [call[2] for call in client.calls]
    assert "/api/v1/wake-word/stop" in paths
    assert "/api/v1/record-until-silence/audio" not in paths
    assert "/api/v1/playback/start" not in paths


def test_missing_farewell_cache_falls_back_to_live_speak(monkeypatch, tmp_path):
    monkeypatch.setattr(console_module, "SESSION_END_PROMPT", tmp_path / "absent.wav")
    client = _RESTFixture()
    result = console_module.Sprint2Console(client)._play_session_farewell()
    assert result.ok
    assert [call[2] for call in client.calls] == ["/speak", "/api/v1/playback/start"]


def test_manual_two_turns_reuse_verification_and_keep_grounded_tts(monkeypatch):
    class TwoTurns(_RESTFixture):
        def __init__(self):
            super().__init__()
            self.rag_count = 0
            self.transcript_count = 0

        def request(self, service, method, path, **kwargs):
            if path == "/api/v1/transcribe":
                self.transcript_count += 1
                self.calls.append((service, method, path, kwargs))
                return console_module.LiveResponse(200, {}, {"text": "A normal question" if self.transcript_count == 1 else "Goodbye"}, b"")
            if path == "/api/v1/rag/commands/stop":
                self.calls.append((service, method, path, kwargs))
                return console_module.LiveResponse(200, {}, {"is_stop_command": self.transcript_count > 1}, b"")
            if path == "/api/v1/rag/query":
                self.rag_count += 1
                if self.rag_count == 1:
                    self.calls.append((service, method, path, kwargs))
                    return console_module.LiveResponse(
                        200, {}, {"response": "A grounded answer.", "source": "teachme_grounded"}, b""
                    )
            return super().request(service, method, path, **kwargs)

    monkeypatch.setattr(console_module, "SpaceSessionStop", _NoKeyboardStop)
    monkeypatch.setattr(console_module, "_wait_for_spacebar", lambda _prompt: None)
    client = TwoTurns()
    console_module.Sprint2Console(client).return_user("manual")
    paths = [call[2] for call in client.calls]
    assert paths.count("/api/v1/record-until-silence/audio") == 2
    assert paths.count("/api/v1/verify-speaker") == 1
    assert paths.count("/api/v1/transcribe") == 2
    assert paths.count("/api/v1/rag/query") == 1
    assert paths.count("/speak") == 1  # grounded answer, not farewell
    assert paths.count("/api/v1/playback/start") == 2  # opening, answer; silent stop
