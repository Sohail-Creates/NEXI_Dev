"""Central's single restricted-RAG policy boundary."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from difflib import SequenceMatcher
import json
import logging
import os
import re
import threading
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from shared.jwt_manager import require_session_claims
from langdetect import DetectorFactory, LangDetectException, detect_langs
from pydantic import BaseModel, ConfigDict, Field

from basic_commands import classify_basic_command
from conversations_persistence import add_conversation
from shared.clients.llm_client import LLMServiceClient
from shared.semantic_embeddings import knowledge_text
from teachme_connector import get_teachme_connector
from shared.security import TRUSTED_USER_HEADER, internal_service_headers, require_internal_service
from config.ssl_config import client_verify
import httpx


TEACH_ME_RESPONSE = "I don't know this yet. Please teach me."
RAG_MATCH_THRESHOLD = float(os.getenv("RAG_MATCH_THRESHOLD", "0.55"))
RAG_CANDIDATE_THRESHOLD = float(os.getenv("RAG_CANDIDATE_THRESHOLD", "0.45"))
RAG_BAND_QUERY_COVERAGE_RATIO = float(os.getenv("RAG_BAND_QUERY_COVERAGE_RATIO", "1.0"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
NOT_ANSWERABLE_MARKER = "[[NEXI_NOT_ANSWERABLE]]"
RAG_FILLER_PHRASES = tuple(
    phrase.strip().casefold()
    for phrase in os.getenv(
        "RAG_FILLER_PHRASES",
        "do you know anything about;do you know;can you tell me;could you tell me;"
        "would you tell me;anything about;please tell me;tell me about;basically",
    ).split(";")
    if phrase.strip()
)
try:
    RAG_QUERY_REWRITES = json.loads(os.getenv(
        "RAG_QUERY_REWRITES",
        '{"where is my home": "where is my hometown"}',
    ))
except json.JSONDecodeError as exc:
    raise RuntimeError("RAG_QUERY_REWRITES must be a JSON object of phrase replacements") from exc
if not isinstance(RAG_QUERY_REWRITES, dict) or not all(
    isinstance(source, str) and isinstance(target, str)
    for source, target in RAG_QUERY_REWRITES.items()
):
    raise RuntimeError("RAG_QUERY_REWRITES must be a JSON object of phrase replacements")
RAG_LANGUAGE_MIN_TOKENS = int(os.getenv("RAG_LANGUAGE_MIN_TOKENS", "5"))
RAG_LANGUAGE_CONFIDENCE_THRESHOLD = float(os.getenv("RAG_LANGUAGE_CONFIDENCE_THRESHOLD", "0.90"))
try:
    _farewell_phrases = json.loads(os.getenv(
        "RAG_FAREWELL_PHRASES",
        '["bye", "goodbye", "see you", "that\'s all", "stop"]',
    ))
except json.JSONDecodeError as exc:
    raise RuntimeError("RAG_FAREWELL_PHRASES must be a JSON list of strings") from exc
if not isinstance(_farewell_phrases, list) or not all(
    isinstance(phrase, str) for phrase in _farewell_phrases
):
    raise RuntimeError("RAG_FAREWELL_PHRASES must be a JSON list of strings")
RAG_FAREWELL_PHRASES = frozenset(phrase.casefold().strip() for phrase in _farewell_phrases)
DetectorFactory.seed = 0
logger = logging.getLogger(__name__)


class NonEnglishQueryError(ValueError):
    pass


class RAGProviderError(RuntimeError):
    pass


class RAGQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, min_length=1, max_length=128)


class NoSpeechDetected(ValueError):
    pass


@dataclass
class RAGSession:
    user_id: str | None
    verified: bool
    last_entity: str | None
    last_activity: float
    turn_count: int = 0


RAG_SESSION_IDLE_SECONDS = float(os.getenv("RAG_SESSION_IDLE_SECONDS", "300"))
_rag_sessions: dict[str, RAGSession] = {}
_rag_sessions_lock = threading.RLock()
_expired_rag_sessions: list[tuple[str, str]] = []
_AUDIO_SERVICE_URL = os.getenv("AUDIO_SERVICE_URL", "https://localhost:8002").rstrip("/")


def evict_idle_rag_sessions(now: float | None = None) -> int:
    """Remove expired in-memory RAG sessions; no device lease is held here."""
    now = time.monotonic() if now is None else now
    with _rag_sessions_lock:
        expired = [
            session_id for session_id, state in _rag_sessions.items()
            if now - state.last_activity >= RAG_SESSION_IDLE_SECONDS
        ]
        for session_id in expired:
            state = _rag_sessions.pop(session_id)
            if state.user_id is not None:
                _expired_rag_sessions.append((session_id, state.user_id))
    return len(expired)


def _resolve_session_query(
    session_id: str, user_id: str, query: str, *, allow_create: bool = True
) -> tuple[str, RAGSession]:
    now = time.monotonic()
    evict_idle_rag_sessions(now)
    with _rag_sessions_lock:
        state = _rag_sessions.get(session_id)
        if state is None:
            if not allow_create:
                raise HTTPException(
                    status_code=410,
                    detail={"code": "SESSION_EXPIRED", "message": "Manual session expired; start a new session"},
                )
            state = RAGSession(user_id=user_id, verified=True, last_entity=None, last_activity=now)
            _rag_sessions[session_id] = state
        elif state.user_id != user_id or not state.verified:
            raise HTTPException(status_code=403, detail={"code": "SESSION_USER_MISMATCH", "message": "Session does not belong to this verified user"})
        state.last_activity = now
        state.turn_count += 1
        resolved = query
        if state.last_entity:
            resolved = re.sub(
                r"\b(it|that|this|they|them|those|these)\b",
                lambda match: state.last_entity,
                query,
                flags=re.IGNORECASE,
            )
        return resolved, state


def create_rag_session(user_id: str) -> tuple[str, RAGSession]:
    """Create an identified session from a previously validated bearer subject."""
    now = time.monotonic()
    session_id = uuid.uuid4().hex
    state = RAGSession(user_id=user_id, verified=True, last_entity=None, last_activity=now)
    with _rag_sessions_lock:
        _rag_sessions[session_id] = state
    return session_id, state


def normalize_retrieval_query(query: str) -> str:
    """Remove configured conversational filler while retaining a semantic phrase."""
    normalized = query.strip()
    for source, target in sorted(RAG_QUERY_REWRITES.items(), key=lambda item: len(item[0]), reverse=True):
        normalized = re.sub(
            rf"(?<!\w){re.escape(source)}(?!\w)", target, normalized,
            flags=re.IGNORECASE,
        )
    for phrase in sorted(RAG_FILLER_PHRASES, key=len, reverse=True):
        normalized = re.sub(
            rf"(?<!\w){re.escape(phrase)}(?!\w)", " ", normalized,
            flags=re.IGNORECASE,
        )
    normalized = re.sub(r"\s+([,.;?!])", r"\1", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or query.strip()


def _update_session_entity(state: RAGSession, result: "RAGResult") -> None:
    if result.source == "teachme_grounded" and result.resolved_entity:
        state.last_entity = result.resolved_entity
        state.last_activity = time.monotonic()


def require_english(query: str) -> None:
    if not any(character.isalnum() for character in query):
        raise NoSpeechDetected("No speech detected")
    tokens = _tokens(query)
    try:
        ranked = detect_langs(query)
    except LangDetectException as exc:
        raise NonEnglishQueryError("Query language could not be identified as English") from exc
    if not ranked:
        raise NonEnglishQueryError("Query language could not be identified as English")
    language = ranked[0].lang
    confidence = ranked[0].prob
    token_set = set(tokens)
    english_markers = {
        "what", "which", "where", "when", "who", "why", "how", "does", "do",
        "is", "are", "can", "could", "would", "should", "tell", "explain", "about",
        "please", "you", "your", "me", "my", "the", "i", "to", "going", "am",
    }
    marker_count = len(token_set & english_markers)
    short_supported_english = (
        query.isascii()
        and len(tokens) <= RAG_LANGUAGE_MIN_TOKENS
        and marker_count >= 2
    )
    uncertain_supported_english = (
        query.isascii()
        and confidence < RAG_LANGUAGE_CONFIDENCE_THRESHOLD
        and marker_count >= 2
    )
    if language != "en" and not (short_supported_english or uncertain_supported_english):
        raise NonEnglishQueryError(f"English-only input required; detected language: {language}")


def _fact_text(item: dict[str, Any]) -> str:
    data = item.get("data")
    item_type = item.get("type")
    if not isinstance(data, dict) or item_type not in {"object", "fact"}:
        raise ValueError("TeachMe returned an invalid typed knowledge item")
    return knowledge_text(item_type, data)


def build_grounded_prompt(query: str, matches: list[dict[str, Any]]) -> tuple[str, list[str]]:
    facts = [_fact_text(item) for item in matches]
    fact_block = "\n".join(f"- {fact}" for fact in facts)
    prompt = (
        "Answer the question strictly and only from the facts below. "
        "Do not add outside knowledge, assumptions, or new claims. "
        f"If these facts do not contain what is needed to answer the question, "
        f"reply with exactly this marker and nothing else: {NOT_ANSWERABLE_MARKER}\n"
        f"FACTS:\n{fact_block}\n"
        f"QUESTION:\n{query}"
    )
    return prompt, facts


_GROUNDING_GLUE = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is",
    "i", "it", "me", "my", "of", "on", "or", "that", "the", "this", "to", "was",
    "we", "were", "with", "you", "your",
}

_QUERY_GLUE = _GROUNDING_GLUE | {
    "am", "can", "could", "did", "do", "does", "exactly", "give", "had",
    "has", "have", "he", "her", "here", "hers", "him", "his", "how", "i",
    "it", "its", "know", "me", "mine", "more", "most", "my", "our", "ours",
    "please", "say", "she", "tell", "their", "theirs", "them", "then", "there",
    "these", "they", "those", "us", "we", "what", "when", "where", "which",
    "who", "whom", "why", "would", "you", "your", "yours",
}
_QUERY_GLUE = frozenset(
    token.strip().casefold()
    for token in os.getenv("RAG_QUERY_GLUE_WORDS", ",".join(sorted(_QUERY_GLUE))).split(",")
    if token.strip()
)


def _tokens(text: str) -> list[str]:
    normalized = re.sub(r"['’]s\b", "", text.casefold())
    return re.findall(r"[a-z0-9]+", normalized)


def _retrieval_terms(text: str) -> list[str]:
    """Return stable lexical terms used only to validate near-threshold matches."""
    return list(dict.fromkeys(token for token in _tokens(text) if token not in _QUERY_GLUE))


def _has_meaningful_overlap(query: str, item: dict[str, Any]) -> bool:
    query_terms = set(_retrieval_terms(query))
    if not query_terms:
        return False
    knowledge_terms = set(_retrieval_terms(_fact_text(item)))
    overlap = query_terms & knowledge_terms
    return bool(overlap) and len(overlap) / len(query_terms) >= RAG_BAND_QUERY_COVERAGE_RATIO


def is_grounded(response: str, facts: list[str]) -> bool:
    """Check faithfulness only; relevance is enforced by retrieval and answerability."""
    response_tokens = _tokens(response)
    fact_tokens = _tokens(" ".join(facts))
    if not response_tokens or not fact_tokens:
        return False
    response_claims = [token for token in response_tokens if token not in _GROUNDING_GLUE]
    fact_claims = {token for token in fact_tokens if token not in _GROUNDING_GLUE}
    if not response_claims:
        return False
    coverage = sum(token in fact_claims for token in response_claims) / len(response_claims)
    similarity = SequenceMatcher(None, " ".join(response_tokens), " ".join(fact_tokens)).ratio()
    return coverage >= 0.9 and similarity >= 0.45


@dataclass(frozen=True)
class RAGResult:
    response: str
    source: str
    query_tokens: tuple[str, ...] = ()
    retrieval_terms: tuple[str, ...] = ()
    best_similarity: float | None = None
    resolved_entity: str | None = None


def _diagnostic_headers(
    query_tokens: tuple[str, ...],
    retrieval_terms: tuple[str, ...],
    best_similarity: float | None = None,
) -> dict[str, str]:
    """Expose safe retrieval diagnostics without changing the JSON contract."""
    headers = {
        "X-NEXI-Query-Tokens": ",".join(query_tokens),
        "X-NEXI-Retrieval-Terms": ",".join(retrieval_terms),
    }
    if best_similarity is not None:
        headers["X-NEXI-Best-Similarity"] = f"{best_similarity:.6f}"
    return headers


class RestrictedRAGPipeline:
    """Enforce command/retrieval/generation ordering with injected clients."""

    def __init__(self, teachme_client: Any, llm_client: Any):
        self.teachme_client = teachme_client
        self.llm_client = llm_client

    async def answer(self, query: str, user_id: str | None = None) -> RAGResult:
        if not any(character.isalnum() for character in query):
            raise NoSpeechDetected("No speech detected")
        query_tokens = tuple(_tokens(query))
        retrieval_terms = tuple(_retrieval_terms(query))
        command_response = classify_basic_command(query)
        if command_response is not None:
            return RAGResult(
                response=command_response,
                source="basic_command",
                query_tokens=query_tokens,
                retrieval_terms=retrieval_terms,
            )

        require_english(query)
        retrieval_query = normalize_retrieval_query(query)

        retrieval_args = {
            # Keep the complete semantic clause, removing only configured filler.
            "query": retrieval_query,
            "k": RAG_TOP_K,
            # Retrieve a small candidate set, then enforce the stricter policy
            # locally. This permits lexical evidence to rescue only genuinely
            # related near-threshold phrasing.
            "threshold": min(RAG_CANDIDATE_THRESHOLD, RAG_MATCH_THRESHOLD),
        }
        if user_id is not None:
            retrieval_args["user_id"] = user_id
        retrieval = await self.teachme_client.search_by_embedding(**retrieval_args)
        candidates = (retrieval or {}).get("results", [])
        matches = [
            item for item in candidates
            if (
                float(item.get("similarity", 0.0)) >= RAG_MATCH_THRESHOLD
                or (
                    float(item.get("similarity", 0.0)) >= RAG_CANDIDATE_THRESHOLD
                    and _has_meaningful_overlap(retrieval_query, item)
                )
            )
        ]
        best_similarity = max(
            (float(item.get("similarity", 0.0)) for item in candidates),
            default=None,
        )
        if not matches:
            logger.info("teachme_no_match query=%r", query)
            return RAGResult(
                response=TEACH_ME_RESPONSE,
                source="no_match",
                query_tokens=query_tokens,
                retrieval_terms=retrieval_terms,
                best_similarity=best_similarity,
            )

        prompt, facts = build_grounded_prompt(query, matches)
        success, result = await self.llm_client.generate_response(
            prompt,
            language="en",
            max_response_tokens=256,
            temperature=0.2,
            request_context="teachme",
        )
        if not success:
            raise RAGProviderError(result.get("error", "LLM generation failed"))
        response = result.get("response", "")
        if NOT_ANSWERABLE_MARKER in response:
            logger.info("teachme_not_answerable query=%r", query)
            return RAGResult(
                response=TEACH_ME_RESPONSE,
                source="not_answerable",
                query_tokens=query_tokens,
                retrieval_terms=retrieval_terms,
                best_similarity=best_similarity,
            )
        if not is_grounded(response, facts):
            logger.warning("grounding_validation_failed query=%r", query)
            return RAGResult(
                response=TEACH_ME_RESPONSE,
                source="grounding_failure",
                query_tokens=query_tokens,
                retrieval_terms=retrieval_terms,
                best_similarity=best_similarity,
            )
        return RAGResult(
            response=response,
            source="teachme_grounded",
            query_tokens=query_tokens,
            retrieval_terms=retrieval_terms,
            best_similarity=best_similarity,
            resolved_entity=str(matches[0].get("data", {}).get("subject") or "") or None,
        )


async def _answer_while_connected(
    pipeline: RestrictedRAGPipeline,
    query: str,
    user_id: str,
    request: Request,
) -> RAGResult:
    """Propagate a disconnected REST client as cancellation through async RAG clients."""
    task = asyncio.create_task(pipeline.answer(query, user_id=user_id))
    try:
        while not task.done():
            if await request.is_disconnected():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                raise asyncio.CancelledError("RAG client disconnected")
            await asyncio.sleep(0.025)
        return await task
    except asyncio.CancelledError:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        raise


router = APIRouter(prefix="/api/v1/rag", tags=["restricted-rag"])
_llm_client = LLMServiceClient()


@router.post("/sessions", status_code=201)
async def start_rag_session(
    request: Request,
    _trusted: str | None = Depends(require_internal_service),
):
    """Create a session only from the validated bearer subject after voice verification."""
    claims = require_session_claims(request)
    session_id, state = create_rag_session(str(claims["sub"]))
    return {
        "success": True,
        "session_id": session_id,
        "verified": state.verified,
        "user_id": state.user_id,
        "idle_timeout_seconds": RAG_SESSION_IDLE_SECONDS,
    }


@router.delete("/sessions/{session_id}", status_code=204)
async def close_rag_session(
    session_id: str,
    _trusted: str | None = Depends(require_internal_service),
):
    """Explicitly release manual session state when the console exits/cancels."""
    with _rag_sessions_lock:
        _rag_sessions.pop(session_id, None)
    return Response(status_code=204)


@router.post("/query")
async def restricted_query(request: RAGQueryRequest, http_request: Request, response: Response):
    try:
        claims = require_session_claims(http_request)
        user_id = str(claims["sub"])
        if not any(character.isalnum() for character in request.query):
            raise NoSpeechDetected("No speech detected")
        explicit_session = request.session_id is not None
        session_id = request.session_id or uuid.uuid4().hex
        if explicit_session:
            with _rag_sessions_lock:
                if session_id not in _rag_sessions:
                    raise HTTPException(
                        status_code=410,
                        detail={"code": "SESSION_EXPIRED", "message": "Manual session expired; start a new session"},
                    )
        resolved_query, session_state = _resolve_session_query(
            session_id, user_id, request.query, allow_create=not explicit_session
        )
        pipeline = RestrictedRAGPipeline(get_teachme_connector(), _llm_client)
        result = await _answer_while_connected(pipeline, resolved_query, user_id, http_request)
        _update_session_entity(session_state, result)
        normalized_command = " ".join(re.findall(r"[a-z0-9']+", request.query.casefold()))
        is_farewell = result.source == "basic_command" and normalized_command in RAG_FAREWELL_PHRASES
        if is_farewell:
            with _rag_sessions_lock:
                _rag_sessions.pop(session_id, None)
        if result.source in {"teachme_grounded", "no_match", "not_answerable", "grounding_failure"}:
            persisted = await asyncio.to_thread(
                add_conversation,
                user_id=user_id,
                user_message=request.query,
                assistant_response=result.response,
                language="en",
                metadata={"source": result.source, "automatic": True},
            )
            if not persisted:
                raise HTTPException(
                    status_code=500,
                    detail={
                        "code": "CONVERSATION_PERSISTENCE_FAILED",
                        "message": "RAG response could not be stored",
                    },
                )
        for name, value in _diagnostic_headers(
            result.query_tokens,
            result.retrieval_terms,
            result.best_similarity,
        ).items():
            response.headers[name] = value
        response.headers["X-NEXI-Session-ID"] = session_id
        response.headers["X-NEXI-Session-Ended"] = str(is_farewell).lower()
        response.headers["X-NEXI-Session-Turn-Count"] = str(session_state.turn_count)
        response.headers["X-NEXI-Session-Idle-Timeout"] = str(RAG_SESSION_IDLE_SECONDS)
        return {"success": True, "response": result.response, "source": result.source}
    except NoSpeechDetected:
        return {"success": True, "status": "no_speech", "response": "No speech detected", "source": "no_speech"}
    except NonEnglishQueryError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "english_only", "message": str(exc)},
            headers=_diagnostic_headers(tuple(_tokens(request.query)), tuple(_retrieval_terms(request.query))),
        ) from exc
    except RAGProviderError as exc:
        raise HTTPException(status_code=502, detail={"code": "llm_failure", "message": str(exc)}) from exc


async def rag_session_eviction_loop() -> None:
    """Periodic TTL cleanup so idle sessions expire even without another query."""
    interval = max(0.1, min(RAG_SESSION_IDLE_SECONDS / 4, 5.0))
    while True:
        await asyncio.sleep(interval)
        evicted = evict_idle_rag_sessions()
        if evicted:
            logger.info("rag_idle_sessions_evicted count=%d", evicted)
        with _rag_sessions_lock:
            expired = list(_expired_rag_sessions)
            _expired_rag_sessions.clear()
        for _session_id, user_id in expired:
            try:
                async with httpx.AsyncClient(
                    timeout=5.0,
                    headers={
                        **internal_service_headers(user_id=user_id),
                        TRUSTED_USER_HEADER: user_id,
                    },
                    verify=client_verify(_AUDIO_SERVICE_URL),
                ) as client:
                    response = await client.post(
                        f"{_AUDIO_SERVICE_URL}/api/v1/conversation/end",
                        params={"user_id": user_id},
                    )
                    response.raise_for_status()
            except Exception:
                logger.exception("Could not close idle Audio conversation for user %s", user_id)
