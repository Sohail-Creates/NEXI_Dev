"""Reuse successful photo checks for final enrollment without trusting client vectors."""

from collections import OrderedDict
import hashlib
from pathlib import Path
import threading
import time
import logging

from app.clients.vision_client import VisionClient
from config.settings import settings
from fastapi import HTTPException

logger = logging.getLogger(__name__)


def validation_result(*, valid: bool, confidence=None, reason=None) -> dict:
    """Public metadata only; embeddings remain inside the enrollment service."""
    return {"valid": valid, "face_detected": True if valid else (False if reason == "NO_FACE_DETECTED" else None),
            "confidence": confidence, "embedding_generated": valid, "reason": reason}


class PhotoValidation:
    def __init__(self, client: VisionClient):
        self.client = client
        self._cache: OrderedDict[tuple[str, str], tuple[float, dict]] = OrderedDict()
        self._lock = threading.Lock()

    async def get_face_embedding(self, path: str) -> dict:
        # Content identity ties the early check to the exact final uploaded photo.
        digest = (settings.photo_validation_version, hashlib.sha256(Path(path).read_bytes()).hexdigest())
        started = time.perf_counter()
        now = time.monotonic()
        with self._lock:
            expired = [key for key, (stamp, _) in self._cache.items()
                       if now - stamp >= settings.photo_validation_cache_ttl_seconds]
            for key in expired:
                del self._cache[key]
            cached = self._cache.get(digest)
            if cached is not None:
                self._cache.move_to_end(digest)
                logger.info("photo_validation", extra={"cache_hit": True, "result": "valid", "reason": None,
                            "latency_ms": (time.perf_counter() - started) * 1000})
                return {**cached[1], "embedding": list(cached[1]["embedding"])}
        try:
            face = await self.client.get_face_embedding(path)
        except HTTPException as exc:
            reason = exc.detail.get("reason") if isinstance(exc.detail, dict) else "INFERENCE_ERROR"
            logger.info("photo_validation", extra={"cache_hit": False, "result": "failed", "reason": reason,
                        "latency_ms": (time.perf_counter() - started) * 1000})
            raise
        logger.info("photo_validation", extra={"cache_hit": False, "result": "valid", "reason": None,
                    "latency_ms": (time.perf_counter() - started) * 1000})
        with self._lock:
            if settings.photo_validation_cache_max_items > 0 and settings.photo_validation_cache_ttl_seconds > 0:
                self._cache[digest] = (time.monotonic(), {**face, "embedding": list(face["embedding"])})
                while len(self._cache) > settings.photo_validation_cache_max_items:
                    self._cache.popitem(last=False)
        return face

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
