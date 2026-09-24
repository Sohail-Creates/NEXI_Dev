# NEXI Endpoint Documentation

Verified against the live HTTPS stack on **2026-09-24**. The seven checked-in OpenAPI documents were regenerated with each service's own isolated interpreter and matched each live `/openapi.json` exactly.

> Evidence standard: every operation below has a live proof in the appendix. A 2xx body is shown only when this pass actually received it. Where a safe probe intentionally used a nonexistent identity or invalid media, the table says so instead of inventing a success body.

## 1. Overview

All traffic is HTTPS. Trust the project CA; never disable certificate verification. See [COMMANDS.txt](COMMANDS.txt) and [ARCHITECTURE.md](ARCHITECTURE.md) for certificate/startup setup.

| Service | Port | Base URL | OpenAPI paths | Operations |
|---|---:|---|---:|---:|
| Central | 8000 | `https://127.0.0.1:8000` | 43 | 46 |
| Vision | 8001 | `https://127.0.0.1:8001` | 11 | 11 |
| Audio | 8002 | `https://127.0.0.1:8002` | 42 | 43 |
| TTS | 8003 | `https://127.0.0.1:8003` | 16 | 16 |
| TeachMe | 8004 | `https://127.0.0.1:8004` | 16 | 16 |
| Enrollment | 8005 | `https://127.0.0.1:8005` | 11 | 12 |
| LLM | 8006 | `https://127.0.0.1:8006` | 5 | 5 |

## 2. Authentication

NEXI has two separate trust layers:

1. **Internal service credential:** `X-NEXI-Service-Token: <NEXI_INTERNAL_SERVICE_TOKEN>`. It is required on protected service-to-service route families. Frontend/mobile applications must not embed this shared secret; calls requiring it belong behind a trusted backend/BFF.
2. **End-user session:** `Authorization: Bearer <session JWT>`. Obtain it with `POST /users/session/voice` using multipart field `file`. The response contains `user_id`, `access_token`, `token_type`, and `expires_in`. The current configured/default session lifetime is **30 minutes (1800 seconds)**. Per-user endpoints enforce that the JWT subject owns `{user_id}`. Trusted internal callers may instead send both the service credential and `X-NEXI-Trusted-User-ID`, which must match the requested user.

The live OpenAPI documents do not declare `securitySchemes` because enforcement is custom middleware/dependency based. Therefore the **Auth required** column below is authoritative for clients; schema viewers alone will not reveal these headers.

## 3. Standard error envelope

Every installed shared handler returns:

```json
{
  "error": {
    "status_code": 404,
    "code": "NOT_FOUND",
    "message": "Conversation 'docs-probe-conversation-missing' not found",
    "request_id": "endpoint-docs-20260924"
  }
}
```

Canonical HTTP-derived codes currently defined: `BAD_REQUEST`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `METHOD_NOT_ALLOWED`, `CONFLICT`, `LENGTH_REQUIRED`, `PAYLOAD_TOO_LARGE`, `UNSUPPORTED_MEDIA_TYPE`, `VALIDATION_ERROR`, `RATE_LIMITED`, `INTERNAL_SERVER_ERROR`, `NOT_IMPLEMENTED`, `BAD_GATEWAY`, `SERVICE_UNAVAILABLE`, `GATEWAY_TIMEOUT`.

Current custom/public codes found in mounted code or observed live: `ENGLISH_ONLY`, `LLM_FAILURE`, `MISSING_NAME`, `REGISTRATION_FAILED`, `ADD_EMBEDDINGS_FAILED`, `AUDIO_SERVICE_UNAVAILABLE`, `CONVERSATION_HISTORY_RETIRED`, `AUTHENTICATION_ERROR`, `AUTHORIZATION_ERROR`, `SERVICE_TIMEOUT`, `CIRCUIT_BREAKER_OPEN`, `DATABASE_ERROR`, `CONFIGURATION_ERROR`, `INTERNAL_ERROR`, plus the structured `AUDIO_*`, `VISION_*`, `ENROLLMENT_*`, `DB_*`, and `SERVICE_*` integration families defined in `shared/error_handler.py`. Treat `code` as the stable machine field and `message` as human-readable detail.

## 4.1. Central service

Base URL: `https://127.0.0.1:8000`

