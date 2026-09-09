# NEXI Sprint 2 Architecture and Remediation Plan

## 1. Executive Engineering Assessment

The audit (PROJECT.md, evidence dated 2026-09-07/08) establishes that the NEXI backend is not a working Sprint 2 system with residual cleanup work. It is a checkout where five of seven services fail to start at all, the two services that do start are degraded or narrower than the documented contract, and the single most consequential Sprint 2 change (restricted, TeachMe-grounded RAG) has no enforcement anywhere in the executable request path. Overall audit score is 2.3/10, classification NOT READY. None of the 13 Sprint 2 requirements (S2-01 through S2-13) is fully verified as implemented; most are PARTIAL or CONFLICTING, meaning Sprint 1 behavior (emotion context, multilingual acceptance, offline command backlog, multi-voice TTS internals) coexists in the same codebase as unfinished Sprint 2 replacements rather than having been cleanly retired.

This document does not repeat the audit. It converts the audit's findings into an ordered, dependency-safe plan for reaching a genuinely production-ready, enterprise-grade backend: one authoritative Central application, one enforced RAG policy boundary, one resource authority, one data-durability guarantee, and a contract other teams (frontend, mobile, video calling) can build against without guessing which of two competing APIs is real.

Three judgments drive every recommendation in this document:

1. **Contracts and durability come before features.** A restricted-RAG pipeline built on top of a Central Server that cannot durably persist a conversation, or that has two independent camera managers that can both grant the same camera, will fail in ways that look like new bugs but are the same root cause resurfacing. Sections 8-14 and 17-18 are prerequisites to section 16, not parallel work.
2. **"Remove offline" and "remove local models" are not the same instruction**, and the audit is explicit that this is unresolved (PROJECT.md section 6 closing note, section 31.D). Whisper, Piper, Porcupine, DeepFace and YOLO are local-inference components that predate and are orthogonal to the offline LLM fallback that Sprint 2 actually targeted. This plan treats the offline-LLM removal as in scope and treats blanket removal of local perception/speech models as **HUMAN DECISION REQUIRED**, not as an audit finding to execute on.
3. **No new infrastructure class is justified by anything in the audit.** The evidence supports one authoritative HTTP contract per service, one transactional persistence choice for concurrently-written stores, and one in-process supervised scheduler for cloud sync. It does not support a message queue, a service mesh, a vector database, or a distributed cache. Every architectural recommendation in this document is traceable to a specific NEXI-XXX finding; none is speculative hardening.

**Current state in one sentence:** two Central applications with incompatible contracts, four other services that cannot start in this environment, one service (LLM) that starts once its missing route is restored but has no answer-restriction logic at all, and no requirement in the 13-item Sprint 2 matrix that can be marked complete without further engineering work.

**Target state in one sentence:** one authoritative Central application enforcing identity, resource leases, and RAG policy at the boundary; seven services with matching, versioned, tested contracts; one durable data model per data category with an explicit local/cloud boundary; and a documented backend contract the video, frontend, and mobile teams can integrate against without inspecting source code.

## 2. Source and Evidence Rules

This document uses the evidence grading required for this phase. A claim is graded exactly as strongly as PROJECT.md supports it, using the following labels throughout:

| Label | Meaning |
|---|---|
| CONFIRMED | Reproduced at runtime in PROJECT.md (an actual exit code, HTTP status, log line, or executed test) |
| LIKELY | Strong static evidence (source citation, AST/reference match) without a reproduced runtime observation |
| PARTIAL | Some part of the requirement/behavior is implemented and evidenced; another part is missing, stale, or contradicted |
| UNVERIFIED | Blocked by environment, hardware, credentials, or a missing dependency; PROJECT.md explicitly could not test it |
| CONFLICTING | PROJECT.md found evidence for and against the same claim (for example, one service enforces a policy another service ignores) |
| BROKEN | Reproduced failure with no working fallback in the current source |

PROJECT.md's own phrasing is preserved wherever it draws a distinction ("possibly unused" is never restated as "unused"; "not runtime verified" is never restated as "working"). Every finding referenced below carries its original NEXI-XXX or S2-XX identifier so it remains traceable to the audit. No claim in this document asserts a fact PROJECT.md did not establish; where this document reaches a design conclusion PROJECT.md did not state outright, that is marked as a **recommendation**, distinct from an audit **finding**.

## 3. Current System Architecture

### 3.1 What actually exists

Seven HTTP service directories, a shared Python library tree, local JSON/SQLite/pickle storage, and multiple overlapping orchestration implementations within the same repository (PROJECT.md section 4). Cloud sync is an imported class that does not exist in the source tree, not a working eighth service. Frontend, mobile, and video-calling implementations are outside this repository's scope; the backend's job is to expose a contract those teams can integrate against, and that contract does not currently exist in a single, consistent form.

### 3.2 Actual request topology (as discovered, not as designed)

```
Frontend / mobile / robot clients
        |
        v
   Central: main:app (documented authority, DOES NOT START)
        or
   Central: api_v2:app (only app that reaches liveness; narrower surface,
                         no TeachMe / camera / resources routes)
        |
        +--> Enrollment (8005) --> Vision (8001), Audio (8002), Central
        |
        +--> Audio (8002) --> LLM (8006), TTS (8003), Central
        |         \--> Groq STT (external)
        |
        +--> TeachMe (8004, cannot start) --> Vision (8001)
        |
        +--> LLM (8006) --> OpenRouter (external)
        |
        \--> Cloud sync (imported, absent implementation; scheduler never runs)

Persistence (local, unencrypted unless noted):
  Central:   users.json, conversations.json  (two independent write paths: main / v2)
  TeachMe:   knowledge_data.json, backups, in-memory/vector index
  Audio:     speaker embedding pickle, SQLite command backlog
  Enrollment: conditionally Fernet-encrypted local metadata, temporary media
```

This is the topology PROJECT.md's own mermaid diagram (section 4) describes, annotated with the runtime outcome for each edge from sections 15-16. Arrows represent intended calls found in source; several do not currently resolve to a live, compatible endpoint (Enrollment to Vision's `/process-face`, Central to TeachMe's `/knowledge/learn`, and both to a not-listening LLM/TeachMe process in the concurrent run, per the cross-service HTTP evidence table in section 15).

### 3.3 Why "network separation" does not currently deliver fault isolation

Seven separate processes suggest independent failure domains, but PROJECT.md documents shared imports, process-global in-memory state (conversation history, camera ownership, model caches), and two independently-implemented resource managers that can grant the same physical camera to two callers (NEXI-005). The service boundary exists in the directory structure; it does not yet exist in the runtime behavior. This plan treats "seven independent services" as an accurate description of the source layout and an inaccurate description of the current failure-isolation properties, and treats closing that gap (sections 14, 18) as a P0/P1 concern rather than a stylistic one.

## 4. Current Service Inventory

| Service | Purpose | Entry point | Port | Inbound callers | Outbound deps | Hardware | Data owned | Models | External APIs | Sprint 2 responsibility | Health |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Central (main) | User/conversation persistence, resource coordination, cloud sync, TeachMe proxy | `main:app` (documented, README.md:74) | 8000 | Frontend, Audio, Enrollment, Vision camera client | TeachMe | Camera, microphone (via managers) | `users.json`, `conversations.json` | none | none directly | Query collection/separation, coordination, sync, orchestration | BROKEN - does not start (NEXI-001) |
| Central (v2) | Narrower user registration + LLM proxy | `api_v2:app` | 8000 | Frontend (if pointed here) | LLM | none exposed | separate user records with embedded turns | none | none directly | Partially overlaps main; no TeachMe/camera/resources | CONFIRMED live, narrower surface than intended orchestration |
| Vision | Face detection/embedding, object detection, camera control | `vision_service.app:app` | 8001 | Central, TeachMe, Enrollment | Central `/camera/*` (legacy) | Camera | none audited persistent store | DeepFace, YOLOv8 | none | Retain recognition; emotion analysis removed from inference | CONFIRMED degraded - liveness only, face model load fails (NEXI-011), health falsely reports healthy (NEXI-010) |
| Audio | Recording, wake/stop word, speaker verification, STT, conversation orchestration, command backlog | `main:app` (`03_audio_service`) | 8002 | Central, Enrollment | LLM, TTS, Central, Groq | Microphone | speaker embedding pickle, SQLite command queue | Porcupine, Resemblyzer, Groq/Whisper | Groq | Wake-word fallback, English-only, single-speaker downstream | BROKEN - does not start (NEXI-006, NEXI-007) |
| TTS | Speech synthesis, voice selection, caching | `tts_service.app:app` | 8003 | Audio, Central, nexctl | none | Speaker output | voice cache, preferences | Piper (weights absent) | none | Jenny-only, English-only | BROKEN - starts then exits, missing model weights (NEXI-014) |
| TeachMe | Fact/object storage, retrieval, Vision enrichment | `teachme_service.app:app` | 8004 | Central | Vision | none | `knowledge_data.json`, backups, vector index | hash-derived pseudo-embeddings (NEXI-018) | none | Sole grounding source for restricted RAG; local-only | BROKEN - does not start, missing `services` package (NEXI-016) |
| Enrollment | Biometric enrollment/re-enrollment/improve-training workflow | `app.main:app` | 8005 | Frontend | Vision, Audio, Central | none directly (delegates) | encrypted-if-enabled local metadata, temp media | none itself | none | Identity onboarding; unaffected by Sprint 2 policy changes except resource priority | CONFIRMED live, workflow contracts broken downstream (NEXI-020, NEXI-021) |
| LLM | Chat generation via one online provider | `main:app` | 8006 | Audio, Central (shared client), nexctl | OpenRouter | none | none (stateless) | none local (offline loader present but unmounted) | OpenRouter | Sole LLM; must not answer outside supplied context | BROKEN - missing route import (NEXI-022); once fixed, has zero RAG/output enforcement (NEXI-023) |
| Cloud sync | Intended 24-hour ordinary-Q/A export | not a service; imported class inside Central `main.py` | n/a | n/a | intended external cloud receiver | none | intended durable outbox (absent) | none | intended, absent | S2-13 in full | BROKEN - class does not exist; blocks Central main startup (NEXI-001) |
| Shared/root | HTTP clients, circuit breakers, config, CLI, orchestration helpers | no server | n/a | all services import from here | varies | none | none | none | none | Cross-cutting: config, retries, breakers, logging | PARTIAL - inconsistent interfaces, one confirmed misrouted URL (NEXI-026) |

## 5. Audit Contradictions / Ambiguities

PROJECT.md is internally self-consistent as an audit (it distinguishes static from runtime evidence throughout), but the *system it describes* contains genuine contradictions between what different parts of the source claim, and a small number of scope ambiguities the audit explicitly declines to resolve on its own authority. These are listed here exactly as such - as decisions required, not defects to silently fix one way.

| ID | Claim A | Claim B | Likely explanation | Stronger evidence | Decision required? | Further verification needed? |
|---|---|---|---|---|---|---|
| AC-01 | README documents `main:app` as the authoritative Central entry point (README.md:74) | Only `api_v2:app` reaches runtime liveness; it exposes a materially different, narrower API with no TeachMe/camera/resources routes (PROJECT.md section 7, section 15) | `main` was the intended long-term architecture; `v2` is a working but incomplete alternative built during instability | Runtime evidence (v2 liveness, confirmed) is stronger than documentation (main's intent) for "what currently works," but main's route surface is closer to what Sprint 2 orchestration actually needs | Yes - this is the single highest-impact decision in this plan (ADR-001) | Confirm with whoever wrote `api_v2.py` whether it was meant as a temporary shim or a deliberate redesign |
| AC-02 | Vision's face inference no longer calls emotion analysis; face response model omits emotion (`face_detector.py:76-132`) | Central `api_v2.py:453,603` retains emotion/mood payload fields; Vision's own health/root/streaming responses and old tests still reference emotion; FER dependency remains in the manifest | Emotion removal (S2-04) was done at the inference layer in Vision but not propagated through the schema, health reporting, or dependent Central code | Source removal in the inference path is concrete; the surviving references are broader and more numerous | Yes - defines the actual scope of the S2-04 cleanup (schema, health, dependency manifest, or all three) | Confirm no downstream consumer (frontend/mobile) still reads a mood field before removing it from the schema |
| AC-03 | Audio's LLM/STT config still exposes English/Urdu (`config.py:146`) and TTS explicitly accepts `ur`/`urdu` (`app.py:483-496`) | S2-11 requires English-only, and the meeting minutes state non-English queries "will not be processed" | Sprint 1 multilingual support was never actively stripped, only left unused by product intent | The requirement (minutes) is unambiguous; the code has not caught up | No decision needed on the requirement itself, but a decision is needed on whether unsupported-language input should be silently coerced to English or explicitly rejected with an error | None beyond confirming the rejection UX with product |
| AC-04 | S2-09 requires removing offline functionality | Local perception (DeepFace, YOLOv8) and local speech (Whisper fallback, Piper TTS, Porcupine wake word) are all local/offline-capable components that remain load-bearing and are not offline *LLM* fallback | PROJECT.md explicitly states this interpretation gap and declines to resolve it (section 6 closing note, section 31.D) | Neither reading is stronger; this is a scope question, not an evidence question | Yes - this determines whether Piper/DeepFace/YOLO/Porcupine are in scope for any removal work at all | Requires an explicit product-owner ruling, per PROJECT.md section 31.D; this plan defaults to "offline LLM fallback only" (see ADR-002 rationale) until overruled |
| AC-05 | TeachMe's configured embedding dimension is 768 (`config.py:67`) | Central's connector sends 128-D vectors to TeachMe (`teachme_connector.py:184-191`) | Central's contract was written against an earlier TeachMe embedding scheme (likely the 128-D FaceNet-style vectors from Sprint 1's face embeddings, reused incorrectly for object/fact embeddings) that never matched TeachMe's own configured model | Both are static source facts; neither is runtime-proven correct, but they cannot both be right simultaneously and one caller-side or provider-side contract must change | Yes - which side is authoritative (embedding model choice belongs to TeachMe or to a shared embedding client) | Requires selecting and versioning one actual semantic embedding model (NEXI-018); this is a data-migration decision, not a one-line fix |
| AC-06 | pytest reports "3 nominal passed" for both Vision-selected tests and LLM tests with no server running | Manual HTTP probes in the same audit show the underlying operations actually failing (Vision camera pause/resume return 500; LLM has no server to call) | Tests catch connection/HTTP errors and return early without asserting on them (NEXI-012) | The manual, assertion-based HTTP probes are far stronger evidence than the pytest pass count | No product decision needed; this is a confirmed test-integrity defect | None - already reproduced; fix is mechanical (assert instead of catch-and-return) |
| AC-07 | `docs/openapi.yaml` advertises `/api/v1/query`, `/api/v1/enroll`, `/api/v1/llm/generate`, `/api/v1/tts/synthesize` | Neither `main`, `v2`, nor any live service exposes these exact paths | Documentation was written against a third, aspirational contract that matches neither the intended (`main`) nor the running (`v2`) application | Live OpenAPI output (confirmed by direct probe) is authoritative over static docs | No - this resolves automatically once ADR-001 is decided and docs are regenerated from the chosen app | Regenerate docs only after Central authority is fixed, or this contradiction reappears immediately |

## 6. Sprint 2 Requirement Status

Status values used here (DONE / PARTIAL / NOT DONE / BROKEN / CONFLICTING / UNVERIFIED / OUT OF SCOPE) map onto PROJECT.md's own per-requirement findings (section 6), which used MISSING/PARTIAL/BROKEN/CONFLICTING. Where PROJECT.md used MISSING, this table uses NOT DONE (no functional difference intended; NOT DONE is simply the label this framework specifies). No requirement is marked DONE anywhere in this table, matching PROJECT.md's explicit statement that no requirement earns "implemented" from file presence alone.

