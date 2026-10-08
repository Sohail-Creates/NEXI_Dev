# NEXI REST API Reference

Authoritative source audit date: **2026-10-08**. This contract is derived from the seven currently constructed FastAPI application objects, their mounted `APIRouter` instances, request/response models, middleware, and route-level dependencies. Framework routes (`/docs`, `/redoc`, `/openapi.json`) are excluded. TLS is enabled by default; deployment may override host, port, or TLS settings.

> Authentication is conditionally enforced by `AUTH_ENFORCEMENT_ENABLED`. Its code default is `false`; production deployments should set it to `true`. Every endpoint below states the rule that becomes mandatory when enforcement is enabled. Never place the internal shared token in a 3D client; proxy internal calls through a trusted backend.

## Service overview

| Service | Default port | Local base URL | Purpose |
|---|---:|---|---|
| Central Server | 8000 | `https://localhost:8000` | User/session persistence, restricted RAG orchestration, TeachMe proxying, and shared hardware-resource authority. |
| Vision Service | 8001 | `https://localhost:8001` | Camera control, image/frame capture, face analysis, object detection, and object signatures. |
| Audio Service | 8002 | `https://localhost:8002` | Recording, wake/stop-word control, speaker enrollment/verification, transcription, and voice-turn orchestration. |
| TTS Service | 8003 | `https://localhost:8003` | Speech synthesis, voice selection, speaker state, cache, metrics, and diagnostics. |
| TeachMe Service | 8004 | `https://localhost:8004` | Persistent learned facts/objects, semantic retrieval, recognition, relationship lookup, and knowledge administration. |
| Enrollment Service | 8005 | `https://localhost:8005` | Multi-modal enrollment, photo validation, training improvement, model refresh, and synchronized deletion. |
| LLM Service | 8006 | `https://localhost:8006` | Bounded online generation and deterministic response/expression formatting. |

## Authentication headers

| Trust type | Exact header | Use |
|---|---|---|
| Internal service | `X-NEXI-Service-Token: <token>` | Value comes from `NEXI_INTERNAL_SERVICE_TOKEN` (the previous rotation value is also accepted). |
| End-user session | `Authorization: Bearer <session-jwt>` | Signed session JWT issued after successful voice verification/enrollment. |
| Trusted user context | `X-NEXI-Trusted-User-ID: <user-id>` | Only with a valid internal token; required where an internal caller acts for a user. |

## Shared error contract

Installed error handlers use this envelope (some older endpoint-local errors return their documented response model instead):

```json
{"error":{"status_code":422,"code":"VALIDATION_ERROR","message":"Request validation failed","request_id":"<correlation-id>"}}
```

Common middleware outcomes are `401` (credential), `403` (ownership), `411` (missing upload `Content-Length`), `413` (upload too large), `415` (unsupported upload media type), `422` (request validation), and `429` (rate limiting). Route implementations also use `410`, `501`, `502`, `503`, and `504` where explicitly described below. Route tables list statuses declared by the active OpenAPI schema; the source-semantics notes take precedence where OpenAPI is incomplete.

# Central Server

## Base URL

`https://<host>:8000`

## Authentication

Public and protected routes coexist. Protected rules used in this service: Bearer session owning the user, or internal token plus matching trusted-user header; End-user bearer session, or internal token plus trusted-user header; Internal service token; Internal service token **and** end-user bearer session.

## Endpoints

### GET /

> **Simulation Integration**

**Purpose**

Root.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /admin/stats

> **Internal Service Endpoint**

**Purpose**

Get Conversation Statistics. Get analytics about all conversations (admin endpoint).

**Authentication**

Internal service token.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /api/v1/rag/commands/stop

> **Simulation Integration**

**Purpose**

Check Stop Command. Classify a complete stop command without retrieval, generation or storage.

**Authentication**

End-user bearer session, or internal token plus trusted-user header.

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `query` | string | Yes | min length: 1; max length: 2000 |
| `session_id` | string \| null | No | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Source response semantics**

Success JSON is `{"is_stop_command": <boolean>}`.

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /api/v1/rag/query

> **Simulation Integration**

**Purpose**

Restricted Query.

**Authentication**

End-user bearer session, or internal token plus trusted-user header.

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `query` | string | Yes | min length: 1; max length: 2000 |
| `session_id` | string \| null | No | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Source response semantics**

Success JSON fields are `success`, `response`, `source`, `response_source`, `fallback_used`, `fallback_reason`, `llm_provider`, `llm_model`, `llm_latency_ms`, and `retrieved_record_ids`. A no-speech decision returns `success: true`, `status: "no_speech"`, `response`, and `source: "no_speech"`. Response headers include `X-NEXI-Session-ID`, `X-NEXI-Session-Ended`, `X-NEXI-Session-Turn-Count`, and `X-NEXI-Session-Idle-Timeout`. An unknown explicit session returns `410`; non-English input returns `422`; an LLM provider failure returns `502`.

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /api/v1/rag/sessions

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Start Rag Session. Create a session only from the validated bearer subject after voice verification.

**Authentication**

Internal service token **and** end-user bearer session.

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `201` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Source response semantics**

`201` JSON fields are `success`, `session_id`, `verified`, `user_id`, and `idle_timeout_seconds`.

**Important status codes**

- Declared by the active application: `201`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### DELETE /api/v1/rag/sessions/{session_id}

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Close Rag Session. Explicitly release manual session state when the console exits/cancels.

**Authentication**

Internal service token.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `session_id` | path | string | Yes | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `204` | — | Successful Response; No response body. |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `204`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /calls/end

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

End Call.

**Authentication**

Internal service token.

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `call_id` | string | Yes | min length: 1; max length: 128; pattern: `^[A-Za-z0-9_.:-]+$` |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /calls/screenshot

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Capture Call Screenshot.

**Authentication**

