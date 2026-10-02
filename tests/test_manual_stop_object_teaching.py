"""Focused manual REST orchestration; no physical-device inference in tests."""

from concurrent.futures import Future
import sys
import threading
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import test as console_module
import basic_commands
import restricted_rag


def reply(body=None, *, status=200, headers=None, raw=b""):
    return console_module.LiveResponse(status, headers or {}, body, raw)


class Keys:
    def __init__(self, _on_stop, **_kwargs):
        self.requested = threading.Event()
        self.reason = "space"
        self.prompts = []

    def start(self):
        pass

    def close(self):
        pass

    def wait_for_enter(self, prompt):
        self.prompts.append(prompt)
        return True


@pytest.mark.parametrize("text,expected", [
    ("Goodbye", True), ("goodbye!", True), ("good bye", True),
    ("Say goodbye to him", False), ("goodbye bottle", False), ("hello", False),
])
def test_existing_stop_classifier_exact_whole_command(text, expected):
    assert basic_commands.is_stop_command(text, restricted_rag.RAG_FAREWELL_PHRASES) is expected


def test_command_rest_requires_auth_and_does_not_use_rag(monkeypatch):
    monkeypatch.setattr(restricted_rag, "get_teachme_connector", lambda: pytest.fail("Stop check invoked retrieval"))
    monkeypatch.setenv("AUTH_ENFORCEMENT_ENABLED", "true")
    monkeypatch.setenv("NEXI_INTERNAL_SERVICE_TOKEN", "command-test-token")
    app = FastAPI()
    app.include_router(restricted_rag.router)
    with TestClient(app) as client:
        assert client.post("/api/v1/rag/commands/stop", json={"query": "goodbye"}).status_code == 401
        headers = {"X-NEXI-Service-Token": "command-test-token"}
        # Match the trusted-user header's existing configured spelling.
        from shared.security import TRUSTED_USER_HEADER
        headers[TRUSTED_USER_HEADER] = "test-user"
        assert client.post("/api/v1/rag/commands/stop", headers=headers,
                           json={"query": "good bye"}).json() == {"is_stop_command": True}


class ManualREST:
    output_mode = "narrative"

    def __init__(self, *, silence=False, normal=False):
        self.calls = []
        self.captures = 0
        self.transcripts = 0
        self.silence = silence
        self.normal = normal

    def request_cancellable(self, *args, **kwargs):
        return self.request(*args, **kwargs)

    def request(self, service, method, path, **kwargs):
        self.calls.append((service, method, path, kwargs))
        if path == "/api/v1/record-until-silence/audio":
            self.captures += 1
            if self.silence and self.captures == 1:
                return reply(status=204, headers={"x-nexi-recording-end-reason": "no_speech"})
            return reply(raw=b"RIFFclip", headers={"x-nexi-recording-end-reason": "speech_end"})
        if path == "/api/v1/verify-speaker":
            return reply({"is_verified": True, "user_id": "test-user", "access_token": "test-token"})
        if path == "/api/v1/rag/sessions":
            return reply({"session_id": "test-session"})
        if path == "/api/v1/transcribe":
            self.transcripts += 1
            return reply({"text": "normal question" if self.normal and self.transcripts == 1 else "Goodbye"})
        if path == "/api/v1/rag/commands/stop":
            return reply({"is_stop_command": kwargs["json_body"]["query"] == "Goodbye"})
        if path == "/api/v1/rag/query":
            return reply({"source": "teachme_grounded", "response": "Stored answer"})
        if path == "/speak":
            return reply(raw=b"RIFFspeech")
        return reply({"success": True, "state": "active"})


@pytest.mark.parametrize("silence,normal", [(False, False), (True, False), (False, True)])
def test_manual_stop_before_rag_and_no_speech_waits(monkeypatch, silence, normal):
    watchers = []

    def watcher(*args, **kwargs):
        keys = Keys(*args, **kwargs)
        watchers.append(keys)
        return keys

    monkeypatch.setattr(console_module, "SpaceSessionStop", watcher)
    monkeypatch.setattr(console_module, "_wait_for_spacebar", lambda _prompt: None)
    client = ManualREST(silence=silence, normal=normal)
    console_module.Sprint2Console(client).return_user("manual")
    paths = [call[2] for call in client.calls]
    assert paths.count("/api/v1/verify-speaker") == 1
    assert paths.count("/api/v1/transcribe") == 1 + int(normal)
    assert paths.count("/api/v1/rag/query") == int(normal)
    assert paths.count("/speak") == int(normal)
    assert paths.count("/api/v1/playback/start") == 1 + int(normal)  # No farewell on transcript stop.
    assert "/api/v1/conversation/end" in paths
    assert paths[-1] == "/api/v1/rag/sessions/test-session"
    assert len(watchers[0].prompts) == 1 + int(silence)


def observation(name="bottle", class_id=39):
    return {"class_id": class_id, "class_name": name, "confidence": 0.9,
            "bounding_box": {"x": 1, "y": 1, "width": 10, "height": 10},
            "embedding": [0.25] * 64, "embedding_model": "yolov8n-p3-roi-avg-v1",
            "embedding_dimension": 64, "instance_embedding": [0.125] * 512,
            "instance_embedding_model": "torchvision-resnet18-imagenet1k-v1",
            "instance_embedding_dimension": 512, "instance_embedding_version": 1}


class ImmediateExecutor:
    def __init__(self, **_kwargs):
        pass

    def submit(self, function, *args):
        future = Future()
        try:
            future.set_result(function(*args))
        except Exception as exc:
            future.set_exception(exc)
        return future

    def shutdown(self, **_kwargs):
        pass


