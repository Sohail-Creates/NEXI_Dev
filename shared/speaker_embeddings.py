"""Shared validation and compatibility helpers for speaker embeddings."""

from __future__ import annotations

import math
from numbers import Real
from typing import Any, Mapping


SPEAKER_EMBEDDING_DIMENSION = 256


class SpeakerEmbeddingError(ValueError):
    """Invalid speaker vector or persisted voice-embedding shape."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


def _as_values(value: Any) -> list[Any] | None:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        return list(value)
    return None


def validate_speaker_embedding(value: Any) -> list[float]:
    """Return a finite, non-zero, exactly 256D vector as plain floats."""
    values = _as_values(value)
    if values is None or not values:
        raise SpeakerEmbeddingError("invalid_legacy_shape", "Speaker embedding must be a non-empty vector")
    if len(values) != SPEAKER_EMBEDDING_DIMENSION:
        raise SpeakerEmbeddingError(
            "invalid_embedding_dimension",
            f"Speaker embedding must have {SPEAKER_EMBEDDING_DIMENSION} values; got {len(values)}",
        )

    normalized: list[float] = []
    for item in values:
        if isinstance(item, bool) or not isinstance(item, Real):
            raise SpeakerEmbeddingError("non_numeric_embedding", "Speaker embedding values must be numeric")
        number = float(item)
        if not math.isfinite(number):
            raise SpeakerEmbeddingError("non_finite_embedding", "Speaker embedding values must be finite")
        normalized.append(number)

    norm = math.hypot(*normalized)
    if not math.isfinite(norm) or norm == 0.0:
        raise SpeakerEmbeddingError("zero_norm_embedding", "Speaker embedding must have a non-zero finite norm")
    return normalized


def normalize_voice_embeddings(record: Mapping[str, Any]) -> list[list[float]]:
    """Normalize canonical and supported legacy record shapes without mutation.

    Supported inputs are a list of 256D vectors, one flat 256D vector in the
    plural field, or one flat 256D vector in the legacy singular field.
    """
    plural = record.get("voice_embeddings")
    singular = record.get("voice_embedding")
    source = plural if plural is not None else singular

    if source is None:
        return []

    values = _as_values(source)
    if values is None:
        raise SpeakerEmbeddingError("invalid_legacy_shape", "voice embeddings must be a vector or list of vectors")
    if not values:
        if plural is not None and singular is not None:
            singular_values = _as_values(singular)
            if singular_values:
                values = singular_values
            else:
                return []
        else:
            return []

    if not values:
        return []

    # Legacy flat-vector form: the plural field contains exactly one vector.
    if all(isinstance(item, Real) and not isinstance(item, bool) for item in values):
        return [validate_speaker_embedding(values)]

    embeddings: list[list[float]] = []
    for item in values:
        try:
            embeddings.append(validate_speaker_embedding(item))
        except SpeakerEmbeddingError as exc:
            if exc.reason == "invalid_legacy_shape":
                raise SpeakerEmbeddingError("invalid_legacy_shape", "voice_embeddings must contain only vectors") from exc
            raise
    return embeddings


def cosine_similarity(query: Any, candidate: Any) -> float:
    """Compute cosine similarity, where larger values indicate a closer match."""
    return cosine_similarities(query, [candidate])[0]


def cosine_similarities(
    query: Any,
    candidates: list[Any],
    *,
    candidates_are_validated: bool = False,
) -> list[float]:
    """Validate once, then score a query against a candidate batch efficiently."""
    query_values = validate_speaker_embedding(query)
    if not candidates:
        return []
    # NumPy is already a runtime dependency of the Audio embedding/matching path;
    # batching avoids Python-level per-dimension scoring for family-scale indexes.
    import numpy as np

    query_array = np.asarray(query_values, dtype=np.float64)
    if candidates_are_validated:
        candidate_matrix = np.asarray(candidates, dtype=np.float64)
        if candidate_matrix.shape != (len(candidates), SPEAKER_EMBEDDING_DIMENSION):
            raise SpeakerEmbeddingError("invalid_embedding_dimension", "Candidate matrix must contain 256D vectors")
        if not np.isfinite(candidate_matrix).all() or np.any(np.linalg.norm(candidate_matrix, axis=1) == 0.0):
            raise SpeakerEmbeddingError("invalid_candidate_embedding", "Candidate index contains an invalid vector")
    else:
        candidate_values = [validate_speaker_embedding(candidate) for candidate in candidates]
        candidate_matrix = np.asarray(candidate_values, dtype=np.float64)
    scores = candidate_matrix @ query_array / (
        np.linalg.norm(candidate_matrix, axis=1) * np.linalg.norm(query_array)
    )
    return np.clip(scores, -1.0, 1.0).astype(float).tolist()
