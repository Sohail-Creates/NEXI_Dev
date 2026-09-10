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
    "stop": "Stopping.",
    "thank you": "You're welcome!",
    "thanks": "You're welcome!",
    "help": "Please ask me about something you have taught me.",
}


def _normalize(text: str) -> str:
    words = re.findall(r"[a-z0-9']+", text.casefold())
    return " ".join(words)


def classify_basic_command(text: str) -> Optional[str]:
    """Return a fixed response only when the complete normalized input matches."""
    return BASIC_COMMAND_RESPONSES.get(_normalize(text))
