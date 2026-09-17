"""Central's single restricted-RAG policy boundary."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from difflib import SequenceMatcher
import logging
import os
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from shared.jwt_manager import require_session_claims
from langdetect import DetectorFactory, LangDetectException, detect
from pydantic import BaseModel, ConfigDict, Field

from basic_commands import classify_basic_command
from conversations_persistence import add_conversation
from shared.clients.llm_client import LLMServiceClient
from shared.semantic_embeddings import knowledge_text
from teachme_connector import get_teachme_connector


TEACH_ME_RESPONSE = "I don't know this yet. Please teach me."
RAG_MATCH_THRESHOLD = float(os.getenv("RAG_MATCH_THRESHOLD", "0.55"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
DetectorFactory.seed = 0
logger = logging.getLogger(__name__)


class NonEnglishQueryError(ValueError):
    pass


class RAGProviderError(RuntimeError):
    pass


class RAGQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=2000)


def require_english(query: str) -> None:
    try:
        language = detect(query)
    except LangDetectException as exc:
        raise NonEnglishQueryError("Query language could not be identified as English") from exc
    tokens = set(re.findall(r"[a-z]+", query.casefold()))
    english_markers = {
        "what", "which", "where", "when", "who", "why", "how", "does", "do",
        "is", "are", "can", "could", "would", "should", "tell", "explain", "about",
        "please", "you", "your", "me", "my", "the",
    }
    short_ascii_english = query.isascii() and bool(tokens & english_markers)
    if language != "en" and not short_ascii_english:
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
        "Do not add outside knowledge, assumptions, or new claims.\n"
        f"FACTS:\n{fact_block}\n"
        f"QUESTION:\n{query}"
    )
    return prompt, facts


_GROUNDING_GLUE = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is",
    "it", "of", "on", "or", "that", "the", "this", "to", "was", "were", "with",
}


def _tokens(text: str) -> list[str]:
    normalized = re.sub(r"['’]s\b", "", text.casefold())
    return re.findall(r"[a-z0-9]+", normalized)


def is_grounded(response: str, facts: list[str]) -> bool:
    """Conservatively require the response's claims to be contained in the facts."""
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


class RestrictedRAGPipeline:
    """Enforce command/retrieval/generation ordering with injected clients."""

    def __init__(self, teachme_client: Any, llm_client: Any):
        self.teachme_client = teachme_client
        self.llm_client = llm_client

    async def answer(self, query: str, user_id: str | None = None) -> RAGResult:
        command_response = classify_basic_command(query)
        if command_response is not None:
            return RAGResult(response=command_response, source="basic_command")

        require_english(query)

        retrieval_args = {
            "query": query,
            "k": RAG_TOP_K,
            "threshold": RAG_MATCH_THRESHOLD,
        }
        if user_id is not None:
            retrieval_args["user_id"] = user_id
        retrieval = await self.teachme_client.search_by_embedding(**retrieval_args)
        candidates = (retrieval or {}).get("results", [])
        matches = [
            item for item in candidates
            if float(item.get("similarity", 0.0)) >= RAG_MATCH_THRESHOLD
        ]
        if not matches:
            logger.info("teachme_no_match query=%r", query)
            return RAGResult(response=TEACH_ME_RESPONSE, source="no_match")

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
        if not is_grounded(response, facts):
            logger.warning("grounding_validation_failed query=%r", query)
            return RAGResult(response=TEACH_ME_RESPONSE, source="grounding_failure")
        return RAGResult(response=response, source="teachme_grounded")


router = APIRouter(prefix="/api/v1/rag", tags=["restricted-rag"])
_llm_client = LLMServiceClient()


@router.post("/query")
async def restricted_query(request: RAGQueryRequest, http_request: Request):
    try:
        claims = require_session_claims(http_request)
        user_id = str(claims["sub"])
        pipeline = RestrictedRAGPipeline(get_teachme_connector(), _llm_client)
        result = await pipeline.answer(request.query, user_id=user_id)
        if result.source in {"teachme_grounded", "no_match", "grounding_failure"}:
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
        return {"success": True, "response": result.response, "source": result.source}
    except NonEnglishQueryError as exc:
        raise HTTPException(status_code=422, detail={"code": "english_only", "message": str(exc)}) from exc
    except RAGProviderError as exc:
        raise HTTPException(status_code=502, detail={"code": "llm_failure", "message": str(exc)}) from exc
