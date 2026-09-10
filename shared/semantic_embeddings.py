"""Shared semantic text embedding configuration and implementation."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Mapping


SEMANTIC_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
SEMANTIC_EMBEDDING_DIMENSION = 384


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    # Models are provisioned during deployment; runtime inference must not depend
    # on network availability or silently switch artifacts.
    model = SentenceTransformer(SEMANTIC_EMBEDDING_MODEL, local_files_only=True)
    dimension = model.get_embedding_dimension()
    if dimension != SEMANTIC_EMBEDDING_DIMENSION:
        raise RuntimeError(
            f"Embedding model dimension {dimension} does not match configured "
            f"dimension {SEMANTIC_EMBEDDING_DIMENSION}"
        )
    return model


def embed_text(text: str) -> list[float]:
    """Return a normalized, real semantic embedding for non-empty text."""
    normalized = " ".join(text.split())
    if not normalized:
        raise ValueError("Cannot embed empty text")
    vector = _model().encode(normalized, normalize_embeddings=True)
    result = vector.tolist()
    if len(result) != SEMANTIC_EMBEDDING_DIMENSION:
        raise RuntimeError(f"Unexpected embedding dimension: {len(result)}")
    return result


def knowledge_text(item_type: str, data: Mapping[str, Any]) -> str:
    """Render typed TeachMe knowledge into the canonical text used for embedding."""
    if item_type == "fact":
        return " ".join(str(data.get(key, "")) for key in ("subject", "predicate", "object")).strip()
    if item_type == "object":
        details = [data.get("name", ""), data.get("category", ""), data.get("description", "")]
        attributes = data.get("attributes") or {}
        if isinstance(attributes, Mapping):
            details.extend(f"{key} {value}" for key, value in sorted(attributes.items()))
        return " ".join(str(value) for value in details if value).strip()
    raise ValueError(f"Unsupported knowledge type: {item_type}")
