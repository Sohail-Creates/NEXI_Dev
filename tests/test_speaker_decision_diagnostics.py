"""Decision boundary and safe diagnostic contracts use the production matcher."""
import sys
import threading
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03_audio_service"))


@pytest.mark.parametrize("score,second,expected", [
    (0.7554, 0.5, "unknown"),
    (0.78, 0.73, "ambiguous"),
    (0.82, 0.6, "matched"),
    (0.759, 0.5, "matched"),
    (0.78, None, "matched"),
    (0.70, None, "unknown"),
    (0.8, 0.8, "ambiguous"),
])
def test_production_boundaries_and_candidate_diagnostics(monkeypatch, score, second, expected):
    from audio_service.services import speaker_service as module
    service = module.SpeakerService.__new__(module.SpeakerService)
    service._index_lock = threading.RLock()
    query = np.zeros(256)
    query[0] = 1
    def candidate(value):
        result = np.zeros(256)
        result[:2] = [value, np.sqrt(1-value*value)]
        return result
    service.speaker_embeddings = {"first": candidate(score)}
    if second is not None:
        service.speaker_embeddings["second"] = candidate(second)
    monkeypatch.setitem(module.SPEAKER_CONFIG, "verification_threshold", 0.759)
    monkeypatch.setitem(module.SPEAKER_CONFIG, "min_margin", 0.1084)
    result = service.identify_embedding(query)
    assert result["decision"] == expected
    assert result["top1_score"] == pytest.approx(score)
    assert result["candidate_count"] == (1 if second is None else 2)
    assert result["top2_user"] == (None if second is None else "second")
    assert result["user_id"] == ("first" if expected == "matched" else None)
    if second is None:
        assert result["margin"] is None


def test_console_reports_ambiguity_without_applying_matching_policy(capsys):
    import test as harness
    client = object.__new__(harness.LiveRESTClient)
    client.output_mode = "narrative"
    client._report_narrative("audio", "POST", "/api/v1/verify-speaker",
        harness.LiveResponse(200, {}, {
            "decision": "ambiguous", "is_verified": False, "confidence": 0.7812,
            "threshold": 0.759, "top1_user": "a", "top1_score": 0.7812,
            "top2_user": "b", "top2_score": 0.7350, "margin": 0.0462,
            "required_margin": 0.1084, "candidate_count": 2,
        }, b""))
    output = capsys.readouterr().out
    assert "Speaker decision: AMBIGUOUS" in output
    assert "Top-2: b 0.7350" in output
    assert "required margin: 0.1084" in output
    assert "Speaker not recognized" not in output


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["matched", "unknown", "ambiguous"])
async def test_central_voice_session_respects_audio_decision(monkeypatch, decision):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01_central_server"))
    from routes import user_routes
    from shared.clients.models import ServiceCallResult
    from fastapi import HTTPException
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    matched = decision == "matched"
    data = {"decision": decision, "verified": matched,
            "user_id": "a" if matched else "unknown",
            "access_token": "test-session" if matched else None}
    monkeypatch.setattr(user_routes, "_audio_verification_client",
        SimpleNamespace(verify_speaker=AsyncMock(return_value=ServiceCallResult(True, data))))
    upload = SimpleNamespace(filename="voice.wav", read=AsyncMock(return_value=b"fixture"))
    if matched:
        assert (await user_routes.create_voice_session(upload))["user_id"] == "a"
    else:
        with pytest.raises(HTTPException) as error:
            await user_routes.create_voice_session(upload)
        assert error.value.status_code == 401
