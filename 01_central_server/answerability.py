"""Small transient intent/evidence bridge; no retrieval or external inference."""
from dataclasses import dataclass
import re
from typing import Any

from shared.semantic_embeddings import knowledge_text


_QUESTION_RELATIONS = {
    "where": "location", "why": "reason", "when": "time", "who": "person",
    "which": "identity", "what": "description", "how": "method",
}
_RELATION_EVIDENCE = {
    "location": r"\b(?:located|location|address|situated|kept|stored|lives|resides|inside|on the|in the|at the)\b",
    "reason": r"\b(?:because|reason|due to|so that)\b",
    "time": r"\b(?:when|date|time|during|before|after|at \d|on \d)\b",
    "person": r"\b(?:who|person|owner|author|creator|given by|made by|taught by)\b",
    "method": r"\b(?:how|method|process|steps|by using|using|first .* then)\b",
}
_MISSING_RELATION = {
    "location": "where it is", "reason": "why", "time": "when",
    "person": "who is involved", "method": "how",
}


@dataclass(frozen=True)
class AnswerPlan:
    resolved_subject: str | None
    requested_relation: str
    subject_known: bool
    # None means the existing single expression/answerability request must
    # interpret the evidence; do not guess a fact's value type from its label.
    requested_relation_known: bool | None

    def missing_response(self, *, confirmed_missing: bool = False, unavailable: bool = False) -> str | None:
        if (not self.subject_known or self.requested_relation not in _MISSING_RELATION
                or (self.requested_relation_known is not False and not confirmed_missing
                    and not (unavailable and self.requested_relation_known is None))):
            return None
        subject = re.sub(r"^this is\s+", "", self.resolved_subject or "", flags=re.I)
        subject = re.sub(r"\bmy\b", "your", subject, flags=re.I).strip().rstrip(".?!")
        if unavailable and self.requested_relation_known is None and not confirmed_missing:
            return f"I remember {subject}, but I can't confirm its {self.requested_relation} from what I've learned."
        return f"I remember {subject}, but you haven't taught me {_MISSING_RELATION[self.requested_relation]}."


def build_answer_plan(query: str, records: list[dict[str, Any]], *, subject_referenced: bool) -> AnswerPlan:
    words = re.findall(r"\b(?:where|why|when|who|which|what|how)\b", query.casefold())
    relation = _QUESTION_RELATIONS.get(words[0], "description") if words else "description"
    if not records:
        return AnswerPlan(None, relation, False, False)
    data = records[0].get("data", {})
    subject = str(data.get("subject") or data.get("name") or "").strip() or None
    if relation in {"description", "identity"}:
        return AnswerPlan(subject, relation, bool(subject) and subject_referenced, True)
    evidence = " ".join(knowledge_text(record["type"], record["data"]) for record in records)
    if re.search(_RELATION_EVIDENCE[relation], evidence, flags=re.I):
        return AnswerPlan(subject, relation, bool(subject) and subject_referenced, True)
    # An object label alone cannot establish a location/reason/time/person/method.
    # Unstructured fact values remain subject to the existing answerability gate.
    description = " ".join(str(data.get("description") or "").split())
    # Absence of a keyword does NOT prove absence of a relation in free text.
    # Only label-only objects can be rejected without the existing expression
    # request. Canonical rendering already excludes detector-generated prose.
    user_description = bool(description and description in evidence)
    known = False if len(records) == 1 and records[0]["type"] == "object" and not user_description else None
    return AnswerPlan(subject, relation, bool(subject) and subject_referenced, known)


def without_attribution(response: str) -> str:
    """Remove only harmless speech framing, never factual predicates/adjectives."""
    return re.sub(
        r"^(?:i remember(?: you (?:told|taught) me)?|you (?:told|taught) me)(?: that)?[, :]+",
        "", response.strip(), flags=re.I,
    )