Internal service token.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json`, `image/jpeg` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Source response semantics**

Success body is JPEG bytes (`image/jpeg`) with `X-NEXI-Call-ID`.

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /calls/start

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Start Call.

**Authentication**

Internal service token.

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `call_id` | string | Yes | min length: 1; max length: 128; pattern: `^[A-Za-z0-9_.:-]+$` |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /calls/status

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Get Call Status.

**Authentication**

Internal service token.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /camera/force-release

> **Internal Service Endpoint**

**Purpose**

Force Release Camera.

**Authentication**

Internal service token.

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /camera/release

> **Internal Service Endpoint**

**Purpose**

Release Camera.

**Authentication**

Internal service token.

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `service_name` | string | Yes | No additional constraint declared. |
| `timeout` | integer | No | default: 30 |
| `lease_id` | string \| null | No | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /camera/request

> **Internal Service Endpoint**

**Purpose**

Request Camera.

**Authentication**

Internal service token.

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `service_name` | string | Yes | No additional constraint declared. |
| `timeout` | integer | No | default: 30 |
| `lease_id` | string \| null | No | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /camera/status

> **Internal Service Endpoint**

**Purpose**

Get Camera Status.

**Authentication**

Internal service token.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /conversations/{conversation_id}

**Purpose**

Get Single Conversation. Retrieve a specific conversation by ID.

**Authentication**

Bearer session owning the user, or internal token plus matching trusted-user header.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `conversation_id` | path | string | Yes | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /health

> **Simulation Integration**

**Purpose**

Health.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Source response semantics**

Returns HTTP `200` with `status: "healthy"` and `service: "central_server"`; it does not probe downstream services.

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### POST /resources/acknowledge/{lease_id}

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Acknowledge Grant.

**Authentication**

Internal service token.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `lease_id` | path | string | Yes | No additional constraint declared. |

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /resources/focus

> **Internal Service Endpoint**

**Purpose**

Get Focus Mode. Poll the cooperative service-level focus signal.

**Authentication**

Internal service token.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /resources/health

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Resource Manager Health. Health check for resource manager.

**Authentication**

Internal service token.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /resources/release/{lease_id}

> **Internal Service Endpoint**

**Purpose**

Release Resource. Release a hardware resource lease.

**Authentication**

Internal service token.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `lease_id` | path | string | Yes | No additional constraint declared. |
| `forced` | query | boolean | No | default: `False` |

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /resources/request

> **Internal Service Endpoint**

**Purpose**

Request Resource. Request access to a hardware resource.

**Authentication**

Internal service token.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `resource_type` | query | string | Yes | Type of resource: camera, microphone |
| `service_name` | query | string | Yes | Name of requesting service |
| `priority` | query | string | No | Priority: CRITICAL, HIGH, MEDIUM, LOW (default: `MEDIUM`) |
| `timeout_seconds` | query | integer | No | Maximum time to hold resource (default: 30) |
| `holder_pid` | query | integer \| null | No | No additional constraint declared. |
| `holder_started` | query | number \| null | No | No additional constraint declared. |
| `holder_port` | query | integer \| null | No | No additional constraint declared. |

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /resources/revoke/{lease_id}

> **Internal Service Endpoint**

**Purpose**

Revoke Lease.

**Authentication**

Internal service token.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `lease_id` | path | string | Yes | No additional constraint declared. |

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /resources/status

> **Internal Service Endpoint**

**Purpose**

Get All Resources Status. Get comprehensive status of all hardware resources.

**Authentication**

Internal service token.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /resources/status/{lease_id}

> **Internal Service Endpoint**

**Purpose**

Get Lease Status. Check the status of a resource lease.

**Authentication**

Internal service token.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `lease_id` | path | string | Yes | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /sync/status

> **Internal Service Endpoint**

**Purpose**

Sync Status.

**Authentication**

Internal service token.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /teachme/health

> **Simulation Integration**

**Purpose**

Teachme Health. Check TeachMe service health

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### POST /teachme/learn

> **Simulation Integration**

**Purpose**

Learn Object. Learn a typed object or fact; TeachMe owns semantic embedding generation.

**Authentication**

Public.

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `type` | enum (`object`, `fact`) | Yes | No additional constraint declared. |
| `data` | object \| object | Yes | No additional constraint declared. |
| `tags` | array<string> | No | No additional constraint declared. |
| `confidence` | number | No | default: 1.0; min: 0.0; max: 1.0 |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.

### GET /teachme/metrics

**Purpose**

Get Metrics. Get TeachMe connector metrics.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /teachme/objects

**Purpose**

Get All Objects. Get all learned objects from TeachMe.

**Authentication**

Public.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `limit` | query | integer | No | default: 100; min: 1; max: 500 |
| `offset` | query | integer | No | default: 0; min: 0 |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.

### POST /teachme/search/by-embedding

**Purpose**

Search By Embedding. Search objects by semantic similarity using embedding.

**Authentication**

Public.

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `query` | string | Yes | min length: 1; max length: 200 |
| `k` | integer | No | default: 5 |
| `threshold` | number | No | default: 0.3 |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.

### GET /teachme/search/by-text/{query}

**Purpose**

Search By Name. Search learned objects by name.

**Authentication**

Public.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `query` | path | string | Yes | No additional constraint declared. |
| `limit` | query | integer | No | default: 10; min: 1; max: 100 |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.

### POST /teachme/search/embedding

> **Legacy / Compatibility Endpoint** Hidden from OpenAPI; exact alias of `POST /teachme/search/by-embedding`.

**Purpose**

Search By Embedding. Search objects by semantic similarity using embedding.

**Authentication**

Public.

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `query` | string | Yes | min length: 1; max length: 200 |
| `k` | integer | No | default: 5 |
| `threshold` | number | No | default: 0.3 |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.

### GET /teachme/search/{query}

> **Legacy / Compatibility Endpoint** Hidden from OpenAPI; exact alias of `GET /teachme/search/by-text/{query}`.

**Purpose**

Search By Name. Search learned objects by name.

**Authentication**

Public.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `query` | path | string | Yes | No additional constraint declared. |
| `limit` | query | integer | No | default: 10; min: 1; max: 100 |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.

### GET /teachme/status

**Purpose**

Teachme Status. Get detailed TeachMe status and metrics

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### POST /teachme/sync

**Purpose**

Sync Knowledge. Sync knowledge with other services.

**Authentication**

Public.

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `service_name` | string | Yes | No additional constraint declared. |
| `items` | array<object> | Yes | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.

### POST /users

> **Internal Service Endpoint**

**Purpose**

Add User. Create a user record through the canonical users collection.

**Authentication**

Internal service token.

**Content-Type**

`application/json`.

**application/json body**

Declared type: `object`. The application does not declare named body fields in OpenAPI.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /users/add-embeddings

> **Legacy / Compatibility Endpoint** Hidden from OpenAPI; exact alias of `POST /users/register-with-embeddings`.

**Purpose**

Add User Embeddings. Register a new user from already-extracted embeddings.

**Authentication**

Public.

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `user_name` | string | Yes | User name; blank values are rejected. |
| `age` | JSON value | No | Stored without additional validation. |
| `relation` | JSON value | No | Stored without additional validation. |
| `voice_embeddings` | array<array<number>> | No | Defaults to an empty list; normalized before storage. |
| `face_embeddings` | array<array<number>> | No | Defaults to an empty list. |
| `face_confidences` | array<number> | No | Defaults to zero for each face embedding. |
| `voice_qualities` | array<number> | No | Defaults to zero for each voice embedding. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /users/check

> **Internal Service Endpoint**

**Purpose**

Check User Exists. Check if user exists

**Authentication**

Internal service token.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `name` | query | string | Yes | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /users/data/add_user

> **Legacy / Compatibility Endpoint** Hidden from OpenAPI; exact alias of `POST /users`.

> **Internal Service Endpoint**

**Purpose**

Add User. Create a user record through the canonical users collection.

**Authentication**

Internal service token.

**Content-Type**

`application/json`.

**application/json body**

Declared type: `object`. The application does not declare named body fields in OpenAPI.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /users/enroll-complete

> **Simulation Integration**

**Purpose**

Enroll User Complete. Complete user enrollment with audio samples (from Streamlit app.py).

**Authentication**

Public.

**Content-Type**

`multipart/form-data`.

**multipart/form-data body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `user_name` | string | Yes | No additional constraint declared. |
| `age` | string \| null | No | No additional constraint declared. |
| `relation` | string \| null | No | No additional constraint declared. |
| `audio_samples` | array<JSON value> | Yes | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.

### GET /users/list

> **Internal Service Endpoint**

**Purpose**

List Users. List all registered users with their embeddings

**Authentication**

Internal service token.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /users/register

**Purpose**

Register User. Register user with audio and/or photo files.

**Authentication**

Public.

**Content-Type**

`multipart/form-data`.

**multipart/form-data body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `name` | string | No | No additional constraint declared. |
| `audio_file` | file (binary) \| null | No | No additional constraint declared. |
| `photo_file` | file (binary) \| null | No | No additional constraint declared. |
| `user_name` | string | No | No additional constraint declared. |
| `user_email` | string | No | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.

### POST /users/register-with-embeddings

**Purpose**

Add User Embeddings. Register a new user from already-extracted embeddings.

**Authentication**

Public.

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `user_name` | string | Yes | User name; blank values are rejected. |
| `age` | JSON value | No | Stored without additional validation. |
| `relation` | JSON value | No | Stored without additional validation. |
| `voice_embeddings` | array<array<number>> | No | Defaults to an empty list; normalized before storage. |
| `face_embeddings` | array<array<number>> | No | Defaults to an empty list. |
| `face_confidences` | array<number> | No | Defaults to zero for each face embedding. |
| `voice_qualities` | array<number> | No | Defaults to zero for each voice embedding. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### POST /users/register-with-voice

**Purpose**

Register User With Voice. Register user with 3 voice samples for speaker enrollment via Audio Service.

**Authentication**

Public.

**Content-Type**

`multipart/form-data`.

**multipart/form-data body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `name` | string | Yes | No additional constraint declared. |
| `email` | string | Yes | No additional constraint declared. |
| `audio_sample1` | file (binary) | Yes | No additional constraint declared. |
| `audio_sample2` | file (binary) | Yes | No additional constraint declared. |
| `audio_sample3` | file (binary) | Yes | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.

### GET /users/search/{user_name}

> **Internal Service Endpoint**

**Purpose**

Search User By Name. Get user data by name

**Authentication**

Internal service token.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `user_name` | path | string | Yes | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /users/session/voice

> **Simulation Integration**

**Purpose**

Create Voice Session. Issue a session only through Audio's existing speaker matcher.

**Authentication**

Public.

**Content-Type**

`multipart/form-data`.

**multipart/form-data body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `file` | file (binary) | Yes | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Source response semantics**

Success JSON fields are `user_id`, `access_token`, `token_type`, and `expires_in`; biometric rejection is `401`.

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.

### GET /users/{user_id}

**Purpose**

Get User By Id. Get user profile by user_id.

**Authentication**

Bearer session owning the user, or internal token plus matching trusted-user header.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `user_id` | path | string | Yes | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### DELETE /users/{user_id}

**Purpose**

Delete User. Delete a user's Central profile, conversation/outbox data, and RAG context.

**Authentication**

Bearer session owning the user, or internal token plus matching trusted-user header.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `user_id` | path | string | Yes | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /users/{user_id}/append-embeddings

**Purpose**

Append User Embeddings. Append new embeddings to existing user (used for improve training).

**Authentication**

Bearer session owning the user, or internal token plus matching trusted-user header.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `user_id` | path | string | Yes | No additional constraint declared. |

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `voice_embeddings` | array<array<number>> | Yes | New voice embeddings to append. |
| `face_embeddings` | array<array<number>> | Yes | New face embeddings to append. |
| `face_confidences` | array<number> | No | Confidence values appended with face embeddings. |
| `voice_qualities` | array<number> | No | Quality values appended with voice embeddings. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /users/{user_id}/conversation-history

> **Legacy / Compatibility Endpoint** Hidden from OpenAPI. Always returns `410 Gone`; use `GET /users/{user_id}/conversations`.

**Purpose**

Retired User Conversation History. Transition response for the retired embedded-history resource.

**Authentication**

Bearer session owning the user, or internal token plus matching trusted-user header.

**Response**

`410 Gone` with error code `CONVERSATION_HISTORY_RETIRED` and a message directing callers to the durable conversations endpoint.

**Important status codes**

- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /users/{user_id}/conversations

**Purpose**

Get User Conversations Endpoint. Retrieve conversations for a user.

**Authentication**

Bearer session owning the user, or internal token plus matching trusted-user header.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `user_id` | path | string | Yes | No additional constraint declared. |
| `limit` | query | integer | No | default: 10; min: 1; max: 500 |
| `start_date` | query | string \| null | No | No additional constraint declared. |
| `end_date` | query | string \| null | No | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /users/{user_id}/conversations

**Purpose**

Store User Conversation. Store a new conversation for a user.

**Authentication**

Bearer session owning the user, or internal token plus matching trusted-user header.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `user_id` | path | string | Yes | No additional constraint declared. |

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `user_message` | string | Yes | Non-blank user message. |
| `assistant_response` | string | Yes | Non-blank assistant response. |
| `language` | string | No | Defaults to `en`. |
| `metadata` | object | No | Defaults to `{}`. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### DELETE /users/{user_id}/conversations

**Purpose**

Delete All User Conversations. Delete all conversations for a user (e.g., for privacy/account deletion).

**Authentication**

Bearer session owning the user, or internal token plus matching trusted-user header.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `user_id` | path | string | Yes | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### PUT /users/{user_id}/embeddings

**Purpose**

Update User Embeddings. Replace user embeddings entirely (used for re-enrollment).

**Authentication**

Bearer session owning the user, or internal token plus matching trusted-user header.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `user_id` | path | string | Yes | No additional constraint declared. |

**Content-Type**

`application/json`.

**application/json body**

Declared type: `object`. The application does not declare named body fields in OpenAPI.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

# Vision Service

## Base URL

`https://<host>:8001`