| ID | Requirement | Status | Evidence | Problems | Remaining work | Risk |
|---|---|---|---|---|---|---|
| S2-01 | Restricted TeachMe-grounded RAG, approved basic commands, teach-first fallback | NOT DONE | `generation.py:10-43` has no retrieval, command, or output gate; caller controls `system_prompt`; TeachMe itself cannot start (NEXI-016) | No enforcement point exists anywhere in the executable path; an isolated test with a fake provider shows open-domain input accepted and forwarded unchanged | Recover TeachMe source, fix Central-to-TeachMe contract (AC-05), build the actual gate (section 16), add adversarial tests | HIGH - this is the core Sprint 2 product requirement |
| S2-02 | Single online LLM, remove local fallback architecture | PARTIAL | One OpenRouter client exists and is the only mounted provider (`openrouter_client.py:32`); `shared/quantized_llm.py` retains an executable local loader with no found caller | Local loader is dead code, not proven removed; provider/fine-tuning path itself is UNVERIFIED because the service does not start | Confirm zero callers, then remove; separately fix LLM startup (NEXI-022) | MEDIUM - removal is low-regression once no-caller is confirmed |
| S2-03 | Wake-word failure permits direct voice; approx. 10-second silence or manual end | BROKEN | Fallback module is missing entirely (`wake_word_service.py:35`); the code path that exists falls back to a keyboard-triggered fake file, not direct voice; configured timeout is 120s, not 10s (`config.py:323`) | No working fallback of any kind currently exists | Implement the actual direct-voice fallback and silence timer from scratch; this is new behavior, not a fix | HIGH - hardware/session behavior, needs real microphone testing |
| S2-04 | Remove emotion/mood entirely; retain face recognition | CONFLICTING | Vision inference no longer analyzes emotion; Central v2, Vision health/tests, and the FER dependency manifest all still reference it | Partial removal at one layer, not propagated | Schema, health-response, and dependency-manifest cleanup (see AC-02); do not touch DeepFace/recognition | MEDIUM - regression risk is removing recognition by mistake while chasing emotion references |
| S2-05 | Collect ordinary Q/A with identity/time/durability/sync state | PARTIAL | Central `conversations_persistence.py` and routes exist; TeachMe-side history store import is missing (`app.py:244`) | Schema exists; durable round-trip and sync-state fields are unverified/absent | Add sync-state fields (batch id, synced flag, timestamp) to the schema; verify durable write under concurrency | MEDIUM-HIGH - depends on NEXI-003 persistence fix first |
| S2-06 | Separate TeachMe and ordinary Q/A storage/API/sync | PARTIAL | Separate files/intent exist; v2 stores conversation turns inside user records instead; sync implementation is entirely absent | Two different Central apps disagree on where conversation data even lives | Resolve ADR-001 first; then define one authoritative separation with an explicit export allowlist | HIGH - directly affects the S2-13 cloud boundary guarantee |
| S2-07 | TeachMe gets maximum resources; other work yields via lazy shifting | PARTIAL | Logical revoke exists in `hardware_resource_manager.py`; Vision's own `resource_pool.py` independently retains camera regardless | Two independent resource authorities; a logical grant does not force physical release | Consolidate to one resource authority (section 18) before implementing lazy-shift semantics | HIGH - concurrency and hardware-ownership risk |
| S2-08 | Remove redundant/obsolete code without regressions | PARTIAL | Multiple active/alternate apps, clients, prompt builders, and loaders documented across sections 24-26 of the audit; no deletion has been performed | Cannot be completed until contracts are fixed and consumers are known (this is explicitly sequenced last, not first) | Execute Section 25/26/33 of this plan after functional paths are verified | MEDIUM - premature cleanup here is the highest-regret mistake available in this plan |
| S2-09 | Online-only; remove offline functionality | CONFLICTING | Audio's command backlog is actively wired at startup (`main.py:97-132`); the LLM app itself has no discovered local-loader call currently | Scope ambiguity per AC-04; the offline-LLM piece is closer to done than the offline-Audio-backlog piece | Requires the AC-04 scope decision before further work is meaningful | MEDIUM - risk of removing needed local models under an overly broad reading |
| S2-10 | Jenny-only TTS | PARTIAL | Public voice registry contains only Jenny and is validated by `resolve_voice` (`app.py:113-127,217-232`); internal worker/cache/status code still implements Ryan and Shahid | Public surface is correct in source; internals are not cleaned up, and no runtime synthesis test could run (missing model weights, NEXI-014) | Remove internal multi-voice code paths after confirming no other caller depends on them; separately provision Jenny's actual model weights | LOW-MEDIUM once weights are provisioned; internal cleanup is low-regression |
| S2-11 | English-only input/output | CONFLICTING | Audio config still declares en/ur; TTS explicitly accepts Urdu; LLM has no language constraint at all | Every layer independently still accepts non-English | Enforce English at one boundary consistently (recommend: Central's RAG policy layer, section 16) rather than patching three services separately | MEDIUM - root cause is policy-not-centralized, matching Principle 4 |
| S2-12 | Video-call priority, camera release/reacquire, integration hooks | PARTIAL | Generic camera/resource routes exist; no call lifecycle, no working pause/resume (`/camera/pause` and `/camera/resume` both return 500, NEXI-009) | No actual call-state contract exists anywhere; even the generic camera control that would underlie it is broken | Fix NEXI-009 first, then build the actual call-lifecycle contract (section 20) with the video team | HIGH - blocks another team's integration entirely until resolved |
| S2-13 | Ordinary Q/A cloud sync every 24 hours; TeachMe stays local | BROKEN | The sync class Central imports does not exist; Central `main.py` cannot even start because of this import | Nothing runs; retry, idempotency, and the local/cloud data boundary are all UNVERIFIED because there is no code to verify | Build the sync worker from the ground up as a supervised, in-process scheduled task (section 19) | HIGH - both a Central-startup blocker (shared root cause with S2-01/05/06) and a privacy-boundary requirement |

No requirement above is closer to DONE than PARTIAL, and three (S2-03, S2-13, and functionally S2-01 given TeachMe's inability to start) are BROKEN or NOT DONE outright. This table is the ground truth this plan's phased remediation (section 32) is built to close out.

## 7. Architectural Root Causes

Thirty-three individually numbered issues in PROJECT.md's register collapse into a much smaller number of underlying architectural problems. Fixing symptoms one NEXI-ID at a time would reintroduce the same failure class under a new ID; this section names the root cause once and section 29 maps every related issue to it.

| Root Cause | Description | Representative issues |
|---|---|---|
| RC-01: No single orchestration authority | Two Central applications with incompatible route sets, storage models, and error envelopes both exist as live candidates | NEXI-001, NEXI-002, NEXI-030, AC-01 |
| RC-02: No enforced policy boundary between the LLM and the outside world | Restricted-RAG policy (S2-01), language policy (S2-11), and voice policy (S2-10) are each expected to be enforced by convention/prompt text rather than by code the caller cannot override | NEXI-023, NEXI-024, AC-03, AC-04 partially |
| RC-03: No transactional persistence layer | Every JSON-backed store (Central users/conversations, TeachMe knowledge) can acknowledge a write that did not durably happen, and concurrent writers are not locked at the correct scope | NEXI-003, NEXI-013 (as a data-integrity variant), NEXI-020 |
| RC-04: No single hardware-resource authority | Camera and (to a lesser extent) microphone ownership is implemented independently in at least three places (Central's two managers, Vision's local pool), so priority/lease semantics are metadata-only | NEXI-005, NEXI-009, S2-07, S2-12 |
| RC-05: Missing or unintegrated source modules | Several services import packages, classes, or route modules that do not exist in the tree at all; these are not bugs in working code, they are gaps in the checkout | NEXI-001, NEXI-006, NEXI-016, NEXI-022 |
| RC-06: Contract drift between producer and consumer | Independently-evolved client/server pairs (Audio-to-STT media type, Central-to-TeachMe payload shape and dimensionality, Enrollment-to-Vision route paths, LLM client-to-server response shape) have drifted without a shared schema or contract test to catch it | NEXI-008, NEXI-017, NEXI-018, NEXI-021, NEXI-024, NEXI-026, AC-05 |
| RC-07: No enforced access control on sensitive routes | Every public service lacks authentication/authorization on identity, biometric, knowledge, storage-deletion, and resource-control endpoints; auth helpers exist in places (TeachMe) but are not wired to the routes they should protect | NEXI-004, NEXI-029 |
| RC-08: Diagnostics that hide failure instead of reporting it | Health checks report liveness as capability; tests catch and swallow the exact failures they should assert on; error envelopes vary per service, so failure is not machine-distinguishable from success in several call paths | NEXI-010, NEXI-012, NEXI-019, NEXI-024's fallback-as-success behavior, NEXI-028 |
| RC-09: Sprint 1 policy not fully retired at every layer it touched | Emotion, multilingual support, multi-voice TTS, and offline local-LLM code were each partially removed at one layer (usually the primary inference/config path) but left in place in schemas, health responses, internal caches, or dependency manifests | NEXI-015, AC-02, AC-03, S2-04, S2-09, S2-10, S2-11 |
| RC-10: Deployment artifacts describe an application that does not match the source | Dockerfiles reference missing entrypoints and wrong working directories; CI does not build the base image it depends on; documentation and OpenAPI describe routes no live app exposes | NEXI-025, NEXI-031, AC-07 |

Sections 8 through 27 diagnose each service and cross-cutting concern against these ten root causes. Section 32's phased plan is explicitly ordered so that RC-05 (missing source) and RC-01 (orchestration authority) are resolved before RC-02 (policy enforcement) is attempted, and RC-03/RC-04 (data and hardware authority) are resolved before RC-06 (contract alignment) is finalized - fixing a contract between two sides that still cannot durably persist or safely share hardware would only relocate the defect.

## 8. Central Server Analysis

#### Current responsibility
User/conversation persistence, request routing to all other services, camera/microphone resource allocation, RAG context aggregation, cloud sync scheduling, and (in `main`) TeachMe proxying. This is already more responsibility than one service should hold, and it is currently split unevenly and incompatibly across two competing applications.

#### What is good and should be preserved
The intent to centralize orchestration is correct for a system this size (Principle 5 - do not split for aesthetics). `teachme_connector.py` implements real retry/backoff/circuit-breaker behavior (15s timeout) that is worth keeping once its payload contract is fixed. `v2`'s narrower surface, while incomplete, demonstrates the kind of focused API this service should converge toward once TeachMe/camera/resources are added back deliberately rather than inherited from `main` wholesale.

#### Confirmed problems
NEXI-001 (BLOCKER, main cannot start - missing `services.cloud_sync_service`), NEXI-002 (`main` and `v2` expose incompatible surfaces), NEXI-003 (persistence errors swallowed; conversation writer uses a fixed temp filename without full-scope locking), NEXI-004 (CRITICAL - no authentication/ownership on any user/conversation/resource route), NEXI-005 (two independent camera-allocation implementations can both grant the same camera; queued-release cancellation fails).

#### Root architectural problems
RC-01 (no single authority), RC-03 (non-durable persistence), RC-04 (competing resource managers), RC-07 (no access control).

#### Sprint 2 gaps
S2-05 PARTIAL (schema exists, no sync-state/idempotency fields), S2-06 PARTIAL (main and v2 disagree on where conversation data lives), S2-07 PARTIAL (logical leases only), S2-04 CONFLICTING (v2 retains emotion payload fields), S2-11 CONFLICTING (unrestricted language field), S2-12 PARTIAL (generic leases, no call lifecycle), S2-13 BROKEN (missing sync import blocks startup entirely).

#### Redundancy / duplication
`camera_manager.py` and `hardware_resource_manager.py` both mounted by `main` with overlapping ownership. `routes/llm_routes.py` factory has no call site anywhere in the repository. `main` mounts a sibling `teachme_routes.py` with different contracts than the one actually wired.

#### Security concerns
NEXI-004 (CRITICAL): no auth/ownership dependency on `/users/*`, `/users/{id}/conversations`, `/conversations/{id}`, `/resources/*`. Wildcard credentialed CORS (`main.py:40-43`). `v2` has no OpenAPI security scheme either. User-list endpoint reportedly returns embeddings - biometric data exposed without any access control.

#### Reliability concerns
Main does not start at all. `v2` starts but a formatter error occurs during logging (NEXI-028) and Audio being unavailable is treated as a warning, not a hard dependency failure signal.

#### Scalability concerns
Blocking JSON persistence inside async routes; process-local locks/caches do not coordinate across workers; full-document read-modify-write risks lost updates under any concurrent write.

#### Maintainability concerns
Two parallel applications mean every future change must be made twice or a decision must finally be made. Hard-coded URLs and ports exist alongside a separate environment-aware shared config that is not consistently used (`service_config.py:44-50`, `main.py:91`).

#### Integration/API concerns
Main mixes JSON, query parameters, and multipart across routes; `v2`'s LLM generation uses form inputs. Error envelopes vary between `HTTPException` detail, a custom `APIResponse`, and bare success booleans. No idempotency key on any route. Frontend/mobile cannot safely target "Central" as a single concept until ADR-001 is resolved.

#### What should stay
The orchestration-hub concept; `teachme_connector.py`'s retry/circuit-breaker pattern (payload fixed); the JSON user/conversation schema as a starting point for migration, not as the final store (see section 17).

#### What should change
Consolidate to one Central application (ADR-001). Add an explicit RAG-policy boundary component that owns constructing the LLM system prompt server-side (section 16) rather than trusting caller-supplied prompts. Consolidate camera/microphone ownership into one authority (section 18). Add sync-state fields to the conversation schema and implement the actual sync worker (section 19).

#### What should be removed
Whichever of `main`/`api_v2` is not selected as authoritative, after its unique required routes are migrated into the winner (do not delete either file until ADR-001 is executed and migration is verified). The unreferenced `routes/llm_routes.py` factory, after confirming zero external callers. `persistence_async.py`, after confirming it is genuinely unused (currently: no discovered consumer, but not yet proven safe).

#### What must NOT be removed yet
Both `camera_manager.py` and `hardware_resource_manager.py` until the consolidated resource authority (section 18) is built and verified against both existing call sites. The currently-mounted `teachme_routes.py` variant actually in use, versus the unmounted sibling, until callers of the unmounted one are confirmed absent.

#### Dependencies before modification
ADR-001 decision; a recovered/implemented cloud sync class; a verified TeachMe contract (Section 11) before Central's TeachMe proxy can be trusted; a single resource authority (Section 18) before resource routes can be considered fixed rather than relocated.

#### Regression risks
HIGH. Any client currently pointed at either `main`'s intended routes or `v2`'s live routes will break if the non-chosen surface is removed without a compatibility/migration window. Data migration risk on `users.json`/`conversations.json` if the persistence layer changes (Section 17).

#### Required tests after modification
Startup/import test that fails loudly if either the sync class or any mounted route module is missing (closes the NEXI-012 test-integrity gap for this service specifically). Contract tests for every route the chosen authoritative app exposes. Concurrent-write test proving no lost update under simultaneous conversation appends. Resource-manager test proving a single camera cannot be granted to two callers simultaneously.

#### Target service responsibility
Identity and conversation persistence; resource-lease authority; RAG-policy boundary (prompt construction and output validation, working in concert with LLM per section 16); cloud-sync scheduling. Explicitly not: face/voice inference, TTS synthesis, or TeachMe's own retrieval logic - those remain owned by their respective services and are called, not reimplemented, by Central.

#### Service priority
P0

## 9. Audio Service Analysis

#### Current responsibility
Microphone recording, wake/stop-word detection, Resemblyzer speaker verification, Groq/Whisper STT, conversation-turn orchestration, and a SQLite-backed command backlog.

#### What is good and should be preserved
The layered design (recording, VAD, STT, verification, orchestration as distinct modules) is sound in principle. Lazy singleton speaker-encoder handling in the main advanced routes (as opposed to the legacy `api.py`, which constructs a new encoder per request) is the correct pattern and should be the only pattern retained.

#### Confirmed problems
NEXI-006 (BLOCKER - unconditional import of a missing `keyboard_wake_word` module; the fallback that does exist is a keyboard-triggered fake file, not a direct-voice fallback). NEXI-007 (environment - inherited non-boolean DEBUG value rejected by shared settings, a separate blocker from NEXI-006). NEXI-008 (the conversation orchestrator posts raw octet-stream bytes to a transcribe endpoint that requires multipart `UploadFile` - the normal turn pipeline cannot function even once the service starts).

#### Root architectural problems
RC-05 (missing source module), RC-06 (producer/consumer media-type drift between the orchestrator and its own transcribe endpoint), RC-09 (offline command backlog still actively wired despite S2-09's online-only intent).

#### Sprint 2 gaps
S2-03 BROKEN (no working fallback of any kind). S2-09 CONFLICTING (backlog wired at `main.py:97-132`; this is a real behavior, not documentation drift). S2-11 CONFLICTING (`config.py:146` still declares en/ur, and STT auto-detection is active). S2-10 PARTIAL at the caller boundary (arbitrary `speaker_id` accepted rather than a fixed contract).

#### Redundancy / duplication
`api.py` is a separate, unmounted legacy embedding API using relative imports without a package initializer - not reachable via `main`, but not proven to have zero external callers either. Two conversation-state implementations exist (`managers/conversation_state_manager.py` vs `services/conversation_state.py`); only the latter is imported by `main`.

#### Security concerns
No global authentication/per-user authorization anywhere in the router set (shared RC-07/NEXI-004). Wildcard credentialed CORS (`main.py:302`). Server-side `audio_file_path` accepted directly in a request schema (`orchestration_routes.py:24-29`) - a path-containment concern, not just an auth gap (NEXI-032). Speaker store is loaded via `pickle` (NEXI-033) - a deserialization risk if the file is ever attacker-writable.

#### Reliability concerns
Two independent, separately-reproduced startup blockers (environment and code). No isolated automated regression suite; the only test file is an interactive, hardware-writing diagnostic outside pytest convention.

#### Scalability concerns
Synchronous recording/STT/file operations inside async routes; conversation state and hardware access are process-global, meaning a single process instance is an implicit scalability ceiling regardless of worker count.

#### Maintainability concerns
Two parallel conversation-state and two parallel embedding-extraction implementations with no clear migration status between them.

#### Integration/API concerns
NEXI-008's media-type mismatch is not a hypothetical integration issue - it currently prevents the core speech-to-response pipeline from functioning even in a fully-started environment. No shared error envelope with other services.

#### What should stay
The mounted, lazy-singleton speaker-verification path. The layered module structure. The SQLite command backlog, pending the AC-04 scope decision - it is currently load-bearing (actively wired), not legacy.

#### What should change
Implement the actual S2-03 direct-voice fallback and silence-timeout behavior (this is new functionality, not a repair of existing code - none currently exists). Fix the STT media-type contract (NEXI-008) so the orchestrator and endpoint agree on multipart vs. raw bytes. Enforce English-only at the boundary this service reports to, once the centralized language policy (section 16) is in place, rather than patching `config.py` in isolation.

#### What should be removed
`api.py` and its associated `embedding_extractor.py`, after confirming no external caller depends on the legacy embedding path. The unused `managers/conversation_state_manager.py`, after confirming `services/conversation_state.py` is the sole active implementation.

#### What must NOT be removed yet
The SQLite command backlog and its queue modules - `main.py` actively starts and uses them; removing them requires an explicit feature migration decision (AC-04), not a cleanup pass.

#### Dependencies before modification
Recovered or implemented `keyboard_wake_word`-replacement module (or, better, the actual direct-voice fallback this plan recommends building instead, see Section 32 Phase 3). Fixed environment DEBUG-value handling before any of this is testable at all.

#### Regression risks
HIGH - hardware and session-timing behavior cannot be fully verified without physical microphone testing; any change to wake-word/fallback logic needs a real-device acceptance pass, not just unit tests.

#### Required tests after modification
Startup test with a DEBUG value matching production configuration. Wake-word-failure integration test proving direct voice is actually accepted and a session both auto-terminates after silence and terminates on manual stop. Contract test for the transcribe endpoint matching the orchestrator's actual request shape.

#### Target service responsibility
Recording, wake-word/fallback session lifecycle, speaker verification, and STT. Language and voice policy enforcement is reported by this service but centrally defined (section 16), not independently configured here.

#### Service priority
P0

## 10. Vision Service Analysis

#### Current responsibility
Face detection and embedding (DeepFace), object detection (YOLOv8), MJPEG streaming, and camera control.

#### What is good and should be preserved
Face inference itself no longer calls emotion analysis (`face_detector.py:76-132`) - the actual removal Sprint 2 asked for has happened at the inference layer. DeepFace and YOLOv8 are both confirmed load-bearing for retained capabilities (recognition, object teaching) and must not be removed under any reading of the offline-functionality requirement (AC-04).

#### Confirmed problems
NEXI-005 (camera client eventually grants access even after an explicit Central denial, and caches availability without a TTL refresh - a fail-open behavior). NEXI-009 (`/camera/pause` and `/camera/resume` both return HTTP 500 because a required response field is omitted, and the state change happens before the error response - meaning the camera state can already have changed by the time the caller sees a failure). NEXI-010 (`/health` reports healthy while assuming camera availability rather than checking it). NEXI-011 (DeepFace import fails against the installed TensorFlow version because `tf-keras` is not installed). NEXI-012 (selected pytest tests report "3 nominal passed" while the camera-control test itself printed a failure and returned False). NEXI-013 (a failed face-embedding extraction returns a 128-zero vector indistinguishable from valid face data, with no validity flag).

#### Root architectural problems
RC-04 (independent resource ownership; a paused stream still retains the open camera handle), RC-08 (health/readiness conflated with capability; false-positive tests).

#### Sprint 2 gaps
S2-04 PARTIAL locally (inference layer clean), CONFLICTING repository-wide (health/tests/schema retain emotion fields). S2-07 PARTIAL (this service's local resource pool does not cooperate with Central's leases). S2-12 BROKEN (the camera-control contract that any call-priority behavior would depend on does not work).

#### Redundancy / duplication
Unused queue modules exist but are not initialized by the current app lifespan; old tests and `queue_processor.py` reference unprefixed detection paths that no longer match live routes.

#### Security concerns
No OpenAPI security scheme, wildcard credentialed CORS, no authorization on camera control or biometric output. Upload handling reads full request bodies into memory before validation, and exceptions can expose implementation details.

#### Reliability concerns
Health reports healthy despite failed model load (NEXI-010) - this is the single most dangerous reliability defect in this service, because any orchestrator trusting Vision's health check will route real biometric traffic to a service that cannot actually recognize faces.

#### Scalability concerns
Synchronous model loading with retry sleeps inside an async lifespan; YOLO is eagerly triggered at startup despite being nominally lazy; models stay resident in memory with no TeachMe-priority unload hook.

#### Maintainability concerns
Emotion references scattered across health, root, streaming, and test code make it unclear from any single file whether emotion is actually gone.

#### Integration/API concerns
Exceptions sometimes surface as HTTP 200 with an internal `status=error` field (`routes/detection.py:105-119`) rather than an actual error status code - this breaks any client that checks HTTP status rather than parsing the body.

#### What should stay
DeepFace, YOLOv8, and the core face/object detection routes. The fact that emotion inference is already removed at the source.

#### What should change
Fix `/camera/pause` and `/camera/resume` to return the required response schema and to make the state change atomic with the response (NEXI-009). Fix `/health` to report actual model-load status, not just process liveness (NEXI-010). Replace the zero-vector failure path with a typed failure response that a caller cannot mistake for valid biometric data (NEXI-013). Remove emotion fields from health/schema/tests once AC-02's scope is confirmed.

#### What should be removed
The unused queue modules, after confirming no external consumer and after their stale unprefixed routes are also removed from any test/docs referencing them. Emotion-only test assertions, replaced with equivalent face-only assertions rather than deleted outright.

#### What must NOT be removed yet
DeepFace, YOLOv8, and their TensorFlow/Torch dependency chains under any circumstances - explicitly called out as DO NOT REMOVE in the audit and re-affirmed here regardless of how the offline-functionality question (AC-04) is eventually resolved.

#### Dependencies before modification
Resolution of the single resource authority (section 18) before Vision's local pool can be safely simplified to a cooperating client rather than an independent owner. A working DeepFace/tf-keras-compatible environment before health can honestly report model status.

#### Regression risks
MEDIUM-HIGH on the camera contract fix (any caller currently working around the 500 responses would need to be updated); LOW on removing genuinely unreferenced queue modules.

#### Required tests after modification
Health test asserting healthy=false when the face model fails to load. Camera pause/resume contract test asserting both the response schema and that no state change occurs without a successful acknowledgement. Embedding-extraction test asserting a typed failure is returned (not a zero vector) when no face is detected.

#### Target service responsibility
Face and object perception, camera hardware access as a cooperating client of the single resource authority. No emotion inference, no independent resource-ownership decisions.

#### Service priority
P0

## 11. TTS Service Analysis

#### Current responsibility
Local Piper/ONNX speech synthesis, voice selection, a worker/queue pool, and diagnostics.

#### What is good and should be preserved
The public `VOICE_DEFINITIONS` registry already contains only Jenny, and `resolve_voice` validates against that registry (`app.py:113-127,217-232`) - the public-facing part of S2-10 is genuinely implemented, which is a stronger state than most other Sprint 2 requirements in this codebase.

#### Confirmed problems
NEXI-014 (ENVIRONMENT BLOCKER - Piper model metadata exists but the actual `.onnx` weight files are absent; the service starts and then exits). Active worker `EngineManager` and the unified model cache still implement Urdu and Ryan/Shahid internally despite the public registry being Jenny-only (`parallel_worker_pool.py:119`, `engine_manager.py:104-125,154,211`) - the audit is explicit that this does not prove an exploitable bypass (the `/speakers/switch` endpoint validates through `resolve_voice`), but it does mean the internals are not actually clean.

#### Root architectural problems
RC-09 (Sprint 1 multi-voice/multilingual internals not retired even though the public contract was updated).

#### Sprint 2 gaps
S2-10 PARTIAL (public contract correct, internals not, runtime weights missing). S2-11 CONFLICTING (`app.py:483-496` explicitly accepts `en`/`english`/`ur`/`urdu`). S2-09 CONFLICTING under a literal online-only reading, but the audit is explicit this needs the AC-04 scope decision rather than a default assumption that local TTS itself is in scope for removal.

#### Redundancy / duplication
Three independent worker caches, each eagerly loading Jenny separately at startup - this is a resource-efficiency concern more than a correctness one, but it does mean Jenny's model is resident in memory three times over.

#### Security concerns
Wildcard credentialed CORS, no global auth. Diagnostics/error endpoints can disclose internal paths.

#### Reliability concerns
Cannot currently synthesize any audio at all in this environment - not a logic defect, an artifact-provisioning gap (Jenny's actual weight file needs to be sourced and checksummed).

#### Scalability concerns
Per-worker model duplication increases resident RAM proportionally to worker count with no shared-cache option evaluated.

#### Maintainability concerns
The gap between "public contract says Jenny-only" and "internal code still branches on Urdu/Ryan/Shahid" is exactly the kind of drift that reappears if a future change touches the internals without checking the public contract stayed intact, or vice versa.

#### Integration/API concerns
`/speak` returns raw WAV bytes, not a JSON-wrapped audio reference, which is inconsistent with most other services' JSON-first contracts - worth deciding deliberately rather than leaving as an accident of TTS being built differently.

#### What should stay
The public Jenny-only registry and `resolve_voice` validation exactly as implemented.

#### What should change
Remove Urdu/Ryan/Shahid handling from `EngineManager`, the unified cache, and speaker-status configuration once confirmed unreferenced by any live caller other than the internals being removed. Reject (not silently ignore) `language=ur`/`urdu` in `SpeechRequest` validation rather than accepting it.

#### What should be removed
Ryan/Shahid voice configs and old preferences, and Lessac/LibriTTS metadata with no current public registry entry - both classified LIKELY SAFE - VERIFY FIRST in the audit, and re-affirmed here pending confirmation that removing the internal mapping does not also remove code the (correct) public Jenny path depends on.

#### What must NOT be removed yet
The engine/language/cache manager modules themselves (imported by live workers) until the internal Urdu/multi-voice branches are excised from within them, not the modules wholesale. Jenny's metadata, which is the required partner of the still-missing weight file.

#### Dependencies before modification
Provisioning of the actual Jenny Piper model weights before any runtime synthesis behavior (including the language-rejection fix) can be verified rather than just reviewed statically.

#### Regression risks
LOW-MEDIUM. This is one of the lower-risk services to clean up because the public contract is already correct; the risk is entirely in the internal refactor accidentally breaking Jenny synthesis itself.

#### Required tests after modification
Model-load smoke test (Jenny weights present and loadable) as an explicit startup gate. Contract test asserting `language=ur` is rejected with a clear error, not silently coerced or accepted. Contract test asserting `/speakers/switch` to any non-Jenny voice is rejected end-to-end, not just at the resolver layer.

#### Target service responsibility
English-only, Jenny-only speech synthesis. No internal multi-voice or multilingual code paths at all, public or private.

#### Service priority
P1 (blocked on artifact provisioning, not primarily a logic fix)

## 12. TeachMe Service Analysis

#### Current responsibility
Storing and retrieving taught facts and objects, with Vision enrichment for object embeddings and similarity search.

#### What is good and should be preserved
The architectural intent - a local-only, per-user knowledge store that is the sole grounding source for restricted RAG - is exactly correct for S2-01 and S2-06. `safe_file_lock.py` is actively used by the synchronous persistence path and should be preserved and extended to the async path, which currently does not use it.

#### Confirmed problems
NEXI-016 (BLOCKER - the `teachme_service/services` package referenced by `knowledge_base.py:23-25` and `app.py:244-245` does not exist in the repository; the service cannot start). NEXI-017 (Central sends `POST /knowledge/learn` with a flat name/category/128-D-embedding payload; TeachMe's live source expects typed object/fact data at `POST /learn`; even the search endpoint expects query parameters, not the vector JSON Central sends). NEXI-018 (the object-feature-vector generator uses deterministic MD5/text-derived vectors, not real semantic embeddings, and TeachMe's configured dimension is 768 while Central sends 128 - see AC-05).

#### Root architectural problems
RC-05 (missing source package - this is the single most severe individual finding for S2-01, because it means the sole grounding source for restricted RAG cannot run at all), RC-06 (contract drift with both Central and Vision), RC-03 (async save path does not use the same lock as the sync writer, extending NEXI-003).

#### Sprint 2 gaps
S2-01 BROKEN end-to-end because TeachMe itself is unavailable - this is the most direct blocker of the entire Sprint 2 restricted-RAG requirement. S2-05/S2-06 PARTIAL (schemas exist for the new history store but the store itself is one of the missing modules). S2-07 has no service-wide TeachMe-priority integration at all. S2-13 BROKEN transitively (the missing history store this service should own is a dependency of the sync boundary).

#### Redundancy / duplication
None specific to this service beyond the shared circuit-breaker/rate-limiter inconsistencies documented at the shared-library level (section 15).

#### Security concerns
Authentication helpers exist (`authentication.py`) and `AUTH_ENABLED` defaults true, but the learn/read/delete routes do not apply `require_api_key`/`require_jwt` at all - the flag being true does not protect anything if no route uses it. Registration is publicly callable. The optional JWT-support path silently bypasses checks when the JWT library is unavailable (`authentication.py:279`) - this is a fail-open security defect, not just a missing feature. NEXI-019: the rate-limit middleware raises an `HTTPException` object directly rather than returning a `Response`, which is invalid ASGI middleware behavior and produces a 500 instead of the intended 429.

#### Reliability concerns
Cannot start at all in the current checkout. Async writer and sync writer do not share a lock, meaning any code path that exercises both concurrently can race even after the missing package is restored.

#### Scalability concerns
Fallback search is linear (acceptable at small scale per the original Sprint 1 report's own assessment, but worth stating explicitly rather than assuming FAISS availability); full JSON snapshots and index remain process-local with no workload preemption or model unloading tied to TeachMe's own resource-priority requirement (S2-07).

#### Maintainability concerns
Two different embedding dimensionalities configured across two services (768 here, 128 sent by Central) with no version tag on either side - any future embedding-model change has no mechanism to detect a mismatch other than the kind of manual audit that produced NEXI-018.

#### Integration/API concerns
The Vision-enrichment call target itself is stale (`config.py:24` uses `/analyze/complete`, missing Vision's actual `/api/v1` prefix) - a third contract mismatch alongside the Central-facing ones.

#### What should stay
The local-only, per-user storage model. `safe_file_lock.py`. The retry/circuit-breaker connector pattern used elsewhere in the codebase, applied consistently here once contracts are fixed.

#### What should change
Recover or reimplement the missing `services` package (`embedding_client`, `dedup_checker`, `confidence_gate`, `query_history_store`, `query_rotation_policy`) - this is new/recovered implementation work, not a configuration fix. Align the Central-to-TeachMe learn/search contract on one payload shape and one embedding dimension (AC-05, ADR to be written once the embedding-model choice is made). Wire the existing authentication helpers to the actual data routes. Fix the Vision call path to include the correct prefix.

#### What should be removed
Nothing in this service is currently classified as a safe removal candidate independent of first recovering the missing package - the hash-embedding path is "actively invoked" and must not be removed without a working replacement in hand simultaneously (not sequentially), per the audit's own caution.

#### What must NOT be removed yet
The authentication helpers (wire them, do not remove them for being currently ineffective). The hash-based embedding path, until a real semantic-embedding replacement is deployed and migrated to.

#### Dependencies before modification
This service cannot be meaningfully modified until its missing package is recovered or rebuilt - every other finding in this service (contract alignment, auth wiring, embedding quality) is downstream of the service being runnable at all.

#### Regression risks
HIGH on the embedding-dimension migration specifically (any existing taught facts/objects would need re-embedding, not just a schema change) - treat this as a data migration, not a code change.

#### Required tests after modification
Startup/import test. Contract test between Central and TeachMe covering both the learn and search payload shapes at the agreed dimension. Authentication test asserting unauthenticated requests to learn/read/delete are rejected. Concurrency test proving the async and sync writers do not race under simultaneous calls.

#### Target service responsibility
Sole authoritative store and retrieval engine for taught knowledge; local-only; the exclusive grounding source the restricted-RAG policy layer (section 16) queries before ever calling the LLM.

#### Service priority
P0

## 13. Enrollment Service Analysis

#### Current responsibility
Orchestrating five-photo/five-voice enrollment, improve-training, and re-enrollment workflows; local (conditionally encrypted) storage of enrollment metadata; registering identity with Central.

#### What is good and should be preserved
This is a genuinely distinct workflow (multi-step biometric collection with its own state machine) with its own storage and encryption concerns - the audit does not find evidence that it unnecessarily duplicates Central's orchestration, and this plan does not recommend merging it (see ADR-007). Fernet encryption is actually implemented for local metadata, conditional on `ENABLE_ENCRYPTION`.

#### Confirmed problems
NEXI-020 (a normal local enrollment record omits the face/voice embeddings that startup recovery logic expects to find - the recovery code and the write code disagree with each other within the same service; registration with Central happens before the local durable save, and failure/deletion has no cross-service rollback, meaning a deletion can report all-system success after only the local step failed). NEXI-021 (the Vision client posts to `/process-face`, a path absent from Vision's actual live OpenAPI; Central's `add_user` response omits the `user_id` Enrollment needs; the Audio-health adapter treats a typed result object as a plain dict and throws).

#### Root architectural problems
RC-03 (non-atomic final-file write, extending NEXI-003), RC-06 (three separate downstream contract mismatches - Vision, Central, and Audio's health adapter - all within one service's outbound calls).

#### Sprint 2 gaps
Enrollment itself is largely orthogonal to the Sprint 2 policy changes (RAG, language, voice) - its gaps are S2-07/S2-12 (no global priority/call-preemption awareness) and it is not the owner of the ordinary-Q/A dataset (S2-05/S2-06 do not apply here).

#### Redundancy / duplication
`enrollment_service_enhanced.py` exists as an alternate, more complete-looking implementation that the current router does not import at all (`routes/enrollment.py:12,22` mounts the standard version). `app/storage/enrollment_storage.py` is a second storage class alongside the two the `StorageAdapter` already constructs.

#### Security concerns
Encryption is conditional and does not cover Central's biometric JSON or transient media, only Enrollment's own local metadata. Key-file chmod errors are silently ignored and a fallback-key search occurs (`utils/encryption.py:24-47,142-164`) - Windows ACL behavior, rotation, and recovery are all UNVERIFIED. No authentication on storage retrieval/deletion routes (shared RC-07/NEXI-004) - this specifically means unauthenticated user enumeration and deletion are currently possible in source. Upload size is checked only after a full read (NEXI-032), and the original file suffix is trusted and reused.

#### Reliability concerns
The registration-before-local-save ordering (NEXI-020) means a crash between those two steps leaves Central with an identity that has no recoverable local record, and vice versa if local save succeeds but Central registration fails.

#### Scalability concerns
Ten samples (five face, five voice) are processed strictly sequentially; async storage writes go directly to the final file with no atomic-replace/transaction lock (`storage_async.py:54-70`).

#### Maintainability concerns
Two full alternate implementations (`enrollment_service.py` vs `enrollment_service_enhanced.py`; two storage classes) with no clear signal in the code about which is intended to survive.

#### Integration/API concerns
`update`/`improve-training` sometimes interpret `user_id` as `name` (`enrollment_service.py:281,620`) - an unstable external identity contract that any frontend/mobile client would need to work around inconsistently depending on which code path it hits.

#### What should stay
The overall enrollment-as-a-distinct-service boundary (see ADR-007 - explicitly not recommended for merging into Central). Fernet encryption for local metadata. The five-face/five-voice workflow structure itself, which matches the Sprint 1 design and is not something Sprint 2's minutes changed.

#### What should change
Fix the local-record schema to include the embeddings recovery logic actually expects (NEXI-020) - this is a data-integrity fix, treat the current mismatch as the authoritative bug and align the write path to the read path's expectations, not the reverse, since the recovery path's expectations reflect the intended durable-record shape. Reorder registration and local save so a durable local record exists before (or atomically with) Central registration, with a defined compensation path if either step fails. Fix the three downstream contract mismatches (Vision path, Central response shape, Audio health-adapter type handling) as a single contract-alignment pass across this service's outbound clients.

#### What should be removed
`enrollment_service_enhanced.py` and `app/storage/enrollment_storage.py`, both classified LIKELY SAFE - VERIFY FIRST in the audit - but only after confirming neither is invoked by any manual tooling, CLI script, or external consumer outside the currently-mounted router.

#### What must NOT be removed yet
Both currently-instantiated storage classes (sync and async) until their consumers are migrated to one. The nested directory containing the encryption key and any existing enrollment data - this is recovery material, not duplication, regardless of its awkward nested path.

#### Dependencies before modification
Fixed Vision face-detection contract (section 10) and fixed Central user-registration response shape (section 8) before Enrollment's downstream calls can be considered fixed rather than pointed at a moving target.

#### Regression risks
HIGH on the local-record schema change specifically, since it affects biometric recovery data - treat this as requiring a migration path for any records written under the old schema, not a breaking schema swap.

#### Required tests after modification
Full-workflow integration test (enroll, then simulate a crash between local-save and Central-registration, then verify recovery behavior is correct in both directions). Contract tests against Vision, Central, and Audio matching their actual current (post-fix) response shapes. Deletion test asserting a partial failure is reported as partial, never as blanket success.

#### Target service responsibility
Biometric enrollment/re-enrollment/improve-training workflow orchestration and local encrypted metadata, remaining a distinct service from Central per ADR-007.

#### Service priority
P1

## 14. LLM Service Analysis

#### Current responsibility
Stateless chat-generation proxy to one OpenRouter model.

#### What is good and should be preserved
Exactly one cloud provider is configured (`openrouter_client.py:32`), which is the correct end state for S2-02. There is no discovered local-loader invocation in this service's current app - the offline-LLM removal is closer to done here than in almost any other Sprint 2 area, once the missing route is restored.

#### Confirmed problems
NEXI-022 (BLOCKER - `main.py:20` imports a missing `llm_service.routes.format` module unconditionally; the service cannot start at all). NEXI-023 (HIGH, Sprint blocker - even once started, `routes/generation.py:10-43` has no retrieval gate, no basic-command allowlist, and no output-grounding check; the caller fully controls `system_prompt`, and any `knowledge_items`/history Central might send are not schema fields at all and are silently discarded). NEXI-024 (the shared LLM client calls a circuit-breaker method that does not exist, expects a nested response shape the route does not return, and a caught failure path can report a canned fallback as if it were a successful generation - actively hiding failures from callers).

#### Root architectural problems
RC-02 (no policy boundary at all - this is the service where RC-02's absence is most consequential, since this is the only place an LLM call actually happens), RC-05 (missing route module), RC-06 (client/server response-shape mismatch).

#### Sprint 2 gaps
S2-01 MISSING entirely at this layer (no gate of any kind exists in the executable path). S2-02 PARTIAL (provider choice correct; service itself broken). S2-04 CONFLICTING (legacy prompt/context files still reference emotion, though unreferenced by the live route). S2-05 MISSING (no collection happens in the direct generation path - if this is meant to be where ordinary Q/A is captured, it currently is not). S2-09 PARTIAL (local inference not mounted, but the dead code remains present). S2-11 MISSING (no English enforcement anywhere - an isolated test with a fake provider showed `language=ur` accepted without any rejection).

#### Redundancy / duplication
`prompt_builder.py` and `system_prompts.py` have no current app/client import found and explicitly encourage general-knowledge answers "when no match exists" (`system_prompts.py:160-176`) - this is legacy Sprint 1 policy that actively contradicts S2-01 and must not be mistaken for the current route's behavior even though it is currently unreferenced. `shared/quantized_llm.py` retains an executable local-model loader with no discovered caller. `quick_start.py` still sets up a SmolLM environment.

#### Security concerns
No authentication, no authorization, no rate limiter on this app at all. Caller-controlled `system_prompt`, unlimited query size, and unconstrained `max_tokens`/`temperature` (an isolated test accepted `max_tokens=-1` and `temperature=99`) together create both a cost-abuse and a resource-abuse surface if this service were exposed as-is. The OpenRouter API key environment variable name is case-sensitive and inconsistently cased across configuration.

#### Reliability concerns
Does not start in the current checkout. Once started, a caught provider failure can be reported as a successful canned response (NEXI-024) - meaning even monitoring this service's success rate would not reliably detect a failing provider.

#### Scalability concerns
Synchronous `requests.post` inside an async route (`openrouter_client.py:97`) serializes the event loop around every external call; no pooled session; routes registered inside `lifespan` can duplicate across repeated lifespan runs.

#### Maintainability concerns
`tokens_generated` counts whitespace-split words rather than actual provider token usage (`openrouter_client.py:114`) - any cost or capacity planning based on this metric would be wrong by construction, not just imprecise.

#### Integration/API concerns
The intended health path is `/api/v1/health`, not the `/health` several root health-check scripts probe - this alone would cause a naive health-check integration to report this service as down even when it is genuinely up.

#### What should stay
The single-OpenRouter-provider design. The basic route shape (`/api/v1/generate`) once its request/response schema is fixed to match what Central and Audio actually send/expect.

#### What should change
This is where the restricted-RAG enforcement actually has to live at the request-boundary level, in coordination with Central's policy construction (section 16) - the LLM service should receive an already-restricted prompt and a fixed, small set of allowed generation parameters, not raw caller input. Fix the response-shape mismatch with the shared client (NEXI-024) and remove the fallback-as-success behavior so failures are reported as failures. Bound `max_tokens`/`temperature` server-side regardless of what a caller requests. Replace the word-count token metric with actual provider-reported usage.

#### What should be removed
`prompt_builder.py` and `system_prompts.py`, after confirming zero callers - these are not just unused, they are actively contrary to Sprint 2 policy and should not be left in place even as inert dead code, since a future change could accidentally reference them. `shared/quantized_llm.py` and `quick_start.py`'s SmolLM setup, after confirming zero external callers, per S2-02.

#### What must NOT be removed yet
The `generation.py` route and OpenRouter client themselves - these are the actual intended path and must be fixed, not replaced.

#### Dependencies before modification
The RAG-policy design (section 16) must be finalized before this service's request schema can be correctly redefined - fixing the schema first and the policy second would likely require redefining the schema twice.

#### Regression risks
MEDIUM-HIGH - once caller-supplied `system_prompt` is removed in favor of server-constructed prompts, any existing caller relying on custom prompts (even for testing) will need to be updated; this is an intentional breaking change required by S2-01, not an accidental one.

#### Required tests after modification
Startup/import test. Contract test proving a caller cannot override the system prompt or bypass the knowledge gate. Adversarial test suite specifically for FLOW-07/FLOW-08 (unknown question requests teaching; open-domain request is blocked) using both a fake provider (fast, deterministic) and, separately, the real provider (slower, for acceptance). Test asserting out-of-range `max_tokens`/`temperature` are clamped or rejected, not passed through.

#### Target service responsibility
Stateless, policy-constrained generation against one online provider. This service does not decide what it is allowed to know or say - that decision is made and enforced before the request reaches it (section 16).

#### Service priority
P0

## 15. Shared Infrastructure Analysis

#### Current responsibility
Cross-cutting HTTP client behavior, circuit breakers, rate limiting, structured logging, configuration/port resolution, and root-level CLI/orchestration tooling used by all seven services.

#### What is good and should be preserved
The intent to centralize HTTP client behavior (`shared/clients/base_client.py`), retries, and circuit-breaking in one place instead of seven is architecturally correct and should be strengthened, not abandoned.

#### Confirmed problems
Two incompatible circuit-breaker interfaces exist (`shared/clients/base_client.py` vs `shared/utils/circuit_breaker.py`), and the LLM client calls a method that exists on neither correctly (NEXI-024). `ServiceClientFactory.get_audio_client` passes a keyword argument the `AudioServiceClient` constructor does not accept - reproduced as a `TypeError` (NEXI-026). `config/ports.py:82-91` omits `llm` from its base-URL resolution, so LLM's URL silently resolves to Central's URL instead - confirmed by direct evaluation showing both URLs equal. `shared/rate_limiter.py` raises `HTTPException` inside middleware, which is invalid ASGI middleware behavior and produces a 500 instead of a 429 (NEXI-019, reproduced as `[200, 500]` under an isolated one-request-limit test). `shared/models/structured_logger.py` installs a `trace_id`-requiring formatter without a universal enrichment filter, reproduced as a live formatting error in Central v2 (NEXI-028).

#### Root architectural problems
RC-06 (interface drift between parallel implementations of the same concern - two circuit breakers, two retry-handler modules), RC-08 (the rate-limiter and logging defects both convert a well-intentioned safety mechanism into a failure that looks like an application bug to callers).

#### Sprint 2 gaps
Not Sprint-2-specific by requirement ID, but this layer is the natural home for centrally enforcing S2-11 (English-only) and any shared request-budget policy - currently it enforces neither.

#### Redundancy / duplication
`shared/retry_handler.py` and `shared/utils/retry_handler.py` are parallel retry policies. `shared/utils/trace_context.py` has two same-named functions with similar-but-not-identical AST bodies at different line numbers (sync vs async scope) - the audit is explicit this must not be resolved by hash-based deletion, since the semantics differ despite the similarity.

#### Security concerns
None unique to this layer beyond what it fails to centrally enforce (auth, rate limiting) for every service that depends on it.

#### Reliability concerns
The rate-limiter and logging defects are two more root causes (beyond RC-01 through RC-07) of confusing failure signals reaching operators and callers - both are RC-08 instances.

#### Scalability concerns
None distinctly new at this layer; it inherits whatever the services built on top of it do.

#### Maintainability concerns
`nexctl.py` (operational CLI) has stale route assumptions and interactive destructive-cleanup actions; `scripts/health_check_all.py` checks six services and omits LLM entirely, meaning the one operational health script currently in the repository cannot even report on the service most central to Sprint 2's restricted-RAG requirement.

#### Integration/API concerns
Root `service/rag_orchestrator.py` and `llm_context_builder.py` provide an alternate orchestration path used by the large interactive test harness (`test_nexi_system_enhanced.py`), not by any deployed service - this must not be confused with actual enforced policy, and its absence from the deployment import path is itself meaningful evidence that it is not currently load-bearing in production.

#### What should stay
The base HTTP client abstraction, once consolidated to one circuit-breaker interface. Structured logging's overall design, once the trace-ID enrichment gap is closed.

#### What should change
Consolidate to one circuit-breaker interface and update every caller (LLM client's `is_closed` call being the confirmed, reproduced casualty). Fix the rate-limiter to return an ASGI-valid `Response` at the correct middleware layer. Add `llm` to `config/ports.py`'s base-URL map. Fix `ServiceClientFactory.get_audio_client`'s keyword mismatch. Ensure every logger handler either has the trace-ID field or the formatter does not require it unconditionally.

#### What should be removed
Whichever of the two retry-handler modules is not the one actually consumed by live services, after a reference check - not yet classified as safe without that check.

#### What must NOT be removed yet
`shared/utils/trace_context.py`'s apparently-duplicate functions - explicitly flagged in the audit as similar-but-semantically-different (sync/async), not a hash-deletion candidate.

#### Dependencies before modification
None blocking - this layer's fixes (breaker consolidation, rate-limiter, port map, factory signature) are largely independent, low-regression corrections that should happen early (Phase 1) precisely because every service depends on them.

#### Regression risks
MEDIUM - any service currently working around a shared-layer defect (for example, a caller that never actually hits the rate limit in practice) could see new behavior once the defect is fixed; this is expected and desired, but should be rolled out with contract tests per affected service.

#### Required tests after modification
A single shared-layer contract test suite: circuit-breaker state transitions against the one consolidated interface; rate-limiter returns 429 (not 500) at threshold across at least two services that use it; `ServiceClientFactory` constructs every service client without a `TypeError`; port resolution returns a distinct, correct URL for every configured service including LLM.

#### Target service responsibility
One circuit-breaker interface, one retry-handler module, one port/URL resolution map, correct ASGI-compliant rate limiting, and reliable structured logging - consumed identically by all seven services.

#### Service priority
P0 (blocks reliable diagnosis of every other service's fixes)

## 16. Restricted RAG Architecture

This is the single most consequential Sprint 2 change, and the audit's evidence is unambiguous: **no enforcement of any kind currently exists in the executable request path.** `routes/generation.py:10-43` accepts a caller-supplied `system_prompt`, does not look at any command allowlist, does not query TeachMe, does not check whether knowledge exists, and forwards the model's output unfiltered. An isolated test using a real router and a fake provider reproduced this directly: an open-domain question with a caller-controlled prompt returned HTTP 200 with the synthetic output passed through unchanged, and supplied "knowledge" was discarded because it is not even a schema field on the request. Separately, TeachMe - the intended sole grounding source - cannot start at all (NEXI-016), so even a correctly-gated LLM call would currently have nothing to ground against.

#### 16.1 Expected flow (per the Sprint 2 requirement and meeting minutes)

```
User query
    |
    v
Fixed-command classifier (10-15 hard-coded greetings/commands)
    |
    +-- match --> hard-coded response, LLM never called
    |
    +-- no match
          |
          v
       TeachMe retrieval
          |
          +-- no relevant grounded data --> "I don't know this yet. Please teach me."
          |                                  (LLM never called)
          |
          +-- relevant data found
                |
                v
             LLM receives ONLY the retrieved facts, in a server-constructed prompt
             the caller cannot override
                |
                v
             generated response
                |
                v
             output validation: does the response stay within the supplied facts?
                |
                v
             response returned to user
```

#### 16.2 Where the current architecture diverges

| Expected stage | Current reality | Evidence |
|---|---|---|
| Fixed-command classifier | Does not exist anywhere in the executable path | `generation.py:10-43`; no allowlist discovered on any generation route |
| TeachMe retrieval | TeachMe cannot start | NEXI-016 |
| Teach-first fallback on no match | Does not exist; legacy `system_prompts.py` explicitly does the opposite (encourages general-knowledge answers), though that file is currently unreferenced | NEXI-023 |
| Server-constructed, caller-unoverridable prompt | Caller fully controls `system_prompt` | `generation.py:10-43` |
| Knowledge passed through a typed schema | `knowledge_items`/history are not schema fields at all; anything sent is silently discarded | NEXI-023 |
| Output grounding validation | Does not exist; output is forwarded unfiltered | NEXI-023, isolated test result |
| Bypass check: can the LLM answer from pretrained knowledge? | Yes, unconditionally, for any query | Reproduced directly in the isolated fake-provider test |

#### 16.3 Recommended final RAG request path

This design does not introduce a vector database. TeachMe's own configured retrieval (linear fallback plus optional FAISS) is sufficient at the described scale, per PROJECT.md section 33's own recommendation and Principle 5 (minimum architecture necessary). The design instead relocates *where enforcement happens*: from "nowhere" to a single owned component.

**Ownership: this policy layer lives in Central, as a new internal module (not a new service - Principle 5), positioned between the inbound request and the LLM client call.** It is the only caller of the LLM service. Audio and any other current direct LLM callers are redirected to call Central's policy endpoint instead of the LLM service directly (this is a deliberate breaking change to Audio's current LLM-calling path; see ADR-002).

1. **Intent classification (Central, new).** A small, fixed allowlist (10-15 entries, per the meeting minutes) matched deterministically (exact or fuzzy string match - no model call). On match, return the hard-coded response immediately. This is a product-owned input (the approved command list), not an engineering decision.
2. **TeachMe retrieval (Central calls TeachMe, contract fixed per section 12).** If no command matched, query TeachMe with the user's question. TeachMe returns either a relevant fact/object with a confidence score, or nothing.
3. **Teach-first short-circuit.** If TeachMe returns nothing above the confidence threshold, return the configured "teach me" response immediately. The LLM is never called. This is the single highest-value change for cost, latency, and correctness together.
4. **Server-constructed prompt.** If TeachMe returns a match, Central constructs the full prompt server-side, embedding only the retrieved fact(s) and a fixed instruction to answer strictly from that content. The caller-facing API for this path does not accept a `system_prompt` field at all - it accepts a query and, internally, retrieved facts are the only context ever injected.
5. **LLM call (LLM service, fixed contract per section 14).** The LLM service receives the fully-constructed prompt and a small set of server-controlled generation parameters (temperature, max tokens) that a caller cannot override.
6. **Output grounding validation (Central, new).** Before returning the LLM's output to the caller, check that it does not contradict or exceed the scope of the retrieved fact(s). At minimum-necessary scope, this can be a simple containment/similarity check against the retrieved fact text, not a second model call - a second LLM call to validate the first is disproportionate at this stage and should only be considered later if simple checks prove insufficient in practice.
7. **English-only enforcement.** Applied once, at this same boundary (step 1's classifier and step 4's prompt construction both operate in English only; non-English input is rejected here rather than separately in Audio, TTS, and LLM as it is today, closing AC-03 and RC-09 in one place).

#### 16.4 What this resolves and what it still requires

This design closes S2-01 and S2-11 structurally, and gives S2-04/S2-09/S2-10's "one enforcement point" pattern something to imitate for the requirements not directly about RAG. It requires, as prerequisites: TeachMe running with a fixed contract (section 12), Central's authority resolved (ADR-001) so there is one place to put this module, and the approved basic-command list from product (explicitly an external input per PROJECT.md section 33, not something this plan can supply). It does not require, and this plan explicitly rejects, introducing a vector database, a separate "policy service," or an LLM-based output validator as a first iteration.

## 17. Data Architecture

| Data category | Owner | Current storage | Required persistence | Local/cloud | Retention | Sync policy | Sensitivity | Backup | Concurrency risk | Migration need |
|---|---|---|---|---|---|---|---|---|---|---|
| Users (identity + biometric embeddings) | Central | `users.json`, unencrypted | Durable, transactional | Local (never exported) | Indefinite, pending a retention policy decision | Never synced | Biometric - highest sensitivity | Not established | HIGH - full-document read-modify-write, no locking scope proven correct | Migrate to a transactional store (recommend SQLite) |
| Conversations (ordinary Q/A) | Central | `conversations.json` (main) or embedded in user records (v2) | Durable, transactional, with sync-state fields | Local, then synced every 24h | 500 records/user currently; needs an explicit policy | 24-hour batch export, TeachMe/biometric excluded by schema | Moderate - query content, not biometric | Not established | HIGH - fixed temp filename, incomplete lock scope | Migrate to a transactional store with a `synced`/`batch_id`/`last_attempt` column set |
| TeachMe facts/objects | TeachMe | `knowledge_data.json`, backups, in-memory/vector index | Durable, transactional | Local only, never synced | Indefinite (user-managed) | Explicitly excluded from cloud sync | Personal but not biometric | Backups exist; recovery process unverified | HIGH - async writer does not share the sync writer's lock | Same transactional migration as above; separately, re-embed existing entries once a real embedding model is chosen |
| Audio speaker embeddings | Audio | Local pickle | Durable, non-executable serialization | Local only | Tied to user enrollment lifecycle | Never synced | Biometric | Not established | Not primarily a concurrency risk; a deserialization-security risk (NEXI-033) | Migrate away from pickle to a validated, non-executable format (e.g., JSON/NumPy array with a schema) |
| Audio command backlog | Audio | SQLite | Already transactional | Local, operational only | Short-lived (queue semantics) | Not a sync source; not an ordinary-Q/A dataset substitute | Low - operational metadata | Not established | LOW - SQLite already provides this | None - already the right technology choice for this data type |
| Enrollment metadata | Enrollment | Conditionally Fernet-encrypted local files | Durable, atomic write | Local only | Tied to enrollment lifecycle | Never synced | Biometric | Existing key/data must be preserved through any change | MEDIUM - final-file write is not atomic (NEXI-020 extension) | Fix write atomicity; align schema with what recovery logic expects |
| Credential/key files | Root/Central/Enrollment | Tracked salted-hash records; local key files | Durable, access-controlled | Local only | Indefinite | Never synced | Highest sensitivity | Rotation/backup policy not established | Not primarily a concurrency risk | Requires an explicit credential-lifecycle policy decision (human decision required) before any migration |
| TTS voice cache | TTS | Local file cache | Ephemeral, regenerable | Local only | Bounded by cache-eviction policy (exists) | Never synced | None | Not needed - regenerable | LOW | None required |
| Temporary media (enrollment uploads, recordings) | Enrollment, Audio | Local temp files | Ephemeral, must be cleaned up reliably | Local only | Should not outlive the request/session | Never synced | Biometric while it exists | Not applicable | MEDIUM - crash cleanup/retention is unverified | Add explicit cleanup-on-failure and cleanup-on-timeout guarantees |
| Logs | All services | Local files | Short-to-medium retention | Local, not synced without explicit redaction | Bounded, with redaction of personal/biometric/credential fields | Never synced as-is | Variable - can contain transcription/user content today | Not established | LOW | Add redaction before any log-shipping is introduced |

**Recommendation (not automatic PostgreSQL adoption, per Principle 5):** migrate the three JSON stores with confirmed concurrent-writer risk (Central users, Central conversations, TeachMe knowledge) to SQLite. SQLite is already a proven, working technology in this codebase (Audio's command backlog uses it correctly today) and provides real transactions, which is exactly what NEXI-003's root cause (RC-03) requires - no new database technology needs to be introduced to fix this. This is a **root-cause fix for RC-03 in one migration**, not five separate per-file patches, consistent with Principle 4. PostgreSQL would only become justified if this system needed multi-process/multi-host concurrent writers at a scale this single-robot-backend deployment profile does not currently describe (Principle 9's "proportional to deployment context" applies equally to persistence choices).

The export boundary for cloud sync (section 19) must be schema-enforced, not convention-enforced: the sync worker should read from an explicit, narrow "exportable fields" projection of the conversations table, and should have no code path capable of reading from the users table or the TeachMe knowledge table at all - this is a stronger guarantee than "the sync worker currently doesn't look at those tables" and is the correct way to make NEXI-030's TeachMe-exclusion requirement verifiable rather than merely believed.

## 18. Resource Management Architecture

#### 18.1 Current state

At least three independent implementations exist with overlapping camera-ownership claims: Central's `hardware_resource_manager.py` and `camera_manager.py` (both mounted by `main`), and Vision's own local `resource_pool.py`. The audit reproduced, using real manager instances, that two independent managers can grant the same camera simultaneously, that a queued release cannot be cancelled once requested, and that Vision's camera client is fail-open (it eventually grants access even after an explicit Central denial, and caches availability without a TTL refresh). A logical priority-revoke succeeding in a unit test does not mean the physical device was released - Vision's paused stream retains its open `VideoCapture` handle regardless of what any manager's metadata says (NEXI-005, NEXI-009).

#### 18.2 Resources and competing operations

| Resource | Competing operations |
|---|---|
| Camera | Passive background monitoring (if any remains post-emotion-removal), active conversation (face context, if retained), enrollment face capture, TeachMe object-teaching capture, incoming video call, screenshot during a call |
| Microphone | Passive wake-word listening, active conversation recording, enrollment voice capture, speaker verification |
| Speaker (audio output) | TTS playback during conversation, TTS playback during enrollment prompts, call audio (owned by the video team, not this backend) |
| CPU/RAM | DeepFace/YOLO resident models, Piper TTS worker pool, LLM's local-loader dead code (to be removed), TeachMe's index/search |
| GPU (if present) | DeepFace/YOLO inference, any future TeachMe embedding-model inference |

#### 18.3 Recommended priority hierarchy

Derived directly from the Sprint 2 meeting minutes (item 6: TeachMe gets maximum available resources during teaching; item 11: an incoming call takes priority and pauses other ongoing activity so the caller can see the robot's live feed) rather than invented:

```
VIDEO CALL (incoming, once accepted)
    >
ACTIVE TEACHME SESSION
    >
ENROLLMENT
    >
ACTIVE CONVERSATION
    >
BACKGROUND / IDLE MONITORING
```

Video call sits above active TeachMe because the minutes state the incoming call takes priority and pauses "other ongoing activity" without carving out an exception for TeachMe; this should be confirmed explicitly with product before implementation, since it is a real-world interruption (a child teaching an object having the camera taken away by an office call) with a corresponding UX consequence, not purely a technical ranking (marked HUMAN DECISION REQUIRED for final confirmation, defaulting to the minutes' literal reading).

#### 18.4 Recommended architecture

**One resource authority, in Central, replacing both `camera_manager.py` and `hardware_resource_manager.py` with a single consolidated implementation.** Vision's local `resource_pool.py` becomes a cooperating client of this authority, not an independent decision-maker - it requests, receives an acknowledged grant, and must acknowledge release before the authority considers the resource free. This directly closes the fail-open behavior (NEXI-005): a request to Vision's camera client should fail closed (deny access) if it cannot reach the authority or receives an explicit denial, with no fallback path that grants access anyway.

Priority means: **revoke request sent to the current holder, an acknowledged stop/release from that holder (not just an internal metadata flag), grant to the new requester, and eventual restoration to whatever the priority order says should resume afterward.** This requires an explicit release-acknowledgement callback that does not currently exist anywhere in the codebase - this is new coordination logic, not a bug fix. A bounded timeout applies to the acknowledgement step (if a holder does not release within, for example, a few seconds, the authority should treat this as a fault, log it, and force-close the underlying hardware handle itself rather than waiting indefinitely) to close the current "queued release fails silently" defect.

Queue cancellation (currently broken - a cancelled queued request still retains its place, per the audit) must actually remove the request from the queue, not merely mark it cancelled while leaving it queued.

#### 18.5 What this does not require

No distributed lock service, no message queue. This is a single-process (or, if Central is ever split across processes, a single logical authority reachable by all of them) in-memory coordinator with the acknowledgement and timeout semantics described above - the same category of component that already exists in the codebase today, corrected rather than replaced with new infrastructure.

## 19. Cloud Sync Architecture

#### 19.1 Current state

`Central/main.py:17` imports a `CloudSyncService` class that does not exist anywhere in the source tree - this is the reason `main` cannot start at all, making cloud sync not merely "incomplete" but the direct cause of Central's primary startup blocker (NEXI-001). The code that does exist (`main.py:20-28,68`) constructs this absent class with a hard-coded absolute history path outside the repository checkout, then runs a sync-and-sleep(86400) loop with no supervision - meaning any exception inside that loop would silently kill the entire scheduled task with no restart and no alert.

#### 19.2 Required properties (per S2-13 and the meeting minutes)

Ordinary Q/A data syncs to the cloud roughly every 24 hours; TeachMe data never leaves the device. Beyond the literal 24-hour interval, a correct implementation needs: an explicit unsynced-record state, batch identifiers, timestamps, retries with backoff, timeout handling, partial-failure handling, idempotency (so a retried batch does not create duplicate cloud records), last-success tracking, safe behavior across a service restart, and safe behavior when the network or cloud receiver is unavailable. None of these properties currently exist because the class implementing them does not exist.

#### 19.3 Recommended design

**An in-process, supervised, single-instance scheduled task within Central - not Celery, not Redis, not a separate service.** The audit's own recommendation (section 33) and Principle 5 both support this: nothing about a 24-hour batch export of a small local dataset justifies external queue infrastructure.

1. **Outbox table.** Using the same SQLite migration recommended in section 17, add `synced` (boolean), `batch_id` (nullable), and `sync_attempted_at`/`sync_succeeded_at` columns to the conversations table (or an equivalent outbox table referencing it). This makes "what needs to sync" a query, not a separate tracked file.
2. **Supervised scheduler.** Replace the unsupervised `sleep(86400)` loop with a task that is restarted by its supervisor (the same process-lifecycle mechanism Central already uses for its own startup, extended to wrap this task in a try/except that logs and retries rather than silently dying) and that computes the next run based on the last successful run's timestamp, not simply "time since this loop iteration started" - this distinction matters after a restart, where a naive sleep-based loop would either sync too early or wait a full extra day.
3. **Explicit export projection.** The sync worker reads only from the narrow exportable-fields projection described in section 17, with no code path capable of reaching the users table or the TeachMe knowledge store - this is what makes the TeachMe-exclusion guarantee verifiable (a code-review and a static-analysis check can confirm the sync module imports nothing from TeachMe's or the users table's modules) rather than simply asserted.
4. **Idempotent batch acknowledgement.** Each batch gets a generated `batch_id`; the cloud receiver's acknowledgement of that `batch_id` is what advances the local `synced`/`last_success` state. A retried batch with the same `batch_id` must be safely re-sendable without the receiver creating duplicates - this requires an idempotency contract with whatever the cloud receiver is (an external input this plan cannot supply on its own, consistent with PROJECT.md's own note that the cloud dataset contract is a product-owned input).
5. **Bounded retry with backoff**, reusing the shared HTTP client's existing retry/circuit-breaker pattern (section 15) once consolidated to one interface.
6. **Independently testable.** The audit's own minimum delivery gate calls for "an independently runnable cloud-sync test using a controlled receiver" - this design supports that directly, since the outbox and scheduler can be exercised against a local test HTTP receiver without any real cloud dependency.

#### 19.4 What this resolves

Closes S2-13 structurally and removes the direct cause of NEXI-001 (Central's startup blocker), since the sync worker's absence is what breaks the import today. Does not require, and this plan explicitly rejects, any message-queue or distributed-scheduler technology for a once-daily batch export at this data scale.

## 20. Video Call Integration Contract

The calling feature itself belongs to another team. This backend's job is to expose a stable contract that team can integrate against; it currently exposes none, because even the generic camera control the contract would sit on top of is broken (`/camera/pause` and `/camera/resume` both return 500, NEXI-009).

| Responsibility | Owner |
|---|---|
| Call signaling, WebRTC/media transport, UI, screenshot capture UX | Video/frontend team |
| Camera lease grant/preemption at VIDEO_CALL priority (section 18) | NEXI backend (Central resource authority) |
| Pausing/resuming whatever NEXI activity currently holds the camera (conversation, TeachMe) when a call starts/ends | NEXI backend |
| An explicit "incoming call" state the resource authority understands as the highest-priority requester | NEXI backend (new - does not exist today) |
| Camera stream/frame access during an active call | NEXI backend, exposed via a stable frame-access endpoint (build on a fixed version of the existing streaming route) |
| Screenshot capture mechanism (backend hook to grab a still frame on request) | NEXI backend, new endpoint; actual UI/save-to-device behavior is the video team's |
| Notifying frontend/mobile that a call is active (for UI state) | NEXI backend emits a status the frontend polls or subscribes to; exact transport (webhook vs. polling) is a joint decision with the frontend team |
| Call authorization/authentication (who is allowed to call the robot) | Video team's identity system; NEXI backend only needs to trust the call-start signal it receives, per whatever the two teams agree is the authentication boundary |

**What NEXI backend must build:** a `CALL_ACTIVE` priority state in the resource authority (section 18.3-18.4), fixed camera pause/resume endpoints (section 10's NEXI-009 fix is a direct prerequisite here), and a documented, versioned contract for call-start/call-end signals and screenshot capture. None of this should be built before section 10 and section 18's fixes land - a call-priority feature built on top of a camera-control endpoint that returns 500 half the time will surface as "video calling is broken" when the actual defect is the pre-existing camera contract.

## 21. API / Frontend / Mobile Integration

The single biggest integration blocker is AC-01: there is currently no one answer to "what is the Central API." Every other contract issue in this section is secondary to that one.

| Concern | Current state | Recommendation |
|---|---|---|
| Endpoint consistency | Two incompatible Central surfaces; JSON/query/multipart mixed inconsistently across services | Resolve ADR-001 first; standardize on JSON bodies for all non-file-upload routes |
| Versioning | No consistent `/api/v1` prefix across services (LLM and TeachMe partially use one, others do not) | Adopt one versioning scheme repository-wide once the authoritative Central app is fixed |
| Error envelope | At least three different shapes in use (`HTTPException` detail, custom `APIResponse`, bare booleans); some services return HTTP 200 with an internal `status=error` field | One shared error envelope (status code plus a typed error body), enforced via the shared library (section 15) |
| Health/readiness | Health frequently reports liveness, not capability (Vision, LLM's wrong path, Central's Audio-down-as-warning) | Every `/health` must report actual dependency/model status, not just process liveness (ties to section 23) |
| Media handling | Inconsistent raw-bytes vs. multipart across Audio/TTS | Standardize per data type: multipart for uploads, raw audio bytes only for direct playback responses, JSON everywhere else |
| Session/user IDs | Enrollment's `user_id`/`name` conflation (NEXI-021); Central's registration response omitting `user_id` in one path | Fix as part of section 8/13's contract-alignment work; one canonical identity field name throughout |
| Async operation status | Not currently modeled anywhere (enrollment steps, sync batches are fire-and-forget) | Add explicit status fields where a client needs to poll progress (enrollment step, sync batch) |
| Resource conflict errors | Not currently a distinguishable error type from any other 500 | A dedicated error code/type for "resource unavailable/preempted" once section 18's authority exists |
| Video call hooks | None | Section 20 |
| Cloud-sync status | None exposed | A minimal read-only status endpoint (last sync time, pending count) once section 19 exists |
| OpenAPI quality | Static docs describe routes no live app serves (AC-07) | Regenerate OpenAPI from the actual chosen application after ADR-001, do not hand-maintain a separate spec |
| CORS | Wildcard combined with credentials on multiple services - invalid per the CORS specification and rejected by strict clients | Explicit allowed-origin list per environment, credentials only where actually needed |
| Auth assumptions | None anywhere (RC-07) | Section 22 |
| Environment-based service URLs | `config/ports.py` omits LLM (NEXI-026); several hard-coded URLs bypass the shared config | Single source of truth for all service URLs, LLM included, with no hard-coded fallbacks in application code |

**Recommended breaking change (the only one this plan considers unavoidable and worth calling out explicitly):**

| | |
|---|---|
| OLD | Two Central apps (`main`, `api_v2`) with different routes, auth-free, caller-controlled LLM prompts |
| NEW | One Central app; authenticated identity/conversation/resource routes; no caller-controlled `system_prompt` anywhere in the public contract |
| RATIONALE | AC-01, NEXI-004, S2-01 all require this; there is no non-breaking path to a single authoritative, policy-enforcing Central |
| MIGRATION PLAN | Publish the new contract and an OpenAPI diff before Phase 6 (section 32) begins; keep the losing app's unique routes available under their existing paths on the new app for one migration window; require any internal test harness or CLI depending on the removed app's exact shape to update in the same window |
| FRONTEND/MOBILE IMPACT | Any client currently pointed at either app must be repointed at the merged app's URL/port and updated for the new auth requirement; any client relying on custom system prompts (should not exist outside internal testing) must switch to the query-only restricted-RAG contract |

## 22. Security Architecture

### Immediate / Internal Deployment (must address now, even for a trusted internal network)
Fail-closed the deserialization-security issue in Audio's speaker store (NEXI-033 - migrate off `pickle`). Fix TeachMe's fail-open JWT bypass so a missing JWT library denies rather than silently allows (`authentication.py:279`). Fix the rate limiter so it actually returns 429 instead of crashing to 500 (NEXI-019) - a broken rate limiter is worse than none, because it looks like an application bug rather than an enforced control. Stop accepting `max_tokens=-1`/`temperature=99` and similar out-of-range LLM parameters unconditionally.

### Before External Network Deployment (must address before exposing beyond a trusted internal network)
Authentication and per-resource authorization on every route touching identity, biometric data, conversation history, TeachMe data, and resource/camera control (RC-07, NEXI-004, NEXI-029) - this is the single largest security gap in the audit and the one most explicitly called out as CRITICAL. Replace wildcard-plus-credentials CORS with an explicit allowed-origin list on every service. Add TLS termination in front of all seven services (currently plain HTTP throughout). Add request-size and content-type validation before, not after, a full body read (NEXI-032). Add input validation on server-side file paths (`audio_file_path` accepted directly from request bodies).

### Before Commercial Production
Full encryption-at-rest for all biometric stores (currently JSON/pickle unencrypted for Central and Audio; Enrollment's is conditional), not just Enrollment's already-partial coverage. A defined credential-rotation policy for the Fernet key and the OpenRouter API key (currently a fallback-key search with silently-ignored chmod errors, `utils/encryption.py:24-47,142-164`). Log redaction for any field containing transcription text, biometric identifiers, or credentials before any log-shipping/aggregation is introduced. A dependency-vulnerability scan integrated into CI (not currently present per the audit's CI findings).

This plan explicitly does not recommend a WAF, a secrets-management platform, or a SIEM at this stage - those are commercial-production-tier controls disproportionate to a single-robot internal deployment (Principle 9), and are listed here only as a forward pointer, not a near-term requirement.

## 23. Observability Strategy

The minimum useful visibility, derived directly from what the audit found itself unable to diagnose without manual source inspection and reproduction:

| Need | Current state | Minimum recommendation |
|---|---|---|
| Structured logs | Present in most services, but a live formatting error exists in Central v2 (NEXI-028) | Fix the trace-ID enrichment gap; keep the existing structured-logging library, do not replace it |
| Request/correlation ID | Not consistently propagated across service-to-service calls | Generate at the edge (Central), propagate via a header, log it in every service touching that request |
| Startup/model status | Health checks report liveness, not model-load success (Vision's false-positive health being the clearest example, NEXI-010) | Every `/health` includes explicit per-dependency/per-model status, not just "process is up" |
| Health/readiness distinction | Not currently separated anywhere | Liveness (process up) and readiness (dependencies/models actually usable) as two distinct signals, per service |
| Latency | Not currently measured anywhere in the audit's findings | Basic per-route timing in the shared logging middleware (section 15), no separate tracing platform required |
| Errors | Inconsistent envelopes make errors hard to count reliably (section 21) | Fix the error envelope first; error-rate counting becomes straightforward once errors are a distinguishable shape |
| Resource lease state | Not observable at all today (contributing directly to NEXI-005 being hard to diagnose without source review) | The consolidated resource authority (section 18) exposes a read-only current-lease-state endpoint |
| Cloud sync status | Does not exist (section 19) | The sync worker's outbox status becomes directly queryable once built |
| External API failures | LLM's fallback-as-success behavior currently hides OpenRouter failures entirely (NEXI-024) | Fixing NEXI-024 is itself the observability fix here - once failures are reported as failures, they become countable |

This is application-level instrumentation only. Infrastructure-level collection (a metrics backend, a log aggregator, a dashboard) is explicitly out of scope for this plan - Principle 5 and the observability section's own instruction apply equally here: build what the application should expose, and defer the collection platform decision until there is a deployment target that needs one.

## 24. Test Architecture

The audit's own finding that pytest can report "3 nominal passed" while the actual operations fail (NEXI-012, AC-06) means the current test suite cannot be trusted as a regression gate until this is fixed - this is addressed first, not last, in the testing strategy.

| Layer | Current state | Target |
|---|---|---|
| Unit | Sparse; several test files are interactive/hardware-writing scripts rather than pytest-discoverable assertions | Per-service unit tests for the logic this plan changes (RAG gate, resource authority, sync worker, contract-fixed clients) |
| Service/component | The false-positive tests are concentrated here (Vision, LLM) | Rewrite to assert on outcomes, not just "no exception was thrown"; fail loudly on connection errors instead of catching and returning |
| Contract | None discovered between any two services | One contract test per producer/consumer pair fixed in this plan: Central-TeachMe (AC-05), Audio-STT media type (NEXI-008), Enrollment-Vision/Central/Audio (NEXI-021), LLM client-server shape (NEXI-024) |
| Integration | `test_nexi_system_enhanced.py` exists but exercises the unmounted root orchestrator, not the deployed services - it currently validates an architecture that is not what runs in production | Either retarget it at the deployed services once they are fixed, or explicitly relabel it as a design-reference harness, not a regression gate |
| End-to-end | UNVERIFIED - no evidence any full user-facing flow currently completes | Build after Phase 3-5 (section 32) restores basic service startup and contract correctness; premature before that |
| Failure/resilience | Not present for any of the specific Sprint 2 behaviors | Add the specific tests enumerated below |

**Required Sprint 2 behavior tests** (each maps to a status row in section 6): a known-TeachMe-fact question returns a grounded answer; an unknown question returns the configured teach-me response and never reaches the LLM (verifiable via a call-count assertion on a mocked LLM client); an open-domain question is blocked even when phrased to resemble a known fact (adversarial case); a wake-word failure permits direct voice and the session terminates on ~10s silence or manual stop; non-English input is rejected at the policy boundary; only Jenny can be selected via `/speakers/switch`, end-to-end; no emotion field appears in any live response schema; the offline LLM loader is proven unreferenced by an import-graph check, not just absent from the currently-read routes; TeachMe data is provably unreachable from the sync worker's import graph; a duplicate sync batch (same `batch_id`) is a no-op on the receiver; enrollment recovers correctly from a crash between local-save and Central-registration in both directions; a video-call priority request preempts an active TeachMe session and the camera is confirmed released, not just logically marked so; every service restarts cleanly and reaches readiness after a forced process kill.

## 25. Duplication / Redundancy Strategy

| Group | Authoritative | Legacy | Shared-code opportunity | Action |
|---|---|---|---|---|
| Central application | `api_v2:app` (only one that runs), pending ADR-001 | `main:app` (documented intent, cannot start) | Merge main's intended route surface (TeachMe/camera/resources) into v2's working foundation | MERGE, per ADR-001 - do not delete either until migration is verified |
| Central resource managers | Neither, as-is | Both `camera_manager.py` and `hardware_resource_manager.py` | A single consolidated authority (section 18) | REPLACE both with one new implementation; do not keep either as-is |
| Central LLM routes | The route mounted and actually called by Audio/frontend today | `routes/llm_routes.py` factory (no call site found) | None needed | REMOVE after confirming zero callers |
| Vision queue modules | None currently initialized | Unused queue modules, stale unprefixed test/doc references | None | REMOVE after confirming no consumer; update any doc/test referencing the old paths |
| Audio conversation state | `services/conversation_state.py` (imported by `main`) | `managers/conversation_state_manager.py` | None | REMOVE legacy after confirming zero callers |
| Audio embedding path | The lazy-singleton path in the mounted advanced routes | `api.py` + `embedding_extractor.py` (unmounted, broken relative imports) | None | REMOVE after confirming zero external callers |
| TTS voice configuration | Public `VOICE_DEFINITIONS` (Jenny-only) | Internal `EngineManager`/cache Urdu and Ryan/Shahid branches | The validated `resolve_voice` pattern should be the only path anything internal uses too | REMOVE internal multi-voice branches; KEEP and extend `resolve_voice` as the sole gate |
| LLM prompt/context modules | The (to-be-fixed) live `generation.py` route plus the new RAG-policy layer in Central | `prompt_builder.py`, `system_prompts.py` (unreferenced, and actively contrary to S2-01 policy) | None | REMOVE after confirming zero callers - do not leave in place even as inert code, per section 14 |
| LLM offline loader | N/A - target state has none | `shared/quantized_llm.py`, `quick_start.py`'s SmolLM setup | None | REMOVE after confirming zero callers, pending the AC-04 scope ruling |
| Enrollment implementation | The router-mounted `enrollment_service.py` | `enrollment_service_enhanced.py` | Compare feature sets before removal in case the enhanced version fixed something the mounted one has not | REMOVE enhanced version after a feature-parity check, or MERGE its fixes into the mounted version if any exist |
| Enrollment storage | The `StorageAdapter`-selected active class | `app/storage/enrollment_storage.py` | Consolidate to the adapter pattern already in use | REMOVE after confirming zero direct callers |
| Shared circuit breakers | One interface, chosen during Phase 1 (section 15) | The other of the two | Update every caller to the chosen interface | MERGE callers onto one interface, REMOVE the other |
| Shared retry handlers | The one actually consumed by live services | The other | None | REMOVE after a reference check |
| Root orchestration harness | N/A for production; KEEP as a design reference if retargeted at real services | `service/rag_orchestrator.py`, `llm_context_builder.py`, `test_nexi_system_enhanced.py` as currently written | The intent behind `rag_orchestrator.py` is close to section 16's design and can inform its implementation | KEEP SEPARATE from production code explicitly, or retarget/rewrite once section 16 exists - do not delete outright, since it documents original design intent |

**Deletion dependency graph (high level):** fix contracts and confirm zero-caller status before any deletion in this table; resolve ADR-001 before touching either Central app; consolidate the resource authority before removing either old camera manager; land the RAG-policy layer (section 16) before removing `prompt_builder.py`/`system_prompts.py`, since the new layer is what actually replaces their intended function. No item in this table should be deleted in Phase 1-2 of section 32; deletions are concentrated in Phase 4 and Phase 10, after their replacements are verified working.

## 26. Dependency Cleanup Strategy

| Feature removed/consolidated | Dependency candidates | Verification required before removal |
|---|---|---|
| Emotion detection (S2-04) | FER-related packages in the manifest; any TensorFlow/Keras dependency used only by the emotion path (DeepFace's own TensorFlow dependency must be kept - it is load-bearing for face recognition) | Confirm the emotion-specific package is not the same TensorFlow/Keras install DeepFace requires before removing anything from the manifest |
| Offline LLM (S2-02/S2-09) | `transformers`, local model weight files, any quantization package, HuggingFace download cache | Confirm `shared/quantized_llm.py` and `quick_start.py`'s SmolLM setup have zero callers (section 14) before removing the dependency, not just the calling code |
| Urdu/Rehnuma/multilingual (S2-11) | Rehnuma-specific packages/assets, language-detection library, any multilingual tokenizer data | Confirm no retained component (STT, TTS, LLM) still declares a language parameter accepting non-English values (AC-03) before removing supporting packages |
| Legacy audio embedding path | Any package used exclusively by `api.py`/`embedding_extractor.py` | Confirm zero external callers of the legacy path itself first (section 25) |
| Pickle-based speaker storage (security fix, section 22) | None removed; format changes, dependency does not | N/A - this is a format migration, not a dependency removal |

No dependency is removed under this plan until PROJECT.md-equivalent evidence (a repository-wide reference search performed at execution time, not assumed from this document) proves zero remaining callers - this table identifies *candidates*, consistent with section 19 of the original audit framework's instruction not to remove a dependency until no other active feature is proven to use it.

## 27. Target Sprint 2 Architecture

```
Client / Robot / Mobile / Frontend
        |
        v
   Central (single authoritative app)
   - Identity & conversation persistence (SQLite)
   - Resource lease authority (camera/microphone, priority-ordered)
   - RAG policy boundary (intent classifier -> TeachMe lookup ->
     teach-first fallback -> server-built prompt -> output validation)
   - Cloud sync scheduler (outbox pattern, TeachMe excluded by
     schema-enforced projection)
        |
        +------------+------------+-------------+
        |            |            |             |
        v            v            v             v
      Audio        Vision       TeachMe     Enrollment
   (record, wake  (face/object  (sole        (biometric
    fallback,      detection,    grounding    onboarding
    verify, STT)   camera as     source,      workflow,
                   lease client) local-only)  local storage)
        |
        v
   Single LLM (OpenRouter only; receives only server-built,
   policy-constrained prompts; no caller-controlled system prompt)
        |
        v
   Jenny-only TTS (English only)
        |
        v
   Output to client

Local Personal Storage: TeachMe knowledge (never synced), biometric
  embeddings (Central users table, Audio speaker store, Enrollment
  metadata) - never synced under any code path.

Regular QA Store -> 24h Cloud Sync: Central conversations table,
  narrow exportable-fields projection only.

Resource Coordinator: single authority in Central; VIDEO_CALL >
  ACTIVE_TEACHME > ENROLLMENT > ACTIVE_CONVERSATION > BACKGROUND.

Video Call Integration Boundary: Central exposes CALL_ACTIVE priority
  state, fixed camera pause/resume, and a screenshot hook; the video
  team owns signaling, transport, and UI.
```

| Component | Responsibility | Separate service? | Data ownership | Resource ownership | Dependencies | Failure behavior |
|---|---|---|---|---|---|---|
| Central | Identity, conversation, resource authority, RAG policy, cloud sync | Yes (existing) | Users, conversations | Camera/microphone lease authority | TeachMe, LLM, Audio, Vision | Must fail loudly on startup (no more silent missing-import failures); RAG policy fails closed (teach-me response) on any TeachMe/LLM error |
| Audio | Recording, wake/fallback session lifecycle, verification, STT | Yes (existing) | Speaker embeddings, command backlog | Microphone (as lease client) | Central, TTS, Groq | On STT/verification failure, session ends gracefully with a clear error, not a hang |
| Vision | Face/object perception | Yes (existing) | None persistent (stateless inference) | Camera (as lease client) | Central (resource authority) | Health reports actual model-load status; camera denial fails closed |
| TTS | English/Jenny-only synthesis | Yes (existing) | Voice cache only | Speaker output | None external | Falls back to text-only response on synthesis failure, per the existing fallback cascade design |
| TeachMe | Sole grounding source | Yes (existing) | Knowledge facts/objects | None | Vision (enrichment) | RAG policy layer treats TeachMe unavailability as "nothing found," triggering the teach-me fallback, not an open-domain answer |
| Enrollment | Biometric onboarding workflow | Yes (existing, per ADR-007) | Local encrypted metadata | Camera/microphone (as lease client, ENROLLMENT priority) | Vision, Audio, Central | Local-save-then-register ordering with defined compensation on partial failure |
| LLM | Policy-constrained generation | Yes (existing) | None (stateless) | None | OpenRouter | Failure is reported as failure (not a canned success); Central's RAG layer treats it as "cannot answer right now" |

This target explicitly does not add a service mesh, an API gateway product, a vector database, or a message queue - every component above already exists as a directory in the current repository; this is a correction of contracts and internal boundaries, not a new system.

## 28. Architectural Decision Records

### ADR-001 - Central authority selection

**Context:** Two Central applications exist (`main:app`, `api_v2:app`) with incompatible route sets; only `v2` starts. **Problem:** No single answer exists to "what is the Central API," blocking every other Sprint 2 requirement that touches orchestration. **Options considered:** (a) fix `main` and retire `v2`; (b) keep `v2` and add the missing TeachMe/camera/resources routes to it; (c) write a new third app combining both. **Chosen approach:** (b) - keep `v2` as the foundation and extend it with `main`'s intended route surface, fixing `main`'s startup blocker only long enough to confirm it has no route logic worth preserving that `v2` lacks. **Why:** `v2` is proven to run; extending working code carries less risk than debugging code that has never successfully started. **Trade-offs:** `v2`'s current data model (conversation turns embedded in user records) needs to be reconciled with the separate-storage requirement (S2-06) as part of this work, not deferred. **Migration impact:** Section 21's breaking-change entry. **Rollback possibility:** High - both apps remain in version control; if extending `v2` proves harder than expected, `main`'s route definitions remain available as a reference.

### ADR-002 - Restricted RAG enforcement location

**Context:** No enforcement exists anywhere; the LLM service currently accepts a caller-controlled prompt. **Problem:** Where should the classifier/retrieval/gate/validation logic live. **Options considered:** (a) inside the LLM service itself; (b) inside Audio (the current primary caller); (c) inside Central, as the sole caller of LLM going forward. **Chosen approach:** (c). **Why:** Central already owns TeachMe's connector and is the natural single point through which every conversation-producing request flows; placing policy in the LLM service would leave it unable to distinguish a policy-compliant caller from any other caller, and placing it in Audio would leave a second entry point (any future text-only client) unprotected. **Trade-offs:** Requires redirecting Audio's current direct LLM calls through Central instead - a deliberate breaking change. **Migration impact:** Audio's LLM-calling code changes to call Central; LLM's request schema shrinks to remove `system_prompt`. **Rollback possibility:** Medium - reversible, but would reopen the exact gap this ADR closes.

### ADR-003 - Persistence technology for concurrently-written stores

**Context:** Central users/conversations and TeachMe knowledge are all JSON files with confirmed concurrency defects (RC-03). **Problem:** What replaces them. **Options considered:** (a) keep JSON with improved locking; (b) SQLite; (c) PostgreSQL. **Chosen approach:** (b) SQLite. **Why:** SQLite already exists and works correctly in this codebase (Audio's command backlog); it provides real transactions, which improved file-locking around JSON cannot fully guarantee under crash scenarios; PostgreSQL is not justified by any documented concurrency or scale requirement in the audit (Principle 5/9). **Trade-offs:** Requires a data-migration script for existing JSON records; slightly more operational surface than flat files (a single `.db` file, still trivially backed up). **Migration impact:** Section 17. **Rollback possibility:** Medium - requires re-exporting to JSON if reversed, but the migration script can be written to be reversible.

### ADR-004 - Resource coordination consolidation

**Context:** Three independent camera-ownership implementations exist (RC-04). **Problem:** Which becomes authoritative. **Options considered:** (a) pick one of the three existing managers and extend it; (b) build one new consolidated authority and retire all three. **Chosen approach:** (b). **Why:** All three have at least one confirmed defect (NEXI-005, NEXI-009); none is a clean foundation, and the acknowledgement/timeout semantics this plan requires (section 18.4) do not exist in any of them. **Trade-offs:** More upfront work than extending an existing manager. **Migration impact:** Section 18. **Rollback possibility:** Low once services are migrated to the new authority's client interface - treat this as a one-way migration with thorough testing before cutover, not an easily-reversible change.

### ADR-005 - Cloud sync as an in-process supervised worker

**Context:** `CloudSyncService` does not exist; S2-13 requires a 24-hour batch export. **Problem:** What technology implements this. **Options considered:** (a) Celery/Redis-backed task queue; (b) an external cron job calling an API; (c) an in-process supervised asyncio task within Central. **Chosen approach:** (c). **Why:** A once-daily batch export of a local dataset does not justify a distributed task queue (Principle 5); an external cron job would need its own access to Central's data store, duplicating the persistence boundary. **Trade-offs:** Tied to Central's process lifecycle - if Central is ever scaled to multiple instances, this needs a leader-election step to avoid duplicate syncs (not currently needed, explicitly deferred). **Migration impact:** Section 19. **Rollback possibility:** High.

### ADR-006 - Video call integration boundary contract

**Context:** Video calling is built by another team; this backend must expose integration points. **Problem:** Where the boundary sits. **Options considered:** (a) NEXI backend owns nothing beyond generic camera access, leaving the video team to build their own resource coordination; (b) NEXI backend owns a first-class CALL_ACTIVE priority state and camera lifecycle hooks. **Chosen approach:** (b). **Why:** The meeting minutes describe call-priority behavior (pausing other activity) that only this backend's resource authority can actually enforce, since it already owns every other camera consumer. **Trade-offs:** Requires this backend to model a call's state even though it does not implement calling itself. **Migration impact:** Section 20. **Rollback possibility:** High - this is additive, not a replacement of existing behavior.

### ADR-007 - Enrollment remains a separate service

**Context:** Section 12/13 of the driving framework asks whether Enrollment unnecessarily duplicates Central. **Problem:** Merge or keep separate. **Options considered:** (a) merge Enrollment into Central; (b) keep it separate. **Chosen approach:** (b). **Why:** The audit finds Enrollment owns a genuinely distinct workflow (multi-step biometric collection), its own encrypted local storage, and its own state machine, with no evidence it duplicates Central's orchestration logic - its problems are contract mismatches with its dependencies (section 13), not a redundant responsibility. **Trade-offs:** None significant; this is a "no change" decision made explicitly rather than by default. **Migration impact:** None. **Rollback possibility:** N/A.

### ADR-008 - Single OpenAPI source of truth

**Context:** `docs/openapi.yaml` describes routes no live app serves (AC-07). **Problem:** How to keep documentation and reality aligned going forward. **Options considered:** (a) hand-maintain the YAML file; (b) generate OpenAPI directly from the chosen authoritative Central app (and each other service's own app) at build/release time. **Chosen approach:** (b). **Why:** Hand-maintained docs are exactly how AC-07 happened in the first place; generated docs cannot drift from the routes that actually exist. **Trade-offs:** Requires each service's route definitions to carry adequate schema/descriptions for generated docs to be useful, which may need incremental improvement. **Migration impact:** Section 21. **Rollback possibility:** High.

## 29. Complete Issue Consolidation

| Root Cause ID | Related PROJECT.md issues | Affected services | Impact | Recommended solution | Priority | Dependencies |
|---|---|---|---|---|---|---|
| RC-01 | NEXI-001, NEXI-002, NEXI-030, AC-01 | Central, every downstream caller | No single orchestration contract exists | ADR-001: extend `v2`, retire or migrate `main` | P0 | Section 8 |
| RC-02 | NEXI-023, NEXI-024, AC-03, AC-04 | LLM, Central, Audio, TTS | Sprint 2's core product requirement (S2-01) is entirely unenforced | ADR-002 + section 16's RAG policy layer | P0 | RC-01, RC-05 (TeachMe) |
| RC-03 | NEXI-003, NEXI-013, NEXI-020 | Central, TeachMe, Enrollment | Silent data loss / lost updates possible on every concurrently-written store | ADR-003: migrate to SQLite | P0 | None (can start immediately) |
| RC-04 | NEXI-005, NEXI-009, S2-07, S2-12 | Central, Vision | Two callers can hold the same camera; priority/lease semantics are metadata-only | ADR-004: single resource authority | P0 | RC-01 (authority needs a home) |
| RC-05 | NEXI-001, NEXI-006, NEXI-016, NEXI-022 | Central, Audio, TeachMe, LLM | Five of seven services cannot start at all | Recover/implement missing modules per service section | P0 | None (must be first) |
| RC-06 | NEXI-008, NEXI-017, NEXI-018, NEXI-021, NEXI-024, NEXI-026, AC-05 | Audio, TeachMe, Enrollment, LLM, shared | Producer/consumer contracts drifted independently across nearly every service boundary | Per-pair contract fixes (sections 9-15), each backed by a contract test | P1 | RC-05 (services must run to test contracts) |
| RC-07 | NEXI-004, NEXI-029 | All services | No authentication/authorization anywhere; biometric and identity data exposed | Section 22 - auth/authz before external exposure | P1 (P0 for biometric-exposing routes specifically) | RC-01 for a single place to add shared auth middleware |
| RC-08 | NEXI-010, NEXI-012, NEXI-019, NEXI-024, NEXI-028 | Vision, LLM, shared, Central | Health/tests/logging misreport success, making every other fix harder to verify | Fix health/test/rate-limiter/logging defects early (section 15, 24) | P0 (verification depends on this) | None |
| RC-09 | NEXI-015, AC-02, AC-03, S2-04, S2-09, S2-10, S2-11 | Vision, Audio, TTS, LLM, Central | Sprint 1 policy incompletely retired at schema/health/internal layers | Per-service cleanup passes (sections 9-14), sequenced after functional fixes | P2 | Functional fixes in the same service first |
| RC-10 | NEXI-025, NEXI-031, AC-07 | Deployment, CI, docs | Deployment artifacts and documentation describe an application that does not match source | ADR-008 + Dockerfile/CI corrections | P2 | RC-01 (docs/deploy target the chosen app) |

## 30. Prioritized Backlog

Priority definitions per the governing framework: P0 (system cannot operate safely / data corruption / catastrophic defect), P1 (Sprint 2 blocker or major integration blocker), P2 (architecture/reliability/security issue that should precede production), P3 (maintainability/refactoring/cleanup), P4 (optimization/future improvement).

| Priority | Item | Root cause | Notes |
|---|---|---|---|
| P0 | Recover/implement all five missing modules blocking service startup (Central sync class, Audio wake-word fallback module, TeachMe services package, LLM format route, environment DEBUG handling) | RC-05 | Nothing else is testable until this is done |
| P0 | Fix health checks and the pytest false-positive pattern (NEXI-010, NEXI-012) | RC-08 | Must happen alongside/immediately after startup fixes so every subsequent fix can be verified honestly |
| P0 | ADR-001: resolve Central authority | RC-01 | Blocks nearly everything else |
| P0 | ADR-003: migrate concurrently-written stores to SQLite | RC-03 | Data-integrity foundation for RAG, sync, and enrollment work |
| P0 | ADR-004: consolidate resource authority | RC-04 | Foundation for TeachMe priority (S2-07) and video-call integration (S2-12) |
| P0 | Fix shared circuit-breaker/rate-limiter/port-map defects | RC-08, RC-06 | Every service depends on this layer |
| P1 | Build the restricted-RAG policy layer (section 16) | RC-02 | The core Sprint 2 product requirement; depends on RC-01, RC-05 (TeachMe running) |
| P1 | Fix TeachMe/Central/Audio/Enrollment/LLM contract mismatches (section 25's contract list) | RC-06 | Needed before any of these services can be trusted end-to-end |
| P1 | Add authentication/authorization to identity, biometric, TeachMe, and resource routes | RC-07 | Required before any deployment beyond a fully trusted local network |
| P1 | Build the cloud sync worker (section 19) | RC-05, related to RC-01 | Also removes Central's startup blocker |
| P1 | Fix camera pause/resume contract (NEXI-009) | RC-04 | Direct prerequisite for video-call integration |
| P2 | Complete emotion/multilingual/multi-voice/offline-LLM cleanup at schema, health, and internal-code layers | RC-09 | Sequenced after the functional fixes in the same services |
| P2 | Build the video-call integration contract (section 20) | RC-04 | Depends on the resource authority and the camera-control fix |
| P2 | Deployment artifact and CI corrections (Dockerfiles, base-image build order) | RC-10 | Needed before any environment beyond local development |
| P2 | Encryption-at-rest expansion beyond Enrollment's current partial coverage | RC-07 (extension) | Before-commercial-production tier per section 22 |
| P3 | Remove confirmed-safe duplicate/legacy code (section 25) | RC-01, RC-06, RC-09 | Only after each replacement is verified working; explicitly sequenced last among functional work |
| P3 | Regenerate OpenAPI from the authoritative app (ADR-008) | RC-10 | After ADR-001 is executed |
| P4 | TTS per-worker model-cache deduplication (three separate Jenny loads) | none blocking | Resource-efficiency optimization, not correctness |
| P4 | Token-usage metric correction (word-count proxy) in the LLM client | none blocking | Improves cost visibility, not required for Sprint 2 completion |

## 31. Dependency Graph

```
FOUNDATION
  Recover missing modules (RC-05)
  Fix health/test integrity (RC-08)
  Fix shared circuit-breaker/rate-limiter/port-map (RC-06/RC-08)
        |
        v
DATA & RESOURCE FOUNDATIONS  (can proceed in parallel with each other)
  ADR-003: SQLite migration (RC-03)  --------\
  ADR-004: resource authority (RC-04) --------+--> both required before contract work below
        |
        v
ORCHESTRATION AUTHORITY
  ADR-001: Central authority resolved (RC-01)
        |
        v
CONTRACT ALIGNMENT (can proceed in parallel per pair, once above is done)
  Central <-> TeachMe (AC-05)
  Audio <-> STT endpoint (NEXI-008)
  Enrollment <-> Vision / Central / Audio (NEXI-021)
  LLM client <-> server (NEXI-024)
        |
        v
RESTRICTED RAG POLICY LAYER
  ADR-002: section 16 built in Central, calling the now-fixed TeachMe
  and LLM contracts
        |
        v
SECURITY HARDENING (auth/authz - can start in parallel with RAG layer
  once ADR-001 gives it a single place to live, but must complete
  before any external-network exposure)
        |
        v
CLOUD SYNC
  ADR-005: sync worker built on the SQLite outbox from the data
  foundation step
        |
        v
VIDEO CALL INTEGRATION
  ADR-006: built on the resource authority + fixed camera contract
        |
        v
SPRINT-1-RESIDUE CLEANUP (RC-09)
  Schema/health/internal-code cleanup per service
        |
        v
API STABILIZATION
  ADR-008: regenerate OpenAPI from the authoritative app
        |
        v
DUPLICATION/DEPENDENCY REMOVAL (section 25/26)
  Only after every replacement above is verified
        |
        v
TESTING COMPLETION (section 24's full matrix)
        |
        v
PRODUCTION HARDENING (section 22's before-commercial tier)
```

Parallelizable work: the SQLite migration and the resource-authority consolidation do not depend on each other and can proceed simultaneously once foundation work is done. Contract-alignment pairs are independent of each other and can be split across engineers. Security hardening can begin as soon as Central's authority is resolved, in parallel with the RAG policy layer, provided both land before any external-network deployment gate.

## 32. Phased Remediation Plan

### PHASE 0 - Protect the baseline
**Objective:** Ensure no further work happens against an unversioned or ambiguous starting point.
**Issues resolved:** None directly; this is a safety phase.
**Affected services:** All.
**Preconditions:** None.
**Tasks:** Tag the current commit as the pre-remediation baseline. Freeze `main.py`/`api_v2.py` as-is (no further ad hoc edits) until ADR-001 is executed deliberately. Snapshot all current JSON/pickle/SQLite data files before any migration work touches them.
**Do NOT touch yet:** Anything - this phase is read-only.
**Tests required:** None new; confirm the existing (flawed) test suite's current pass/fail state is recorded for comparison.
**Acceptance criteria:** A tagged commit exists; a data snapshot exists; no code has changed.
**Rollback strategy:** N/A - this phase creates the rollback point for every later phase.
**Estimated complexity:** Trivial. **Risk:** None.

### PHASE 1 - Resolve blockers (recover missing modules, fix diagnostics)
**Objective:** Get all seven services to actually start, and make the test suite trustworthy enough to verify the rest of this plan.
**Issues resolved:** NEXI-001 (partially - the missing sync class is stubbed/implemented per Phase 7, but the import itself must resolve here to unblock Central), NEXI-006, NEXI-007, NEXI-016, NEXI-022, NEXI-010, NEXI-012, NEXI-019, NEXI-026, NEXI-028.
**Affected services:** Central, Audio, TeachMe, LLM, shared.
**Preconditions:** Phase 0 complete.
**Tasks:** Implement or recover the missing modules (Central's sync class can be a minimal stub in this phase, with the full outbox design deferred to Phase 7 - the goal here is import resolution, not the final feature). Implement Audio's actual direct-voice fallback module (this is new functionality, not a recovery - see Phase 3 for the full S2-03 behavior; a minimal version that at least allows import/startup can land here). Recover TeachMe's `services` package. Add the missing `llm_service.routes.format` module. Fix the environment DEBUG-value handling. Fix Vision's and LLM's health checks to report actual dependency status. Rewrite the false-positive tests to assert on outcomes. Fix the rate limiter's ASGI compliance. Add `llm` to the port map. Fix `ServiceClientFactory`'s keyword mismatch. Fix the logging formatter's trace-ID requirement.
**Do NOT touch yet:** RAG policy logic, resource-authority consolidation, data migration, authentication, cleanup/deletions.
**Tests required:** A startup/import test per service that fails loudly on any missing module. Rerun the full existing test suite and confirm no more false positives of the NEXI-012 pattern remain.
**Acceptance criteria:** All seven services start successfully in the target environment and respond to `/health` with an honest status. The test suite's pass count reflects actual reproduced behavior, not silently-caught errors.
**Rollback strategy:** Revert to the Phase 0 tag; no data migration has occurred yet, so this is a clean code revert.
**Estimated complexity:** High (multiple independent missing-module implementations). **Risk:** Medium - new code (the fallback module, the sync stub) needs its own basic tests even at this stage.

### PHASE 2 - Establish architecture foundations
**Objective:** Put the data and resource ownership model on solid ground before anything is built on top of it.
**Issues resolved:** NEXI-003, NEXI-005, NEXI-009, NEXI-013, NEXI-020 (schema alignment portion).
**Affected services:** Central, TeachMe, Vision, Enrollment.
**Preconditions:** Phase 1 complete (services must start to be tested).
**Tasks:** Execute ADR-003 (SQLite migration for Central users/conversations and TeachMe knowledge), including a migration script from existing JSON and a verified rollback export. Execute ADR-004 (consolidated resource authority), retiring `camera_manager.py` and `hardware_resource_manager.py` in favor of the new implementation, with Vision's local pool converted to a cooperating client. Fix Vision's camera pause/resume response schema (NEXI-009). Fix Enrollment's local-record schema to include what recovery logic expects (NEXI-020), with a migration path for existing records.
**Do NOT touch yet:** RAG policy layer, cloud sync worker (beyond the Phase 1 stub), authentication, video-call contract, cleanup/deletions.
**Tests required:** Concurrent-write test on the new SQLite stores proving no lost updates. Resource-authority test proving a single camera cannot be double-granted and that a cancelled queued request is actually removed. Enrollment crash-recovery test (local-save-then-register ordering) in both failure directions.
**Acceptance criteria:** No JSON-based concurrent-writer store remains for users/conversations/TeachMe knowledge. A single resource authority exists and every camera/microphone consumer goes through it. Enrollment's local record schema matches what its own recovery code reads.
**Rollback strategy:** The Phase 0 data snapshot allows reverting to JSON storage if the SQLite migration reveals an unforeseen issue; the resource-authority change should be feature-flagged during rollout so the old managers can be re-enabled if a hardware-integration issue appears.
**Estimated complexity:** High. **Risk:** Data-integrity risk during migration (mitigated by the Phase 0 snapshot and a verified migration script); hardware-integration risk during resource-authority cutover (mitigated by feature-flagging).

### PHASE 3 - Implement missing Sprint 2 behavior
**Objective:** Build the product-facing Sprint 2 behaviors that do not yet exist in any form.
**Issues resolved:** S2-03 (full behavior, beyond Phase 1's minimal stub), S2-07 (lazy-shift semantics on top of Phase 2's authority), S2-12 (call-priority state, pending Phase 2's fixed camera contract).
**Affected services:** Audio, Central.
**Preconditions:** Phase 2 complete (resource authority must exist before priority/lazy-shift semantics can be built on it).
**Tasks:** Build the actual direct-voice fallback and ~10-second silence-timeout session lifecycle in Audio, replacing Phase 1's minimal stub. Build the TeachMe-priority lazy-shift behavior (a "focus mode" signal other consumers respond to by yielding, per section 18) on top of the consolidated resource authority. Add the CALL_ACTIVE priority state and the acknowledgement/timeout semantics needed for future video-call integration (the actual call-signaling contract itself is Phase 6/section 20, but the underlying priority-state machinery belongs here alongside the rest of the priority hierarchy).
**Do NOT touch yet:** RAG policy layer (Phase 4), cleanup/deletions, authentication (can proceed in parallel per section 31, but is tracked as Phase 5 here for clarity).
**Tests required:** Wake-word-failure integration test with real or simulated microphone input. TeachMe-priority test proving another consumer (for example, a simulated LLM call) actually yields resources during an active TeachMe session, not just receives a logical notification. Call-priority state-transition test.
**Acceptance criteria:** A user can speak directly when wake-word detection fails, and the session ends correctly on silence or manual stop, in a real-device acceptance test. A TeachMe session provably reduces resource contention from other consumers during its active window.
**Rollback strategy:** Each behavior is additive and can be individually disabled via configuration if a real-device test surfaces a problem.
**Estimated complexity:** High (hardware/timing-sensitive). **Risk:** Medium-high - requires physical device acceptance testing, not just unit tests.

### PHASE 4 - Restricted RAG implementation
**Objective:** Implement the core Sprint 2 product requirement.
**Issues resolved:** S2-01, S2-11 (via the same policy boundary), NEXI-017, NEXI-018 (as part of fixing the Central-TeachMe contract this phase depends on), NEXI-023.
**Affected services:** Central, TeachMe, LLM.
**Preconditions:** Phase 2 complete (TeachMe running on the fixed data layer); ADR-001 executed (a single Central to build this in); the approved 10-15 item basic-command list obtained from product.
**Tasks:** Fix the Central-TeachMe contract (payload shape and embedding dimension, per AC-05 - this includes selecting one real semantic embedding model and re-embedding existing TeachMe entries, which is a data migration in its own right). Build the intent classifier, teach-first fallback, server-side prompt construction, and output-grounding validation described in section 16. Remove the `system_prompt` field from the LLM service's public request schema. Enforce English-only at this boundary. Fix the LLM client/server response-shape mismatch (NEXI-024) and remove the fallback-as-success behavior.
**Do NOT touch yet:** Deletion of `prompt_builder.py`/`system_prompts.py` (defer to Phase 10, once this replacement is proven in production-like testing, not merely passing tests).
**Tests required:** The full Sprint 2 behavior test list from section 24 relating to RAG: known-fact grounding, unknown-question teach-me fallback with a call-count assertion proving the LLM was never invoked, adversarial open-domain rejection, non-English rejection.
**Acceptance criteria:** Matches section 34's RAG-specific acceptance criteria exactly (see below).
**Rollback strategy:** Feature-flag the policy layer so Audio/Central can temporarily route around it back to the pre-Phase-4 LLM contract if a severe regression appears - this flag should be removed once Phase 4 is confirmed stable in Phase 8's acceptance testing, not left permanently.
**Estimated complexity:** High. **Risk:** High - this is the highest-value and highest-visibility change in the entire plan; treat its acceptance testing as the primary gate for calling Sprint 2 "done."

### PHASE 5 - Security hardening (identity, authorization, immediate-tier fixes)
**Objective:** Close the access-control gap before any deployment beyond a fully trusted local network.
**Issues resolved:** NEXI-004, NEXI-029, NEXI-019 (already fixed in Phase 1, verified here under load), NEXI-032, NEXI-033.
**Affected services:** All.
**Preconditions:** ADR-001 executed (one place to add shared auth middleware).
**Tasks:** Add authentication and per-resource authorization to every route touching identity, biometric data, conversation history, TeachMe data, and resource/camera control. Wire TeachMe's existing but unwired authentication helpers to its actual data routes, and fix the fail-open JWT bypass. Replace wildcard-plus-credentials CORS with an explicit per-environment allowed-origin list on every service. Add request-size/content-type validation before body reads. Validate/sanitize any server-side file path accepted from a request body. Migrate Audio's speaker store off `pickle`.
**Do NOT touch yet:** Full encryption-at-rest expansion (Phase 9, before-commercial tier); TLS (Phase 9).
**Tests required:** Authorization test suite proving an unauthenticated or wrongly-scoped request is rejected on every previously-open route. CORS configuration test per environment. A targeted deserialization-safety test for the migrated speaker-store format.
**Acceptance criteria:** No route touching identity, biometric, conversation, TeachMe, or resource data is reachable without authentication in the target deployment environment.
**Rollback strategy:** Roll out auth per-service behind a configuration flag during an internal soak period before requiring it universally, to avoid locking out legitimate internal tooling mid-migration.
**Estimated complexity:** Medium-high (breadth, not depth). **Risk:** Medium - primary risk is breaking an internal tool or test harness that assumed no auth; mitigated by the soak-period rollout.

### PHASE 6 - API stabilization
**Objective:** Give frontend/mobile/video teams one stable, documented contract.
**Issues resolved:** AC-01 (final resolution), AC-07, section 21's error-envelope and versioning inconsistencies, NEXI-021 (identity-field alignment).
**Affected services:** All, primarily Central.
**Preconditions:** Phases 1-5 complete (the contract being stabilized must already be functionally correct).
**Tasks:** Execute the section 21 breaking-change migration (single Central app, documented and versioned). Standardize the error envelope across all services via the shared library. Fix Enrollment's `user_id`/`name` conflation. Fix Central's registration-response `user_id` omission. Build the video-call integration contract (section 20), now that the underlying camera and resource fixes from Phases 2-3 are in place.
**Do NOT touch yet:** Cleanup/deletions (Phase 10).
**Tests required:** Contract tests for every public route on the stabilized API. A frontend/mobile-facing integration smoke test against the final contract.
**Acceptance criteria:** Exactly one documented Central API exists; every service uses one shared error envelope; the video-call contract is published and independently testable by the video team against a mock or the real backend.
**Rollback strategy:** Maintain the pre-Phase-6 routes for one migration window per section 21's migration plan before fully retiring them.
**Estimated complexity:** Medium. **Risk:** Medium - primarily coordination risk with external teams, not technical risk.

### PHASE 7 - Persistence/sync completion
**Objective:** Implement the full cloud-sync design, replacing Phase 1's minimal stub.
**Issues resolved:** S2-13 in full, S2-05, S2-06 (final data-separation guarantee).
**Affected services:** Central.
**Preconditions:** Phase 2's SQLite migration complete (the outbox pattern is built on it); Phase 6's stable API (the sync-status read endpoint is published through it).
**Tasks:** Implement the full outbox schema, supervised scheduler, idempotent batch acknowledgement, and bounded retry described in section 19. Implement the schema-enforced exportable-fields projection with a static-analysis check confirming no import path from the sync module reaches TeachMe or the users table.
**Do NOT touch yet:** Cleanup/deletions.
**Tests required:** Sync-worker test against a controlled local test receiver, including a forced-restart scenario and a duplicate-batch-id idempotency scenario. Static-analysis test confirming the TeachMe-exclusion import-graph guarantee.
**Acceptance criteria:** Matches section 34's sync-specific acceptance criteria.
**Rollback strategy:** The sync worker can be disabled via configuration without affecting any other Central functionality, since it is an independent scheduled task.
**Estimated complexity:** Medium. **Risk:** Medium - the idempotency contract depends on an external cloud receiver's behavior, which this plan cannot fully control; document the assumed contract explicitly and validate against the real receiver as early as possible.

### PHASE 8 - Testing and failure verification
**Objective:** Build out the full test matrix from section 24 and section 35 across everything the previous phases changed.
**Issues resolved:** Residual verification gaps across all previous phases.
**Affected services:** All.
**Preconditions:** Phases 1-7 complete.
**Tasks:** Implement the complete regression test matrix (section 35). Run failure/resilience tests: forced process kill and restart per service, network failure during sync, resource-authority behavior under simulated crash of a lease-holder.
**Do NOT touch yet:** Cleanup/deletions (this phase verifies correctness before Phase 10 removes anything).
**Tests required:** All of section 35.
**Acceptance criteria:** Every row in section 35 passes.
**Rollback strategy:** N/A - this phase does not change production code, only adds tests; any failure found here routes back to the relevant earlier phase for a fix.
**Estimated complexity:** High (breadth). **Risk:** Low to the system itself; this phase's purpose is finding remaining risk, not introducing it.

### PHASE 9 - Security/observability hardening (before-external and before-commercial tiers)
**Objective:** Close the remaining security and observability gaps beyond Phase 5's immediate tier.
**Issues resolved:** TLS absence, encryption-at-rest gaps, credential-rotation policy, log redaction, dependency-vulnerability scanning, structured latency/correlation-ID observability (section 23).
**Affected services:** All.
**Preconditions:** Phase 5 (immediate-tier security) and Phase 6 (stable API) complete.
**Tasks:** Add TLS termination in front of all services. Expand encryption-at-rest to Central's user store and Audio's speaker store, matching Enrollment's existing (already partial) coverage. Define and implement a credential-rotation policy for the Fernet key and the OpenRouter API key. Add log redaction for transcription/biometric/credential fields. Integrate a dependency-vulnerability scan into CI. Add correlation-ID propagation and per-route latency logging via the shared library.
**Do NOT touch yet:** Cleanup/deletions (Phase 10).
**Tests required:** TLS configuration test per service. Encryption-at-rest verification (data files are not plaintext-readable). A log-redaction test confirming sensitive fields never appear in plain log output.
**Acceptance criteria:** Matches section 36's before-external and before-commercial deployment gates.
**Rollback strategy:** TLS and encryption can be rolled out per-service with a fallback plaintext mode during a migration window, removed once all clients are confirmed updated.
**Estimated complexity:** Medium-high. **Risk:** Low-medium - mostly additive controls, with the main risk being a misconfigured TLS/encryption rollout locking out legitimate traffic during migration.

### PHASE 10 - Final cleanup and release validation
**Objective:** Remove everything identified as safe-to-remove now that its replacement is proven, and perform final release validation.
**Issues resolved:** S2-08 (in full - this is deliberately the last phase, not the first, per this plan's ordering rationale), the remaining RC-09 schema/health/dependency cleanup, RC-10's deployment-artifact corrections.
**Affected services:** All.
**Preconditions:** Phases 1-9 complete and Phase 8's full test matrix passing.
**Tasks:** Execute section 25's duplication/redundancy table and section 26's dependency-cleanup table, in the dependency order given there. Remove Sprint-1-residue schema fields (emotion, unrestricted language options, non-Jenny voice internals) confirmed unreferenced. Fix Dockerfiles, CI build order, and regenerate OpenAPI from the final authoritative app (ADR-008).
**Do NOT touch yet:** Nothing remains gated after this phase; this is the terminal cleanup step.
**Tests required:** Full regression suite (section 35) rerun after every deletion batch, not just once at the end. A final import-graph/reference-search confirming zero remaining callers for everything removed.
**Acceptance criteria:** Section 36's final deployment gate is met.
**Rollback strategy:** Each deletion batch is its own commit; any regression found by the rerun test suite is reverted at the batch level, not the whole phase.
**Estimated complexity:** Medium. **Risk:** Low, provided the "verify before delete" discipline from every earlier phase was actually followed - this is the phase where insufficient earlier verification would surface as a regression.

## 33. Safe Cleanup Plan

### SAFE TO REMOVE NOW
None. Every candidate identified in the audit has at least one unresolved "confirm zero callers" or "confirm replacement works" precondition. This plan deliberately places zero items in this category to avoid the single most common cause of avoidable regressions in a project at this stage of instability - removing something before its replacement is proven, per Principle 3.

### REMOVE AFTER <DEPENDENCY>

| Path/component | Why it exists | Why removal is considered | Known references | Prerequisite | Regression risk | Validation after deletion |
|---|---|---|---|---|---|---|
| `Central/routes/llm_routes.py` factory | Alternate LLM-routing factory | No call site found | None discovered | Repository-wide reference search at execution time | Low | Full Central test suite passes; LLM calls still function via the actually-mounted path |
| Whichever Central app loses ADR-001 | Historical parallel implementation | Superseded by ADR-001's chosen/merged app | Depends on which clients still point at it | ADR-001 executed and migration window (section 21) elapsed | High if removed early; low after the migration window | All frontend/mobile/CLI clients confirmed repointed |
| `Audio/api.py`, `embedding_extractor.py` | Legacy unmounted embedding API | Unreachable via `main`, broken relative imports | None discovered as external caller | Reference search confirming no external tooling imports this module directly | Low | Speaker verification still functions via the mounted path |
| `Audio/managers/conversation_state_manager.py` | Superseded conversation-state implementation | `services/conversation_state.py` is the one `main` imports | None discovered | Reference search | Low | Conversation flow tests pass |
| TTS internal Urdu/Ryan/Shahid branches in `EngineManager`/cache | Sprint 1 multi-voice/multilingual support | Public registry is already Jenny-only | Internal only; public `resolve_voice` is unaffected | Confirm no internal code path reaches these branches other than the ones being removed | Low-medium | Jenny synthesis still functions; `/speakers/switch` to any other voice still rejected |
| `LLM/prompt_builder.py`, `system_prompts.py` | Sprint 1 general-knowledge-encouraging prompt logic | Actively contrary to S2-01; unreferenced by the live route | None discovered | Section 16's RAG policy layer live and verified | Low (already unreferenced) but treat as an S2-01 regression check regardless | Adversarial open-domain test still blocks correctly after removal |
| `shared/quantized_llm.py`, `quick_start.py` SmolLM setup | Sprint 1 offline-LLM fallback | S2-02 requires a single online LLM | None discovered in the live app | AC-04 scope ruling confirms this is in scope for removal (this plan's default assumption) | Low | LLM service functions identically without it |
| `Enrollment/enrollment_service_enhanced.py` | Alternate, possibly more complete implementation | Router mounts the standard version only | Unknown - requires feature-parity comparison, not just a reference search | Feature-parity check; merge any fixes found before deleting | Medium (may contain fixes not yet in the mounted version) | Full enrollment workflow test suite passes |
| `Enrollment/app/storage/enrollment_storage.py` | Second storage class alongside `StorageAdapter`'s choices | Redundant with the adapter pattern | Requires reference search | Confirm zero direct callers outside the adapter | Low | Enrollment persistence tests pass |
| Duplicate shared circuit-breaker/retry-handler modules | Parallel implementations of the same concern | One is chosen as authoritative per section 15 | All current callers of the non-chosen one | Every caller migrated to the chosen interface | Medium (breadth of callers) | Shared-layer contract test suite (section 15) passes |
| Vision's unused queue modules | Unclear original intent, not initialized by the current lifespan | No current consumer | None discovered | Reference search including test/doc references to old unprefixed routes | Low | Vision detection tests pass |
| Stale FER/emotion dependency-manifest entries | Sprint 1 emotion detection | S2-04 | Must not overlap with DeepFace's own TensorFlow/Keras requirement | Confirm the specific package is not shared with DeepFace's dependency chain | Medium if confused with a shared dependency | Face recognition still functions after removal |

### KEEP

DeepFace, YOLOv8, and their full dependency chains (explicitly required for retained recognition/object-teaching capability, regardless of the AC-04 outcome). Piper, Porcupine, Whisper/Groq as local speech components (pending the AC-04 scope decision, but this plan's working assumption keeps them - see ADR context in section 1). `safe_file_lock.py`. The base HTTP client abstraction in `shared/clients/base_client.py` (once consolidated to one circuit-breaker interface, not removed). Enrollment's Fernet encryption implementation. The root `service/rag_orchestrator.py`/`llm_context_builder.py` design-reference harness (kept separate from production, per section 25, not deleted).

### HUMAN DECISION REQUIRED

| Item | Why it needs a human decision |
|---|---|
| Scope of "remove offline functionality" (AC-04) | Determines whether Whisper/Piper/Porcupine/DeepFace/YOLO are in scope at all; this plan defaults to "offline-LLM only" but explicitly flags this as requiring product confirmation before Phase 10 executes any removal touching these components |
| Video-call vs. active-TeachMe priority ordering (section 18.3) | The meeting minutes' literal reading places video calls above TeachMe; confirm this is the intended real-world UX before implementing preemption in Phase 3 |
| Credential-rotation policy (section 17, section 22) | No policy currently exists for the Fernet key or the OpenRouter API key; this is a security-operations decision, not an engineering one |
| Data-retention policy for users/conversations (section 17) | "Indefinite" is the current de facto state; a real retention period is a product/legal decision |
| Cloud receiver's idempotency contract (section 19) | This plan assumes a `batch_id`-based acknowledgement contract exists or can be built with whatever the cloud receiver is; that receiver is outside this repository's scope and its actual contract must be confirmed |

## 34. Acceptance Criteria

Each criterion below is written to be objectively testable, per the framework's "bad: improve RAG / good: measurable" instruction.

- **S2-01 (restricted RAG):** Given a question absent from TeachMe and not matching any entry in the approved basic-command list, the response must not contain a factual answer sourced from the LLM's pretrained knowledge, and must return the configured teach-me prompt, in 100% of a defined adversarial test set (minimum 20 cases spanning direct questions, rephrased questions, and questions disguised as commands). A mocked-LLM call-count assertion confirms the LLM is never invoked on the no-match path.
- **S2-02 (single LLM):** No source file outside version-control history imports or instantiates `shared/quantized_llm.py` or any other local-inference loader; the dependency manifest contains no local-inference-only package; the LLM service starts and serves exclusively via the OpenRouter client.
- **S2-03 (wake-word fallback):** On a simulated or forced Porcupine API failure, a direct spoken query without a wake word is accepted and processed in 100% of a defined test set (minimum 10 trials); the session terminates within a defined tolerance (for example, 10 seconds plus at most 1 second of measured system latency) of continuous silence, and terminates immediately on a manual stop signal in 100% of trials.
- **S2-04 (emotion removal):** No live HTTP response schema, from any of the seven services, contains an emotion or mood field, verified by a schema-diff check against every service's generated OpenAPI output. Face recognition accuracy on a fixed benchmark set is unchanged from its pre-removal baseline (proving recognition was not accidentally degraded while removing emotion).
- **S2-05/S2-06 (data collection and segregation):** A generated conversation record is durably retrievable after a forced process restart in 100% of a defined write-then-restart-then-read test set (minimum 20 writes). No TeachMe write ever appears in the conversations table/store and no conversation write ever appears in the TeachMe store, verified by a schema/table-level check, not a filtering convention.
- **S2-07 (TeachMe priority):** During an active TeachMe session in a defined test scenario, a concurrent request from another consumer for the same resource is measurably delayed or rejected until the TeachMe session yields or completes, verified by a timing assertion, not just a logged intent.
- **S2-08 (cleanup):** Zero files remain in the categories listed as REMOVE in section 33 after Phase 10, verified by their absence in the repository tree; the full regression suite (section 35) passes at 100% both immediately before and immediately after the cleanup commit.
- **S2-09 (offline removal, scoped per AC-04's resolution):** No source file imports the local-LLM loader (see S2-02's criterion); if AC-04 is resolved to include local perception/speech models, an equivalent zero-reference criterion applies to each named component individually.
- **S2-10 (Jenny-only):** A request to `/speakers/switch` with any voice other than Jenny is rejected with a defined error code in 100% of a defined test set covering every previously-available voice name; synthesis via `/speak` with no voice parameter produces audio using Jenny's model in 100% of trials.
- **S2-11 (English-only):** A request with `language` set to any non-English value, at any of the three previously-accepting layers (Audio config, TTS, LLM), is rejected with a defined error at the centralized policy boundary in 100% of a defined test set.
- **S2-12 (video-call integration):** A simulated incoming-call signal results in the camera being released by its current holder (verified by an actual hardware-handle-closed check, not just a logical flag) and reacquired at CALL_ACTIVE priority within a defined time bound, in 100% of a defined test set; `/camera/pause` and `/camera/resume` return the correct schema and status code in 100% of calls.
- **S2-13 (cloud sync):** A conversation record marked unsynced is included in the next scheduled batch and marked synced only after a receiver acknowledgement is received; a batch retried with the same `batch_id` produces no duplicate record on the receiver side, verified against a controlled test receiver in a defined test set (minimum 10 batches including at least 2 forced-retry cases).

## 35. Regression Test Matrix

| Area | Test | Trigger | Expected result |
|---|---|---|---|
| Service startup | All-service startup smoke test | Cold start of all seven services | Every service reaches ready state; no missing-import failures |
| Health integrity | Health-vs-capability test | Force a dependency/model-load failure per service | `/health` reports unhealthy/degraded, not a false positive |
| RAG - known fact | Grounded-answer test | Query matching an existing TeachMe entry | Response derived from the retrieved fact; LLM called exactly once with a server-built prompt |
| RAG - unknown | Teach-me fallback test | Query with no TeachMe match | Configured teach-me response; LLM call count is zero |
| RAG - adversarial | Open-domain-disguised-as-command test | Open-domain query phrased to resemble an approved command | Rejected/routed to teach-me fallback, not answered from pretrained knowledge |
| RAG - language | Non-English rejection test | Query in a non-English language | Rejected at the policy boundary with a defined error |
| Wake word | Direct-voice fallback test | Simulated Porcupine failure, spoken query without wake word | Query accepted and processed |
| Wake word | Silence-timeout test | Silence following a fallback-triggered session | Session ends within the defined tolerance |
| Wake word | Manual-stop test | Manual stop signal mid-session | Session ends immediately |
| Emotion | Schema-absence test | Generated OpenAPI diff across all services | No emotion/mood field present anywhere |
| TTS | Jenny-only enforcement test | Request for a non-Jenny voice | Rejected with a defined error |
| Persistence | Concurrent-write test | Simultaneous writes to the same conversation/user/TeachMe record | No lost update; both writes durably reflected or a defined conflict-resolution outcome occurs |
| Persistence | Restart-durability test | Forced process restart after a write | Data present and correct after restart |
| Resource authority | Double-grant prevention test | Two simultaneous camera requests | Exactly one holder at a time |
| Resource authority | Priority-preemption test | Higher-priority request during a lower-priority hold | Lower-priority holder's hardware handle is actually released, confirmed at the hardware level |
| Resource authority | Queue-cancellation test | Cancel a queued resource request | Request is removed from the queue, not merely flagged |
| Cloud sync | Batch-idempotency test | Retry a batch with the same `batch_id` | No duplicate record on the receiver |
| Cloud sync | TeachMe-exclusion test | Static import-graph analysis of the sync module | No import path reaches TeachMe or the users table |
| Cloud sync | Restart-scheduling test | Force a restart mid-interval | Next sync scheduled from the last success time, not restarted from zero or double-fired |
| Enrollment | Crash-recovery test (local-save-first) | Forced failure between local save and Central registration | Recovery behavior is well-defined and does not silently lose the local record |
| Enrollment | Crash-recovery test (registration-first, if ordering differs after the fix) | Forced failure between Central registration and local save | Recovery behavior is well-defined and does not leave an orphaned Central identity |
| Video call | Camera-preemption test | Simulated incoming call during active conversation/TeachMe | Camera released and reacquired at CALL_ACTIVE priority within the defined bound |
| Security | Unauthenticated-access test | Request to any identity/biometric/TeachMe/resource route without credentials | Rejected |
| Security | CORS test | Cross-origin request from a non-allowlisted origin | Rejected |
| Process resilience | Forced-kill-and-restart test | SIGKILL to each service process | Service restarts and reaches ready state without manual intervention |
| Service failure | Downstream-unavailable test | Each service's primary dependency made unavailable | Documented fallback behavior occurs (teach-me fallback for TeachMe-down, text-only for TTS-down, etc.), not an unhandled exception |

## 36. Deployment Gates

| Gate | Required before | Criteria |
|---|---|---|
| Internal development gate | Any shared internal testing beyond the original author's machine | Phase 1 complete: all seven services start; health checks are honest |
| Sprint 2 functional gate | Declaring Sprint 2 "feature complete" | Phases 1-4 complete: section 6's requirement table shows no requirement below PARTIAL, and S2-01/S2-03/S2-13 specifically reach a testable, non-BROKEN state |
| Internal-network deployment gate | Deploying to a shared internal network beyond individual developer machines | Phase 5 complete: authentication/authorization on all identity/biometric/TeachMe/resource routes; ASGI-valid rate limiting; no pickle-based biometric deserialization |
| External-network deployment gate | Exposing any service beyond a trusted internal network | Phase 9's before-external tier complete: TLS on all services; explicit CORS allowlists; validated input handling on all upload/path-accepting routes |
| Frontend/mobile/video integration gate | Other teams beginning integration work against this backend | Phase 6 complete: one authoritative, documented, versioned API; published video-call contract |
| Commercial production gate | Any commercial/public launch | Phase 9's before-commercial tier complete: full encryption-at-rest, credential-rotation policy in force, log redaction, dependency-vulnerability scanning in CI |
| Final release gate | Calling this remediation plan complete | Phase 10 complete: section 35's full regression matrix passing at 100%; zero items remaining in section 33's REMOVE-AFTER category with unmet prerequisites; every HUMAN DECISION REQUIRED item in section 33 explicitly resolved by a product/security owner, not defaulted |

## 37. Engineering Scorecard

Current scores are carried forward consistent with PROJECT.md's own evidence-based scoring (this plan does not re-litigate scores the audit already grounded in reproduced evidence, per Principle 1 - inventing a different current score would itself be an unsupported claim). Expected-after-remediation scores are this plan's own projection, deliberately conservative and tied to specific phases above rather than assuming a perfect outcome.

| Dimension | Current | Expected after remediation | Tied to phase(s) |
|---|---|---|---|
| Functional correctness | 1/10 | 7/10 | 1-4, 8 |
| Sprint 2 completion | 1/10 | 8/10 | 3, 4, 10 |
| Architecture | 3/10 | 7/10 | 2, 4, 6 |
| Modularity | 4/10 | 7/10 | 6, 10 |
| Scalability | 3/10 | 6/10 | 2, 7 |
| Maintainability | 3/10 | 7/10 | 6, 10 |
| Readability | 4/10 | 7/10 | 10 |
| Reliability | 2/10 | 7/10 | 1, 2, 8 |
| Fault tolerance | 2/10 | 7/10 | 2, 3, 8 |
| Security | 1/10 | 7/10 | 5, 9 |
| Data integrity | 2/10 | 8/10 | 2 |
| Performance | 4/10 | 6/10 | 7 (partial; not a primary focus of this plan) |
| Resource efficiency | 3/10 | 6/10 | 2, 3 |
| Testing | 1/10 | 7/10 | 1, 8 |
| Observability | 2/10 | 6/10 | 1, 9 |
| API design | 2/10 | 7/10 | 6 |
| Frontend/mobile integration readiness | 1/10 | 7/10 | 6, 20 |
| Deployment readiness | 1/10 | 6/10 | 9 |
| Repository cleanliness | 3/10 | 8/10 | 10 |
| **Overall (mean)** | **2.3/10** | **~6.9/10** | |

No dimension is projected above 8/10; this plan does not claim remediation produces a perfect system, consistent with Principle 5's instruction against overengineering and against inflated scoring. Performance and resource efficiency are projected more conservatively than other dimensions because this plan's scope is correctness, security, and Sprint 2 completion first - deeper performance optimization (per-worker model deduplication, token-metric accuracy) is explicitly P4 and deferred beyond this plan's phases.

## 38. Final Verdict

The NEXI backend, as audited, is not a system with Sprint 2 gaps to close - it is a system where five of seven services cannot start, the two competing orchestration applications describe two different products, and the one Sprint 2 requirement that defines the entire sprint's purpose (restricted, TeachMe-grounded responses) has no enforcement anywhere in the code that runs. Every one of the thirteen Sprint 2 requirements remains PARTIAL, CONFLICTING, or BROKEN. This is consistent with, not contradictory to, the audit's own 2.3/10 NOT READY verdict.

This plan does not treat that verdict as a reason to rush. It treats it as a reason to sequence carefully: recover what cannot start before fixing what runs incorrectly; establish durable data and single-authority resource control before building policy on top of them; build the restricted-RAG policy layer once, in one place, rather than patching language/voice/knowledge restrictions independently in three services; and defer every deletion until its replacement is proven, because a codebase already this unstable cannot absorb premature cleanup without new regressions indistinguishable from the ones already documented.

Ten phases, in the dependency order given in section 31 and detailed in section 32, take the system from its current 2.3/10 state to a projected ~6.9/10: a single authoritative, authenticated, documented backend; a TeachMe-grounded response pipeline that cannot be talked out of its restriction by rephrasing; one resource authority that a video-calling team can integrate against without inheriting three competing camera managers; and a data architecture where "TeachMe stays local" is a property the code enforces, not a convention it happens to follow today.

No code has been modified in the production of this document, per the operating constraint for this phase. The next decision is yours: confirm ADR-001 (Central authority) and the AC-04 scope ruling (offline-functionality boundary) first, since nearly every phase in section 32 depends on one or both, and then this plan is ready to execute starting at Phase 0.

