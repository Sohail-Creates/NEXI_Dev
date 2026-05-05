"""
Lightweight file-based preprocess cache.

Stores recent preprocessing results (processed audio numpy arrays and sample rates)
keyed by absolute file path and file mtime. Thread-safe with LRU eviction.

This is intentionally small and conservative to avoid memory bloat.
"""
from collections import OrderedDict
import threading
from pathlib import Path
from typing import Optional, Tuple
import os

import numpy as np

class FilePreprocessCache:
    """A tiny LRU cache for file preprocessing results.

    Stores mapping: abs_path -> (mtime, (processed_data, sample_rate))
    """
    def __init__(self, max_items: int = 32):
        self.max_items = max_items
        self._lock = threading.RLock()
        self._data = OrderedDict()

    def _make_key(self, file_path: str) -> str:
        return str(Path(file_path).resolve())

    def get(self, file_path: str) -> Optional[Tuple[np.ndarray, int]]:
        """Return cached (processed_data, sample_rate) or None if not present or stale."""
        key = self._make_key(file_path)
        try:
            mtime = os.path.getmtime(key)
        except Exception:
            return None

        with self._lock:
            entry = self._data.get(key)
            if not entry:
                return None
            entry_mtime, value = entry
            if entry_mtime != mtime:
                # Stale cache entry
                del self._data[key]
                return None
            # Move to end as recently used
            self._data.move_to_end(key)
            return value

    def set(self, file_path: str, processed: Tuple[np.ndarray, int]):
        """Cache the processed result for file_path."""
        key = self._make_key(file_path)
        try:
            mtime = os.path.getmtime(key)
        except Exception:
            # If file missing, don't cache
            return

        with self._lock:
            self._data[key] = (mtime, processed)
            self._data.move_to_end(key)
            # Evict oldest if over capacity
            while len(self._data) > self.max_items:
                try:
                    self._data.popitem(last=False)
                except Exception:
                    break


# Module-level default cache
_default_cache: Optional[FilePreprocessCache] = None

def get_default_cache(max_items: int = 32) -> FilePreprocessCache:
    global _default_cache
    if _default_cache is None:
        _default_cache = FilePreprocessCache(max_items=max_items)
    return _default_cache