## Authentication

Public and protected routes coexist. Protected rules used in this service: Internal service token.

## Endpoints

### GET /

> **Simulation Integration**

**Purpose**

Health Check Root. Root endpoint - service information
From Vision-Nexus

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object fields: `service`, `version`, `status`, `features`, `timestamp` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /api/face-data

> **Internal Service Endpoint**

**Purpose**

Get Face Data. Get current real-time face data
Useful for web UI polling

**Authentication**

Internal service token.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object fields: `face_count`, `primary_emotion`, `confidence`, `timestamp` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /api/v1/analyze/complete

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Complete Analysis. Complete analysis of current camera frame.

**Authentication**

Internal service token.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `detector_backend` | query | string | No | default: `opencv` |
| `model_name` | query | string | No | default: `Facenet` |

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object fields: `status`, `timestamp`, `frame_width`, `frame_height`, `faces_detected`, `faces`, `objects_detected`, `objects` |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /api/v1/detect/faces

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Detect Faces From Camera. Detect faces from camera feed.

**Authentication**

Internal service token.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `detector_backend` | query | string | No | Face detection algorithm (default: `opencv`) |
| `model_name` | query | string | No | Embedding model name (default: `Facenet`) |

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object fields: `status`, `timestamp`, `frame_width`, `frame_height`, `faces_detected`, `faces` |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /api/v1/detect/faces/upload

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Detect Faces From Upload. Detect faces from uploaded image.

**Authentication**

Internal service token.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `detector_backend` | query | string | No | default: `opencv` |
| `model_name` | query | string | No | default: `Facenet` |

**Content-Type**

`multipart/form-data`.

**multipart/form-data body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `file` | file (binary) | Yes | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object fields: `status`, `timestamp`, `frame_width`, `frame_height`, `faces_detected`, `faces` |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /api/v1/detect/objects

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Detect Objects From Camera. Detect and embed camera objects without invoking the face pipeline.

**Authentication**

Internal service token.

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object fields: `status`, `timestamp`, `frame_width`, `frame_height`, `objects_detected`, `detections` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /api/v1/detect/objects/signature/upload

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Signature From Upload. Embed an explicitly selected ROI; no YOLO class is required.

**Authentication**

Internal service token.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `x` | query | integer | Yes | min: 0 |
| `y` | query | integer | Yes | min: 0 |
| `width` | query | integer | Yes | No additional constraint declared. |
| `height` | query | integer | Yes | No additional constraint declared. |

**Content-Type**

`multipart/form-data`.

**multipart/form-data body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `file` | file (binary) | Yes | No additional constraint declared. |

**Verified media constraints**

The uploaded image has the same size/pixel limits as object upload. The selected ROI must be at least 16x16 pixels and remain inside the decoded image.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object fields: `status`, `bounding_box`, `instance_embedding`, `instance_embedding_model`, `instance_embedding_dimension`, `instance_embedding_version` |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /api/v1/detect/objects/upload

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Detect Objects From Upload. Object-only detection on an uploaded photo; same model and vector path as camera.

**Authentication**

Internal service token.

**Content-Type**

`multipart/form-data`.

**multipart/form-data body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `file` | file (binary) | Yes | No additional constraint declared. |

**Verified media constraints**

The uploaded image must decode successfully, be at most `VISION_MAX_OBJECT_UPLOAD_BYTES` (default 10,000,000 bytes), and contain at most `VISION_MAX_OBJECT_IMAGE_PIXELS` (default 16,000,000 pixels).

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object fields: `status`, `timestamp`, `frame_width`, `frame_height`, `objects_detected`, `detections` |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /api/v1/frame

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Capture Call Frame. Capture one JPEG through the existing camera context using a call lease.

