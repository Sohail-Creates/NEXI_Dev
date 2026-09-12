"""Shared current/previous secret handling for zero-downtime rotation."""

from __future__ import annotations

from dataclasses import dataclass
import os
import secrets


@dataclass(frozen=True)
class SecretPair:
    """A write-current/read-current-or-previous credential pair."""

    current: str
    previous: str | None = None

    @classmethod
    def from_env(
        cls,
        current_name: str,
        previous_name: str,
        *,
        required: bool = True,
    ) -> "SecretPair":
        current = os.getenv(current_name, "").strip()
        previous = os.getenv(previous_name, "").strip() or None
        if required and not current:
            raise RuntimeError(f"{current_name} is required")
        if previous == current:
            previous = None
        return cls(current=current, previous=previous)

    @property
    def active(self) -> tuple[str, ...]:
        return tuple(value for value in (self.current, self.previous) if value)

    def accepts(self, supplied: str) -> bool:
        return bool(supplied) and any(
            secrets.compare_digest(supplied, candidate) for candidate in self.active
        )