@pytest.mark.parametrize("detections,captured", [
    ([], False), ([observation("person", 0)], False),
    ([observation(), observation("cup", 41)], False),
    ([observation(), observation("person", 0)], True),
])
def test_camera_exactly_one_nonperson_and_cleanup(monkeypatch, detections, captured):
    released = []
    displayed = []
    keys = iter([13, 13 if captured else 27])
    frames = iter([np.full((20, 20, 3), 1, np.uint8), np.full((20, 20, 3), 2, np.uint8)])
    camera = SimpleNamespace(isOpened=lambda: True, read=lambda: (True, next(frames)),
                             release=lambda: released.append("camera"))
    cv2 = SimpleNamespace(VideoCapture=lambda _device: camera,
                          imencode=lambda _ext, frame: (True, np.array([frame[0, 0, 0]], np.uint8)),
                          imshow=lambda _window, frame: displayed.append(int(frame[0, 0, 0])),
                          waitKey=lambda _delay: next(keys), rectangle=lambda *_args: None,
                          putText=lambda *_args: None, FONT_HERSHEY_SIMPLEX=0,
                          destroyAllWindows=lambda: released.append("window"))
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    monkeypatch.setattr(console_module, "ThreadPoolExecutor", ImmediateExecutor)
    uploads = []

    def detect(_service, _method, path, **kwargs):
        assert path == "/api/v1/detect/objects/upload" and kwargs["internal"]
        uploads.append(kwargs["files"]["file"][1])
        return reply({"detections": detections})

    result = console_module._capture_object_observation(SimpleNamespace(
        client=SimpleNamespace(request_cancellable=detect)))
    assert (result is not None) is captured
    assert released == ["camera", "window"]
    assert displayed == [1, 1]  # Detection of frame 1 is never drawn on frame 2.
    assert uploads == [b"\x01", b"\x02"]
    if captured:
        assert result == detections[0]


def test_spoken_label_uses_audio_rest_only(monkeypatch):
    monkeypatch.setattr(console_module, "SpaceSessionStop", Keys)
    client = ManualREST()
    assert console_module._spoken_object_label(SimpleNamespace(client=client)) == "Goodbye"
    assert [call[2] for call in client.calls] == ["/api/v1/record-until-silence/audio", "/api/v1/transcribe"]


@pytest.mark.parametrize("cancel_at", ["camera", "label"])
def test_object_cancel_does_not_teach(monkeypatch, cancel_at):
    monkeypatch.setattr("builtins.input", lambda _prompt: "object")
    monkeypatch.setattr(console_module, "_capture_object_observation",
                        lambda _console: None if cancel_at == "camera" else observation())
    monkeypatch.setattr(console_module, "_spoken_object_label", lambda _console: None)
    console = SimpleNamespace(_play_cached_prompt=lambda _name: None,
                              _speak_instruction=lambda _text: None,
                              teach=lambda *_args: pytest.fail("Cancelled object was persisted"))
    assert console_module._interactive_teach(console) is None


def test_object_forwards_exact_observation_and_spoken_label(monkeypatch):
    selected = observation()
    taught = []
    monkeypatch.setattr("builtins.input", lambda _prompt: "object")
    monkeypatch.setattr(console_module, "_capture_object_observation", lambda _console: selected)
    monkeypatch.setattr(console_module, "_spoken_object_label", lambda _console: "My Gym Bottle")
    console = SimpleNamespace(_play_cached_prompt=lambda _name: None,
                              _speak_instruction=lambda _text: None,
                              teach=lambda kind, data: taught.append((kind, data)))
    console_module._interactive_teach(console)
    assert taught[0][0] == "object"
    assert taught[0][1]["vision_observation"] is selected
    assert taught[0][1]["name"] == "My Gym Bottle"
    assert taught[0][1]["category"] == "bottle"


@pytest.mark.parametrize("persisted", [True, False])
def test_object_success_requires_persisted_representations(monkeypatch, persisted):
    selected = observation()
    data = {"name": "My bottle", "category": "bottle", "vision_observation": selected}
    record = {"id": "item-1", "data": {"name": "My bottle", "category": "bottle"},
              "visual_embedding": selected["embedding"],
              "instance_prototypes": [selected["instance_embedding"]] if persisted else None}
    client = SimpleNamespace(request=lambda *_args, **_kwargs: reply({"success": True, "item_id": "item-1"}))
    console = console_module.Sprint2Console(client)
    monkeypatch.setattr(console, "list_knowledge", lambda _kind: reply({"objects": [record]}))
    prompts = []
    monkeypatch.setattr(console, "_start_cached_prompt", prompts.append)
    assert console.teach("object", data).ok is persisted
    assert prompts == (["object_taught_confirmation"] if persisted else [])


def test_selected_object_vectors_are_redacted_in_debug_output():
    safe = console_module._safe_payload(observation())
    assert isinstance(safe["embedding"], str)
    assert isinstance(safe["instance_embedding"], str)
    assert safe["class_name"] == "bottle"
    assert isinstance(console_module._safe_payload({"instance_prototypes": [[1.0]]})["instance_prototypes"], str)


def test_stop_contract_failure_never_forwards_transcript_to_rag(monkeypatch):
    class BrokenCommandREST(ManualREST):
        def request(self, service, method, path, **kwargs):
            if path == "/api/v1/rag/commands/stop":
                self.calls.append((service, method, path, kwargs))
                return reply({"unexpected": True})
            return super().request(service, method, path, **kwargs)

    monkeypatch.setattr(console_module, "SpaceSessionStop", Keys)
    monkeypatch.setattr(console_module, "_wait_for_spacebar", lambda _prompt: None)
    client = BrokenCommandREST()
    console_module.Sprint2Console(client).return_user("manual")
    assert "/api/v1/rag/query" not in [call[2] for call in client.calls]
