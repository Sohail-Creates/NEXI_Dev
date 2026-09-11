"""Shared HTTP error contract for every NEXI service."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse


class ErrorBody(BaseModel):
    status_code: int
    code: str
    message: str
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody


_STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    411: "LENGTH_REQUIRED",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_SERVER_ERROR",
    501: "NOT_IMPLEMENTED",
    502: "BAD_GATEWAY",
    503: "SERVICE_UNAVAILABLE",
    504: "GATEWAY_TIMEOUT",
}


def request_id_for(request: Request) -> str:
    """Reuse an inbound correlation ID, otherwise assign one once per request."""
    request_id = getattr(request.state, "request_id", None)
    if not request_id:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
    return str(request_id)


def _detail_parts(status_code: int, detail: Any) -> tuple[str, str]:
    code = _STATUS_CODES.get(status_code, f"HTTP_{status_code}")
    if isinstance(detail, dict):
        candidate_code = detail.get("code") or detail.get("type") or detail.get("error_code")
        if candidate_code:
            code = str(candidate_code).upper()
        message = detail.get("message") or detail.get("detail") or detail.get("error")
        return code, str(message or code.replace("_", " ").title())
    return code, str(detail or code.replace("_", " ").title())


def error_response(
    request: Request,
    status_code: int,
    message: Any,
    *,
    code: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build the sole public error-envelope shape."""
    inferred_code, normalized_message = _detail_parts(status_code, message)
    request_id = request_id_for(request)
    response_headers = dict(headers or {})
    response_headers["X-Request-ID"] = request_id
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "status_code": status_code,
                "code": code or inferred_code,
                "message": normalized_message,
                "request_id": request_id,
            }
        },
        headers=response_headers,
    )


def install_error_handlers(app: FastAPI, service_name: str) -> None:
    """Install the same HTTP, validation, and catch-all handlers on an app."""
    logger = logging.getLogger(f"{service_name}.api")

    async def handle_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error_response(
            request,
            exc.status_code,
            exc.detail,
            headers=getattr(exc, "headers", None),
        )

    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            request,
            422,
            "Request validation failed",
            code="VALIDATION_ERROR",
        )

    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled request error request_id=%s",
            request_id_for(request),
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return error_response(
            request,
            500,
            "Internal server error",
            code="INTERNAL_SERVER_ERROR",
        )

    app.add_exception_handler(StarletteHTTPException, handle_http)
    app.add_exception_handler(HTTPException, handle_http)
    app.add_exception_handler(RequestValidationError, handle_validation)
    app.add_exception_handler(Exception, handle_unexpected)

    original_openapi = app.openapi

    def openapi_with_error_contract() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = original_openapi()
        schemas = schema.setdefault("components", {}).setdefault("schemas", {})
        schemas["ErrorBody"] = {
            "type": "object",
            "required": ["status_code", "code", "message", "request_id"],
            "properties": {
                "status_code": {"type": "integer"},
                "code": {"type": "string"},
                "message": {"type": "string"},
                "request_id": {"type": "string"},
            },
        }
        schemas["ErrorEnvelope"] = {
            "type": "object",
            "required": ["error"],
            "properties": {"error": {"$ref": "#/components/schemas/ErrorBody"}},
        }
        envelope = {
            "description": "Error response",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorEnvelope"}
                }
            },
        }
        for path_item in schema.get("paths", {}).values():
            for method, operation in path_item.items():
                if method not in {"get", "post", "put", "patch", "delete", "options", "head"}:
                    continue
                responses = operation.setdefault("responses", {})
                for status_code in ("400", "401", "403", "404", "409", "422", "429", "500"):
                    responses.setdefault(status_code, envelope)
                # FastAPI's built-in 422 schema does not match the installed handler.
                responses["422"] = envelope
        app.openapi_schema = schema
        return schema

    app.openapi = openapi_with_error_contract