**Authentication**

Internal service token.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `lease_id` | query | string | Yes | min length: 1 |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json`, `image/jpeg` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Source response semantics**

Success is raw JPEG bytes (`image/jpeg`).

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /camera/pause

> **Internal Service Endpoint**

**Purpose**

Pause Camera. Pause camera - stop capturing frames

**Authentication**

Internal service token.

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object fields: `status`, `message` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /camera/resume

> **Internal Service Endpoint**

**Purpose**

Resume Camera. Resume camera - start capturing frames

**Authentication**

Internal service token.

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object fields: `status`, `message` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /health

> **Simulation Integration**

**Purpose**

Health Check Detailed. Detailed health check endpoint
Return readiness without acquiring hardware; camera is intentionally not probed.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object fields: `status`, `camera`, `face_model`, `object_model`, `instance_model`, `opencv_version`, `emotion_detection`, `timestamp` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Source response semantics**

Returns `503` if the resource pool is absent. Otherwise HTTP `200` contains `status: "healthy"` only when required models are ready, or `status: "degraded"`; camera is deliberately reported as `not_checked`.

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /live

> **Internal Service Endpoint**

**Purpose**

Live View. HTML page for live video streaming
From Vision-Nexus /live endpoint

**Authentication**

Internal service token.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `text/html` | Successful Response; HTML live-view page |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Source response semantics**

Success is the browser viewer page (`text/html`).

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /stream

> **Internal Service Endpoint**

**Purpose**

Stream Video. MJPEG stream with face detection and emotion overlays
From Vision-Nexus streaming endpoint

**Authentication**

Internal service token.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `multipart/x-mixed-replace; boundary=frame` | Successful Response; long-lived MJPEG stream |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Source response semantics**

Success is a long-lived MJPEG stream (`multipart/x-mixed-replace; boundary=frame`).

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

# Audio Service

## Base URL

`https://<host>:8002`

## Authentication

Public and protected routes coexist. Protected rules used in this service: Bearer session owning `user_id`, or internal token plus matching trusted-user header; Internal service token; Public with default `event_mode=false`; internal service token required when `event_mode=true`.

## Endpoints

### GET /

> **Simulation Integration**

**Purpose**

Root. Root endpoint for health check.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /api/v1/conversation-state

**Purpose**

Get Conversation State. Get current conversation state and timeout status.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object fields: `state`, `duration_seconds`, `elapsed_time_seconds`, `timeout_seconds`, `timed_out` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### POST /api/v1/conversation/end

> **Simulation Integration**

**Purpose**

End Continuous Conversation. End continuous conversation session.

**Authentication**

Bearer session owning `user_id`, or internal token plus matching trusted-user header.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `user_id` | query | string | Yes | No additional constraint declared. |

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /api/v1/conversation/metrics

**Purpose**

Get Orchestration Metrics. Get orchestration performance metrics.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### POST /api/v1/conversation/start

> **Simulation Integration**

**Purpose**

Start Continuous Conversation. Start continuous conversation session.

**Authentication**

Bearer session owning `user_id`, or internal token plus matching trusted-user header.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `user_id` | query | string | Yes | No additional constraint declared. |

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /api/v1/conversation/turn

> **Simulation Integration**

**Purpose**

Process Conversation Turn. Process complete conversation turn end-to-end.

**Authentication**

Bearer session owning `user_id`, or internal token plus matching trusted-user header.

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `user_id` | string | Yes | No additional constraint declared. |
| `audio_file_path` | string | Yes | No additional constraint declared. |
| `language` | string | No | default: `en` |
| `speaker_id` | string | No | default: `jenny` |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object fields: `success`, `user_text`, `llm_response`, `audio_file`, `duration_ms`, `language`, `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### DELETE /api/v1/delete-audio/{filename}

**Purpose**

Delete Audio Endpoint. Delete a specific audio file.

**Authentication**

Public.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `filename` | path | string | Yes | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Audio file deleted successfully; object fields: `status`, `message`, `filename` |
| `404` | `application/json` | File not found; object fields: `status`, `message`, `error_type` |
| `500` | `application/json` | Internal server error; object fields: `status`, `message`, `error_type` |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `404`, `500`, `422`, `400`, `401`, `403`, `409`, `429`.

### POST /api/v1/enroll-speaker

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Enroll Speaker. Enroll a new speaker for voice verification.

**Authentication**

Internal service token.

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `user_id` | string | Yes | Unique identifier for the speaker |
| `duration` | number \| null | No | Duration in seconds for voice sample recording (default: 5.0) |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `201` | `application/json` | Speaker enrolled successfully; object fields: `status`, `message`, `user_id`, `audio_file`, `embedding_size`, `voice_embedding`, `timestamp` |
| `400` | `application/json` | Invalid request parameters; object fields: `status`, `message`, `error_type` |
| `500` | `application/json` | Enrollment failed; object fields: `status`, `message`, `error_type` |
| `422` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `201`, `400`, `500`, `422`, `401`, `403`, `404`, `409`, `429`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /api/v1/enroll-speaker-files

> **Simulation Integration**

**Purpose**

Enroll speaker with uploaded audio files. Enroll a speaker using uploaded audio files (alternative to microphone recording).

**Authentication**

Public.

**Content-Type**

`application/json`.

**application/json body**

Declared type: `object`. The application does not declare named body fields in OpenAPI.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `201` | `application/json` | Successful Response; object fields: `status`, `message`, `user_id`, `audio_file`, `embedding_size`, `voice_embedding`, `timestamp` |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `201`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.

### POST /api/v1/interrupt-playback

**Purpose**

Interrupt Playback. Interrupt current audio playback (stop TTS).

**Authentication**

Public.

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /api/v1/list-audio

**Purpose**

List Audio Endpoint. List all saved audio files.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Audio files retrieved successfully; object fields: `status`, `count`, `files` |
| `500` | `application/json` | Internal server error; object fields: `status`, `message`, `error_type` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `500`, `400`, `401`, `403`, `404`, `409`, `422`, `429`.

### GET /api/v1/orchestration/health

> **Simulation Integration**

**Purpose**

Orchestration Health. Check orchestration system health.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /api/v1/orchestration/test/end-to-end

**Purpose**

Test End To End. Test complete orchestration pipeline.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### POST /api/v1/playback/start

> **Internal Service Endpoint**

**Purpose**

Start Playback. Play a supplied WAV through Audio's existing playback manager.

**Authentication**

Internal service token.

**Content-Type**

`multipart/form-data`.

**multipart/form-data body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `file` | file (binary) | Yes | No additional constraint declared. |

**Verified media constraints**

Upload guard: multipart body, `Content-Length` required, maximum request size 10 MiB.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /api/v1/poll-stop-word

**Purpose**

Poll Stop Word. Poll for stop word detection events.

**Authentication**

Public.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `timeout` | query | number | No | default: 1.0; min: 0.1; max: 60.0 |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.

### POST /api/v1/process-command

**Purpose**

Process Command. Complete command processing pipeline.

**Authentication**

Public.

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `audio_file` | string | Yes | Path to command audio file |
| `verify_speaker` | boolean \| null | No | Whether to perform speaker verification (default: `True`) |
| `language` | string \| null | No | Language for transcription (default: `auto`) |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Command processed successfully; object fields: `status`, `text`, `language`, `user_id`, `speaker_confidence`, `is_verified`, `audio_file`, `duration`, `timestamp`, `success` |
| `400` | `application/json` | Invalid request parameters; object fields: `status`, `message`, `error_type` |
| `500` | `application/json` | Processing failed; object fields: `status`, `message`, `error_type` |
| `422` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `500`, `422`, `401`, `403`, `404`, `409`, `429`.

### POST /api/v1/process-pipeline

**Purpose**

Complete voice processing pipeline. Complete end-to-end voice processing pipeline.

**Authentication**

Public.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `send_to_backend` | query | boolean | No | default: `True` |

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.

### POST /api/v1/process-voice

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Process Voice File. Extract voice embedding from uploaded audio file.

**Authentication**

Internal service token.

**Content-Type**

`multipart/form-data`.

**multipart/form-data body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `file` | file (binary) | Yes | No additional constraint declared. |

**Verified media constraints**

Upload guard: multipart body, `Content-Length` required, maximum request size 10 MiB. Source accepts WAV/MP3 through the audio loader; it does not enforce one fixed sample rate for this upload.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Voice embedding extracted successfully; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Invalid audio file; object fields: `status`, `message`, `error_type` |
| `500` | `application/json` | Processing failed; object fields: `status`, `message`, `error_type` |
| `422` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |

**Source response semantics**

Success JSON fields returned by source are `status`, `voice_embedding`, `embedding_size`, `quality_score`, `voice_detected`, `duration`, `sample_rate`, and `timestamp`.

**Important status codes**

- Declared by the active application: `200`, `400`, `500`, `422`, `401`, `403`, `404`, `409`, `429`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /api/v1/record

**Purpose**

Record Audio Endpoint. Record audio from the system microphone and save to file.

**Authentication**

Public.

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `duration` | number \| null | No | Recording duration in seconds (default: 5.0) |
| `sample_rate` | integer \| null | No | Audio sample rate in Hz (default: 16000) |
| `channels` | integer \| null | No | Number of audio channels (1=mono, 2=stereo) (default: 1) |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `201` | `application/json` | Audio recorded successfully; object fields: `status`, `message`, `file_name`, `filepath`, `duration`, `sample_rate`, `channels`, `file_size`, `timestamp` |
| `400` | `application/json` | Invalid request parameters; object fields: `status`, `message`, `error_type` |
| `500` | `application/json` | Internal server error; object fields: `status`, `message`, `error_type` |
| `422` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `201`, `400`, `500`, `422`, `401`, `403`, `404`, `409`, `429`.

### POST /api/v1/record-until-silence

**Purpose**

Record Until Silence. Record audio until silence is detected using VAD.

**Authentication**

Public.

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object fields: `success`, `audio_file`, `duration`, `stopped_by`, `end_reason`, `chunks_recorded`, `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### POST /api/v1/record-until-silence/audio

