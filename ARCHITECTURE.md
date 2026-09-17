# NEXI backend architecture

This is the living architecture reference for the post-Sprint-2 NEXI backend.
Historical audits, remediation plans, and phase evidence are in `docs/archive/`.

## Topology

| Service | Port | Authoritative ASGI application | Primary responsibility |
|---|---:|---|---|
| Central | 8000 | `01_central_server/main.py` → `main:app` | External policy boundary, users/conversations, resource authority, cloud-sync worker |
| Vision | 8001 | `02_vision_service/vision_service/app.py` → `vision_service.app:app` | Camera, face/frame, and object-detection APIs |
| Audio | 8002 | `03_audio_service/main.py` → `main:app` | Wake/direct-voice lifecycle, speaker verification, audio orchestration |
| TTS | 8003 | `04_tts_service/tts_service/app.py` → `tts_service.app:app` | Piper speech synthesis |
| TeachMe | 8004 | `05_teachme_service/teachme_service/app.py` → `teachme_service.app:app` | User-taught fact persistence and semantic retrieval |
| Enrollment | 8005 | `06_enrollment_service/app/main.py` → `app.main:app` | Biometric enrollment and enrollment token issuance |
| LLM | 8006 | `07_llm_service/main.py` → `main:app` | Online OpenRouter generation contract |

External policy-sensitive requests enter through Central. Audio and Enrollment
establish user identity through existing biometric verification/enrollment.
Central calls TeachMe for retrieval and LLM only after policy checks. Internal
service APIs are authenticated contracts, not alternate policy gateways.

## Restricted RAG flow

1. Central validates the external session token and uses its `sub` claim as the
   user identity; caller-supplied ownership fields are not authoritative.
2. `restricted_rag.py` enforces the English-only boundary.
3. Exact placeholder basic commands return deterministic responses without a
   TeachMe or LLM call. The command list remains pending product sign-off.
4. Other queries retrieve user-scoped facts from TeachMe using the shared
   384-dimensional semantic embedding contract.
5. No qualifying fact returns the fixed teach-first response with zero LLM calls.
6. For a match, Central constructs the grounded prompt server-side. The public
   LLM schema does not accept a caller-controlled system prompt.
7. Provider errors remain errors. Output must pass direct containment/similarity
   grounding or Central returns the safe teach-first response and logs a distinct
   grounding failure.
8. Completed ordinary-Q&A outcomes (`teachme_grounded`, `no_match`, and the safe
   `grounding_failure` fallback) are automatically written through Central's
   durable conversation path and enter the cloud-sync outbox. Basic commands,
   rejected non-English input, and provider failures are not conversation records.

TeachMe owns retrieval. There is no second vector database; FAISS is an optional
accelerator over the same store, with linear retrieval supported. TeachMe warms
its embedding model in the background: health reports `embedding_model=loading`,
and semantic routes return 503 until ready.

## Resource authority

Central owns the single camera/microphone lease authority. Priority is immutable:

```text
VIDEO_CALL > ACTIVE_TEACHME > ENROLLMENT > ACTIVE_CONVERSATION > BACKGROUND
```

The authority provides grant/release, queue cancellation, fail-closed liveness,
watchdog force-release, and reassignment. `CALL_ACTIVE` is state attached to a
`VIDEO_CALL` camera lease, not a priority. TeachMe focus broadcast is cooperative
service yielding, not a second hardware lease mechanism.

While `CALL_ACTIVE` owns the camera lease, Vision's normal background health
probe is intentionally denied a second lease and may report `camera=unavailable`.
This means "unavailable to ordinary Vision work while reserved for the call," not
that the call lease leaked. Ending the call releases the lease and restores normal
priority arbitration.

Vision health probes request a provisional background lease and must release it
when reservation acknowledgement fails. A held non-call Vision lease alongside
`camera=unavailable` is therefore a fault, not the intended call-reservation case.

## Trust, transport, and errors

- Edge requests use JWT session tokens issued after Audio verification or
  Enrollment completion. Expiry is configuration-driven.
- Internal calls use the shared service-trust header. On a user's behalf, the
  outer service validates the JWT once and propagates the validated user ID under
  authenticated service trust rather than forwarding the raw JWT.
- Service traffic uses configuration-driven TLS and CA verification.
- Shared middleware propagates correlation IDs, logs latency, and redacts
  credentials, biometrics, transcripts, and sensitive request data.
- Errors use the shared HTTP status, machine code, message, and request-ID
  envelope. Successful response shapes remain service-owned.
- JWT, service trust, Fernet, and OpenRouter configuration support current and
  previous values during controlled rotation windows.

## Data boundaries

- Central users and Audio/Enrollment biometric stores are encrypted at rest.
- Central conversations are durable SQLite records with cloud-sync outbox state.
- TeachMe facts remain local and user-scoped. The sync projection reads only
  conversation fields and is statically prohibited from importing user or
  TeachMe storage.
- The supervised Central sync worker is provider-agnostic and configuration-
  driven. Its local receiver is only a deduplicating verification fixture; a real
  vendor and its guarantees are external dependencies.

## Key decisions

- **ADR-001:** Central `main:app` is authoritative; `api_v2` is retired.
- **ADR-002:** Online-only LLM means no local fallback answer. Local Vision,
  Audio, and TTS inference are distinct capabilities.
- **ADR-005:** Conversation-only cloud sync uses a SQLite outbox and supervised
  asyncio worker; no queue service or vendor SDK is introduced.
- **ADR-006:** OpenAPI is generated from each running FastAPI application.
- **ADR-008:** Video-call scope here is backend state, resource preemption, and a
  frame hook; signaling/media transport belongs to the video team.
- **Deployment isolation:** every service owns one `venv` and requirements file.
  The root environment is test/development-only.

## Verification and limitations

The protected baseline is 62 tests across unit, contract, integration,
resilience, and E2E layers. Liveness means HTTP 200 with an honest healthy or
degraded body. On the validated Windows host, Vision uses the system-default
camera (or `VISION_CAMERA_DEVICE`) with YOLO and DeepFace, and TTS uses the
configured Jenny Piper model. Audio uses the system-default input (or
`AUDIO_INPUT_DEVICE`), but the validated host's microphone driver does not
support the 16 kHz capture format required by the conversation path. Porcupine
account activation/custom keyword provisioning, production CA/secret
infrastructure, and a real cloud vendor remain deployment/operator-specific.
