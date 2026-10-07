"""Deterministic basic commands that bypass retrieval and generation."""

from __future__ import annotations

import re
from typing import Optional


# PENDING PRODUCT SIGN-OFF: this starter mapping is intentionally small and is
# the sole source of truth until Product supplies the approved command list.
BASIC_COMMAND_RESPONSES = {
    "hello": "Hello!",
    "hi": "Hello!",
    "good morning": "Good morning!",
    "good afternoon": "Good afternoon!",
    "good evening": "Good evening!",
    "goodbye": "Goodbye!",
    "bye": "Goodbye!",
    "see you": "Goodbye!",
    "that's all": "Goodbye!",
    "stop": "Stopping.",
    "thank you": "You're welcome!",
    "thanks": "You're welcome!",
    "okay": "Okay!",
    "ok": "Okay!",
    "cool": "Cool!",
    "help": "Please ask me about something you have taught me.",
}

_FAREWELL_PATTERN = "(?:" + "|".join(
    re.escape(phrase) for phrase, response in BASIC_COMMAND_RESPONSES.items()
    if response in {BASIC_COMMAND_RESPONSES["goodbye"], BASIC_COMMAND_RESPONSES["stop"]}
) + ")"


def _normalize(text: str) -> str:
    words = re.findall(r"[a-z0-9']+", text.casefold())
    normalized = re.sub(r"\bgood bye\b", "goodbye", " ".join(words))
    # Only complete farewell repetitions qualify, not sentences mentioning one.
    acknowledgement = r"(?:okay|ok|cool|thanks|thank you)"
    if re.fullmatch(rf"(?:{acknowledgement} )?{_FAREWELL_PATTERN}(?: {_FAREWELL_PATTERN})*", normalized):
        normalized = re.sub(rf"^{acknowledgement} ", "", normalized)
        return re.match(_FAREWELL_PATTERN, normalized).group(0)
    return normalized


def is_stop_command(text: str, farewell_phrases: frozenset[str]) -> bool:
    """Only complete configured basic commands terminate a conversation."""
    return classify_basic_command(text) is not None and _normalize(text) in farewell_phrases


def classify_basic_command(text: str) -> Optional[str]:
    """Return a fixed response only when the complete normalized input matches."""
    return BASIC_COMMAND_RESPONSES.get(_normalize(text))