> **Internal Service Endpoint**

**Purpose**

Record Until Silence Audio. Capture one VAD-delimited utterance and return transient WAV bytes.

**Authentication**

Internal service token.

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `audio/wav` | VAD-delimited microphone recording; file (binary) |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Source response semantics**

Success is raw VAD-delimited WAV bytes (`audio/wav`) with `X-Audio-Duration-Seconds` and `X-Audio-Sample-Rate` headers.

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /api/v1/set-detection-mode

**Purpose**

Set Detection Mode. Set detection mode: 'idle' (wake word only) or 'conversation' (stop word only).

**Authentication**

Public.

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `mode` | string | No | default: `idle` |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.

### POST /api/v1/speaker-sync

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Sync Speakers From Central. Build and persist a complete candidate map before publishing it.

**Authentication**

Internal service token.

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Speaker sync completed successfully; JSON value; no named response fields are declared in OpenAPI |
| `500` | — | Sync failed; No response body. |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `500`, `400`, `401`, `403`, `404`, `409`, `422`, `429`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /api/v1/speakers

> **Simulation Integration**

**Purpose**

List Enrolled Speakers. Get list of all enrolled speakers.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Speakers list retrieved successfully; object fields: `status`, `count`, `speakers` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /api/v1/speakers/debug

> **Simulation Integration**

**Purpose**

Debug Speakers. DEBUG ENDPOINT: Get detailed information about current speaker embeddings state.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Debug info about current speaker state; JSON value; no named response fields are declared in OpenAPI |
| `500` | — | Debug retrieval failed; No response body. |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `500`, `400`, `401`, `403`, `404`, `409`, `422`, `429`.

### GET /api/v1/stop-word-events/status

**Purpose**

Get Stop Word Events Status. Get stop word event queue status without consuming events.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /api/v1/stt/circuit-breaker-status

**Purpose**

Get circuit breaker status. Get the current circuit breaker status (Week 3 feature)

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /api/v1/test/conversation-status

**Purpose**

Test Conversation Status. Test endpoint to check conversation state manager status.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /api/v1/test/playback-status

**Purpose**

Test Playback Status. Test endpoint to check playback manager status.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /api/v1/test/stop-word-status

**Purpose**

Test Stop Word Status. Test endpoint to check stop word detector status.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### POST /api/v1/transcribe

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Transcribe Audio. Transcribe audio file to text.

**Authentication**

Internal service token.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `language` | query | string | No | default: `auto` |

**Content-Type**

`multipart/form-data`.

**multipart/form-data body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `file` | file (binary) | Yes | No additional constraint declared. |

**Verified media constraints**

Upload guard: multipart or `application/octet-stream`, `Content-Length` required, maximum request size 10 MiB. The route's multipart implementation expects field `file`; `language` is a query parameter.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Audio transcribed successfully; object fields: `status`, `text`, `language`, `duration`, `success`, `confidence`, `timestamp` |
| `400` | `application/json` | Invalid request parameters; object fields: `status`, `message`, `error_type` |
| `500` | `application/json` | Transcription failed; object fields: `status`, `message`, `error_type` |
| `422` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `500`, `422`, `401`, `403`, `404`, `409`, `429`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /api/v1/verify-speaker

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Verify Speaker. Identify a speaker among enrolled users from uploaded audio (1:N with rejection).

**Authentication**

Internal service token.

**Content-Type**

`multipart/form-data`.

**multipart/form-data body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `file` | file (binary) | Yes | No additional constraint declared. |

**Verified media constraints**

Upload guard: multipart body, `Content-Length` required, maximum request size 10 MiB.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Speaker verification completed; object fields: `status`, `user_id`, `confidence`, `is_verified`, `threshold`, `timestamp`, `access_token`, `token_type`, `expires_in`, `decision`, `similarity`, `margin`, `top1_user`, `top1_score`, `top2_user`, `top2_score`, `required_threshold`, `required_margin`, `candidate_count` |
| `400` | `application/json` | Invalid request parameters; object fields: `status`, `message`, `error_type` |
| `500` | `application/json` | Verification failed; object fields: `status`, `message`, `error_type` |
| `422` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `500`, `422`, `401`, `403`, `404`, `409`, `429`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /api/v1/wake-word/detect

**Purpose**

Detect Wake Word And Record. Detect wake word and automatically record command audio.

**Authentication**

Public.

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Wake word detected and command audio recorded successfully; object fields: `status`, `keyword`, `detection_time`, `frames_processed`, `speech_frames`, `audio_file`, `confidence` |
| `408` | `application/json` | Wake word detection timeout; object fields: `status`, `message`, `error_type` |
| `500` | `application/json` | Wake word detection failed; object fields: `status`, `message`, `error_type` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `408`, `500`, `400`, `401`, `403`, `404`, `409`, `422`, `429`.

### POST /api/v1/wake-word/detect/simple

**Purpose**

Detect wake word (simple blocking call). Simple blocking call that waits for wake word detection.

**Authentication**

Public.

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /api/v1/wake-word/events

> **Internal Service Endpoint**

**Purpose**

Poll Wake Word Event. Consume a detection from an explicitly event-mode wake listener.

**Authentication**

Internal service token.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `timeout` | query | number | No | default: 1.0; min: 0.1; max: 60.0 |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /api/v1/wake-word/power-mode

**Purpose**

Get current power mode. Get the current power mode settings

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### POST /api/v1/wake-word/power-mode

**Purpose**

Set wake word detection power mode. Set the power mode for wake word detection (Week 3 feature)

**Authentication**

Public.

**Content-Type**

`application/json`.

**application/json body**

Declared type: `object`. The application does not declare named body fields in OpenAPI.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.

### POST /api/v1/wake-word/start

