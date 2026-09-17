"""Real audio-input discovery and deterministic default/override selection."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Sequence

import sounddevice as sd


@dataclass(frozen=True)
class AudioInputDevice:
    index: int
    name: str
    hostapi: str
    channels: int
    is_default: bool = False


def enumerate_input_devices() -> list[AudioInputDevice]:
    devices = sd.query_devices()
    default_input = int(sd.default.device[0])
    hostapis = sd.query_hostapis()
    return [
        AudioInputDevice(
            index=index,
            name=str(device["name"]),
            hostapi=str(hostapis[int(device["hostapi"])]["name"]),
            channels=int(device["max_input_channels"]),
            is_default=index == default_input,
        )
        for index, device in enumerate(devices)
        if int(device["max_input_channels"]) > 0
    ]


def _resolve(selector: str | int | None, devices: Sequence[AudioInputDevice]) -> AudioInputDevice:
    if not devices:
        raise RuntimeError("No audio input devices are available")
    raw = selector if selector is not None else os.getenv("AUDIO_INPUT_DEVICE", "")
    value = str(raw).strip()
    if not value:
        return next((item for item in devices if item.is_default), devices[0])

    try:
        requested_index = int(value)
    except ValueError:
        requested_index = None
    if requested_index is not None:
        match = next((item for item in devices if item.index == requested_index), None)
        if match is None:
            raise RuntimeError(f"Configured audio input index {requested_index} is unavailable")
        return match

    normalized = value.casefold()
    matches = [item for item in devices if normalized in item.name.casefold()]
    if len(matches) != 1:
        names = ", ".join(item.name for item in devices)
        reason = "ambiguous" if matches else "not found"
        raise RuntimeError(
            f"Configured audio input name {value!r} is {reason}; available inputs: {names}"
        )
    return matches[0]


def resolve_sounddevice_input(selector: str | int | None = None) -> AudioInputDevice:
    return _resolve(selector, enumerate_input_devices())


def resolve_pyaudio_input(pyaudio_instance: Any, selector: str | int | None = None) -> int:
    """Resolve against PyAudio's own index space rather than assuming SD parity."""
    devices = []
    default_index = int(pyaudio_instance.get_default_input_device_info()["index"])
    for index in range(pyaudio_instance.get_device_count()):
        info = pyaudio_instance.get_device_info_by_index(index)
        if int(info.get("maxInputChannels", 0)) > 0:
            devices.append(
                AudioInputDevice(
                    index=index,
                    name=str(info.get("name", f"Input {index}")),
                    hostapi=str(info.get("hostApi", "unknown")),
                    channels=int(info["maxInputChannels"]),
                    is_default=index == default_index,
                )
            )
    return _resolve(selector, devices).index
