import numpy as np
import pytest
import sys
from pathlib import Path
import asyncio
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03_audio_service"))

from shared.speaker_embeddings import (
    SpeakerEmbeddingError,
    cosine_similarity,
    normalize_voice_embeddings,
    validate_speaker_embedding,
)


def vector(index=0):
    result = np.zeros(256, dtype=float)
    result[index] = 1.0
    return result.tolist()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["process_voice_file", "verify_speaker", "transcribe_audio"])
@pytest.mark.parametrize("failure", [OSError("upload read failed"), asyncio.CancelledError()])
async def test_audio_upload_read_failure_closes_descriptor_and_removes_file(monkeypatch, tmp_path, operation, failure):
    from audio_service.routes import advanced_routes
    from fastapi import HTTPException

    created = []
    real_mkstemp = tempfile.mkstemp

    def create(*args, **kwargs):
        descriptor, path = real_mkstemp(suffix=".wav", dir=tmp_path)
        created.append((descriptor, path))
        return descriptor, path

    monkeypatch.setattr(tempfile, "mkstemp", create)
    upload = SimpleNamespace(filename="voice.wav", read=AsyncMock(side_effect=failure))
    try:
        with pytest.raises((HTTPException, asyncio.CancelledError)):
            await getattr(advanced_routes, operation)(upload)
        descriptor, path = created[0]
        with pytest.raises(OSError):
            os.fstat(descriptor)
        assert not Path(path).exists()
    finally:
        # Keep the deliberately failing pre-fix reproduction disposable too.
        for descriptor, path in created:
            try:
                os.close(descriptor)
            except OSError:
                pass
            Path(path).unlink(missing_ok=True)


def test_canonical_and_legacy_embedding_shapes_normalize():
    expected = vector()
    assert normalize_voice_embeddings({"voice_embeddings": [expected, expected]}) == [expected, expected]
    assert normalize_voice_embeddings({"voice_embeddings": expected}) == [expected]
    assert normalize_voice_embeddings({"voice_embedding": expected}) == [expected]


@pytest.mark.parametrize("bad", [[], [1.0] * 255, [float("nan")] + [0.0] * 255, [0.0] * 256])
def test_invalid_embedding_rejected(bad):
    with pytest.raises(SpeakerEmbeddingError):
        validate_speaker_embedding(bad)


def test_candidate_build_centroids_normalized_and_tracks_ids():
    from audio_service.services.speaker_service import SpeakerService

    service = SpeakerService.__new__(SpeakerService)
    candidates, counts = service.build_candidate_index([
        {"user_id": "a", "voice_embeddings": [vector(0), vector(0)]},
        {"user_id": "b", "voice_embedding": vector(1)},
        {"user_id": "bad", "voice_embeddings": [1.0, 2.0]},
    ])
    assert set(candidates) == {"a", "b"}
    assert np.linalg.norm(candidates["a"]) == pytest.approx(1.0)
    assert counts["users_seen"] == 3
    assert counts["users_loaded"] == 2
    assert counts["users_skipped"] == 1


def test_identification_global_best_unknown_ambiguous_and_tie(monkeypatch):
    from audio_service.services import speaker_service as module

    service = module.SpeakerService.__new__(module.SpeakerService)
    service._index_lock = __import__("threading").RLock()
    service.speaker_embeddings = {
        "older": np.asarray(vector(0), dtype=np.float32),
        "newer": np.asarray(vector(1), dtype=np.float32),
    }
    monkeypatch.setitem(module.SPEAKER_CONFIG, "verification_threshold", 0.65)
    monkeypatch.setitem(module.SPEAKER_CONFIG, "min_margin", 0.0)
    assert service.identify_embedding(vector(1))["user_id"] == "newer"
    assert service.identify_embedding(vector(2))["decision"] == "unknown"

    service.speaker_embeddings["tie"] = np.asarray(vector(1), dtype=np.float32)
    result = service.identify_embedding(vector(1))
    assert result["decision"] == "ambiguous"
    assert result["user_id"] is None


def test_index_replacement_is_complete_and_deletion_safe(monkeypatch, tmp_path):
    from audio_service.services import speaker_service as module

    service = module.SpeakerService.__new__(module.SpeakerService)
    service._index_lock = __import__("threading").RLock()
    service.speaker_embeddings = {"a": np.asarray(vector(0)), "b": np.asarray(vector(1)), "c": np.asarray(vector(2))}
    service.embeddings_file = tmp_path / "speakers.json"
    monkeypatch.setattr(module, "_write_json_store", lambda *_: None)
    service.replace_speaker_index({"a": service.speaker_embeddings["a"], "c": service.speaker_embeddings["c"]})
    assert set(service.get_speaker_embeddings_snapshot()) == {"a", "c"}


def test_failed_central_sync_preserves_live_candidate_index(monkeypatch):
    import asyncio
    import requests
    from audio_service.routes import advanced_routes

    class ExistingIndex:
        speaker_embeddings = {"existing": np.asarray(vector(7), dtype=np.float32)}

        def build_candidate_index(self, users):
            raise AssertionError("candidate build must not run after a failed Central fetch")

        def replace_speaker_index(self, candidates):
            raise AssertionError("live index must not be replaced after a failed Central fetch")

    service = ExistingIndex()
    monkeypatch.setattr(advanced_routes, "get_speaker_service", lambda: service)
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: (_ for _ in ()).throw(requests.ConnectionError("offline")))

    result = asyncio.run(advanced_routes.sync_speakers_from_central())

    assert result["success"] is False
    assert set(service.speaker_embeddings) == {"existing"}


def test_central_writer_canonicalizes_singular_and_flat_shapes():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01_central_server"))
    from routes.user_routes import _canonicalize_voice_fields

    singular_record = {"voice_embedding": vector(3)}
    assert _canonicalize_voice_fields(singular_record) == [vector(3)]
    assert "voice_embedding" not in singular_record
    flat_record = {"voice_embeddings": vector(4)}
    assert _canonicalize_voice_fields(flat_record) == [vector(4)]


def test_cosine_similarity_is_higher_for_matching_vector():
    assert cosine_similarity(vector(0), vector(0)) == pytest.approx(1.0)
    assert cosine_similarity(vector(0), vector(1)) == pytest.approx(0.0)