**Purpose**

Start Wake Word Detection. Start continuous wake word detection.

**Authentication**

Public with default `event_mode=false`; internal service token required when `event_mode=true`.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `event_mode` | query | boolean | No | default: `False` |

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Wake word detection started successfully; object fields: `status`, `is_listening`, `message` |
| `500` | `application/json` | Failed to start wake word detection; object fields: `status`, `message`, `error_type` |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `500`, `422`, `400`, `401`, `403`, `404`, `409`, `429`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /api/v1/wake-word/stats

**Purpose**

Get wake word detection statistics. Get statistics from wake word detection (Week 3 feature)

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /api/v1/wake-word/status

**Purpose**

Get Wake Word Status. Get current status of wake word detection.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Wake word status retrieved successfully; object fields: `status`, `is_listening`, `message` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### POST /api/v1/wake-word/stop

**Purpose**

Stop Wake Word Detection. Stop continuous wake word detection.

**Authentication**

Public.

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Wake word detection stopped successfully; object fields: `status`, `is_listening`, `message` |
| `500` | `application/json` | Failed to stop wake word detection; object fields: `status`, `message`, `error_type` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `500`, `400`, `401`, `403`, `404`, `409`, `422`, `429`.

### GET /health

> **Simulation Integration**

**Purpose**

Health Check. Health check endpoint to verify service availability.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Source response semantics**

HTTP `200` may contain `status: "healthy"` or `status: "degraded"`. It is degraded when stop-word detection is enabled but not ready; inspect `stop_word_detector` and optional `queue_processor`.

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### POST /queue/add

**Purpose**

Add To Queue. Manually add a command to the offline queue.

**Authentication**

Public.

**Content-Type**

`application/json`.

**application/json body**

Declared type: `object`. The application does not declare named body fields in OpenAPI.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.

### POST /queue/process-now

**Purpose**

Trigger Queue Processing. Manually trigger queue processing.

**Authentication**

Public.

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /queue/status

**Purpose**

Get Queue Status. Get current queue processor status.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

# TTS Service

## Base URL

`https://<host>:8003`

## Authentication

Public and protected routes coexist. Protected rules used in this service: Internal service token.

## Endpoints

### GET /cache/status

**Purpose**

Cache Status. Get worker pool cache status.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### POST /config/set_voice

**Purpose**

Set Voice. Set the default voice for synthesis with intelligent speaker switching.

**Authentication**

Public.

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `text` | string | Yes | min length: 1; max length: 5000 |
| `voice_id` | string \| null | No | No additional constraint declared. |
| `language` | string \| null | No | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.

### GET /diagnostics

**Purpose**

Get Full Diagnostics. Complete diagnostics information.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /errors

**Purpose**

Get Error Summary. Get error summary and statistics.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /errors/by_category/{category}

**Purpose**

Get Errors By Category. Get errors filtered by category.

**Authentication**

Public.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `category` | path | string | Yes | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.

### GET /errors/recent

**Purpose**

Get Recent Errors. Get recent error details.

**Authentication**

Public.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `limit` | query | integer | No | default: 20 |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.

### GET /health

> **Simulation Integration**

**Purpose**

Health Check. Basic health check endpoint.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Source response semantics**

HTTP `200` returns `status: "healthy"` when synthesis is ready and `status: "degraded"` otherwise; `voice_model` is `available` or `unavailable`.

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /health/detailed

> **Simulation Integration**

**Purpose**

Health Detailed. Detailed health check with service statistics.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Source response semantics**

Returns `503` when synthesis is not ready; otherwise `200` with `status: "healthy"` plus worker, circuit-breaker, error, and metrics state.

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /metrics

**Purpose**

Get Prometheus Metrics. Get Prometheus format metrics.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `text/plain; charset=utf-8` | Successful Response; Prometheus exposition text |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Source response semantics**

Source returns Prometheus text (`text/plain; charset=utf-8`), despite the generic JSON media type in generated OpenAPI.

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /metrics/json

**Purpose**

Get Metrics Json. Get metrics in JSON format.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### POST /speak

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Speak. Synthesize text to speech using specified voice.

**Authentication**

Internal service token.

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `text` | string | Yes | min length: 1; max length: 5000 |
| `voice_id` | string \| null | No | No additional constraint declared. |
| `language` | string \| null | No | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `audio/wav` | Successful Response; binary WAV audio with `X-Request-ID` |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Source response semantics**

Source is authoritative over the generated schema here: success is raw WAV bytes (`audio/wav`) with `X-Request-ID`, not JSON. The implementation returns `400` for invalid text/language/voice, `503` when not ready, `504` on synthesis timeout, and `500` on synthesis failure.

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /speakers/state/{speaker_id}

> **Simulation Integration**

**Purpose**

Get Speaker State. Get state of a specific speaker.

**Authentication**

Public.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `speaker_id` | path | string | Yes | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.

### GET /speakers/stats

> **Simulation Integration**

**Purpose**

Get Speakers Stats. Get speaker resource usage statistics.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /speakers/status

> **Simulation Integration**

**Purpose**

Get Speakers Status. Get status of all speakers.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### POST /speakers/switch

> **Simulation Integration**

**Purpose**

Switch Speaker. Switch to a different speaker.

**Authentication**

Public.

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `text` | string | Yes | min length: 1; max length: 5000 |
| `voice_id` | string \| null | No | No additional constraint declared. |
| `language` | string \| null | No | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.

### GET /voices

**Purpose**

List Voices. List all available voices in the TTS service.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

# TeachMe Service

## Base URL

`https://<host>:8004`

## Authentication

Public and protected routes coexist. Protected rules used in this service: Internal service token.

## Endpoints

### GET /

> **Simulation Integration**

**Purpose**

Root. Root endpoint - Service status

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### DELETE /forget-by-name/{name}

> **Internal Service Endpoint**

**Purpose**

Forget By Name. Forget items by name (for objects) or subject (for facts)

**Authentication**

Internal service token.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `name` | path | string | Yes | No additional constraint declared. |
| `item_type` | query | enum (`object`, `fact`) \| null | No | Filter by item type |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### DELETE /forget/{item_id}

> **Internal Service Endpoint**

**Purpose**

Forget Item. Forget/remove a specific knowledge item

**Authentication**

Internal service token.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `item_id` | path | string | Yes | No additional constraint declared. |
| `permanent` | query | boolean | No | Permanently delete instead of soft delete (default: `False`) |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /health

> **Simulation Integration**

**Purpose**

Health Check. Comprehensive health check endpoint

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Source response semantics**

The body status can be `healthy`, `degraded`, or `unhealthy`. The handler returns a JSON `http_code` field for its computed readiness code but does not set the HTTP response status from that field, so inspect the body even on HTTP `200`.

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /health/detailed

> **Simulation Integration**

**Purpose**

Health Detailed. Detailed system diagnostics

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /knowledge/all

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Get All Knowledge. Get all learned items

**Authentication**

Internal service token.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /knowledge/facts

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Get Facts. Get all learned facts

**Authentication**

Internal service token.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /knowledge/learn-batch

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Learn Batch. Batch learning endpoint (Phase 3 Optimization)
Learn multiple objects/facts in one call

**Authentication**

Internal service token.

**Content-Type**

`application/json`.

**application/json body**

Declared type: `array<object>`. The application does not declare named body fields in OpenAPI.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /knowledge/objects

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Get Objects. Get all learned objects

**Authentication**

Internal service token.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /knowledge/objects/recognize

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Recognize Visual Object. Resolve an exact taught object, or abstain, from a Vision vector.

**Authentication**

Internal service token.

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `embedding` | array<number> | Yes | No additional constraint declared. |
| `embedding_model` | string | Yes | No additional constraint declared. |
| `embedding_version` | integer \| null | No | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /knowledge/related/{item_id}

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Get Related Items. Find related objects through embeddings (Phase 5 Intelligence)
Returns similar objects/facts based on semantic similarity

