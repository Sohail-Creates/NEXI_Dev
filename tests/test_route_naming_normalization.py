"""Focused transition-contract tests for the pre-Phase-8 route rename pass."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest


ROOT_PATH = Path(__file__).resolve().parents[1]
CENTRAL = ROOT_PATH / "01_central_server"
sys.path[:0] = [str(ROOT_PATH), str(CENTRAL)]

from routes import conversations_routes, user_routes
import teachme_routes
from shared.api_errors import install_error_handlers


SERVICE_TOKEN = "naming-normalization-service-token"


async def _no_persist(*args, **kwargs) -> None:
    return None


def _user_app(users: list[dict] | None = None) -> FastAPI:
    app = FastAPI()
    app.state.db = {"users": list(users or [])}
    app.include_router(user_routes.router)
    install_error_handlers(app, "naming-user-fixture")
    return app


def _route(app: FastAPI, path: str, method: str):
    return next(
        route
        for route in app.routes
        if getattr(route, "path", None) == path
        and method in (getattr(route, "methods", set()) or set())
    )


def test_b_registration_routes_and_old_route_retired(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_ENFORCEMENT_ENABLED", "false")
    app = _user_app()
    paths = {
        (route.path, method)
        for route in app.routes
        for method in (getattr(route, "methods", set()) or set())
    }
    assert ("/users/register", "POST") in paths
    assert ("/users/register-with-voice", "POST") in paths
    assert ("/users/session/voice", "POST") in paths
    assert ("/users/register-old", "POST") not in paths
    with TestClient(app) as client:
        registration = client.post("/users/register", data={"name": "Naming User"})
        retired = client.post("/users/register-old", json={"name": "legacy"})
    assert registration.status_code == 200, registration.text
    assert retired.status_code in {404, 405}, retired.text
    print(
        "TASK_B_ROUTES=PASS register=200 register_with_voice=present "
        f"session_voice=present register_old_post={retired.status_code} registered_route=false"
    )


def test_c_user_creation_alias_is_identical_and_callers_migrated(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_ENFORCEMENT_ENABLED", "true")
    monkeypatch.setenv("NEXI_INTERNAL_SERVICE_TOKEN", SERVICE_TOKEN)
    monkeypatch.setattr(user_routes, "_persist_users", _no_persist)
    monkeypatch.setattr(
        user_routes.uuid, "uuid4", lambda: SimpleNamespace(hex="c" * 32)
    )
    payload = {"name": "Canonical User", "voice_embeddings": [[0.1]], "face_embeddings": [[0.2]]}
    headers = {"X-NEXI-Service-Token": SERVICE_TOKEN}
    with TestClient(_user_app()) as primary_client:
        primary = primary_client.post("/users", headers=headers, json=dict(payload))
    with TestClient(_user_app()) as alias_client:
        alias = alias_client.post("/users/data/add_user", headers=headers, json=dict(payload))
    assert primary.status_code == alias.status_code == 200
    assert primary.json() == alias.json()
    assert _route(_user_app(), "/users", "POST").endpoint is _route(
        _user_app(), "/users/data/add_user", "POST"
    ).endpoint

    caller_files = {
        "central_client": ROOT_PATH / "06_enrollment_service/app/clients/central_server_client.py",
        "enrollment_service": ROOT_PATH / "06_enrollment_service/app/services/enrollment_service.py",
        "sync_script": ROOT_PATH / "scripts/sync_enrollment_to_central.py",
        "phase6_test": ROOT_PATH / "tests/test_phase6.py",
    }
    for name, path in caller_files.items():
        source = path.read_text(encoding="utf-8")
        assert "/users/data/add_user" not in source, name
        assert "/users" in source, name
    print(
        "TASK_C_PRIMARY HTTP=200 PATH=/users "
        f"BODY={json.dumps(primary.json(), separators=(',', ':'))}"
    )
    print(
        "TASK_C_ALIAS HTTP=200 PATH=/users/data/add_user "
        f"BODY={json.dumps(alias.json(), separators=(',', ':'))} identical=true"
    )
    print("TASK_C_CALLERS=PASS production=3 phase6_test=1 old_references=0")


def test_d_embedded_history_is_gone_and_durable_route_serves_data(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_ENFORCEMENT_ENABLED", "false")
    fixture = [{
        "conversation_id": "conv-durable",
        "user_id": "user-durable",
        "timestamp": "2026-09-11T00:00:00Z",
        "user_message": "durable question",
        "assistant_response": "durable answer",
        "mood": "neutral",
        "language": "en",
        "metadata": {},
    }]
    monkeypatch.setattr(
        conversations_routes, "get_user_conversations", lambda **kwargs: fixture
    )
    app = _user_app([{"user_id": "user-durable", "name": "Durable User"}])
    app.include_router(conversations_routes.router)
    with TestClient(app) as client:
        retired = client.get("/users/user-durable/conversation-history")
        durable = client.get("/users/user-durable/conversations")
    assert retired.status_code == 410
    assert retired.json()["error"]["code"] == "CONVERSATION_HISTORY_RETIRED"
    assert durable.status_code == 200
    assert durable.json()["conversations"] == fixture
    assert "/users/user-durable/conversations" in retired.json()["error"]["message"]
    print(
        "TASK_D_RETIRED "
        f"HTTP=410 BODY={json.dumps(retired.json(), separators=(',', ':'))}"
    )
    print(
        "TASK_D_DURABLE "
        f"HTTP=200 BODY={json.dumps(durable.json(), separators=(',', ':'))}"
    )


def test_e_registration_with_embeddings_alias_is_identical(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_ENFORCEMENT_ENABLED", "false")
    monkeypatch.setattr(user_routes, "_persist_users", _no_persist)
    monkeypatch.setattr(
        user_routes.uuid, "uuid4", lambda: SimpleNamespace(hex="e" * 32)
    )
    payload = {
        "user_name": "Embedding User",
        "voice_embeddings": [[0.1]],
        "face_embeddings": [[0.2]],
    }
    with TestClient(_user_app()) as primary_client:
        primary = primary_client.post(
            "/users/register-with-embeddings", json=dict(payload)
        )
    with TestClient(_user_app()) as alias_client:
        alias = alias_client.post("/users/add-embeddings", json=dict(payload))
    assert primary.status_code == alias.status_code == 200
    assert primary.json() == alias.json()
    assert _route(_user_app(), "/users/register-with-embeddings", "POST").endpoint is _route(
        _user_app(), "/users/add-embeddings", "POST"
    ).endpoint
    enhanced = (ROOT_PATH / "test.py").read_text(encoding="utf-8")
    assert "CENTRAL_SERVER}/users/add-embeddings" not in enhanced
    assert '"/enrollment/enroll"' in enhanced
    print(
        "TASK_E_PRIMARY HTTP=200 PATH=/users/register-with-embeddings "
        f"BODY={json.dumps(primary.json(), separators=(',', ':'))}"
    )
    print(
        "TASK_E_ALIAS HTTP=200 PATH=/users/add-embeddings "
        f"BODY={json.dumps(alias.json(), separators=(',', ':'))} identical=true"
    )
    print("TASK_E_APPEND_UNCHANGED path=/users/{user_id}/append-embeddings present=true")


class _TeachMeConnector:
    async def search_by_name(self, query: str, limit: int) -> dict:
        return {"results": [{"name": query, "mode": "text"}], "fallback": False}

    async def search_by_embedding(self, query: str, k: int, threshold: float) -> dict:
        return {"results": [{"name": query, "mode": "embedding"}], "fallback": False}


def test_f_teachme_search_aliases_are_identical(monkeypatch) -> None:
    monkeypatch.setattr(teachme_routes, "get_teachme_connector", lambda: _TeachMeConnector())
    app = FastAPI()
    app.include_router(teachme_routes.router)
    with TestClient(app) as client:
        text_primary = client.get("/teachme/search/by-text/robot", params={"limit": 2})
        text_alias = client.get("/teachme/search/robot", params={"limit": 2})
        embedding_primary = client.post(
            "/teachme/search/by-embedding",
            json={"query": "robot", "k": 2, "threshold": 0.3},
        )
        embedding_alias = client.post(
            "/teachme/search/embedding",
            json={"query": "robot", "k": 2, "threshold": 0.3},
        )
    assert text_primary.status_code == text_alias.status_code == 200
    assert text_primary.json() == text_alias.json()
    assert embedding_primary.status_code == embedding_alias.status_code == 200
    assert embedding_primary.json() == embedding_alias.json()
    assert _route(app, "/teachme/search/by-text/{query}", "GET").endpoint is _route(
        app, "/teachme/search/{query}", "GET"
    ).endpoint
    assert _route(app, "/teachme/search/by-embedding", "POST").endpoint is _route(
        app, "/teachme/search/embedding", "POST"
    ).endpoint
    print(
        "TASK_F_TEXT_PRIMARY_ALIAS=PASS new=/teachme/search/by-text/{query} "
        f"old=/teachme/search/{{query}} HTTP=200 identical=true body={text_primary.json()}"
    )
    print(
        "TASK_F_EMBEDDING_PRIMARY_ALIAS=PASS new=/teachme/search/by-embedding "
        f"old=/teachme/search/embedding HTTP=200 identical=true body={embedding_primary.json()}"
    )


def test_g_openapi_documents_only_primary_paths(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_ENFORCEMENT_ENABLED", "false")
    app = _user_app()
    app.include_router(teachme_routes.router)
    paths = set(app.openapi()["paths"])
    assert {
        "/users",
        "/users/register",
        "/users/register-with-voice",
        "/users/register-with-embeddings",
        "/users/{user_id}/append-embeddings",
        "/teachme/search/by-text/{query}",
        "/teachme/search/by-embedding",
    } <= paths
    assert {
        "/users/register-old",
        "/users/data/add_user",
        "/users/add-embeddings",
        "/users/{user_id}/conversation-history",
        "/teachme/search/{query}",
        "/teachme/search/embedding",
    }.isdisjoint(paths)
    print(
        "TASK_G_OPENAPI=PASS primary_paths=7 functional_aliases=4 "
        "hidden_transition_paths=5 "
        "retired_register_old=absent retired_conversation_history=hidden"
    )