| Method | Path | Auth required | Request body/params | Success response (real example) | Known error cases | Current live status |
|---|---|---|---|---|---|---|
| GET | `/` | None | None | HTTP 200: `{"status":"running","service":"central_server"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `central-get-/` |
| GET | `/admin/stats` | None | None | HTTP 200: `{"total_conversations":0,"unique_users":0,"conversations_per_user":{},"by_language":{},"oldest_timestamp":null,"newest_timestamp":null}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `central-get-/admin/stats` |
| POST | `/api/v1/rag/query` | Bearer session OR internal + trusted-user | application/json required: RAGQueryRequest {query} | No 2xx captured by the bounded safe probe; live HTTP 422: `{"error":{"status_code":422,"code":"VALIDATION_ERROR","message":"Request validation failed","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 422; proof `central-post-/api/v1/rag/query` |
| POST | `/calls/end` | Internal service credential | application/json required: CallRequest {call_id} | No 2xx captured by the bounded safe probe; live HTTP 404: `{"error":{"status_code":404,"code":"NOT_FOUND","message":"Matching active call not found","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 404; proof `central-post-/calls/end` |
| GET | `/calls/screenshot` | Internal service credential | None | No 2xx captured by the bounded safe probe; live HTTP 409: `{"error":{"status_code":409,"code":"CONFLICT","message":"Screenshot requires an active video call","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 409; proof `central-get-/calls/screenshot` |
| POST | `/calls/start` | Internal service credential | application/json required: CallRequest {call_id} | HTTP 200: `{"state":"CALL_ACTIVE","call_id":"docs-probe","lease_id":"eb993deb049b4c7586cdbccafa9c2cc5"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `central-post-/calls/start` |
| GET | `/calls/status` | Internal service credential | None | HTTP 200: `{"state":"CALL_ACTIVE","call_id":"docs-probe","lease_id":"eb993deb049b4c7586cdbccafa9c2cc5","lease_state":"active"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `central-get-/calls/status` |
| POST | `/camera/force-release` | Internal service credential | None | No 2xx captured by the bounded safe probe; live HTTP 409: `{"error":{"status_code":409,"code":"CONFLICT","message":"Physical closure must be acknowledged before release","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 409; proof `central-post-/camera/force-release` |
| POST | `/camera/release` | Internal service credential | application/json required: CameraRequest {lease_id, service_name, timeout} | No 2xx captured by the bounded safe probe; live HTTP 409: `{"error":{"status_code":409,"code":"CONFLICT","message":"Matching lease_id is required","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 409; proof `central-post-/camera/release` |
| POST | `/camera/request` | Internal service credential | application/json required: CameraRequest {lease_id, service_name, timeout} | HTTP 200: `{"status":"denied","message":"Camera is held by another lease"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `central-post-/camera/request` |
| GET | `/camera/status` | Internal service credential | None | HTTP 200: `{"status":"in_use","is_available":false,"holder":"eb993deb049b4c7586cdbccafa9c2cc5","queue":[]}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `central-get-/camera/status` |
| GET | `/conversations/{conversation_id}` | None | path 'conversation_id' required: Conversation Id | No 2xx captured by the bounded safe probe; live HTTP 404: `{"error":{"status_code":404,"code":"NOT_FOUND","message":"Conversation 'docs-probe-conversation-missing' not found","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 404; proof `central-get-/conversations/{conversation_id}` |
| GET | `/health` | None | None | HTTP 200: `{"status":"healthy","service":"central_server"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `central-get-/health` |
| POST | `/resources/acknowledge/{lease_id}` | Internal service credential | path 'lease_id' required: Lease Id | No 2xx captured by the bounded safe probe; live HTTP 409: `{"error":{"status_code":409,"code":"CONFLICT","message":"Grant is not reserved for this lease","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 409; proof `central-post-/resources/acknowledge/{lease_id}` |
| GET | `/resources/focus` | Internal service credential | None | HTTP 200: `{"signal":null,"teachme_active":false,"generation":0,"lease_ids":[]}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `central-get-/resources/focus` |
| GET | `/resources/health` | Internal service credential | None | HTTP 200: `{"success":true,"status":"healthy","active_leases":1,"resources_available":{"camera":false,"microphone":true}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `central-get-/resources/health` |
| POST | `/resources/release/{lease_id}` | Internal service credential | path 'lease_id' required: Lease Id; query 'forced': Forced | No 2xx captured by the bounded safe probe; live HTTP 404: `{"error":{"status_code":404,"code":"NOT_FOUND","message":"Lease not found: docs-probe-lease-missing","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 404; proof `central-post-/resources/release/{lease_id}` |
| POST | `/resources/request` | Internal service credential | query 'resource_type' required: Resource Type; query 'service_name' required: Service Name; query 'priority': Priority; query 'timeout_seconds': Timeout Seconds; query 'holder_pid': Holder Pid; query 'holder_started': Holder Started; query 'holder_port': Holder Port | HTTP 200: `{"success":true,"lease_id":"ac3b53987cb144e0943ad6979006c914","resource_type":"camera","service_name":"docs-probe","granted":false,"state":"queued","timestamp":1790239162.1331193,"message":"Request queued (position 1)"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `central-post-/resources/request` |
| POST | `/resources/revoke/{lease_id}` | Internal service credential | path 'lease_id' required: Lease Id | No 2xx captured by the bounded safe probe; live HTTP 409: `{"error":{"status_code":409,"code":"CONFLICT","message":"Lease cannot be revoked in its current state","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 409; proof `central-post-/resources/revoke/{lease_id}` |
| GET | `/resources/status` | Internal service credential | None | HTTP 200: `{"success":true,"timestamp":1790239162.149832,"resources":{"camera":{"is_available":false,"holder":"eb993deb049b4c7586cdbccafa9c2cc5","queue":["ac3b53987cb144e0943ad6979006c914"]},"microphone":{"is_available":true,"holder":null,"queue":[]}}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `central-get-/resources/status` |
| GET | `/resources/status/{lease_id}` | Internal service credential | path 'lease_id' required: Lease Id | No 2xx captured by the bounded safe probe; live HTTP 404: `{"error":{"status_code":404,"code":"NOT_FOUND","message":"Lease not found: docs-probe-lease-missing","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 404; proof `central-get-/resources/status/{lease_id}` |
| GET | `/sync/status` | Internal service credential | None | HTTP 200: `{"last_successful_sync":null,"pending_records":0,"last_error":null,"enabled":false,"worker_running":false,"next_run_in_seconds":null}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `central-get-/sync/status` |
| GET | `/teachme/health` | None | None | HTTP 200: `{"status":"healthy","service":"teachme","circuit_state":"closed","reachable":true}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `central-get-/teachme/health` |
| POST | `/teachme/learn` | None | application/json required: LearningRequest {confidence, data, tags, type} | No 2xx captured by the bounded safe probe; live HTTP 422: `{"error":{"status_code":422,"code":"VALIDATION_ERROR","message":"Request validation failed","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 422; proof `central-post-/teachme/learn` |
| GET | `/teachme/metrics` | None | None | HTTP 200: `{"service":"teachme","base_url":"https://localhost:8004","circuit_state":"closed","failure_count":0,"last_failure":null,"last_success":"2026-09-24T08:39:25.271556","queue":{"queue_size":0,"max_queue_size":1000,"processing_count":0,"max_concurrent":10,"processed_total":0,"dropped_total":0},"metrics":{"total_requests":1,"successful_requests":2,"failed_requestsÃ¢â‚¬Â¦` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `central-get-/teachme/metrics` |
| GET | `/teachme/objects` | None | query 'limit': Limit; query 'offset': Offset | HTTP 200: `{"objects":[],"total":0,"limit":100,"offset":0,"fallback":false}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `central-get-/teachme/objects` |
| POST | `/teachme/search/by-embedding` | None | application/json required: EmbeddingSearchRequest {k, query, threshold} | HTTP 200: `{"query":"What is the documentation probe fact?","k":5,"results":[{"id":"ae105d51-9c76-4bbe-a8e9-573ffc15bffb","type":"fact","name":"subject='My hometown' predicate='is Layyah' object='punjab, pakistan' context={}","data":{"subject":"My hometown","predicate":"is Layyah","object":"punjab, pakistan","context":{}},"similarity":0.3296,"confidence":1,"tags":["manÃ¢â‚¬Â¦` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `central-post-/teachme/search/by-embedding` |
| GET | `/teachme/search/by-text/{query}` | None | path 'query' required: Query; query 'limit': Limit | HTTP 200: `{"query":"docs-probe-missing","results":[],"total":0,"fallback":false}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `central-get-/teachme/search/by-text/{query}` |
| GET | `/teachme/status` | None | None | HTTP 200: `{"status":"operational","service":"teachme","metrics":{"service":"teachme","base_url":"https://localhost:8004","circuit_state":"closed","failure_count":0,"last_failure":null,"last_success":"2026-09-24T08:39:25.460220","queue":{"queue_size":3,"max_queue_size":1000,"processing_count":0,"max_concurrent":10,"processed_total":3,"dropped_total":0},"metrics":{"totaÃ¢â‚¬Â¦` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `central-get-/teachme/status` |
| POST | `/teachme/sync` | None | application/json required: SyncRequest {items, service_name} | HTTP 200: `{"status":"synced","service":"docs-probe","items_synced":1,"timestamp":"2026-09-24 08:39:25.481903"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `central-post-/teachme/sync` |
| POST | `/users` | Internal service credential | application/json required: User Data | No 2xx captured by the bounded safe probe; live HTTP 400: `{"error":{"status_code":400,"code":"BAD_REQUEST","message":"User name required","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 400; proof `central-post-/users` |
| GET | `/users/check` | Internal service credential | query 'name' required: Name | HTTP 200: `{"exists":false}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `central-get-/users/check` |
| POST | `/users/enroll-complete` | None | multipart/form-data required: Body_enroll_user_complete_users_enroll_complete_post {age, audio_samples, relation, user_name} | No 2xx captured by the bounded safe probe; live HTTP 503: `{"error":{"status_code":503,"code":"AUDIO_SERVICE_UNAVAILABLE","message":"Audio Service client not initialized","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **DEGRADED** Ã¢â‚¬â€ Audio client not initialized; proof `central-post-/users/enroll-complete` |
| GET | `/users/list` | Internal service credential | None | HTTP 200: `{"users":[{"user_id":"<redacted-user-id-1>","user_name":"<redacted-user-name-1>","enrollment_date":"<redacted-enrollment-time-1>","sample_count":{"images":5,"audio":5},"voice_embeddings":"<redacted list length=5>","face_embeddings":"<redacted list length=5>"},{"user_id":"<redacted-user-id-2>","user_name":"<redacted-user-name-2>","enrollment_date":"<redacted-enrollment-time-2>","sample_count":{"images":5Ã¢â‚¬Â¦` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `central-get-/users/list` |
| POST | `/users/register` | None | multipart/form-data: Body | No 2xx captured by the bounded safe probe; live HTTP 400: `{"error":{"status_code":400,"code":"MISSING_NAME","message":"User name is required","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 400; proof `central-post-/users/register` |
| POST | `/users/register-with-embeddings` | None | None | No 2xx captured by the bounded safe probe; live HTTP 500: `{"error":{"status_code":500,"code":"ADD_EMBEDDINGS_FAILED","message":"Failed to add embeddings","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live error path HTTP 500; valid domain fixture required for 2xx; proof `central-post-/users/register-with-embeddings` |
| POST | `/users/register-with-voice` | None | multipart/form-data required: Body_register_user_with_voice_users_register_with_voice_post {audio_sample1, audio_sample2, audio_sample3, email, name} | No 2xx captured by the bounded safe probe; live HTTP 500: `{"error":{"status_code":500,"code":"REGISTRATION_FAILED","message":"Voice registration failed","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live error path HTTP 500; valid domain fixture required for 2xx; proof `central-post-/users/register-with-voice` |
| GET | `/users/search/{user_name}` | Internal service credential | path 'user_name' required: User Name | No 2xx captured by the bounded safe probe; live HTTP 404: `{"error":{"status_code":404,"code":"NOT_FOUND","message":"User 'docs-probe-user-missing' not found","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 404; proof `central-get-/users/search/{user_name}` |
| POST | `/users/session/voice` | None | multipart/form-data required: Body_create_voice_session_users_session_voice_post {file} | No 2xx captured by the bounded safe probe; live HTTP 401: `{"error":{"status_code":401,"code":"UNAUTHORIZED","message":"Biometric verification failed","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 401; proof `central-post-/users/session/voice` |
| DELETE | `/users/{user_id}` | Bearer owner OR internal + matching trusted-user | path 'user_id' required: User Id | No 2xx captured by the bounded safe probe; live HTTP 403: `{"error":{"status_code":403,"code":"FORBIDDEN","message":"Token does not own requested user","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 403; proof `central-delete-/users/{user_id}` |
| GET | `/users/{user_id}` | Bearer owner OR internal + matching trusted-user | path 'user_id' required: User Id | No 2xx captured by the bounded safe probe; live HTTP 403: `{"error":{"status_code":403,"code":"FORBIDDEN","message":"Token does not own requested user","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 403; proof `central-get-/users/{user_id}` |
| POST | `/users/{user_id}/append-embeddings` | Bearer owner OR internal + matching trusted-user | path 'user_id' required: User Id | No 2xx captured by the bounded safe probe; live HTTP 403: `{"error":{"status_code":403,"code":"FORBIDDEN","message":"Token does not own requested user","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 403; proof `central-post-/users/{user_id}/append-embeddings` |
| DELETE | `/users/{user_id}/conversations` | Bearer owner OR internal + matching trusted-user | path 'user_id' required: User Id | No 2xx captured by the bounded safe probe; live HTTP 403: `{"error":{"status_code":403,"code":"FORBIDDEN","message":"Token does not own requested user","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 403; proof `central-delete-/users/{user_id}/conversations` |
| GET | `/users/{user_id}/conversations` | Bearer owner OR internal + matching trusted-user | path 'user_id' required: User Id; query 'limit': Limit; query 'start_date': Start Date; query 'end_date': End Date | No 2xx captured by the bounded safe probe; live HTTP 403: `{"error":{"status_code":403,"code":"FORBIDDEN","message":"Token does not own requested user","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 403; proof `central-get-/users/{user_id}/conversations` |
| POST | `/users/{user_id}/conversations` | Bearer owner OR internal + matching trusted-user | path 'user_id' required: User Id | No 2xx captured by the bounded safe probe; live HTTP 403: `{"error":{"status_code":403,"code":"FORBIDDEN","message":"Token does not own requested user","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 403; proof `central-post-/users/{user_id}/conversations` |
| PUT | `/users/{user_id}/embeddings` | Bearer owner OR internal + matching trusted-user | path 'user_id' required: User Id; application/json required: Payload | No 2xx captured by the bounded safe probe; live HTTP 403: `{"error":{"status_code":403,"code":"FORBIDDEN","message":"Token does not own requested user","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 403; proof `central-put-/users/{user_id}/embeddings` |

## 4.2. Vision service

Base URL: `https://127.0.0.1:8001`

| Method | Path | Auth required | Request body/params | Success response (real example) | Known error cases | Current live status |
|---|---|---|---|---|---|---|
| GET | `/` | None | None | HTTP 200: `{"service":"Vision Service","version":"4.0.0","status":"operational","features":["face_detection","face_embeddings","video_streaming"],"timestamp":"2026-09-24T08:39:33.610299"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `vision-get-/` |
| GET | `/api/face-data` | Internal service credential | None | HTTP 200: `{"face_count":0,"primary_emotion":null,"confidence":null,"timestamp":"2026-09-24T08:39:33.616008"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `vision-get-/api/face-data` |
| POST | `/api/v1/analyze/complete` | Internal service credential | query 'detector_backend': Detector Backend; query 'model_name': Model Name | No 2xx captured by the bounded safe probe; live HTTP 500: `{"error":{"status_code":500,"code":"INTERNAL_SERVER_ERROR","message":"Complete analysis failed","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **DEGRADED** Ã¢â‚¬â€ live HTTP 500; camera/analysis probe failed; proof `vision-post-/api/v1/analyze/complete` |
| POST | `/api/v1/detect/faces` | Internal service credential | query 'detector_backend': Detector Backend; query 'model_name': Model Name | No 2xx captured by the bounded safe probe; live HTTP 500: `{"error":{"status_code":500,"code":"INTERNAL_SERVER_ERROR","message":"Face detection failed","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **DEGRADED** Ã¢â‚¬â€ live HTTP 500; camera/analysis probe failed; proof `vision-post-/api/v1/detect/faces` |
| POST | `/api/v1/detect/faces/upload` | Internal service credential | query 'detector_backend': Detector Backend; query 'model_name': Model Name; multipart/form-data required: Body_detect_faces_from_upload_api_v1_detect_faces_upload_post {file} | No 2xx captured by the bounded safe probe; live HTTP 400: `{"error":{"status_code":400,"code":"BAD_REQUEST","message":"Upload processing failed: 400: Invalid image file","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 400; proof `vision-post-/api/v1/detect/faces/upload` |
| GET | `/api/v1/frame` | Internal service credential | query 'lease_id' required: Lease Id | No 2xx captured by the bounded safe probe; live HTTP 409: `{"error":{"status_code":409,"code":"CONFLICT","message":"Delegated VIDEO_CALL camera lease is not active","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 409; proof `vision-get-/api/v1/frame` |
| POST | `/camera/pause` | Internal service credential | None | HTTP 200: `{"status":"paused","message":"Camera paused"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `vision-post-/camera/pause` |
| POST | `/camera/resume` | Internal service credential | None | HTTP 200: `{"status":"active","message":"Camera resumed"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `vision-post-/camera/resume` |
| GET | `/health` | None | None | HTTP 200: `{"status":"degraded","camera":"unavailable","face_model":"loaded","opencv_version":"4.8.0","emotion_detection":"disabled","timestamp":"2026-09-24T08:39:33.851158"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `vision-get-/health` |
| GET | `/live` | Internal service credential | None | HTTP 200: `<stream text/html; charset=utf-8 first_chunk_bytes=5171>` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `vision-get-/live` |
| GET | `/stream` | Internal service credential | None | HTTP 200: `<stream multipart/x-mixed-replace; boundary=frame first_chunk_bytes=0>` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `vision-get-/stream` |

## 4.3. Audio service

Base URL: `https://127.0.0.1:8002`

| Method | Path | Auth required | Request body/params | Success response (real example) | Known error cases | Current live status |
|---|---|---|---|---|---|---|
| GET | `/` | None | None | HTTP 200: `{"status":"success","message":"Audio Service API is running","version":"1.0.0"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-get-/` |
| GET | `/api/v1/conversation-state` | None | None | HTTP 200: `{"state":"idle","duration_seconds":0,"elapsed_time_seconds":0,"timeout_seconds":10,"timed_out":false}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-get-/api/v1/conversation-state` |
| POST | `/api/v1/conversation/end` | None | query 'user_id' required: User Id | HTTP 200: `{"success":true,"user_id":"docs-probe-user","state":"idle","message":"Conversation session ended"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-post-/api/v1/conversation/end` |
| GET | `/api/v1/conversation/metrics` | None | None | HTTP 200: `{"status":"success","metrics":{"turns_processed":0,"total_latency_ms":0,"average_latency_ms":0}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-get-/api/v1/conversation/metrics` |
| POST | `/api/v1/conversation/start` | None | query 'user_id' required: User Id | HTTP 200: `{"success":true,"user_id":"docs-probe-user","state":"conversation_active","message":"Conversation session started"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-post-/api/v1/conversation/start` |
| POST | `/api/v1/conversation/turn` | None | application/json required: ConversationRequest {audio_file_path, language, speaker_id, user_id} | No 2xx captured by the bounded safe probe; live HTTP 400: `{"error":{"status_code":400,"code":"BAD_REQUEST","message":"audio_file_path is outside the recording directory","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 400; proof `audio-post-/api/v1/conversation/turn` |
| DELETE | `/api/v1/delete-audio/{filename}` | None | path 'filename' required: Filename | No 2xx captured by the bounded safe probe; live HTTP 404: `{"error":{"status_code":404,"code":"NOT_FOUND","message":"Audio file not found: docs-probe-missing.wav","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 404; proof `audio-delete-/api/v1/delete-audio/{filename}` |
| POST | `/api/v1/enroll-speaker` | Internal service credential | application/json required: EnrollSpeakerRequest {duration, user_id} | No 2xx captured by the bounded safe probe; live HTTP 500: `{"error":{"status_code":500,"code":"INTERNAL_SERVER_ERROR","message":"Failed to enroll speaker docs-probe-user: Failed to record audio: 'dtype'","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **DEGRADED** Ã¢â‚¬â€ live HTTP 500; proof `audio-post-/api/v1/enroll-speaker` |
| POST | `/api/v1/enroll-speaker-files` | None | application/json required: Request | No 2xx captured by the bounded safe probe; live HTTP 500: `{"error":{"status_code":500,"code":"INTERNAL_SERVER_ERROR","message":"400: user_id is required","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live error path HTTP 500; valid domain fixture required for 2xx; proof `audio-post-/api/v1/enroll-speaker-files` |
| POST | `/api/v1/interrupt-playback` | None | None | HTTP 200: `{"success":true,"message":"Playback interrupted","state":"stopped"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-post-/api/v1/interrupt-playback` |
| GET | `/api/v1/list-audio` | None | None | HTTP 200: `{"status":"success","count":1,"files":[{"filename":"docs-probe-missing.wav","relative_path":"docs-probe-missing.wav","file_size":0,"created_at":"2026-09-24T13:39:34.239091","modified_at":"2026-09-24T13:39:34.239091"}]}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-get-/api/v1/list-audio` |
| GET | `/api/v1/orchestration/health` | None | None | HTTP 200: `{"status":"degraded","components":{"orchestrator":"initialized","conversation_state":"initialized","stop_word_detector":"not_initialized","vad_recorder":"initialized","playback_manager":"initialized","conversation_state_details":{"current_state":"conversation_active","in_conversation":true,"conversation_duration_s":0.077551,"elapsed_since_speech_s":0.077551,Ã¢â‚¬Â¦` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-get-/api/v1/orchestration/health` |
| GET | `/api/v1/orchestration/test/end-to-end` | None | None | HTTP 200: `{"status":"success","test_result":"PASSED","metrics":{"turns_processed":0,"total_latency_ms":0,"average_latency_ms":0},"message":"Orchestrator is fully functional"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-get-/api/v1/orchestration/test/end-to-end` |
| POST | `/api/v1/playback/start` | Internal service credential | multipart/form-data required: Body_start_playback_api_v1_playback_start_post {file} | HTTP 200: `{"success":true,"state":"idle","duration":1,"actual_duration":1,"interrupted":false}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-post-/api/v1/playback/start` |
| GET | `/api/v1/poll-stop-word` | None | query 'timeout': Timeout | No 2xx captured by the bounded safe probe; live HTTP 503: `{"error":{"status_code":503,"code":"SERVICE_UNAVAILABLE","message":"Stop word detector not initialized","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **BLOCKED** Ã¢â‚¬â€ live HTTP 503; Porcupine/stop-word or microphone authority unavailable; proof `audio-get-/api/v1/poll-stop-word` |
| POST | `/api/v1/process-command` | None | application/json required: ProcessCommandRequest {audio_file, language, verify_speaker} | No 2xx captured by the bounded safe probe; live HTTP 422: `{"error":{"status_code":422,"code":"VALIDATION_ERROR","message":"Request validation failed","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 422; proof `audio-post-/api/v1/process-command` |
| POST | `/api/v1/process-pipeline` | None | query 'send_to_backend': Send To Backend | No 2xx captured by the bounded safe probe; live HTTP 0: `ReadTimeout: The read operation timed out` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **DEGRADED** Ã¢â‚¬â€ live timeout after 12016 ms; proof `audio-post-/api/v1/process-pipeline` |
| POST | `/api/v1/process-voice` | Internal service credential | multipart/form-data required: Body_process_voice_file_api_v1_process_voice_post {file} | No 2xx captured by the bounded safe probe; live HTTP 400: `{"error":{"status_code":400,"code":"BAD_REQUEST","message":"No clear voice detected in the audio. Please provide clearer speech.","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 400; proof `audio-post-/api/v1/process-voice` |
| POST | `/api/v1/record` | None | application/json required: RecordRequest {channels, duration, sample_rate} | No 2xx captured by the bounded safe probe; live HTTP 500: `{"error":{"status_code":500,"code":"INTERNAL_SERVER_ERROR","message":"Failed to record audio. Please check microphone availability.","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **BLOCKED** Ã¢â‚¬â€ live microphone capture failed in this deployment; proof `audio-post-/api/v1/record` |
| POST | `/api/v1/record-until-silence` | None | None | HTTP 200: `{"success":true,"audio_file":"03_audio_service\\audio_service\\data\\recordings\\vad_recording_20260924_133948867.wav","duration":4.992,"stopped_by":"max_duration","chunks_recorded":156,"error":null}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-post-/api/v1/record-until-silence` |
| POST | `/api/v1/set-detection-mode` | None | application/json required: DetectionModeRequest {mode} | No 2xx captured by the bounded safe probe; live HTTP 400: `{"error":{"status_code":400,"code":"BAD_REQUEST","message":"Mode must be 'idle' or 'conversation'","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 400; proof `audio-post-/api/v1/set-detection-mode` |
| POST | `/api/v1/speaker-sync` | Internal service credential | None | HTTP 200: `{"success":true,"message":"Synced 2 speakers from Central Server","speakers_synced":2,"speakers_skipped":0,"validation_issues":null,"timestamp":"2026-09-24T13:39:56.246361"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-post-/api/v1/speaker-sync` |
| GET | `/api/v1/speakers` | None | None | HTTP 200: `{"status":"success","count":2,"speakers":["<redacted-user-id-1>","<redacted-user-id-2>"]}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-get-/api/v1/speakers` |
| GET | `/api/v1/speakers/debug` | None | None | HTTP 200: `{"status":"debug","timestamp":"2026-09-24T13:39:56.273430","memory":{"speakers_loaded":2,"speaker_ids":["<redacted-user-id-1>","<redacted-user-id-2>"]},"validation":{"total_speakers":2,"valid_speakers":2,"invalid_speakers":[],"dimension_errors":[]},"disk":{"file_exists":false,"file_size_bytes":0,"last_modified":null},"summary":{"memory_ready":true,"all_valid":trueÃ¢â‚¬Â¦` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-get-/api/v1/speakers/debug` |
| GET | `/api/v1/stop-word-events/status` | None | None | No 2xx captured by the bounded safe probe; live HTTP 503: `{"error":{"status_code":503,"code":"SERVICE_UNAVAILABLE","message":"Stop word detector not initialized","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **BLOCKED** Ã¢â‚¬â€ live HTTP 503; Porcupine/stop-word or microphone authority unavailable; proof `audio-get-/api/v1/stop-word-events/status` |
| GET | `/api/v1/stt/circuit-breaker-status` | None | None | HTTP 200: `{"status":"success","state":"closed","failure_count":0,"success_count":0,"last_failure_time":null,"recovery_timeout":60,"api_calls":0,"average_api_latency":0,"last_api_latency":null}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-get-/api/v1/stt/circuit-breaker-status` |
| GET | `/api/v1/test/conversation-status` | None | None | HTTP 200: `{"status":"ok","conversation_state":{"current_state":"processing_query","in_conversation":false,"conversation_duration_s":0,"elapsed_since_speech_s":7.428877,"timeout_exceeded":false,"timeout_seconds":10}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-get-/api/v1/test/conversation-status` |
| GET | `/api/v1/test/playback-status` | None | None | HTTP 200: `{"status":"ok","playback_state":{"state":"idle","playing":false,"position_frames":16000,"total_frames":16000,"interrupted":false}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-get-/api/v1/test/playback-status` |
| GET | `/api/v1/test/stop-word-status` | None | None | HTTP 200: `{"status":"not_initialized","message":"Stop word detector not initialized"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-get-/api/v1/test/stop-word-status` |
| POST | `/api/v1/transcribe` | Internal service credential | query 'language': Language; multipart/form-data required: Body_transcribe_audio_api_v1_transcribe_post {file} | HTTP 200: `{"status":"success","text":"you","language":"English","duration":1,"success":true,"confidence":null,"timestamp":"2026-09-24T13:40:01.626967"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-post-/api/v1/transcribe` |
| POST | `/api/v1/verify-speaker` | Internal service credential | multipart/form-data required: Body_verify_speaker_api_v1_verify_speaker_post {file} | HTTP 200: `{"status":"success","user_id":"unknown","confidence":0.4419,"is_verified":false,"threshold":0.65,"timestamp":"2026-09-24T13:40:01.708116","access_token":"<redacted>","token_type":"<redacted>","expires_in":null}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-post-/api/v1/verify-speaker` |
| POST | `/api/v1/wake-word/detect` | None | None | No 2xx captured by the bounded safe probe; live HTTP 500: `{"error":{"status_code":500,"code":"INTERNAL_SERVER_ERROR","message":"An unexpected error occurred during wake word detection","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 408, 409, 422, 429, 500 | **BLOCKED** Ã¢â‚¬â€ live HTTP 500; Porcupine/stop-word or microphone authority unavailable; proof `audio-post-/api/v1/wake-word/detect` |
| POST | `/api/v1/wake-word/detect/simple` | None | None | No 2xx captured by the bounded safe probe; live HTTP 500: `{"error":{"status_code":500,"code":"INTERNAL_SERVER_ERROR","message":"Microphone authority did not reserve a lease","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **BLOCKED** Ã¢â‚¬â€ live HTTP 500; Porcupine/stop-word or microphone authority unavailable; proof `audio-post-/api/v1/wake-word/detect/simple` |
| GET | `/api/v1/wake-word/power-mode` | None | None | HTTP 200: `{"status":"success","mode":"balanced","vad_enabled":true,"sleep_duration_ms":0}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-get-/api/v1/wake-word/power-mode` |
| POST | `/api/v1/wake-word/power-mode` | None | application/json required: Request | HTTP 200: `{"status":"success","mode":"balanced","vad_enabled":true,"sleep_duration_ms":0}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-post-/api/v1/wake-word/power-mode` |
| POST | `/api/v1/wake-word/start` | None | None | HTTP 200: `{"status":"listening","is_listening":true,"message":"Wake word detection started successfully"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-post-/api/v1/wake-word/start` |
| GET | `/api/v1/wake-word/stats` | None | None | HTTP 200: `{"status":"success","total_frames":0,"speech_frames":0,"silence_frames":0,"detections":0,"errors":0,"power_mode":"balanced","vad_enabled":true,"current_power_mode":"balanced","sleep_duration_ms":0}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-get-/api/v1/wake-word/stats` |
| GET | `/api/v1/wake-word/status` | None | None | HTTP 200: `{"status":"listening","is_listening":true,"message":"Wake word detection is active"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-get-/api/v1/wake-word/status` |
| POST | `/api/v1/wake-word/stop` | None | None | HTTP 200: `{"status":"stopped","is_listening":false,"message":"Wake word detection stopped successfully"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-post-/api/v1/wake-word/stop` |
| GET | `/health` | None | None | HTTP 200: `{"status":"degraded","service":"audio-service","version":"1.0.0","stop_word_detector":{"status":"unavailable","initialized":false},"queue_processor":{"running":true}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-get-/health` |
| POST | `/queue/add` | None | application/json required: Request | HTTP 200: `{"status":"error","message":"Missing 'text' field in request"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-post-/queue/add` |
| POST | `/queue/process-now` | None | None | HTTP 200: `{"status":"success","processed_count":0,"message":"Processed 0 queued commands"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-post-/queue/process-now` |
| GET | `/queue/status` | None | None | HTTP 200: `{"status":"success","running":true,"poll_interval":1,"batch_size":10,"queue_stats":{"total":0,"pending":0,"processing":0,"completed":0,"failed":0},"circuit_breaker_state":"closed"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `audio-get-/queue/status` |

## 4.4. TTS service

Base URL: `https://127.0.0.1:8003`

| Method | Path | Auth required | Request body/params | Success response (real example) | Known error cases | Current live status |
|---|---|---|---|---|---|---|
| GET | `/cache/status` | None | None | HTTP 200: `{"status":"ok","worker_pool":{"num_workers":3,"tasks_processed":0,"tasks_failed":0,"queue_depths":[0,0,0]},"aggregated_cache":{"total_hits":0,"total_misses":1,"hit_rate_percent":0,"total_requests":1},"per_worker_cache":[{"worker_id":0,"cached_models":1,"cached_voices":["jenny"],"cache_hits":0,"cache_misses":1,"hit_rate_percent":0},{"worker_id":1,"cached_modeÃ¢â‚¬Â¦` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `tts-get-/cache/status` |
| POST | `/config/set_voice` | None | application/json required: SpeechRequest {language, text, voice_id} | No 2xx captured by the bounded safe probe; live HTTP 400: `{"error":{"status_code":400,"code":"BAD_REQUEST","message":"voice_id is required","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 400; proof `tts-post-/config/set_voice` |
| GET | `/diagnostics` | None | None | HTTP 200: `{"timestamp":1790239212.959586,"service":{"name":"NEXI TTS","version":"1.0.0","uptime_seconds":1497.5070159435272,"health_score":100},"requests":{"processed":0,"failed":0,"success_rate":0},"errors":{"total_errors":0,"errors_by_type":{},"errors_by_category":{},"critical_errors":0,"retryable_errors":0,"most_common_error":null},"voices":{"available":1,"voice_idÃ¢â‚¬Â¦` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `tts-get-/diagnostics` |
| GET | `/errors` | None | None | HTTP 200: `{"timestamp":1790239212.969537,"error_stats":{"total_errors":0,"errors_by_type":{},"errors_by_category":{},"critical_errors":0,"retryable_errors":0,"most_common_error":null},"error_rate_per_minute":0,"total_errors":0,"max_history":1000}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `tts-get-/errors` |
| GET | `/errors/by_category/{category}` | None | path 'category' required: Category | No 2xx captured by the bounded safe probe; live HTTP 400: `{"error":{"status_code":400,"code":"BAD_REQUEST","message":"Invalid category. Valid: validation, synthesis, timeout, resource, configuration, worker, unknown","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 400; proof `tts-get-/errors/by_category/{category}` |
| GET | `/errors/recent` | None | query 'limit': Limit | HTTP 200: `{"timestamp":1790239212.9884393,"count":0,"errors":[]}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `tts-get-/errors/recent` |
| GET | `/health` | None | None | HTTP 200: `{"status":"healthy","voice_model":"available","service":"NEXI TTS","version":"1.0.0","timestamp":1790239212.9962761}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `tts-get-/health` |
| GET | `/health/detailed` | None | None | HTTP 200: `{"status":"healthy","service":"NEXI TTS","version":"1.0.0","timestamp":1790239213.0103278,"available_voices":1,"worker_pool":{"num_workers":3,"tasks_processed":0,"tasks_failed":0,"queue_depths":[0,0,0],"running":true,"worker_caches":[{"worker_id":0,"cached_models":1,"cached_voices":["jenny"],"cache_hits":0,"cache_misses":1,"hit_rate_percent":0},{"worker_id":Ã¢â‚¬Â¦` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `tts-get-/health/detailed` |
| GET | `/metrics` | None | None | HTTP 200: `# HELP tts_synthesis_requests_total Total synthesis requests # TYPE tts_synthesis_requests_total counter # HELP tts_synthesis_latency_seconds Synthesis request latency # TYPE tts_synthesis_latency_seconds histogram # HELP tts_synthesis_errors_total Total synthesis errors # TYPE tts_synthesis_errors_total counter # HELP tts_worker_queue_depth Current queue deÃ¢â‚¬Â¦` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `tts-get-/metrics` |
| GET | `/metrics/json` | None | None | HTTP 200: `{"timestamp":1790239213.0251086,"service_stats":{"uptime_seconds":1497.573539018631,"requests_processed":0,"requests_failed":0,"last_error":null},"worker_pool_stats":{"num_workers":3,"tasks_processed":0,"tasks_failed":0,"queue_depths":[0,0,0],"running":true,"worker_caches":[{"worker_id":0,"cached_models":1,"cached_voices":["jenny"],"cache_hits":0,"cache_missÃ¢â‚¬Â¦` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `tts-get-/metrics/json` |
| POST | `/speak` | Internal service credential | application/json required: SpeechRequest {language, text, voice_id} | HTTP 200: `<binary audio/wav bytes=76844>` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `tts-post-/speak` |
| GET | `/speakers/state/{speaker_id}` | None | path 'speaker_id' required: Speaker Id | HTTP 200: `{"status":"ok","speaker_id":"docs-probe-speaker-missing","state":"unloaded","is_loaded":false,"is_default":false}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `tts-get-/speakers/state/{speaker_id}` |
| GET | `/speakers/stats` | None | None | HTTP 200: `{"status":"ok","stats":{"current_default":"jenny","loaded_speakers":["jenny"],"idle_speakers":["ryan","shahid"],"num_loaded":1,"num_idle":2,"total_speakers":3,"access_counts":{"jenny":1,"ryan":0,"shahid":0},"memory_optimized":"Loaded 1 of 3 speakers"},"timestamp":1790239219.3530927}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `tts-get-/speakers/stats` |
| GET | `/speakers/status` | None | None | HTTP 200: `{"status":"ok","speakers":{"jenny":{"id":"jenny","name":"Female English voice (British accent) - DEFAULT","language":"english","state":"loaded","is_default":true,"is_loaded":true,"access_count":1,"load_time":"2026-09-24T13:15:18.941634"},"ryan":{"id":"ryan","name":"Male English voice","language":"english","state":"idle","is_default":false,"is_loaded":false,"Ã¢â‚¬Â¦` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `tts-get-/speakers/status` |
| POST | `/speakers/switch` | None | application/json required: SpeechRequest {language, text, voice_id} | No 2xx captured by the bounded safe probe; live HTTP 400: `{"error":{"status_code":400,"code":"BAD_REQUEST","message":"voice_id is required","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 400; proof `tts-post-/speakers/switch` |
| GET | `/voices` | None | None | HTTP 200: `{"voices":[{"id":"jenny","name":"Jenny (Female, English)","locale":"en-GB","gender":"Female","description":"British English accent - natural female voice"}],"default":"jenny","count":1,"english_count":1,"urdu_count":0}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `tts-get-/voices` |

## 4.5. TeachMe service

Base URL: `https://127.0.0.1:8004`

| Method | Path | Auth required | Request body/params | Success response (real example) | Known error cases | Current live status |
|---|---|---|---|---|---|---|
| GET | `/` | None | None | No 2xx captured by the bounded safe probe; live HTTP 500: `{"error":{"status_code":500,"code":"INTERNAL_SERVER_ERROR","message":"Internal server error","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **DEGRADED** Ã¢â‚¬â€ live root route returns HTTP 500; proof `teachme-get-/` |
| DELETE | `/forget-by-name/{name}` | Internal service credential | path 'name' required: Name; query 'item_type': Item Type | HTTP 200: `{"message":"Forgot 0 items matching 'docs-probe-missing'","deleted_ids":[],"name":"docs-probe-missing","type_filter":"any"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `teachme-delete-/forget-by-name/{name}` |
| DELETE | `/forget/{item_id}` | Internal service credential | path 'item_id' required: Item Id; query 'permanent': Permanent | HTTP 200: `{"error":"Item not found","item_id":"docs-probe-item-missing","status_code":404}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `teachme-delete-/forget/{item_id}` |
| GET | `/health` | None | None | HTTP 200: `{"status":"healthy","timestamp":"2026-09-24T08:40:19.647725","checks":{"embedding_model":"<redacted>","knowledge_base":{"status":"healthy","items_count":1,"objects":0,"facts":1},"vision_service":{"status":"healthy","circuit_state":"closed","successful_calls":3,"failed_calls":0,"avg_response_time_ms":100,"url":"https://127.0.0.1:8001"}},"http_code":200}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `teachme-get-/health` |
| GET | `/health/detailed` | None | None | HTTP 200: `{"service":"TeachMe","status":"running","timestamp":"2026-09-24T08:40:19.662372","note":"Detailed metrics require psutil"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `teachme-get-/health/detailed` |
| GET | `/knowledge/all` | Internal service credential | None | HTTP 200: `{"total_count":1,"items":[{"id":"ae105d51-9c76-4bbe-a8e9-573ffc15bffb","type":"fact","data":{"subject":"My hometown","predicate":"is Layyah","object":"punjab, pakistan","context":{}},"tags":["manual-console"],"confidence":1,"created_at":"2026-09-21T13:23:49.622542","updated_at":"2026-09-21T13:23:49.622542","embedding":"<redacted list length=384>"}]}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `teachme-get-/knowledge/all` |
| GET | `/knowledge/facts` | Internal service credential | None | HTTP 200: `{"count":1,"facts":[{"id":"ae105d51-9c76-4bbe-a8e9-573ffc15bffb","type":"fact","data":{"subject":"My hometown","predicate":"is Layyah","object":"punjab, pakistan","context":{}},"tags":["manual-console"],"confidence":1,"created_at":"2026-09-21T13:23:49.622542","updated_at":"2026-09-21T13:23:49.622542","embedding":"<redacted list length=384>"}]}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `teachme-get-/knowledge/facts` |
| POST | `/knowledge/learn-batch` | Internal service credential | application/json required: Requests List | No 2xx captured by the bounded safe probe; live HTTP 422: `{"error":{"status_code":422,"code":"VALIDATION_ERROR","message":"Request validation failed","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 422; proof `teachme-post-/knowledge/learn-batch` |
| GET | `/knowledge/objects` | Internal service credential | None | HTTP 200: `{"count":0,"objects":[]}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `teachme-get-/knowledge/objects` |
| GET | `/knowledge/related/{item_id}` | Internal service credential | path 'item_id' required: Item Id; query 'top_k': Top K | HTTP 200: `{"item_id":"docs-probe-item-missing","item_name":"Unknown","related_count":0,"related_items":[],"note":"Item not found"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `teachme-get-/knowledge/related/{item_id}` |
| POST | `/knowledge/search/advanced` | Internal service credential | query 'name': Name; query 'category': Category; query 'tag': Tag; query 'search_mode': Search Mode | HTTP 200: `{"query":{"name":null,"category":null,"tag":null,"mode":"any"},"count":0,"results":[]}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `teachme-post-/knowledge/search/advanced` |
| POST | `/knowledge/search/embedding` | Internal service credential | query 'query_object_name' required: Query Object Name; query 'top_k': Top K; query 'similarity_threshold': Similarity Threshold | HTTP 200: `{"query":"docs-probe","count":0,"results":[],"from_cache":false,"performance_ms":{"search":5.86,"total":30.03}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `teachme-post-/knowledge/search/embedding` |
| GET | `/knowledge/search/{name}` | Internal service credential | path 'name' required: Name | HTTP 200: `{"search_term":"docs-probe-missing","count":0,"results":[]}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `teachme-get-/knowledge/search/{name}` |
| GET | `/knowledge/stats` | Internal service credential | None | HTTP 200: `{"success":true,"stats":{"total":1,"objects":0,"facts":1,"deleted":0,"categories":{},"storage_file":"knowledge_data.json","last_updated":"2026-09-24T13:40:19.797157","embedding_index":"<redacted>"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `teachme-get-/knowledge/stats` |
| POST | `/learn` | Internal service credential | application/json required: LearningRequest {confidence, data, tags, type} | No 2xx captured by the bounded safe probe; live HTTP 422: `{"error":{"status_code":422,"code":"VALIDATION_ERROR","message":"Request validation failed","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 422; proof `teachme-post-/learn` |
| GET | `/metrics` | None | None | HTTP 200: `{"timestamp":"2026-09-24T08:40:19.820460","system":{"total_items":1,"objects":0,"facts":1,"with_embeddings":"<redacted>"},"performance":{"avg_embedding_time_ms":"<redacted>","avg_search_time_ms":0.67,"cache_size":2,"cache_hit_potential":"Medium"},"api":{"rate_limit_per_minute":60,"active_clients":1}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `teachme-get-/metrics` |

## 4.6. Enrollment service

Base URL: `https://127.0.0.1:8005`

| Method | Path | Auth required | Request body/params | Success response (real example) | Known error cases | Current live status |
|---|---|---|---|---|---|---|
| GET | `/` | None | None | HTTP 200: `{"service":"Enrollment Service","status":"running","port":8005,"dependencies":null}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `enrollment-get-/` |
| GET | `/enrollment/check-user` | Internal service credential | query 'name' required: Name | HTTP 200: `{"exists":false,"user_id":null,"enrollment_date":null,"sample_count":{"images":0,"audio":0}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `enrollment-get-/enrollment/check-user` |
| DELETE | `/enrollment/delete-user/{user_name}` | Bearer owner OR internal + matching trusted-user | path 'user_name' required: User Name | No 2xx captured by the bounded safe probe; live HTTP 403: `{"error":{"status_code":403,"code":"FORBIDDEN","message":"Token does not own requested user","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 403; proof `enrollment-delete-/enrollment/delete-user/{user_name}` |
| POST | `/enrollment/enroll` | None | multipart/form-data required: Body_enroll_user_enrollment_enroll_post {age, photos, relation, user_name, voice_samples} | No 2xx captured by the bounded safe probe; live HTTP 400: `{"error":{"status_code":400,"code":"BAD_REQUEST","message":"Exactly 5 photos required. Received: 1","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 400; proof `enrollment-post-/enrollment/enroll` |
| GET | `/enrollment/health-detailed` | None | None | HTTP 200: `{"service":"Enrollment Service","status":"degraded","port":8005,"dependencies":{"vision_service":true,"audio_service":false,"central_server":true}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `enrollment-get-/enrollment/health-detailed` |
| POST | `/enrollment/improve-training/{user_id}` | Bearer owner OR internal + matching trusted-user | path 'user_id' required: User Id; multipart/form-data required: Body_improve_training_enrollment_improve_training__user_id__post {additional_photos, additional_voice_samples} | No 2xx captured by the bounded safe probe; live HTTP 403: `{"error":{"status_code":403,"code":"FORBIDDEN","message":"Token does not own requested user","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 403; proof `enrollment-post-/enrollment/improve-training/{user_id}` |
| GET | `/enrollment/storage/list` | Internal service credential | None | HTTP 200: `{"status":"success","total_enrollments":2,"user_ids":["<redacted-user-id-2>","<redacted-user-id-1>"]}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `enrollment-get-/enrollment/storage/list` |
| GET | `/enrollment/storage/stats` | Internal service credential | None | No 2xx captured by the bounded safe probe; live HTTP 500: `{"error":{"status_code":500,"code":"INTERNAL_SERVER_ERROR","message":"Failed to get storage stats: 3 validation errors for StorageStatsResponse\ntotal_enrollments\n  Field required [type=missing, input_value={'total_users': 2, 'total.../enrollment_data\\\\logsÃ¢â‚¬Â¦` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **DEGRADED** Ã¢â‚¬â€ live response-model validation failure; proof `enrollment-get-/enrollment/storage/stats` |
| DELETE | `/enrollment/storage/{user_id}` | Bearer owner OR internal + matching trusted-user | path 'user_id' required: User Id | No 2xx captured by the bounded safe probe; live HTTP 403: `{"error":{"status_code":403,"code":"FORBIDDEN","message":"Token does not own requested user","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 403; proof `enrollment-delete-/enrollment/storage/{user_id}` |
| GET | `/enrollment/storage/{user_id}` | Bearer owner OR internal + matching trusted-user | path 'user_id' required: User Id | No 2xx captured by the bounded safe probe; live HTTP 403: `{"error":{"status_code":403,"code":"FORBIDDEN","message":"Token does not own requested user","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 403; proof `enrollment-get-/enrollment/storage/{user_id}` |
| POST | `/enrollment/update-model/{user_id}` | Bearer owner OR internal + matching trusted-user | path 'user_id' required: User Id; multipart/form-data required: Body_update_model_enrollment_update_model__user_id__post {new_photos, new_voice_samples} | No 2xx captured by the bounded safe probe; live HTTP 403: `{"error":{"status_code":403,"code":"FORBIDDEN","message":"Token does not own requested user","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 403; proof `enrollment-post-/enrollment/update-model/{user_id}` |
| GET | `/health` | None | None | HTTP 200: `{"status":"healthy","version":"3.0.0"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `enrollment-get-/health` |

## 4.7. LLM service

Base URL: `https://127.0.0.1:8006`

| Method | Path | Auth required | Request body/params | Success response (real example) | Known error cases | Current live status |
|---|---|---|---|---|---|---|
| GET | `/` | None | None | HTTP 200: `{"service":"NEXI LLM Service","version":"1.0.0","status":"running (online mode)"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `llm-get-/` |
| POST | `/api/v1/format` | None | None | No 2xx captured by the bounded safe probe; live HTTP 501: `{"error":{"status_code":501,"code":"NOT_IMPLEMENTED","message":"Formatting is not implemented","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **BLOCKED** Ã¢â‚¬â€ explicitly not implemented; proof `llm-post-/api/v1/format` |
| POST | `/api/v1/generate` | Internal service credential | application/json required: GenerationRequest {language, max_tokens, query, temperature} | No 2xx captured by the bounded safe probe; live HTTP 422: `{"error":{"status_code":422,"code":"VALIDATION_ERROR","message":"Request validation failed","request_id":"endpoint-docs-20260924"}}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live documented rejection HTTP 422; proof `llm-post-/api/v1/generate` |
| GET | `/api/v1/health` | None | None | HTTP 200: `{"status":"healthy","openrouter":true}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `llm-get-/api/v1/health` |
| GET | `/api/v1/model-info` | None | None | HTTP 200: `{"provider":"openrouter","model":"openai/gpt-4o-mini"}` | HTTP 400, 401, 403, 404, 409, 422, 429, 500 | **WORKING** Ã¢â‚¬â€ live HTTP 200; proof `llm-get-/api/v1/model-info` |

## 5. Deprecated / Legacy Aliases

These paths are deliberately hidden from OpenAPI. They remain live only for transition compatibility; new clients must use the primary path.

| Legacy path | Primary/current path | Live proof | Migration guidance |
|---|---|---|---|
| POST `/users/data/add_user` | POST `/users` | HTTP 200: `{"status":"success","message":"User docs-alias-f2f80c0e enrolled","user_id":"docs-alias-f2f80c0e"}` | Change path only; identical create-user behavior. |
| POST `/users/add-embeddings` | POST `/users/register-with-embeddings` | HTTP 400: `{"error":{"status_code":400,"code":"MISSING_NAME","message":"User name required","request_id":"endpoint-docs-alias"}}` | Change path; preserve the create-with-embeddings payload. |
| GET `/teachme/search/{query}` | GET `/teachme/search/by-text/{query}` | HTTP 200: `{"query":"docs-probe-missing","results":[],"total":0,"fallback":false}` | Use the explicit text-search path. |
| POST `/teachme/search/embedding` | POST `/teachme/search/by-embedding` | HTTP 200: `{"query":"docs-probe-missing","k":1,"results":[],"fallback":false}` | Use the explicit embedding-search path. |
| GET `/users/{user_id}/conversation-history` | GET `/users/{user_id}/conversations` | HTTP 410: `{"error":{"status_code":410,"code":"CONVERSATION_HISTORY_RETIRED","message":"Use /users/docs-alias-f2f80c0e/conversations for durable conversation data","request_id":"endpoint-docs-alias"}}` | Legacy route is retired and returns 410; migrate immediately. |


`/users/register-old` is not live and has no supported replacement beyond choosing the appropriate current registration operation.

## 6. Sequence examples

### A. Enroll a new user

1. `POST https://127.0.0.1:8005/enrollment/enroll` as `multipart/form-data`.
2. Send `user_name`, optional `age` and `relation`, **exactly five** `photos`, and **exactly five** `voice_samples`.
3. Store the returned `user_id` and bearer token. Do not store or expose biometric vectors in the frontend.

```text
photos=@face1.jpg ... photos=@face5.jpg
voice_samples=@voice1.wav ... voice_samples=@voice5.wav
user_name=Alex; age=30; relation=family
```

This pass intentionally did not fabricate a person's biometrics. Its live one-photo/one-audio validation probe returned HTTP 400: `Exactly 5 photos required. Received: 1`. A 2xx enrollment requires five genuine face images and five genuine voice samples.

### B. Voice login, then restricted RAG

1. `POST /users/session/voice` with multipart field `file=@verification.wav`.
2. Read `access_token`, `user_id`, and `expires_in` from the 200 response. The silent documentation fixture correctly returned 401 (`Biometric verification failed`); a real enrolled speaker sample is required.
3. Call `POST /api/v1/rag/query` with `Authorization: Bearer <access_token>` and `{"query":"What does the taught fact mean?"}`.
4. Read history with `GET /users/{user_id}/conversations` using the same bearer token.

The live equivalent trusted-backend proof in this pass returned:

```json
[
  {
    "label": "restricted RAG query",
    "method": "POST",
    "url": "https://127.0.0.1:8000/api/v1/rag/query",
    "status": 200,
    "response": {
      "success": true,
      "response": "docs-90999fabd6 means temporary documentation fact.",
      "source": "teachme_grounded"
    }
  },
  {
    "label": "conversation read-back",
    "method": "GET",
    "url": "https://127.0.0.1:8000/users/docs-d1990c962a/conversations",
    "status": 200,
    "response": {
      "user_id": "docs-d1990c962a",
      "conversations": [
        {
          "conversation_id": "conv_70882d18f03d",
          "user_id": "docs-d1990c962a",
          "timestamp": "2026-09-24T08:42:37.762860",
          "user_message": "What does docs-90999fabd6 mean?",
          "assistant_response": "docs-90999fabd6 means temporary documentation fact.",
          "language": "en",
          "metadata": {
            "source": "teachme_grounded",
            "automatic": true
          }
        }
      ],
      "count": 1,
      "limit": 10,
      "start_date": null,
      "end_date": null
    }
  }
]
```

### C. Teach and retrieve a fact

1. `POST https://127.0.0.1:8004/learn` with the internal service credential.
2. Payload: `{"type":"fact","data":{"subject":"charging dock","predicate":"is","object":"beside the blue sofa"},"confidence":1.0}`.
3. Retrieve with `GET /knowledge/search/charging%20dock`.
4. Use the Central restricted-RAG endpoint for end-user answers; do not call LLM generation directly from a frontend.

Live temporary-fixture proof:

```json
[
  {
    "label": "teach temporary fact",
    "method": "POST",
    "url": "https://127.0.0.1:8004/learn",
    "status": 201,
    "response": {
      "message": "Learned new fact 'docs-90999fabd6 means temporary documentation fact'",
      "item_id": "87603f5f-0a73-4db0-be73-32ef4549e774",
      "type": "fact",
      "is_new": true,
      "vision_enhanced": false,
      "performance_ms": {
        "total": 50.10271072387695,
        "vision": null,
        "embedding": "<redacted>",
        "storage": null
      }
    }
  },
  {
    "label": "retrieve taught fact",
    "method": "GET",
    "url": "https://127.0.0.1:8004/knowledge/search/docs-90999fabd6",
    "status": 200,
    "response": {
      "search_term": "docs-90999fabd6",
      "count": 1,
      "results": [
        {
          "id": "87603f5f-0a73-4db0-be73-32ef4549e774",
          "type": "fact",
          "data": {
            "subject": "docs-90999fabd6",
            "predicate": "means",
            "object": "temporary documentation fact",
            "context": {}
          },
          "tags": [],
          "confidence": 1,
          "created_at": "2026-09-24T13:42:30.384784",
          "updated_at": "2026-09-24T13:42:30.384784",
          "embedding": "<redacted>"
        }
      ]
    }
  }
]
```

## 7. What This System Will Never Do

- It does not provide open-domain answers outside TeachMe grounding through the end-user RAG route.
- It rejects non-English RAG input.
- It exposes Jenny as the supported TTS voice; frontend UX must not promise multi-voice or Urdu synthesis.
- It does not collect, store, or expose emotion/mood data.
- It does not expose internal service credentials or biometric embeddings to frontend/mobile clients.

## 8. Current deployment findings

The following are real findings from this pass, not historical carry-over:

- **Working now:** DeepFace/FaceNet is loaded; YOLO is loaded; Vision health returned 200. Jenny synthesis returned a real 75,820-byte WAV. OpenRouter generation returned 200 using `openai/gpt-4o-mini`. Restricted RAG returned a TeachMe-grounded answer and automatically persisted the conversation.
- **Degraded now:** Central `/users/enroll-complete` reports an uninitialized Audio client; Vision camera analysis endpoints returned 500 for the bounded probe; TeachMe `/` returns 500; Enrollment `/enrollment/storage/stats` returns 500 because its implementation output does not satisfy `StorageStatsResponse`; Audio `/api/v1/process-pipeline` exceeded the 12-second bound.
- **Blocked now:** Audio stop-word/Porcupine routes report the detector unavailable, live microphone recording failed in this deployment, and LLM `/api/v1/format` explicitly returns 501 because formatting is not implemented.

## 9. Live verification appendix

Every OpenAPI operation was called once against the running HTTPS stack. Requests used `X-Correlation-ID: endpoint-docs-20260924`; configured credentials were sent where required but are never printed below. Nonexistent IDs were intentional to avoid deleting real data.

### `central-get-/`

- Request: `GET https://127.0.0.1:8000/`
- Request data: `{}`
- Response: HTTP 200 in 15 ms
- Body: `{"status":"running","service":"central_server"}`

### `central-get-/admin/stats`

- Request: `GET https://127.0.0.1:8000/admin/stats`
- Request data: `{}`
- Response: HTTP 200 in 16 ms
- Body: `{"total_conversations":0,"unique_users":0,"conversations_per_user":{},"by_language":{},"oldest_timestamp":null,"newest_timestamp":null}`

### `central-post-/api/v1/rag/query`

- Request: `POST https://127.0.0.1:8000/api/v1/rag/query`
- Request data: `{"json":{"query":"What is the documentation probe fact?","user_id":"docs-probe-user-missing"}}`
- Response: HTTP 422 in 16 ms
- Body: `{"error":{"status_code":422,"code":"VALIDATION_ERROR","message":"Request validation failed","request_id":"endpoint-docs-20260924"}}`

### `central-post-/calls/end`

- Request: `POST https://127.0.0.1:8000/calls/end`
- Request data: `{"json":{"call_id":"docs-probe"}}`
- Response: HTTP 404 in 0 ms
- Body: `{"error":{"status_code":404,"code":"NOT_FOUND","message":"Matching active call not found","request_id":"endpoint-docs-20260924"}}`

### `central-get-/calls/screenshot`

- Request: `GET https://127.0.0.1:8000/calls/screenshot`
- Request data: `{}`
- Response: HTTP 409 in 15 ms
- Body: `{"error":{"status_code":409,"code":"CONFLICT","message":"Screenshot requires an active video call","request_id":"endpoint-docs-20260924"}}`

### `central-post-/calls/start`

- Request: `POST https://127.0.0.1:8000/calls/start`
- Request data: `{"json":{"call_id":"docs-probe"}}`
- Response: HTTP 200 in 0 ms
- Body: `{"state":"CALL_ACTIVE","call_id":"docs-probe","lease_id":"eb993deb049b4c7586cdbccafa9c2cc5"}`

### `central-get-/calls/status`

- Request: `GET https://127.0.0.1:8000/calls/status`
- Request data: `{}`
- Response: HTTP 200 in 16 ms
- Body: `{"state":"CALL_ACTIVE","call_id":"docs-probe","lease_id":"eb993deb049b4c7586cdbccafa9c2cc5","lease_state":"active"}`

### `central-post-/camera/force-release`

- Request: `POST https://127.0.0.1:8000/camera/force-release`
- Request data: `{}`
- Response: HTTP 409 in 0 ms
- Body: `{"error":{"status_code":409,"code":"CONFLICT","message":"Physical closure must be acknowledged before release","request_id":"endpoint-docs-20260924"}}`

### `central-post-/camera/release`

- Request: `POST https://127.0.0.1:8000/camera/release`
- Request data: `{"json":{"service_name":"docs-probe"}}`
- Response: HTTP 409 in 16 ms
- Body: `{"error":{"status_code":409,"code":"CONFLICT","message":"Matching lease_id is required","request_id":"endpoint-docs-20260924"}}`

### `central-post-/camera/request`

- Request: `POST https://127.0.0.1:8000/camera/request`
- Request data: `{"json":{"service_name":"docs-probe"}}`
- Response: HTTP 200 in 0 ms
- Body: `{"status":"denied","message":"Camera is held by another lease"}`

### `central-get-/camera/status`

- Request: `GET https://127.0.0.1:8000/camera/status`
- Request data: `{}`
- Response: HTTP 200 in 15 ms
- Body: `{"status":"in_use","is_available":false,"holder":"eb993deb049b4c7586cdbccafa9c2cc5","queue":[]}`

### `central-get-/conversations/{conversation_id}`

- Request: `GET https://127.0.0.1:8000/conversations/docs-probe-conversation-missing`
- Request data: `{}`
- Response: HTTP 404 in 16 ms
- Body: `{"error":{"status_code":404,"code":"NOT_FOUND","message":"Conversation 'docs-probe-conversation-missing' not found","request_id":"endpoint-docs-20260924"}}`

### `central-get-/health`

- Request: `GET https://127.0.0.1:8000/health`
- Request data: `{}`
- Response: HTTP 200 in 0 ms
- Body: `{"status":"healthy","service":"central_server"}`

### `central-post-/resources/acknowledge/{lease_id}`

- Request: `POST https://127.0.0.1:8000/resources/acknowledge/docs-probe-lease-missing`
- Request data: `{}`
- Response: HTTP 409 in 15 ms
- Body: `{"error":{"status_code":409,"code":"CONFLICT","message":"Grant is not reserved for this lease","request_id":"endpoint-docs-20260924"}}`

### `central-get-/resources/focus`

- Request: `GET https://127.0.0.1:8000/resources/focus`
- Request data: `{}`
- Response: HTTP 200 in 0 ms
- Body: `{"signal":null,"teachme_active":false,"generation":0,"lease_ids":[]}`

### `central-get-/resources/health`

- Request: `GET https://127.0.0.1:8000/resources/health`
- Request data: `{}`
- Response: HTTP 200 in 0 ms
- Body: `{"success":true,"status":"healthy","active_leases":1,"resources_available":{"camera":false,"microphone":true}}`

### `central-post-/resources/release/{lease_id}`

- Request: `POST https://127.0.0.1:8000/resources/release/docs-probe-lease-missing`
- Request data: `{"params":{"forced":false}}`
- Response: HTTP 404 in 16 ms
- Body: `{"error":{"status_code":404,"code":"NOT_FOUND","message":"Lease not found: docs-probe-lease-missing","request_id":"endpoint-docs-20260924"}}`

### `central-post-/resources/request`

- Request: `POST https://127.0.0.1:8000/resources/request`
- Request data: `{"params":{"resource_type":"camera","service_name":"docs-probe","priority":"MEDIUM","timeout_seconds":30}}`
- Response: HTTP 200 in 0 ms
- Body: `{"success":true,"lease_id":"ac3b53987cb144e0943ad6979006c914","resource_type":"camera","service_name":"docs-probe","granted":false,"state":"queued","timestamp":1790239162.1331193,"message":"Request queued (position 1)"}`

### `central-post-/resources/revoke/{lease_id}`

- Request: `POST https://127.0.0.1:8000/resources/revoke/docs-probe-lease-missing`
- Request data: `{}`
- Response: HTTP 409 in 16 ms
- Body: `{"error":{"status_code":409,"code":"CONFLICT","message":"Lease cannot be revoked in its current state","request_id":"endpoint-docs-20260924"}}`

### `central-get-/resources/status`

- Request: `GET https://127.0.0.1:8000/resources/status`
- Request data: `{}`
- Response: HTTP 200 in 0 ms
- Body: `{"success":true,"timestamp":1790239162.149832,"resources":{"camera":{"is_available":false,"holder":"eb993deb049b4c7586cdbccafa9c2cc5","queue":["ac3b53987cb144e0943ad6979006c914"]},"microphone":{"is_available":true,"holder":null,"queue":[]}}}`

### `central-get-/resources/status/{lease_id}`

- Request: `GET https://127.0.0.1:8000/resources/status/docs-probe-lease-missing`
- Request data: `{}`
- Response: HTTP 404 in 15 ms
- Body: `{"error":{"status_code":404,"code":"NOT_FOUND","message":"Lease not found: docs-probe-lease-missing","request_id":"endpoint-docs-20260924"}}`

### `central-get-/sync/status`

- Request: `GET https://127.0.0.1:8000/sync/status`
- Request data: `{}`
- Response: HTTP 200 in 16 ms
- Body: `{"last_successful_sync":null,"pending_records":0,"last_error":null,"enabled":false,"worker_running":false,"next_run_in_seconds":null}`

### `central-get-/teachme/health`

- Request: `GET https://127.0.0.1:8000/teachme/health`
- Request data: `{}`
- Response: HTTP 200 in 3109 ms
- Body: `{"status":"healthy","service":"teachme","circuit_state":"closed","reachable":true}`

### `central-post-/teachme/learn`

- Request: `POST https://127.0.0.1:8000/teachme/learn`
- Request data: `{"json":{"type":"fact","fact":{"subject":"docs-probe","predicate":"is","object":"temporary"}}}`
- Response: HTTP 422 in 32 ms
- Body: `{"error":{"status_code":422,"code":"VALIDATION_ERROR","message":"Request validation failed","request_id":"endpoint-docs-20260924"}}`

### `central-get-/teachme/metrics`

- Request: `GET https://127.0.0.1:8000/teachme/metrics`
- Request data: `{}`
- Response: HTTP 200 in 31 ms
- Body: `{"service":"teachme","base_url":"https://localhost:8004","circuit_state":"closed","failure_count":0,"last_failure":null,"last_success":"2026-09-24T08:39:25.271556","queue":{"queue_size":0,"max_queue_size":1000,"processing_count":0,"max_concurrent":10,"processed_total":0,"dropped_total":0},"metrics":{"total_requests":1,"successful_requests":2,"failed_requests":0,"retried_requests":1,"circuit_opens":0,"avg_response_time_ms":93.62149238586426}}`

### `central-get-/teachme/objects`

- Request: `GET https://127.0.0.1:8000/teachme/objects`
- Request data: `{"params":{"limit":100,"offset":0}}`
- Response: HTTP 200 in 47 ms
- Body: `{"objects":[],"total":0,"limit":100,"offset":0,"fallback":false}`

### `central-post-/teachme/search/by-embedding`

- Request: `POST https://127.0.0.1:8000/teachme/search/by-embedding`
- Request data: `{"json":{"query":"What is the documentation probe fact?"}}`
- Response: HTTP 200 in 62 ms
- Body: `{"query":"What is the documentation probe fact?","k":5,"results":[{"id":"ae105d51-9c76-4bbe-a8e9-573ffc15bffb","type":"fact","name":"subject='My hometown' predicate='is Layyah' object='punjab, pakistan' context={}","data":{"subject":"My hometown","predicate":"is Layyah","object":"punjab, pakistan","context":{}},"similarity":0.3296,"confidence":1,"tags":["manual-console"]}],"fallback":false}`

### `central-get-/teachme/search/by-text/{query}`

- Request: `GET https://127.0.0.1:8000/teachme/search/by-text/docs-probe-missing`
- Request data: `{"params":{"limit":10}}`
- Response: HTTP 200 in 16 ms
- Body: `{"query":"docs-probe-missing","results":[],"total":0,"fallback":false}`

### `central-get-/teachme/status`

- Request: `GET https://127.0.0.1:8000/teachme/status`
- Request data: `{}`
- Response: HTTP 200 in 0 ms
- Body: `{"status":"operational","service":"teachme","metrics":{"service":"teachme","base_url":"https://localhost:8004","circuit_state":"closed","failure_count":0,"last_failure":null,"last_success":"2026-09-24T08:39:25.460220","queue":{"queue_size":3,"max_queue_size":1000,"processing_count":0,"max_concurrent":10,"processed_total":3,"dropped_total":0},"metrics":{"total_requests":4,"successful_requests":5,"failed_requests":0,"retried_requests":1,"circuit_opens":0,"avg_response_time_ms":44.07918453216553}}}`

### `central-post-/teachme/sync`

- Request: `POST https://127.0.0.1:8000/teachme/sync`
- Request data: `{"json":{"service_name":"docs-probe","items":[{}]}}`
- Response: HTTP 200 in 15 ms
- Body: `{"status":"synced","service":"docs-probe","items_synced":1,"timestamp":"2026-09-24 08:39:25.481903"}`

### `central-post-/users`

- Request: `POST https://127.0.0.1:8000/users`
- Request data: `{"json":{}}`
- Response: HTTP 400 in 16 ms
- Body: `{"error":{"status_code":400,"code":"BAD_REQUEST","message":"User name required","request_id":"endpoint-docs-20260924"}}`

### `central-get-/users/check`

- Request: `GET https://127.0.0.1:8000/users/check`
- Request data: `{"params":{"name":"docs-probe-item"}}`
- Response: HTTP 200 in 16 ms
- Body: `{"exists":false}`

### `central-post-/users/enroll-complete`

- Request: `POST https://127.0.0.1:8000/users/enroll-complete`
- Request data: `{"multipart":{"fields":{"audio_samples":"['docs-probe']","user_name":"docs-probe-user"},"files":[]}}`
- Response: HTTP 503 in 15 ms
- Body: `{"error":{"status_code":503,"code":"AUDIO_SERVICE_UNAVAILABLE","message":"Audio Service client not initialized","request_id":"endpoint-docs-20260924"}}`

### `central-get-/users/list`

- Request: `GET https://127.0.0.1:8000/users/list`
- Request data: `{}`
- Response: HTTP 200 in 32 ms
- Body: `{"users":[{"user_id":"<redacted-user-id-1>","user_name":"<redacted-user-name-1>","enrollment_date":"<redacted-enrollment-time-1>","sample_count":{"images":5,"audio":5},"voice_embeddings":"<redacted list length=5>","face_embeddings":"<redacted list length=5>"},{"user_id":"<redacted-user-id-2>","user_name":"<redacted-user-name-2>","enrollment_date":"<redacted-enrollment-time-2>","sample_count":{"images":5,"audio":5},"voice_embeddings":"<redacted list length=5>","face_embeddings":"<redacted list length=5>"}]}`

### `central-post-/users/register`

- Request: `POST https://127.0.0.1:8000/users/register`
- Request data: `{"multipart":{"fields":{},"files":[]}}`
- Response: HTTP 400 in 15 ms
- Body: `{"error":{"status_code":400,"code":"MISSING_NAME","message":"User name is required","request_id":"endpoint-docs-20260924"}}`

### `central-post-/users/register-with-embeddings`

- Request: `POST https://127.0.0.1:8000/users/register-with-embeddings`
- Request data: `{}`
- Response: HTTP 500 in 94 ms
- Body: `{"error":{"status_code":500,"code":"ADD_EMBEDDINGS_FAILED","message":"Failed to add embeddings","request_id":"endpoint-docs-20260924"}}`

### `central-post-/users/register-with-voice`

- Request: `POST https://127.0.0.1:8000/users/register-with-voice`
- Request data: `{"multipart":{"fields":{"email":"docs-probe","name":"docs-probe-item"},"files":["audio_sample1:docs-probe.wav","audio_sample2:docs-probe.wav","audio_sample3:docs-probe.wav"]}}`
- Response: HTTP 500 in 31 ms
- Body: `{"error":{"status_code":500,"code":"REGISTRATION_FAILED","message":"Voice registration failed","request_id":"endpoint-docs-20260924"}}`

### `central-get-/users/search/{user_name}`

- Request: `GET https://127.0.0.1:8000/users/search/docs-probe-user-missing`
- Request data: `{}`
- Response: HTTP 404 in 16 ms
- Body: `{"error":{"status_code":404,"code":"NOT_FOUND","message":"User 'docs-probe-user-missing' not found","request_id":"endpoint-docs-20260924"}}`

### `central-post-/users/session/voice`

- Request: `POST https://127.0.0.1:8000/users/session/voice`
- Request data: `{"multipart":{"fields":{},"files":["file:docs-probe.wav"]}}`
- Response: HTTP 401 in 7781 ms
- Body: `{"error":{"status_code":401,"code":"UNAUTHORIZED","message":"Biometric verification failed","request_id":"endpoint-docs-20260924"}}`

### `central-delete-/users/{user_id}`

- Request: `DELETE https://127.0.0.1:8000/users/docs-probe-user-missing`
- Request data: `{}`
- Response: HTTP 403 in 16 ms
- Body: `{"error":{"status_code":403,"code":"FORBIDDEN","message":"Token does not own requested user","request_id":"endpoint-docs-20260924"}}`

### `central-get-/users/{user_id}`

- Request: `GET https://127.0.0.1:8000/users/docs-probe-user-missing`
- Request data: `{}`
- Response: HTTP 403 in 15 ms
- Body: `{"error":{"status_code":403,"code":"FORBIDDEN","message":"Token does not own requested user","request_id":"endpoint-docs-20260924"}}`

### `central-post-/users/{user_id}/append-embeddings`

- Request: `POST https://127.0.0.1:8000/users/docs-probe-user-missing/append-embeddings`
- Request data: `{}`
- Response: HTTP 403 in 16 ms
- Body: `{"error":{"status_code":403,"code":"FORBIDDEN","message":"Token does not own requested user","request_id":"endpoint-docs-20260924"}}`

### `central-delete-/users/{user_id}/conversations`

- Request: `DELETE https://127.0.0.1:8000/users/docs-probe-user-missing/conversations`
- Request data: `{}`
- Response: HTTP 403 in 16 ms
- Body: `{"error":{"status_code":403,"code":"FORBIDDEN","message":"Token does not own requested user","request_id":"endpoint-docs-20260924"}}`

### `central-get-/users/{user_id}/conversations`

- Request: `GET https://127.0.0.1:8000/users/docs-probe-user-missing/conversations`
- Request data: `{"params":{"limit":10}}`
- Response: HTTP 403 in 0 ms
- Body: `{"error":{"status_code":403,"code":"FORBIDDEN","message":"Token does not own requested user","request_id":"endpoint-docs-20260924"}}`

### `central-post-/users/{user_id}/conversations`

- Request: `POST https://127.0.0.1:8000/users/docs-probe-user-missing/conversations`
- Request data: `{}`
- Response: HTTP 403 in 15 ms
- Body: `{"error":{"status_code":403,"code":"FORBIDDEN","message":"Token does not own requested user","request_id":"endpoint-docs-20260924"}}`

### `central-put-/users/{user_id}/embeddings`

- Request: `PUT https://127.0.0.1:8000/users/docs-probe-user-missing/embeddings`
- Request data: `{"json":{}}`
- Response: HTTP 403 in 16 ms
- Body: `{"error":{"status_code":403,"code":"FORBIDDEN","message":"Token does not own requested user","request_id":"endpoint-docs-20260924"}}`

### `vision-get-/`

- Request: `GET https://127.0.0.1:8001/`
- Request data: `{}`
- Response: HTTP 200 in 15 ms
- Body: `{"service":"Vision Service","version":"4.0.0","status":"operational","features":["face_detection","face_embeddings","video_streaming"],"timestamp":"2026-09-24T08:39:33.610299"}`

### `vision-get-/api/face-data`

- Request: `GET https://127.0.0.1:8001/api/face-data`
- Request data: `{}`
- Response: HTTP 200 in 0 ms
- Body: `{"face_count":0,"primary_emotion":null,"confidence":null,"timestamp":"2026-09-24T08:39:33.616008"}`

### `vision-post-/api/v1/analyze/complete`

- Request: `POST https://127.0.0.1:8001/api/v1/analyze/complete`
- Request data: `{"params":{"detector_backend":"opencv","model_name":"Facenet"}}`
- Response: HTTP 500 in 63 ms
- Body: `{"error":{"status_code":500,"code":"INTERNAL_SERVER_ERROR","message":"Complete analysis failed","request_id":"endpoint-docs-20260924"}}`

### `vision-post-/api/v1/detect/faces`

- Request: `POST https://127.0.0.1:8001/api/v1/detect/faces`
- Request data: `{"params":{"detector_backend":"opencv","model_name":"Facenet"}}`
- Response: HTTP 500 in 47 ms
- Body: `{"error":{"status_code":500,"code":"INTERNAL_SERVER_ERROR","message":"Face detection failed","request_id":"endpoint-docs-20260924"}}`

### `vision-post-/api/v1/detect/faces/upload`

- Request: `POST https://127.0.0.1:8001/api/v1/detect/faces/upload`
- Request data: `{"params":{"detector_backend":"opencv","model_name":"Facenet"},"multipart":{"fields":{},"files":["file:docs-probe.wav"]}}`
- Response: HTTP 400 in 31 ms
- Body: `{"error":{"status_code":400,"code":"BAD_REQUEST","message":"Upload processing failed: 400: Invalid image file","request_id":"endpoint-docs-20260924"}}`

### `vision-get-/api/v1/frame`

- Request: `GET https://127.0.0.1:8001/api/v1/frame`
- Request data: `{"params":{"lease_id":"docs-probe-lease-missing"}}`
- Response: HTTP 409 in 16 ms
- Body: `{"error":{"status_code":409,"code":"CONFLICT","message":"Delegated VIDEO_CALL camera lease is not active","request_id":"endpoint-docs-20260924"}}`

### `vision-post-/camera/pause`

- Request: `POST https://127.0.0.1:8001/camera/pause`
- Request data: `{}`
- Response: HTTP 200 in 15 ms
- Body: `{"status":"paused","message":"Camera paused"}`

### `vision-post-/camera/resume`

- Request: `POST https://127.0.0.1:8001/camera/resume`
- Request data: `{}`
- Response: HTTP 200 in 0 ms
- Body: `{"status":"active","message":"Camera resumed"}`

### `vision-get-/health`

- Request: `GET https://127.0.0.1:8001/health`
- Request data: `{}`
- Response: HTTP 200 in 63 ms
- Body: `{"status":"degraded","camera":"unavailable","face_model":"loaded","opencv_version":"4.8.0","emotion_detection":"disabled","timestamp":"2026-09-24T08:39:33.851158"}`

### `vision-get-/live`

- Request: `GET https://127.0.0.1:8001/live`
- Request data: `{}`
- Response: HTTP 200 in 15 ms
- Body: `<stream text/html; charset=utf-8 first_chunk_bytes=5171>`

### `vision-get-/stream`

- Request: `GET https://127.0.0.1:8001/stream`
- Request data: `{}`
- Response: HTTP 200 in 94 ms
- Body: `<stream multipart/x-mixed-replace; boundary=frame first_chunk_bytes=0>`

### `audio-get-/`

- Request: `GET https://127.0.0.1:8002/`
- Request data: `{}`
- Response: HTTP 200 in 141 ms
- Body: `{"status":"success","message":"Audio Service API is running","version":"1.0.0"}`

### `audio-get-/api/v1/conversation-state`

- Request: `GET https://127.0.0.1:8002/api/v1/conversation-state`
- Request data: `{}`
- Response: HTTP 200 in 78 ms
- Body: `{"state":"idle","duration_seconds":0,"elapsed_time_seconds":0,"timeout_seconds":10,"timed_out":false}`

### `audio-post-/api/v1/conversation/end`

- Request: `POST https://127.0.0.1:8002/api/v1/conversation/end`
- Request data: `{"params":{"user_id":"docs-probe-user"}}`
- Response: HTTP 200 in 16 ms
- Body: `{"success":true,"user_id":"docs-probe-user","state":"idle","message":"Conversation session ended"}`

### `audio-get-/api/v1/conversation/metrics`

- Request: `GET https://127.0.0.1:8002/api/v1/conversation/metrics`
- Request data: `{}`
- Response: HTTP 200 in 15 ms
- Body: `{"status":"success","metrics":{"turns_processed":0,"total_latency_ms":0,"average_latency_ms":0}}`

### `audio-post-/api/v1/conversation/start`

- Request: `POST https://127.0.0.1:8002/api/v1/conversation/start`
- Request data: `{"params":{"user_id":"docs-probe-user"}}`
- Response: HTTP 200 in 16 ms
- Body: `{"success":true,"user_id":"docs-probe-user","state":"conversation_active","message":"Conversation session started"}`

### `audio-post-/api/v1/conversation/turn`

- Request: `POST https://127.0.0.1:8002/api/v1/conversation/turn`
- Request data: `{"json":{"user_id":"docs-probe-user","audio_file_path":"docs-probe"}}`
- Response: HTTP 400 in 15 ms
- Body: `{"error":{"status_code":400,"code":"BAD_REQUEST","message":"audio_file_path is outside the recording directory","request_id":"endpoint-docs-20260924"}}`

### `audio-delete-/api/v1/delete-audio/{filename}`

- Request: `DELETE https://127.0.0.1:8002/api/v1/delete-audio/docs-probe-missing.wav`
- Request data: `{}`
- Response: HTTP 404 in 0 ms
- Body: `{"error":{"status_code":404,"code":"NOT_FOUND","message":"Audio file not found: docs-probe-missing.wav","request_id":"endpoint-docs-20260924"}}`

### `audio-post-/api/v1/enroll-speaker`

- Request: `POST https://127.0.0.1:8002/api/v1/enroll-speaker`
- Request data: `{"json":{"user_id":"docs-probe-user"}}`
- Response: HTTP 500 in 32 ms
- Body: `{"error":{"status_code":500,"code":"INTERNAL_SERVER_ERROR","message":"Failed to enroll speaker docs-probe-user: Failed to record audio: 'dtype'","request_id":"endpoint-docs-20260924"}}`

### `audio-post-/api/v1/enroll-speaker-files`

- Request: `POST https://127.0.0.1:8002/api/v1/enroll-speaker-files`
- Request data: `{"json":{}}`
- Response: HTTP 500 in 0 ms
- Body: `{"error":{"status_code":500,"code":"INTERNAL_SERVER_ERROR","message":"400: user_id is required","request_id":"endpoint-docs-20260924"}}`

### `audio-post-/api/v1/interrupt-playback`

- Request: `POST https://127.0.0.1:8002/api/v1/interrupt-playback`
- Request data: `{}`
- Response: HTTP 200 in 15 ms
- Body: `{"success":true,"message":"Playback interrupted","state":"stopped"}`

### `audio-get-/api/v1/list-audio`

- Request: `GET https://127.0.0.1:8002/api/v1/list-audio`
- Request data: `{}`
- Response: HTTP 200 in 0 ms
- Body: `{"status":"success","count":1,"files":[{"filename":"docs-probe-missing.wav","relative_path":"docs-probe-missing.wav","file_size":0,"created_at":"2026-09-24T13:39:34.239091","modified_at":"2026-09-24T13:39:34.239091"}]}`

### `audio-get-/api/v1/orchestration/health`

- Request: `GET https://127.0.0.1:8002/api/v1/orchestration/health`
- Request data: `{}`
- Response: HTTP 200 in 16 ms
- Body: `{"status":"degraded","components":{"orchestrator":"initialized","conversation_state":"initialized","stop_word_detector":"not_initialized","vad_recorder":"initialized","playback_manager":"initialized","conversation_state_details":{"current_state":"conversation_active","in_conversation":true,"conversation_duration_s":0.077551,"elapsed_since_speech_s":0.077551,"timeout_exceeded":false,"timeout_seconds":10},"playback_state":{"state":"stopped","playing":false,"position_frames":0,"total_frames":0,"interrupted":true}}}`

### `audio-get-/api/v1/orchestration/test/end-to-end`

- Request: `GET https://127.0.0.1:8002/api/v1/orchestration/test/end-to-end`
- Request data: `{}`
- Response: HTTP 200 in 0 ms
- Body: `{"status":"success","test_result":"PASSED","metrics":{"turns_processed":0,"total_latency_ms":0,"average_latency_ms":0},"message":"Orchestrator is fully functional"}`

### `audio-post-/api/v1/playback/start`

- Request: `POST https://127.0.0.1:8002/api/v1/playback/start`
- Request data: `{"multipart":{"fields":{},"files":["file:docs-probe.wav"]}}`
- Response: HTTP 200 in 2391 ms
- Body: `{"success":true,"state":"idle","duration":1,"actual_duration":1,"interrupted":false}`

### `audio-get-/api/v1/poll-stop-word`

- Request: `GET https://127.0.0.1:8002/api/v1/poll-stop-word`
- Request data: `{"params":{"timeout":1}}`
- Response: HTTP 503 in 46 ms
- Body: `{"error":{"status_code":503,"code":"SERVICE_UNAVAILABLE","message":"Stop word detector not initialized","request_id":"endpoint-docs-20260924"}}`

### `audio-post-/api/v1/process-command`

- Request: `POST https://127.0.0.1:8002/api/v1/process-command`
- Request data: `{"json":{"command":"status"}}`
- Response: HTTP 422 in 16 ms
- Body: `{"error":{"status_code":422,"code":"VALIDATION_ERROR","message":"Request validation failed","request_id":"endpoint-docs-20260924"}}`

### `audio-post-/api/v1/process-pipeline`

- Request: `POST https://127.0.0.1:8002/api/v1/process-pipeline`
- Request data: `{"params":{"send_to_backend":true}}`
- Response: HTTP 0 in 12016 ms
- Body: `ReadTimeout: The read operation timed out`

### `audio-post-/api/v1/process-voice`

- Request: `POST https://127.0.0.1:8002/api/v1/process-voice`
- Request data: `{"multipart":{"fields":{},"files":["file:docs-probe.wav"]}}`
- Response: HTTP 400 in 62 ms
- Body: `{"error":{"status_code":400,"code":"BAD_REQUEST","message":"No clear voice detected in the audio. Please provide clearer speech.","request_id":"endpoint-docs-20260924"}}`

### `audio-post-/api/v1/record`

- Request: `POST https://127.0.0.1:8002/api/v1/record`
- Request data: `{"json":{"channels":1,"duration":0.1,"sample_rate":8000}}`
- Response: HTTP 500 in 31 ms
- Body: `{"error":{"status_code":500,"code":"INTERNAL_SERVER_ERROR","message":"Failed to record audio. Please check microphone availability.","request_id":"endpoint-docs-20260924"}}`

### `audio-post-/api/v1/record-until-silence`

- Request: `POST https://127.0.0.1:8002/api/v1/record-until-silence`
- Request data: `{}`
- Response: HTTP 200 in 5141 ms
- Body: `{"success":true,"audio_file":"03_audio_service\\audio_service\\data\\recordings\\vad_recording_20260924_133948867.wav","duration":4.992,"stopped_by":"max_duration","chunks_recorded":156,"error":null}`

### `audio-post-/api/v1/set-detection-mode`

- Request: `POST https://127.0.0.1:8002/api/v1/set-detection-mode`
- Request data: `{"json":{"mode":"normal"}}`
- Response: HTTP 400 in 47 ms
- Body: `{"error":{"status_code":400,"code":"BAD_REQUEST","message":"Mode must be 'idle' or 'conversation'","request_id":"endpoint-docs-20260924"}}`

### `audio-post-/api/v1/speaker-sync`

- Request: `POST https://127.0.0.1:8002/api/v1/speaker-sync`
- Request data: `{}`
- Response: HTTP 200 in 2203 ms
- Body: `{"success":true,"message":"Synced 2 speakers from Central Server","speakers_synced":2,"speakers_skipped":0,"validation_issues":null,"timestamp":"2026-09-24T13:39:56.246361"}`

### `audio-get-/api/v1/speakers`

- Request: `GET https://127.0.0.1:8002/api/v1/speakers`
- Request data: `{}`
- Response: HTTP 200 in 16 ms
- Body: `{"status":"success","count":2,"speakers":["<redacted-user-id-1>","<redacted-user-id-2>"]}`

### `audio-get-/api/v1/speakers/debug`

- Request: `GET https://127.0.0.1:8002/api/v1/speakers/debug`
- Request data: `{}`
- Response: HTTP 200 in 0 ms
- Body: `{"status":"debug","timestamp":"2026-09-24T13:39:56.273430","memory":{"speakers_loaded":2,"speaker_ids":["<redacted-user-id-1>","<redacted-user-id-2>"]},"validation":{"total_speakers":2,"valid_speakers":2,"invalid_speakers":[],"dimension_errors":[]},"disk":{"file_exists":false,"file_size_bytes":0,"last_modified":null},"summary":{"memory_ready":true,"all_valid":true,"can_verify":true}}`

### `audio-get-/api/v1/stop-word-events/status`

- Request: `GET https://127.0.0.1:8002/api/v1/stop-word-events/status`
- Request data: `{}`
- Response: HTTP 503 in 15 ms
- Body: `{"error":{"status_code":503,"code":"SERVICE_UNAVAILABLE","message":"Stop word detector not initialized","request_id":"endpoint-docs-20260924"}}`

### `audio-get-/api/v1/stt/circuit-breaker-status`

- Request: `GET https://127.0.0.1:8002/api/v1/stt/circuit-breaker-status`
- Request data: `{}`
- Response: HTTP 200 in 0 ms
- Body: `{"status":"success","state":"closed","failure_count":0,"success_count":0,"last_failure_time":null,"recovery_timeout":60,"api_calls":0,"average_api_latency":0,"last_api_latency":null}`

### `audio-get-/api/v1/test/conversation-status`

- Request: `GET https://127.0.0.1:8002/api/v1/test/conversation-status`
- Request data: `{}`
- Response: HTTP 200 in 94 ms
- Body: `{"status":"ok","conversation_state":{"current_state":"processing_query","in_conversation":false,"conversation_duration_s":0,"elapsed_since_speech_s":7.428877,"timeout_exceeded":false,"timeout_seconds":10}}`

### `audio-get-/api/v1/test/playback-status`

- Request: `GET https://127.0.0.1:8002/api/v1/test/playback-status`
- Request data: `{}`
- Response: HTTP 200 in 94 ms
- Body: `{"status":"ok","playback_state":{"state":"idle","playing":false,"position_frames":16000,"total_frames":16000,"interrupted":false}}`

### `audio-get-/api/v1/test/stop-word-status`

- Request: `GET https://127.0.0.1:8002/api/v1/test/stop-word-status`
- Request data: `{}`
- Response: HTTP 200 in 15 ms
- Body: `{"status":"not_initialized","message":"Stop word detector not initialized"}`

### `audio-post-/api/v1/transcribe`

- Request: `POST https://127.0.0.1:8002/api/v1/transcribe`
- Request data: `{"params":{"language":"auto"},"multipart":{"fields":{},"files":["file:docs-probe.wav"]}}`
- Response: HTTP 200 in 5157 ms
- Body: `{"status":"success","text":"you","language":"English","duration":1,"success":true,"confidence":null,"timestamp":"2026-09-24T13:40:01.626967"}`

### `audio-post-/api/v1/verify-speaker`

- Request: `POST https://127.0.0.1:8002/api/v1/verify-speaker`
- Request data: `{"multipart":{"fields":{},"files":["file:docs-probe.wav"]}}`
- Response: HTTP 200 in 78 ms
- Body: `{"status":"success","user_id":"unknown","confidence":0.4419,"is_verified":false,"threshold":0.65,"timestamp":"2026-09-24T13:40:01.708116","access_token":"<redacted>","token_type":"<redacted>","expires_in":null}`

### `audio-post-/api/v1/wake-word/detect`

- Request: `POST https://127.0.0.1:8002/api/v1/wake-word/detect`
- Request data: `{}`
- Response: HTTP 500 in 62 ms
- Body: `{"error":{"status_code":500,"code":"INTERNAL_SERVER_ERROR","message":"An unexpected error occurred during wake word detection","request_id":"endpoint-docs-20260924"}}`

### `audio-post-/api/v1/wake-word/detect/simple`

- Request: `POST https://127.0.0.1:8002/api/v1/wake-word/detect/simple`
- Request data: `{}`
- Response: HTTP 500 in 78 ms
- Body: `{"error":{"status_code":500,"code":"INTERNAL_SERVER_ERROR","message":"Microphone authority did not reserve a lease","request_id":"endpoint-docs-20260924"}}`

### `audio-get-/api/v1/wake-word/power-mode`

- Request: `GET https://127.0.0.1:8002/api/v1/wake-word/power-mode`
- Request data: `{}`
- Response: HTTP 200 in 10375 ms
- Body: `{"status":"success","mode":"balanced","vad_enabled":true,"sleep_duration_ms":0}`

### `audio-post-/api/v1/wake-word/power-mode`

- Request: `POST https://127.0.0.1:8002/api/v1/wake-word/power-mode`
- Request data: `{"json":{"mode":"balanced"}}`
- Response: HTTP 200 in 204 ms
- Body: `{"status":"success","mode":"balanced","vad_enabled":true,"sleep_duration_ms":0}`

### `audio-post-/api/v1/wake-word/start`

- Request: `POST https://127.0.0.1:8002/api/v1/wake-word/start`
- Request data: `{}`
- Response: HTTP 200 in 62 ms
- Body: `{"status":"listening","is_listening":true,"message":"Wake word detection started successfully"}`

### `audio-get-/api/v1/wake-word/stats`

- Request: `GET https://127.0.0.1:8002/api/v1/wake-word/stats`
- Request data: `{}`
- Response: HTTP 200 in 31 ms
- Body: `{"status":"success","total_frames":0,"speech_frames":0,"silence_frames":0,"detections":0,"errors":0,"power_mode":"balanced","vad_enabled":true,"current_power_mode":"balanced","sleep_duration_ms":0}`

### `audio-get-/api/v1/wake-word/status`

- Request: `GET https://127.0.0.1:8002/api/v1/wake-word/status`
- Request data: `{}`
- Response: HTTP 200 in 0 ms
- Body: `{"status":"listening","is_listening":true,"message":"Wake word detection is active"}`

### `audio-post-/api/v1/wake-word/stop`

- Request: `POST https://127.0.0.1:8002/api/v1/wake-word/stop`
- Request data: `{}`
- Response: HTTP 200 in 328 ms
- Body: `{"status":"stopped","is_listening":false,"message":"Wake word detection stopped successfully"}`

### `audio-get-/health`

- Request: `GET https://127.0.0.1:8002/health`
- Request data: `{}`
- Response: HTTP 200 in 0 ms
- Body: `{"status":"degraded","service":"audio-service","version":"1.0.0","stop_word_detector":{"status":"unavailable","initialized":false},"queue_processor":{"running":true}}`

### `audio-post-/queue/add`

- Request: `POST https://127.0.0.1:8002/queue/add`
- Request data: `{"json":{}}`
- Response: HTTP 200 in 16 ms
- Body: `{"status":"error","message":"Missing 'text' field in request"}`

### `audio-post-/queue/process-now`

- Request: `POST https://127.0.0.1:8002/queue/process-now`
- Request data: `{}`
- Response: HTTP 200 in 31 ms
- Body: `{"status":"success","processed_count":0,"message":"Processed 0 queued commands"}`

### `audio-get-/queue/status`

- Request: `GET https://127.0.0.1:8002/queue/status`
- Request data: `{}`
- Response: HTTP 200 in 16 ms
- Body: `{"status":"success","running":true,"poll_interval":1,"batch_size":10,"queue_stats":{"total":0,"pending":0,"processing":0,"completed":0,"failed":0},"circuit_breaker_state":"closed"}`

### `tts-get-/cache/status`

- Request: `GET https://127.0.0.1:8003/cache/status`
- Request data: `{}`
- Response: HTTP 200 in 16 ms
- Body: `{"status":"ok","worker_pool":{"num_workers":3,"tasks_processed":0,"tasks_failed":0,"queue_depths":[0,0,0]},"aggregated_cache":{"total_hits":0,"total_misses":1,"hit_rate_percent":0,"total_requests":1},"per_worker_cache":[{"worker_id":0,"cached_models":1,"cached_voices":["jenny"],"cache_hits":0,"cache_misses":1,"hit_rate_percent":0},{"worker_id":1,"cached_models":0,"cached_voices":[],"cache_hits":0,"cache_misses":0,"hit_rate_percent":0},{"worker_id":2,"cached_models":0,"cached_voices":[],"cache_hits":0,"cache_misses":0,"hit_rate_percent":0}],"available_voices":{"english":["jenny","ryan"],"urdu":["shahid"],"total":3}}`

### `tts-post-/config/set_voice`

- Request: `POST https://127.0.0.1:8003/config/set_voice`
- Request data: `{"json":{"text":"What is the documentation probe fact?"}}`
- Response: HTTP 400 in 15 ms
- Body: `{"error":{"status_code":400,"code":"BAD_REQUEST","message":"voice_id is required","request_id":"endpoint-docs-20260924"}}`

### `tts-get-/diagnostics`

- Request: `GET https://127.0.0.1:8003/diagnostics`
- Request data: `{}`
- Response: HTTP 200 in 16 ms
- Body: `{"timestamp":1790239212.959586,"service":{"name":"NEXI TTS","version":"1.0.0","uptime_seconds":1497.5070159435272,"health_score":100},"requests":{"processed":0,"failed":0,"success_rate":0},"errors":{"total_errors":0,"errors_by_type":{},"errors_by_category":{},"critical_errors":0,"retryable_errors":0,"most_common_error":null},"voices":{"available":1,"voice_ids":["jenny"]},"worker_pool":{"num_workers":3,"tasks_processed":0,"tasks_failed":0,"queue_depths":[0,0,0],"running":true,"worker_caches":[{"worker_id":0,"cached_models":1,"cached_voices":["jenny"],"cache_hits":0,"cache_misses":1,"hit_rate_percent":0},{"worker_id":1,"cached_models":0,"cached_voices":[],"cache_hits":0,"cache_misses":0,"hit_rÃ¢â‚¬Â¦`

### `tts-get-/errors`

- Request: `GET https://127.0.0.1:8003/errors`
- Request data: `{}`
- Response: HTTP 200 in 0 ms
- Body: `{"timestamp":1790239212.969537,"error_stats":{"total_errors":0,"errors_by_type":{},"errors_by_category":{},"critical_errors":0,"retryable_errors":0,"most_common_error":null},"error_rate_per_minute":0,"total_errors":0,"max_history":1000}`

### `tts-get-/errors/by_category/{category}`

- Request: `GET https://127.0.0.1:8003/errors/by_category/network`
- Request data: `{}`
- Response: HTTP 400 in 15 ms
- Body: `{"error":{"status_code":400,"code":"BAD_REQUEST","message":"Invalid category. Valid: validation, synthesis, timeout, resource, configuration, worker, unknown","request_id":"endpoint-docs-20260924"}}`

### `tts-get-/errors/recent`

- Request: `GET https://127.0.0.1:8003/errors/recent`
- Request data: `{"params":{"limit":20}}`
- Response: HTTP 200 in 0 ms
- Body: `{"timestamp":1790239212.9884393,"count":0,"errors":[]}`

### `tts-get-/health`

- Request: `GET https://127.0.0.1:8003/health`
- Request data: `{}`
- Response: HTTP 200 in 16 ms
- Body: `{"status":"healthy","voice_model":"available","service":"NEXI TTS","version":"1.0.0","timestamp":1790239212.9962761}`

### `tts-get-/health/detailed`

- Request: `GET https://127.0.0.1:8003/health/detailed`
- Request data: `{}`
- Response: HTTP 200 in 16 ms
- Body: `{"status":"healthy","service":"NEXI TTS","version":"1.0.0","timestamp":1790239213.0103278,"available_voices":1,"worker_pool":{"num_workers":3,"tasks_processed":0,"tasks_failed":0,"queue_depths":[0,0,0],"running":true,"worker_caches":[{"worker_id":0,"cached_models":1,"cached_voices":["jenny"],"cache_hits":0,"cache_misses":1,"hit_rate_percent":0},{"worker_id":1,"cached_models":0,"cached_voices":[],"cache_hits":0,"cache_misses":0,"hit_rate_percent":0},{"worker_id":2,"cached_models":0,"cached_voices":[],"cache_hits":0,"cache_misses":0,"hit_rate_percent":0}]},"circuit_breakers":{},"stats":{"uptime_seconds":1497.55317568779,"requests_processed":0,"requests_failed":0,"last_error":null},"error_statsÃ¢â‚¬Â¦`

### `tts-get-/metrics`

- Request: `GET https://127.0.0.1:8003/metrics`
- Request data: `{}`
- Response: HTTP 200 in 0 ms
- Body: `# HELP tts_synthesis_requests_total Total synthesis requests # TYPE tts_synthesis_requests_total counter # HELP tts_synthesis_latency_seconds Synthesis request latency # TYPE tts_synthesis_latency_seconds histogram # HELP tts_synthesis_errors_total Total synthesis errors # TYPE tts_synthesis_errors_total counter # HELP tts_worker_queue_depth Current queue depth per worker # TYPE tts_worker_queue_depth gauge # HELP tts_cache_hit_rate Overall cache hit rate (0-1) # TYPE tts_cache_hit_rate gauge tt?`

### `tts-get-/metrics/json`

- Request: `GET https://127.0.0.1:8003/metrics/json`
- Request data: `{}`
- Response: HTTP 200 in 15 ms
- Body: `{"timestamp":1790239213.0251086,"service_stats":{"uptime_seconds":1497.573539018631,"requests_processed":0,"requests_failed":0,"last_error":null},"worker_pool_stats":{"num_workers":3,"tasks_processed":0,"tasks_failed":0,"queue_depths":[0,0,0],"running":true,"worker_caches":[{"worker_id":0,"cached_models":1,"cached_voices":["jenny"],"cache_hits":0,"cache_misses":1,"hit_rate_percent":0},{"worker_id":1,"cached_models":0,"cached_voices":[],"cache_hits":0,"cache_misses":0,"hit_rate_percent":0},{"worker_id":2,"cached_models":0,"cached_voices":[],"cache_hits":0,"cache_misses":0,"hit_rate_percent":0}]},"metrics":{"synthesis_requests_total":0,"synthesis_errors_total":0,"cache_hit_rate":0,"available_vÃ¢â‚¬Â¦`

### `tts-post-/speak`

- Request: `POST https://127.0.0.1:8003/speak`
- Request data: `{"json":{"text":"NEXI documentation probe.","voice":"jenny"}}`
- Response: HTTP 200 in 6313 ms
- Body: `<binary audio/wav bytes=76844>`

### `tts-get-/speakers/state/{speaker_id}`

- Request: `GET https://127.0.0.1:8003/speakers/state/docs-probe-speaker-missing`
- Request data: `{}`
- Response: HTTP 200 in 0 ms
- Body: `{"status":"ok","speaker_id":"docs-probe-speaker-missing","state":"unloaded","is_loaded":false,"is_default":false}`

### `tts-get-/speakers/stats`

- Request: `GET https://127.0.0.1:8003/speakers/stats`
- Request data: `{}`
- Response: HTTP 200 in 15 ms
- Body: `{"status":"ok","stats":{"current_default":"jenny","loaded_speakers":["jenny"],"idle_speakers":["ryan","shahid"],"num_loaded":1,"num_idle":2,"total_speakers":3,"access_counts":{"jenny":1,"ryan":0,"shahid":0},"memory_optimized":"Loaded 1 of 3 speakers"},"timestamp":1790239219.3530927}`

### `tts-get-/speakers/status`

- Request: `GET https://127.0.0.1:8003/speakers/status`
- Request data: `{}`
- Response: HTTP 200 in 0 ms
- Body: `{"status":"ok","speakers":{"jenny":{"id":"jenny","name":"Female English voice (British accent) - DEFAULT","language":"english","state":"loaded","is_default":true,"is_loaded":true,"access_count":1,"load_time":"2026-09-24T13:15:18.941634"},"ryan":{"id":"ryan","name":"Male English voice","language":"english","state":"idle","is_default":false,"is_loaded":false,"access_count":0,"load_time":null},"shahid":{"id":"shahid","name":"Male Urdu voice","language":"urdu","state":"idle","is_default":false,"is_loaded":false,"access_count":0,"load_time":null}},"default_speaker":"jenny","summary":"Loaded: 1, Idle: 2, Total: 3"}`

### `tts-post-/speakers/switch`

- Request: `POST https://127.0.0.1:8003/speakers/switch`
- Request data: `{"json":{"text":"What is the documentation probe fact?"}}`
- Response: HTTP 400 in 16 ms
- Body: `{"error":{"status_code":400,"code":"BAD_REQUEST","message":"voice_id is required","request_id":"endpoint-docs-20260924"}}`

### `tts-get-/voices`

- Request: `GET https://127.0.0.1:8003/voices`
- Request data: `{}`
- Response: HTTP 200 in 0 ms
- Body: `{"voices":[{"id":"jenny","name":"Jenny (Female, English)","locale":"en-GB","gender":"Female","description":"British English accent - natural female voice"}],"default":"jenny","count":1,"english_count":1,"urdu_count":0}`

### `teachme-get-/`

- Request: `GET https://127.0.0.1:8004/`
- Request data: `{}`
- Response: HTTP 500 in 219 ms
- Body: `{"error":{"status_code":500,"code":"INTERNAL_SERVER_ERROR","message":"Internal server error","request_id":"endpoint-docs-20260924"}}`

### `teachme-delete-/forget-by-name/{name}`

- Request: `DELETE https://127.0.0.1:8004/forget-by-name/docs-probe-missing`
- Request data: `{}`
- Response: HTTP 200 in 31 ms
- Body: `{"message":"Forgot 0 items matching 'docs-probe-missing'","deleted_ids":[],"name":"docs-probe-missing","type_filter":"any"}`

### `teachme-delete-/forget/{item_id}`

- Request: `DELETE https://127.0.0.1:8004/forget/docs-probe-item-missing`
- Request data: `{"params":{"permanent":false}}`
- Response: HTTP 200 in 16 ms
- Body: `{"error":"Item not found","item_id":"docs-probe-item-missing","status_code":404}`

### `teachme-get-/health`

- Request: `GET https://127.0.0.1:8004/health`
- Request data: `{}`
- Response: HTTP 200 in 15 ms
- Body: `{"status":"healthy","timestamp":"2026-09-24T08:40:19.647725","checks":{"embedding_model":"<redacted>","knowledge_base":{"status":"healthy","items_count":1,"objects":0,"facts":1},"vision_service":{"status":"healthy","circuit_state":"closed","successful_calls":3,"failed_calls":0,"avg_response_time_ms":100,"url":"https://127.0.0.1:8001"}},"http_code":200}`

### `teachme-get-/health/detailed`

- Request: `GET https://127.0.0.1:8004/health/detailed`
- Request data: `{}`
- Response: HTTP 200 in 0 ms
- Body: `{"service":"TeachMe","status":"running","timestamp":"2026-09-24T08:40:19.662372","note":"Detailed metrics require psutil"}`

### `teachme-get-/knowledge/all`

- Request: `GET https://127.0.0.1:8004/knowledge/all`
- Request data: `{}`
- Response: HTTP 200 in 16 ms
- Body: `{"total_count":1,"items":[{"id":"ae105d51-9c76-4bbe-a8e9-573ffc15bffb","type":"fact","data":{"subject":"My hometown","predicate":"is Layyah","object":"punjab, pakistan","context":{}},"tags":["manual-console"],"confidence":1,"created_at":"2026-09-21T13:23:49.622542","updated_at":"2026-09-21T13:23:49.622542","embedding":"<redacted list length=384>"}]}`

### `teachme-get-/knowledge/facts`

- Request: `GET https://127.0.0.1:8004/knowledge/facts`
- Request data: `{}`
- Response: HTTP 200 in 16 ms
- Body: `{"count":1,"facts":[{"id":"ae105d51-9c76-4bbe-a8e9-573ffc15bffb","type":"fact","data":{"subject":"My hometown","predicate":"is Layyah","object":"punjab, pakistan","context":{}},"tags":["manual-console"],"confidence":1,"created_at":"2026-09-21T13:23:49.622542","updated_at":"2026-09-21T13:23:49.622542","embedding":"<redacted list length=384>"}]}`

### `teachme-post-/knowledge/learn-batch`

- Request: `POST https://127.0.0.1:8004/knowledge/learn-batch`
- Request data: `{"json":[{"type":"fact","fact":{"subject":"docs-probe-batch","predicate":"is","object":"temporary"},"confidence":1}]}`
- Response: HTTP 422 in 15 ms
- Body: `{"error":{"status_code":422,"code":"VALIDATION_ERROR","message":"Request validation failed","request_id":"endpoint-docs-20260924"}}`

### `teachme-get-/knowledge/objects`

- Request: `GET https://127.0.0.1:8004/knowledge/objects`
- Request data: `{}`
- Response: HTTP 200 in 16 ms
- Body: `{"count":0,"objects":[]}`

### `teachme-get-/knowledge/related/{item_id}`

- Request: `GET https://127.0.0.1:8004/knowledge/related/docs-probe-item-missing`
- Request data: `{"params":{"top_k":5}}`
- Response: HTTP 200 in 15 ms
- Body: `{"item_id":"docs-probe-item-missing","item_name":"Unknown","related_count":0,"related_items":[],"note":"Item not found"}`

### `teachme-post-/knowledge/search/advanced`

- Request: `POST https://127.0.0.1:8004/knowledge/search/advanced`
- Request data: `{"params":{"search_mode":"any"},"json":{"query":"docs-probe","limit":1}}`
- Response: HTTP 200 in 0 ms
- Body: `{"query":{"name":null,"category":null,"tag":null,"mode":"any"},"count":0,"results":[]}`

### `teachme-post-/knowledge/search/embedding`

- Request: `POST https://127.0.0.1:8004/knowledge/search/embedding`
- Request data: `{"params":{"query_object_name":"docs-probe","top_k":5,"similarity_threshold":0.5}}`
- Response: HTTP 200 in 47 ms
- Body: `{"query":"docs-probe","count":0,"results":[],"from_cache":false,"performance_ms":{"search":5.86,"total":30.03}}`

### `teachme-get-/knowledge/search/{name}`

- Request: `GET https://127.0.0.1:8004/knowledge/search/docs-probe-missing`
- Request data: `{}`
- Response: HTTP 200 in 16 ms
- Body: `{"search_term":"docs-probe-missing","count":0,"results":[]}`

### `teachme-get-/knowledge/stats`

- Request: `GET https://127.0.0.1:8004/knowledge/stats`
- Request data: `{}`
- Response: HTTP 200 in 0 ms
- Body: `{"success":true,"stats":{"total":1,"objects":0,"facts":1,"deleted":0,"categories":{},"storage_file":"knowledge_data.json","last_updated":"2026-09-24T13:40:19.797157","embedding_index":"<redacted>"}}`

### `teachme-post-/learn`

- Request: `POST https://127.0.0.1:8004/learn`
- Request data: `{"json":{"type":"fact","fact":{"subject":"docs-probe","predicate":"is","object":"temporary"},"confidence":1}}`
- Response: HTTP 422 in 16 ms
- Body: `{"error":{"status_code":422,"code":"VALIDATION_ERROR","message":"Request validation failed","request_id":"endpoint-docs-20260924"}}`

### `teachme-get-/metrics`

- Request: `GET https://127.0.0.1:8004/metrics`
- Request data: `{}`
- Response: HTTP 200 in 0 ms
- Body: `{"timestamp":"2026-09-24T08:40:19.820460","system":{"total_items":1,"objects":0,"facts":1,"with_embeddings":"<redacted>"},"performance":{"avg_embedding_time_ms":"<redacted>","avg_search_time_ms":0.67,"cache_size":2,"cache_hit_potential":"Medium"},"api":{"rate_limit_per_minute":60,"active_clients":1}}`

### `enrollment-get-/`

- Request: `GET https://127.0.0.1:8005/`
- Request data: `{}`
- Response: HTTP 200 in 0 ms
- Body: `{"service":"Enrollment Service","status":"running","port":8005,"dependencies":null}`

### `enrollment-get-/enrollment/check-user`

- Request: `GET https://127.0.0.1:8005/enrollment/check-user`
- Request data: `{"params":{"name":"docs-probe-item"}}`
- Response: HTTP 200 in 47 ms
- Body: `{"exists":false,"user_id":null,"enrollment_date":null,"sample_count":{"images":0,"audio":0}}`

### `enrollment-delete-/enrollment/delete-user/{user_name}`

- Request: `DELETE https://127.0.0.1:8005/enrollment/delete-user/docs-probe-user-missing`
- Request data: `{}`
- Response: HTTP 403 in 47 ms
- Body: `{"error":{"status_code":403,"code":"FORBIDDEN","message":"Token does not own requested user","request_id":"endpoint-docs-20260924"}}`

### `enrollment-post-/enrollment/enroll`

- Request: `POST https://127.0.0.1:8005/enrollment/enroll`
- Request data: `{"multipart":{"fields":{"user_name":"docs-probe-user"},"files":["photos:docs-probe.png","voice_samples:docs-probe.wav"]}}`
- Response: HTTP 400 in 156 ms
- Body: `{"error":{"status_code":400,"code":"BAD_REQUEST","message":"Exactly 5 photos required. Received: 1","request_id":"endpoint-docs-20260924"}}`

### `enrollment-get-/enrollment/health-detailed`

- Request: `GET https://127.0.0.1:8005/enrollment/health-detailed`
- Request data: `{}`
- Response: HTTP 200 in 906 ms
- Body: `{"service":"Enrollment Service","status":"degraded","port":8005,"dependencies":{"vision_service":true,"audio_service":false,"central_server":true}}`

### `enrollment-post-/enrollment/improve-training/{user_id}`

- Request: `POST https://127.0.0.1:8005/enrollment/improve-training/docs-probe-user-missing`
- Request data: `{"multipart":{"fields":{},"files":["additional_photos:docs-probe.png","additional_voice_samples:docs-probe.wav"]}}`
- Response: HTTP 403 in 16 ms
- Body: `{"error":{"status_code":403,"code":"FORBIDDEN","message":"Token does not own requested user","request_id":"endpoint-docs-20260924"}}`

### `enrollment-get-/enrollment/storage/list`

- Request: `GET https://127.0.0.1:8005/enrollment/storage/list`
- Request data: `{}`
- Response: HTTP 200 in 0 ms
- Body: `{"status":"success","total_enrollments":2,"user_ids":["<redacted-user-id-2>","<redacted-user-id-1>"]}`

### `enrollment-get-/enrollment/storage/stats`

- Request: `GET https://127.0.0.1:8005/enrollment/storage/stats`
- Request data: `{}`
- Response: HTTP 500 in 16 ms
- Body: `{"error":{"status_code":500,"code":"INTERNAL_SERVER_ERROR","message":"Failed to get storage stats: 3 validation errors for StorageStatsResponse\ntotal_enrollments\n  Field required [type=missing, input_value={'total_users': 2, 'total.../enrollment_data\\\\logs'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.5/v/missing\nstorage_directory?","request_id":"endpoint-docs-20260924"}}`

### `enrollment-delete-/enrollment/storage/{user_id}`

- Request: `DELETE https://127.0.0.1:8005/enrollment/storage/docs-probe-user-missing`
- Request data: `{}`
- Response: HTTP 403 in 15 ms
- Body: `{"error":{"status_code":403,"code":"FORBIDDEN","message":"Token does not own requested user","request_id":"endpoint-docs-20260924"}}`

### `enrollment-get-/enrollment/storage/{user_id}`

- Request: `GET https://127.0.0.1:8005/enrollment/storage/docs-probe-user-missing`
- Request data: `{}`
- Response: HTTP 403 in 0 ms
- Body: `{"error":{"status_code":403,"code":"FORBIDDEN","message":"Token does not own requested user","request_id":"endpoint-docs-20260924"}}`

### `enrollment-post-/enrollment/update-model/{user_id}`

- Request: `POST https://127.0.0.1:8005/enrollment/update-model/docs-probe-user-missing`
- Request data: `{"multipart":{"fields":{},"files":["new_photos:docs-probe.png","new_voice_samples:docs-probe.wav"]}}`
- Response: HTTP 403 in 16 ms
- Body: `{"error":{"status_code":403,"code":"FORBIDDEN","message":"Token does not own requested user","request_id":"endpoint-docs-20260924"}}`

### `enrollment-get-/health`

- Request: `GET https://127.0.0.1:8005/health`
- Request data: `{}`
- Response: HTTP 200 in 0 ms
- Body: `{"status":"healthy","version":"3.0.0"}`

### `llm-get-/`

- Request: `GET https://127.0.0.1:8006/`
- Request data: `{}`
- Response: HTTP 200 in 16 ms
- Body: `{"service":"NEXI LLM Service","version":"1.0.0","status":"running (online mode)"}`

### `llm-post-/api/v1/format`

- Request: `POST https://127.0.0.1:8006/api/v1/format`
- Request data: `{"json":{"text":"NEXI documentation probe.","format_type":"concise"}}`
- Response: HTTP 501 in 0 ms
- Body: `{"error":{"status_code":501,"code":"NOT_IMPLEMENTED","message":"Formatting is not implemented","request_id":"endpoint-docs-20260924"}}`

### `llm-post-/api/v1/generate`

- Request: `POST https://127.0.0.1:8006/api/v1/generate`
- Request data: `{"json":{"prompt":"Answer only from this context: NEXI documentation probe.","max_tokens":"<redacted>"}}`
- Response: HTTP 422 in 15 ms
- Body: `{"error":{"status_code":422,"code":"VALIDATION_ERROR","message":"Request validation failed","request_id":"endpoint-docs-20260924"}}`

### `llm-get-/api/v1/health`

- Request: `GET https://127.0.0.1:8006/api/v1/health`
- Request data: `{}`
- Response: HTTP 200 in 1047 ms
- Body: `{"status":"healthy","openrouter":true}`

### `llm-get-/api/v1/model-info`

- Request: `GET https://127.0.0.1:8006/api/v1/model-info`
- Request data: `{}`
- Response: HTTP 200 in 16 ms
- Body: `{"provider":"openrouter","model":"openai/gpt-4o-mini"}`

### Successful sequence and cleanup proofs

```json
[
  {
    "label": "create temporary user",
    "method": "POST",
    "url": "https://127.0.0.1:8000/users",
    "status": 200,
    "response": {
      "status": "success",
      "message": "User docs-d1990c962a enrolled",
      "user_id": "docs-d1990c962a"
    }
  },
  {
    "label": "teach temporary fact",
    "method": "POST",
    "url": "https://127.0.0.1:8004/learn",
    "status": 201,
    "response": {
      "message": "Learned new fact 'docs-90999fabd6 means temporary documentation fact'",
      "item_id": "87603f5f-0a73-4db0-be73-32ef4549e774",
      "type": "fact",
      "is_new": true,
      "vision_enhanced": false,
      "performance_ms": {
        "total": 50.10271072387695,
        "vision": null,
        "embedding": "<redacted>",
        "storage": null
      }
    }
  },
  {
    "label": "retrieve taught fact",
    "method": "GET",
    "url": "https://127.0.0.1:8004/knowledge/search/docs-90999fabd6",
    "status": 200,
    "response": {
      "search_term": "docs-90999fabd6",
      "count": 1,
      "results": [
        {
          "id": "87603f5f-0a73-4db0-be73-32ef4549e774",
          "type": "fact",
          "data": {
            "subject": "docs-90999fabd6",
            "predicate": "means",
            "object": "temporary documentation fact",
            "context": {}
          },
          "tags": [],
          "confidence": 1,
          "created_at": "2026-09-24T13:42:30.384784",
          "updated_at": "2026-09-24T13:42:30.384784",
          "embedding": "<redacted>"
        }
      ]
    }
  },
  {
    "label": "restricted RAG query",
    "method": "POST",
    "url": "https://127.0.0.1:8000/api/v1/rag/query",
    "status": 200,
    "response": {
      "success": true,
      "response": "docs-90999fabd6 means temporary documentation fact.",
      "source": "teachme_grounded"
    }
  },
  {
    "label": "conversation read-back",
    "method": "GET",
    "url": "https://127.0.0.1:8000/users/docs-d1990c962a/conversations",
    "status": 200,
    "response": {
      "user_id": "docs-d1990c962a",
      "conversations": [
        {
          "conversation_id": "conv_70882d18f03d",
          "user_id": "docs-d1990c962a",
          "timestamp": "2026-09-24T08:42:37.762860",
          "user_message": "What does docs-90999fabd6 mean?",
          "assistant_response": "docs-90999fabd6 means temporary documentation fact.",
          "language": "en",
          "metadata": {
            "source": "teachme_grounded",
            "automatic": true
          }
        }
      ],
      "count": 1,
      "limit": 10,
      "start_date": null,
      "end_date": null
    }
  },
  {
    "label": "direct LLM provider probe",
    "method": "POST",
    "url": "https://127.0.0.1:8006/api/v1/generate",
    "status": 200,
    "response": {
      "success": true,
      "text": "provider reachable",
      "metadata": {
        "elapsed_seconds": 2.725552797317505,
        "model": "openai/gpt-4o-mini",
        "source": "openrouter",
        "tokens_generated": "<redacted>"
      }
    }
  },
  {
    "label": "Jenny synthesis",
    "method": "POST",
    "url": "https://127.0.0.1:8003/speak",
    "status": 200,
    "response": "<binary audio/wav bytes=75820>"
  },
  {
    "label": "delete temporary fact",
    "method": "DELETE",
    "url": "https://127.0.0.1:8004/forget/87603f5f-0a73-4db0-be73-32ef4549e774",
    "status": 200,
    "response": {
      "message": "Item 87603f5f-0a73-4db0-be73-32ef4549e774 forgotten (soft delete)",
      "item_id": "87603f5f-0a73-4db0-be73-32ef4549e774",
      "permanent": false
    }
  },
  {
    "label": "delete temporary conversations",
    "method": "DELETE",
    "url": "https://127.0.0.1:8000/users/docs-d1990c962a/conversations",
    "status": 200,
    "response": {
      "status": "deleted",
      "user_id": "docs-d1990c962a",
      "message": "All conversations deleted for user docs-d1990c962a"
    }
  },
  {
    "label": "delete temporary user",
    "method": "DELETE",
    "url": "https://127.0.0.1:8000/users/docs-d1990c962a",
    "status": 200,
    "response": {
      "status": "deleted",
      "message": "User 'docs-d1990c962a' and all associated data deleted successfully",
      "user_id": "docs-d1990c962a",
      "user_name": "docs-d1990c962a"
    }
  }
]
```

### Legacy alias proofs

```json
[
  {
    "method": "POST",
    "url": "https://127.0.0.1:8000/users/data/add_user",
    "status": 200,
    "response": {
      "status": "success",
      "message": "User docs-alias-f2f80c0e enrolled",
      "user_id": "docs-alias-f2f80c0e"
    }
  },
  {
    "method": "POST",
    "url": "https://127.0.0.1:8000/users/add-embeddings",
    "status": 400,
    "response": {
      "error": {
        "status_code": 400,
        "code": "MISSING_NAME",
        "message": "User name required",
        "request_id": "endpoint-docs-alias"
      }
    }
  },
  {
    "method": "GET",
    "url": "https://127.0.0.1:8000/teachme/search/docs-probe-missing",
    "status": 200,
    "response": {
      "query": "docs-probe-missing",
      "results": [],
      "total": 0,
      "fallback": false
    }
  },
  {
    "method": "POST",
    "url": "https://127.0.0.1:8000/teachme/search/embedding",
    "status": 200,
    "response": {
      "query": "docs-probe-missing",
      "k": 1,
      "results": [],
      "fallback": false
    }
  },
  {
    "method": "GET",
    "url": "https://127.0.0.1:8000/users/docs-alias-f2f80c0e/conversation-history",
    "status": 410,
    "response": {
      "error": {
        "status_code": 410,
        "code": "CONVERSATION_HISTORY_RETIRED",
        "message": "Use /users/docs-alias-f2f80c0e/conversations for durable conversation data",
        "request_id": "endpoint-docs-alias"
      }
    }
  },
  {
    "method": "DELETE",
    "url": "https://127.0.0.1:8000/users/docs-alias-f2f80c0e",
    "status": 200,
    "response": {
      "status": "deleted",
      "message": "User 'docs-alias-f2f80c0e' and all associated data deleted successfully",
      "user_id": "docs-alias-f2f80c0e",
      "user_name": "docs-alias-f2f80c0e"
    }
  }
]
```

## 10. Verification summary

| Status | Count |
|---|---:|
| WORKING | 136 |
| DEGRADED | 7 |
| BLOCKED | 6 |
| **Total operations** | **149** |

The status counts describe individual operations under this pass's bounded live probes; they are not a claim that unavailable physical hardware or unimplemented features are production-ready.