**Authentication**

Internal service token.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `item_id` | path | string | Yes | No additional constraint declared. |
| `top_k` | query | integer | No | default: 5; min: 1; max: 20 |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /knowledge/search/advanced

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Search Advanced. Advanced multi-field search (Phase 3 Optimization)
Search across name, category, and tags
Includes graceful fallback for empty knowledge bases

**Authentication**

Internal service token.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `name` | query | string \| null | No | Search by object name |
| `category` | query | string \| null | No | Filter by category |
| `tag` | query | string \| null | No | Filter by tag |
| `search_mode` | query | string | No | Search mode: 'any' (OR) or 'all' (AND) (default: `any`) |

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /knowledge/search/embedding

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Search By Embedding. Search for similar objects using embeddings (Phase 2)
WITH caching for performance (Phase 3 Optimization)

**Authentication**

Internal service token.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `query_object_name` | query | string | Yes | Object name to search for (max length: 200) |
| `top_k` | query | integer | No | Number of results (default: 5; min: 1; max: 50) |
| `similarity_threshold` | query | number | No | Min similarity (0.0-1.0) (default: 0.5; min: 0.0; max: 1.0) |

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /knowledge/search/{name}

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Search Knowledge. Search items by name or subject

**Authentication**

Internal service token.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `name` | path | string | Yes | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /knowledge/stats

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Get Knowledge Stats. Get knowledge base statistics

**Authentication**

Internal service token.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /learn

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Learn Item. Learn new object/fact with validation, security, and embeddings
Fully async with performance tracking - PRODUCTION READY

**Authentication**

Internal service token.

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `type` | enum (`object`, `fact`) | Yes | No additional constraint declared. |
| `data` | object \| object | Yes | Learning data |
| `tags` | array<string> | No | Tags for categorization |
| `confidence` | number | No | Confidence level (default: 1.0; min: 0.0; max: 1.0) |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `201` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `201`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /metrics

**Purpose**

Get Metrics. System metrics and performance statistics (Phase 5 + Phase 4)

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

# Enrollment Service

## Base URL

`https://<host>:8005`

## Authentication

Public and protected routes coexist. Protected rules used in this service: Bearer session owning `{user_id}`, or internal token plus matching trusted-user header; Internal service token.

## Endpoints

### GET /

> **Simulation Integration**

**Purpose**

Health Check. Basic health check endpoint

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object fields: `service`, `status`, `port`, `dependencies` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /enrollment/check-user

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Check User.

**Authentication**

Internal service token.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `name` | query | string | Yes | Name of the user to check |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object fields: `exists`, `user_id`, `enrollment_date`, `sample_count` |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### DELETE /enrollment/delete-user/{user_id}

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Delete User Synchronized. Delete the selected user's records across the owning services.

**Authentication**

Internal service token.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `user_id` | path | string | Yes | Unique user ID to permanently delete |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /enrollment/enroll

> **Simulation Integration**

**Purpose**

Enroll User. Enroll a new user with 5 photos and 5 voice samples

**Authentication**

Public.

**Content-Type**

`multipart/form-data`.

**multipart/form-data body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `user_name` | string | Yes | Name of the user |
| `photos` | array<file (binary)> | Yes | Exactly 5 photos (JPG/PNG, max 5MB each) |
| `voice_samples` | array<file (binary)> | Yes | Exactly 5 voice samples (WAV/MP3, max 10MB each) |
| `age` | integer \| null | No | User's age (optional) |
| `relation` | string \| null | No | Relationship (e.g., 'Father', 'Sister') (optional) |

**Verified media constraints**

The route requires exactly five JPG/PNG photos (maximum 5 MiB each) and five WAV/MP3 voice samples (maximum 10 MiB each); the whole multipart request is guarded at 76 MiB.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object fields: `status`, `message`, `user_id`, `details`, `access_token`, `token_type`, `expires_in` |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.

### GET /enrollment/health-detailed

> **Simulation Integration**

**Purpose**

Health Check Detailed.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object fields: `service`, `status`, `port`, `dependencies` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Source response semantics**

HTTP `200` contains `status: "healthy"` only when every dependency check is true, otherwise `status: "degraded"`; inspect `dependencies`.

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### POST /enrollment/improve-training/{user_id}

> **Simulation Integration**

**Purpose**

Improve Training. Add 5 more photos and 5 more voice samples to existing user
(OLD samples are KEPT, NEW samples are ADDED)

**Authentication**

Bearer session owning `{user_id}`, or internal token plus matching trusted-user header.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `user_id` | path | string | Yes | No additional constraint declared. |

**Content-Type**

`multipart/form-data`.

**multipart/form-data body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `additional_photos` | array<file (binary)> | Yes | 5 additional photos |
| `additional_voice_samples` | array<file (binary)> | Yes | 5 additional voice samples |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object fields: `status`, `message`, `user_id`, `total_samples` |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /enrollment/storage/list

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

List Enrollments.

**Authentication**

Internal service token.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /enrollment/storage/stats

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Get Storage Stats.

**Authentication**

Internal service token.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object fields: `total_enrollments`, `storage_directory`, `encryption_enabled`, `disk_usage_mb` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /enrollment/storage/{user_id}

> **Simulation Integration**

**Purpose**

Get Enrollment Data.

**Authentication**

Bearer session owning `{user_id}`, or internal token plus matching trusted-user header.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `user_id` | path | string | Yes | User ID to retrieve |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object fields: `user_id`, `user_name`, `enrollment_data`, `saved_at` |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### DELETE /enrollment/storage/{user_id}

> **Simulation Integration**

**Purpose**

Delete Enrollment Data.

**Authentication**

Bearer session owning `{user_id}`, or internal token plus matching trusted-user header.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `user_id` | path | string | Yes | User ID to delete |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /enrollment/update-model/{user_id}

> **Simulation Integration**

**Purpose**

Update Model. Replace all old photos and voice samples with new ones (RE-ENROLLMENT)
(OLD samples are DELETED, REPLACED by NEW samples)

**Authentication**

Bearer session owning `{user_id}`, or internal token plus matching trusted-user header.

**Path/query parameters**

| Name | In | Type | Required | Description/constraints |
|---|---|---|---:|---|
| `user_id` | path | string | Yes | No additional constraint declared. |

**Content-Type**

`multipart/form-data`.

**multipart/form-data body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `new_photos` | array<file (binary)> | Yes | 5 new photos (replaces old) |
| `new_voice_samples` | array<file (binary)> | Yes | 5 new voice samples (replaces old) |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; object fields: `status`, `message`, `user_id`, `total_samples` |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### POST /enrollment/validate-photo

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Validate Photo.

**Authentication**

Internal service token.

**Content-Type**

`multipart/form-data`.

**multipart/form-data body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `file` | file (binary) | Yes | No additional constraint declared. |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /health

> **Simulation Integration**

**Purpose**

Health. Simple health check

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Source response semantics**

Always returns HTTP `200` with `status: "healthy"` and version `3.0.0`; it does not probe dependencies.

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

# LLM Service

## Base URL

`https://<host>:8006`

## Authentication

Public and protected routes coexist. Protected rules used in this service: Internal service token.

## Endpoints

### GET /

> **Simulation Integration**

**Purpose**

Root.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### POST /api/v1/format

> **Simulation Integration**

**Purpose**

Format Response.

**Authentication**

Public.

**Content-Type / request body**

No request body is declared.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Source response semantics**

This registered compatibility endpoint always returns `501 Not Implemented`; no request body is accepted.

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### POST /api/v1/generate

> **Simulation Integration**

> **Internal Service Endpoint**

**Purpose**

Generate.

**Authentication**

Internal service token.

**Content-Type**

`application/json`.

**application/json body**

