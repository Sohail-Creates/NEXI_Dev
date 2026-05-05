from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import os
import platform
import shutil
import time


@dataclass(frozen=True)
class ResourceSnapshot:
    timestamp: float
    cpu_load: Optional[float]
    disk_free_bytes: Optional[int]
    disk_total_bytes: Optional[int]


def _safe_loadavg() -> Optional[float]:
    if platform.system().lower().startswith("win"):
        return None
    try:
        return os.getloadavg()[0]
    except (AttributeError, OSError):
        return None


def _disk_usage(path: str) -> tuple[Optional[int], Optional[int]]:
    try:
        usage = shutil.disk_usage(path)
        return usage.free, usage.total
    except OSError:
        return None, None


def collect_snapshot(path: str = ".") -> ResourceSnapshot:
    free, total = _disk_usage(path)
    return ResourceSnapshot(
        timestamp=time.time(),
        cpu_load=_safe_loadavg(),
        disk_free_bytes=free,
        disk_total_bytes=total,
    )