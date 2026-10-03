"""Regression for live short speech discarded by capture's speaker-duration gate."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.mark.parametrize("speech_frames", [4, 27, 29, 0, 2])
def test_short_speech_capture_preserves_vad_and_rejects_blips(monkeypatch, tmp_path, speech_frames):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "03_audio_service"))
    from audio_service.services import vad_recorder as module

    calls = []

    def is_speech(_samples, **_kwargs):
        calls.append(1)
        return len(calls) <= speech_frames, {}

    stream = SimpleNamespace(read=lambda *_args, **_kwargs: np.full(480, 2000, np.int16).tobytes(),
                             close=lambda: None)
    device = SimpleNamespace(open=lambda **_kwargs: stream, terminate=lambda: None)
    monkeypatch.setattr(module.pyaudio, "PyAudio", lambda: device)
    monkeypatch.setattr(module, "resolve_pyaudio_input", lambda _device: 0)
    monkeypatch.setattr(module, "VoiceActivityDetector", lambda **_kwargs: SimpleNamespace(is_speech=is_speech))
    recorder = module.VADRecorder(max_duration_seconds=2)
    path = tmp_path / "short-command.wav"
    try:
        result = recorder.record_until_silence(str(path))
        accepted = speech_frames >= recorder.start_speech_frames
        assert result["success"] is True
        assert result["speech_active"] is accepted
        assert result["end_reason"] == ("speech_end" if accepted else "no_speech")
        assert path.exists() is accepted
        if accepted:
            assert result["speech_duration"] == pytest.approx(speech_frames * 0.03)
            assert result["duration"] == pytest.approx(speech_frames * 0.03 + 0.51)
    finally:
        path.unlink(missing_ok=True)
