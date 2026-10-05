"""Deterministic expression of approved textual memory; never performs retrieval."""

import re


def format_grounded_response(facts: list[str], *, partial: bool = False,
                             partial_notice: str = "The other requested information is not learned yet.") -> str:
    sentences = []
    for text in facts:
        text = re.sub(r"\bmy\b", "your", text, flags=re.IGNORECASE).strip()
        if text:
            sentences.append(text[0].upper() + text[1:].rstrip(".?!") + ".")
    if partial:
        sentences.append(partial_notice)
    return " ".join(sentences)