| Field | Type | Required | Description/constraints |
|---|---|---:|---|
| `query` | string | Yes | min length: 1 |
| `max_tokens` | integer | No | default: 128 |
| `temperature` | number | No | default: 0.2 |
| `language` | string | No | default: `en` |

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `422` | `application/json` | Error response; object fields: `error` |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `422`, `400`, `401`, `403`, `404`, `409`, `429`, `500`.
- `401` when authentication enforcement is enabled and required credentials are absent or invalid; ownership checks can return `403`.

### GET /api/v1/health

> **Simulation Integration**

**Purpose**

Health.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Source response semantics**

The body always uses `status: "healthy"`; actual provider readiness is in boolean `openrouter` and `capability_status`, which is `available` or `degraded`.

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

### GET /api/v1/model-info

**Purpose**

Model Info.

**Authentication**

Public.

**Response**

| Status | Media type | Contract |
|---:|---|---|
| `200` | `application/json` | Successful Response; JSON value; no named response fields are declared in OpenAPI |
| `400` | `application/json` | Error response; object fields: `error` |
| `401` | `application/json` | Error response; object fields: `error` |
| `403` | `application/json` | Error response; object fields: `error` |
| `404` | `application/json` | Error response; object fields: `error` |
| `409` | `application/json` | Error response; object fields: `error` |
| `422` | `application/json` | Error response; object fields: `error` |
| `429` | `application/json` | Error response; object fields: `error` |
| `500` | `application/json` | Error response; object fields: `error` |

**Important status codes**

- Declared by the active application: `200`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`.

# Integration examples

The CA path below is the repository-local development CA. Replace hosts and credentials for deployment.

## Create a voice-authenticated Central session

```bash
curl --cacert config/certificates/nexi-local-ca.crt -X POST "https://localhost:8000/users/session/voice" \
  -F "file=@sample.wav"
```

## Verify a speaker through Audio

```bash
curl --cacert config/certificates/nexi-local-ca.crt -X POST "https://localhost:8002/api/v1/verify-speaker" \
  -H "X-NEXI-Service-Token: <service-token>" \
  -F "file=@sample.wav"
```

## Submit a restricted RAG query

```bash
curl --cacert config/certificates/nexi-local-ca.crt -X POST "https://localhost:8000/api/v1/rag/query" \
  -H "Authorization: Bearer <session-jwt>" \
  -H "Content-Type: application/json" \
  -d '{"query":"What did I teach you about the red mug?"}'
```

## Synthesize speech

```bash
curl --cacert config/certificates/nexi-local-ca.crt -X POST "https://localhost:8003/speak" \
  -H "X-NEXI-Service-Token: <service-token>" \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello from NEXI"}' --output response.wav
```

# Cross-service flows supported by source

## Returning-user voice interaction

`simulation/client` -> Central `POST /users/session/voice` -> Audio `POST /api/v1/verify-speaker` -> session JWT -> Central `POST /api/v1/rag/query` -> TeachMe retrieval -> LLM `POST /api/v1/generate` when needed -> TTS `POST /speak`.

## Continuous audio conversation

`simulation/client` -> Audio `POST /api/v1/conversation/start` -> `POST /api/v1/conversation/turn` -> Central/TeachMe/LLM/TTS orchestration -> Audio `POST /api/v1/conversation/end`.

## Teach and recognize an object

`simulation/client` -> Vision `POST /api/v1/detect/objects/signature/upload` (or camera detection) -> TeachMe `POST /learn`; recognition uses Vision signature/detection data with TeachMe `POST /knowledge/objects/recognize`. These are the production routes; no simulation-only API exists.

## Enrollment

`simulation/client` -> Enrollment `POST /enrollment/validate-photo` as needed -> `POST /enrollment/enroll` -> Vision face processing + Audio speaker enrollment + Central user persistence. Training updates use the owner-protected improve/update endpoints.

# 3D Simulation Quick Start

1. Check `GET /health` on ports 8000–8005 and `GET /api/v1/health` on port 8006. A `200` can still contain `degraded`; inspect the body.
2. Keep `X-NEXI-Service-Token` server-side. Obtain a user bearer token through Central `POST /users/session/voice` or successful Enrollment output.
3. Use the bearer token for Central RAG and owner-scoped user/session calls. When a trusted backend acts for a user, send both internal-token and trusted-user headers where documented.
4. For audio, call Audio transcription/verification routes with the exact multipart field tables above; continuous interaction uses the three `/api/v1/conversation/*` routes.
5. For vision, use upload routes when the simulation owns an encoded image and camera routes only when NEXI owns the physical camera lease.
6. Teach and retrieve through TeachMe's `/learn` and `/knowledge/*` routes, normally from a trusted backend.
7. Send final text to TTS `POST /speak`; treat its response media type exactly as declared above.

# Route inventory and verification

| Service | GET | POST | PUT/PATCH | DELETE | Total active routes |
|---|---:|---:|---:|---:|---:|
| Central Server | 24 | 26 | 1 | 3 | 54 |
| Vision Service | 6 | 8 | 0 | 0 | 14 |
| Audio Service | 20 | 24 | 0 | 1 | 45 |
| TTS Service | 13 | 3 | 0 | 0 | 16 |
| TeachMe Service | 10 | 5 | 0 | 2 | 17 |
| Enrollment Service | 7 | 4 | 0 | 2 | 13 |
| LLM Service | 3 | 2 | 0 | 0 | 5 |

**Total active routes documented: 164.** Each active non-framework `APIRoute` appears exactly once above.

## Source/OpenAPI discrepancies

- **Central Server:** checked-in `docs/openapi/central.json` is stale. Current-only: `DELETE /api/v1/rag/sessions/{session_id}`, `POST /api/v1/rag/commands/stop`, `POST /api/v1/rag/sessions`. Snapshot-only: none.
- **Vision Service:** checked-in `docs/openapi/vision.json` is stale. Current-only: `POST /api/v1/detect/objects/signature/upload`, `POST /api/v1/detect/objects/upload`. Snapshot-only: none.
- **Audio Service:** checked-in `docs/openapi/audio.json` is stale. Current-only: `GET /api/v1/wake-word/events`, `POST /api/v1/record-until-silence/audio`. Snapshot-only: none.
- **TeachMe Service:** checked-in `docs/openapi/teachme.json` is stale. Current-only: `POST /knowledge/objects/recognize`. Snapshot-only: none.
- **Enrollment Service:** checked-in `docs/openapi/enrollment.json` is stale. Current-only: `DELETE /enrollment/delete-user/{user_id}`, `POST /enrollment/validate-photo`. Snapshot-only: `DELETE /enrollment/delete-user/{user_name}`.
- Central has five active schema-hidden compatibility routes: `GET /teachme/search/{query}`, `POST /teachme/search/embedding`, `GET /users/{user_id}/conversation-history`, `POST /users/add-embeddings`, and `POST /users/data/add_user`. They are documented above and included in the route count.
- Decorated routes in unmounted Central modules (`verification_endpoints.py` and `routes/audio_orchestration.py`, `routes/enrollment_orchestration.py`, `routes/teachme_routes.py`, `routes/tts_routes.py`, `routes/vision_routes.py`) are not active and are intentionally excluded.
- `03_audio_service/api.py` constructs a separate legacy FastAPI app, but the configured service entrypoint is `03_audio_service/main.py`; its duplicate unmounted routes are not part of the active Audio Service and are intentionally excluded.

## Verification status

- Source registration and isolated application-object route-table audit: **PASS**.
- Current OpenAPI regenerated in memory with each service's isolated interpreter: **PASS**.
- Checked-in OpenAPI snapshot comparison: **PASS, with the stale differences listed above**.
- Generated OpenAPI/runtime-media discrepancy: TTS `POST /speak` declares JSON but source returns `audio/wav`; TTS `GET /metrics`, Vision `GET /stream`, and Vision `GET /live` likewise have more specific source media types documented at their endpoints.
- Live network `/openapi.json` comparison: see final handover; no claim is made here unless the seven HTTPS listeners were available during this audit.
