"""Physical camera discovery and deterministic device selection."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import platform
from typing import Callable, Sequence

import cv2


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CameraDevice:
    index: int
    name: str
    backend: int


def _default_backend() -> int:
    if platform.system() == "Windows":
        return cv2.CAP_DSHOW
    if platform.system() == "Darwin":
        return cv2.CAP_AVFOUNDATION
    return cv2.CAP_V4L2 if hasattr(cv2, "CAP_V4L2") else cv2.CAP_ANY


def enumerate_camera_devices(
    max_index: int = 10,
    capture_factory: Callable = cv2.VideoCapture,
) -> list[CameraDevice]:
    """Return cameras OpenCV can actually open, in default-device order.

    If ``cv2-enumerate-cameras`` is installed, its platform-native friendly
    names and backend-specific indices are used.  The OpenCV probe remains a
    dependency-free fallback and labels devices deterministically by index.
    """
    try:
        from cv2_enumerate_cameras import enumerate_cameras

        devices = [
            CameraDevice(int(item.index), str(item.name), int(item.backend))
            for item in enumerate_cameras(_default_backend())
        ]
        if devices:
            return devices
    except ImportError:
        logger.debug("cv2-enumerate-cameras is unavailable; using OpenCV probe")
    except Exception as exc:
        logger.warning("Native camera enumeration failed; using OpenCV probe: %s", exc)

    backend = _default_backend()
    devices: list[CameraDevice] = []
    for index in range(max_index):
        capture = capture_factory(index, backend)
        try:
            if capture.isOpened():
                try:
                    backend_name = capture.getBackendName()
                except Exception:
                    backend_name = cv2.videoio_registry.getBackendName(backend)
                devices.append(
                    CameraDevice(index, f"Camera {index} ({backend_name})", backend)
                )
        finally:
            capture.release()
    return devices


def resolve_camera_device(
    selector: str | int | None = None,
    devices: Sequence[CameraDevice] | None = None,
) -> CameraDevice:
    """Resolve an optional index/name; otherwise select the OS default camera."""
    raw = selector if selector is not None else os.getenv("VISION_CAMERA_DEVICE", "")
    value = str(raw).strip()
    backend = _default_backend()

    # Index 0 is OpenCV's OS-default capture device. Avoid enumerating/opening
    # every camera on every request when no override was requested.
    if devices is None and not value:
        return CameraDevice(0, "System default camera", backend)

    available = list(devices if devices is not None else enumerate_camera_devices())
    if not available:
        raise RuntimeError("No camera devices are available")
    if not value:
        return next((item for item in available if item.index == 0), available[0])

    try:
        requested_index = int(value)
    except ValueError:
        requested_index = None
    if requested_index is not None:
        if devices is None:
            return CameraDevice(
                requested_index,
                f"Configured camera index {requested_index}",
                backend,
            )
        match = next((item for item in available if item.index == requested_index), None)
        if match is None:
            raise RuntimeError(f"Configured camera index {requested_index} is unavailable")
        return match

    normalized = value.casefold()
    matches = [item for item in available if normalized in item.name.casefold()]
    if len(matches) != 1:
        names = ", ".join(item.name for item in available)
        reason = "ambiguous" if matches else "not found"
        raise RuntimeError(
            f"Configured camera name {value!r} is {reason}; available cameras: {names}"
        )
    return matches[0]


def open_camera(device: CameraDevice, capture_factory: Callable = cv2.VideoCapture):
    """Open a previously resolved device using its enumerated backend."""
    return capture_factory(device.index, device.backend)
