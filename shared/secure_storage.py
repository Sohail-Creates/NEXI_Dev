"""Fernet encryption used by every local biometric store."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from shared.credential_rotation import SecretPair


ENCRYPTED_PREFIX = b"nexi-fernet-v1:"


def biometric_keys() -> SecretPair:
    """Return the shared write-current/read-current-or-previous Fernet keys."""
    current = os.getenv("NEXI_FERNET_KEY", "").strip()
    previous = os.getenv("NEXI_FERNET_PREVIOUS_KEY", "").strip() or None
    root = Path(__file__).resolve().parents[1]
    if not current:
        configured_file = os.getenv("NEXI_FERNET_KEY_FILE") or os.getenv("ENCRYPTION_KEY_FILE")
        if not configured_file:
            raise RuntimeError("NEXI_FERNET_KEY or NEXI_FERNET_KEY_FILE is required for biometric storage")
        path = Path(configured_file)
        if not path.is_absolute():
            path = root / path
        current = path.read_text(encoding="ascii").strip()
    previous_file = os.getenv("NEXI_FERNET_PREVIOUS_KEY_FILE")
    if not previous and previous_file:
        path = Path(previous_file)
        if not path.is_absolute():
            path = root / path
        previous = path.read_text(encoding="ascii").strip()
    return SecretPair(current, previous)


class RotatingFernet:
    def __init__(self, keys: SecretPair | None = None) -> None:
        self.keys = keys or biometric_keys()
        if not self.keys.current:
            raise RuntimeError("A current Fernet key is required for biometric storage")
        # Validate every configured value eagerly and fail closed.
        self._ciphers = tuple(Fernet(value.encode("ascii")) for value in self.keys.active)

    def encrypt(self, plaintext: bytes) -> bytes:
        return ENCRYPTED_PREFIX + self._ciphers[0].encrypt(plaintext)

    def decrypt(self, ciphertext: bytes) -> bytes:
        token = ciphertext[len(ENCRYPTED_PREFIX):] if ciphertext.startswith(ENCRYPTED_PREFIX) else ciphertext
        last_error: InvalidToken | None = None
        for cipher in self._ciphers:
            try:
                return cipher.decrypt(token)
            except InvalidToken as exc:
                last_error = exc
        raise last_error or InvalidToken()

    def is_current(self, ciphertext: bytes) -> bool:
        token = ciphertext[len(ENCRYPTED_PREFIX):] if ciphertext.startswith(ENCRYPTED_PREFIX) else ciphertext
        try:
            self._ciphers[0].decrypt(token)
            return True
        except InvalidToken:
            return False

    def rotate(self, ciphertext: bytes) -> bytes:
        """Rewrap previous-key data with current before closing the window."""
        return self.encrypt(self.decrypt(ciphertext))

    def encrypt_text(self, value: str) -> str:
        return self.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt_text(self, value: str) -> str:
        return self.decrypt(value.encode("ascii")).decode("utf-8")


def encrypt_json(value: Any) -> bytes:
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    return RotatingFernet().encrypt(raw)


def decrypt_json(value: bytes | str) -> Any:
    raw = value.encode("ascii") if isinstance(value, str) else value
    return json.loads(RotatingFernet().decrypt(raw).decode("utf-8"))


def require_encryption_enabled() -> None:
    if os.getenv("ENABLE_ENCRYPTION", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        raise RuntimeError("Biometric encryption is mandatory; ENABLE_ENCRYPTION cannot be disabled")
