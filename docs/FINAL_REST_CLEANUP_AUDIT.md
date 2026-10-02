# REST architecture and cleanup acceptance — 2026-10-02

This pass changes upload cleanup only and removes unreachable code. No model,
threshold, route, authentication, storage schema, or recognition policy changes.

## Artifact classification

| Material | Classification / disposition |
| --- | --- |
| YOLO `02_vision_service/yolov8n.pt`, Facenet under `02_vision_service/models/.deepface/weights`, pinned ResNet18 weights | PRODUCTION REQUIRED; preserved |
| Service venvs, packaged Resemblyzer `pretrained.pt`, provisioned semantic model cache | PRODUCTION REQUIRED; preserved |
| Existing Central/TeachMe SQLite stores, encrypted enrollment/speaker stores, keys, configuration and runtime queue | PRODUCTION REQUIRED or UNKNOWN—KEEP; never migrated/deleted for this audit |
| Existing VAD recording under Audio's configured recordings directory | Intentional recording feature / real media; preserved, not treated as an orphaned REST upload |
| `04_tts_service/voices/*.wav` | PRODUCTION REQUIRED prerecorded playback assets; preserved |
| `tests/fixtures/rag_retrieval_hometown_eval.json`, OpenAPI JSON | TEST REQUIRED / DOCUMENTATION REQUIRED; preserved |
| `scripts/diagnose_enrollment_faces.py`, `shared/face_diagnostics.py`, associated tests and documentation | DIAGNOSTIC REQUIRED / PRODUCTION REQUIRED / TEST REQUIRED; preserved |
| Other documented audit, sync, migration and diagnostic scripts | Intentional utilities; not deleted based on their names |
| Old face-validation runs, photos, failed frames, microphone WAVs, manifests/reports, downloaded face example, camera example, TTS hardware-test WAV, historical runtime/regression logs under `logs/` | TEMPORARY / SAFE TO REMOVE after this acceptance; not permanent test fixtures |
| Prior `nexi-manual-session-services-625873b1b6e245de808518f09f59d040` temp directory | Inspected: generated service logs only; TEMPORARY / SAFE TO REMOVE |
| This pass's `_rest_cleanup_acceptance.py`, isolated service databases and logs | TEMPORARY; helper and all disposable state removed after testing |
| Alternate unmounted speaker/API modules mentioned by archived documentation | UNKNOWN—KEEP until retirement/public-client compatibility is established |

The initial Git status and diff were empty. There were no initial untracked files.
No LibriSpeech/COIL archives or temporary dataset directories were present in the
application tree inspected (virtual environments and required model assets excluded).
Read-only inspection found one real Central user and no benchmark-prefixed users.

## Active responsibility boundaries

| Responsibility | Authoritative implementation / REST contract |
| --- | --- |
| Face validation | Enrollment `PhotoValidation.get_face_embedding` → authenticated Vision `POST /api/v1/detect/faces/upload` → `_process_faces` / `process_face` |
| Early/final enrollment reuse | Enrollment `/enrollment/validate-photo`, `process_enrollment`, `improve_training`, `update_model` all call the same `PhotoValidation` |
| Object detection / P3 | Vision `_process_objects` → `ObjectDetector.detect`; `/api/v1/detect/objects/upload` retains independent per-box vectors |
| Instance embedding | Vision `ObjectInstanceEncoder.encode`; `/api/v1/detect/objects/signature/upload` uses the selected ROI and same encoder |
| Speaker generation | Audio `SpeakerService.generate_embedding`: shared Resemblyzer `preprocess_wav`, mono, 16 kHz; both `/api/v1/process-voice` and `/api/v1/verify-speaker` use it |
| Voice validation / legacy normalization / cosine | `shared/speaker_embeddings.py`; no resizing, padding or fabricated vectors |
| Sync / candidate construction | Audio `/api/v1/speaker-sync` → Central `/users/list` → `build_candidate_index` → normalized centroid → `replace_speaker_index` |
| Speaker decision | `identify_speaker` → `identify_embedding` → score every candidate → global ranking → threshold and margin; ties cannot authenticate a user |
| Visual teaching | Vision selected observation → Central `/teachme/learn` → TeachMe `/learn` → `ObjectProcessor.process_object_async` → `KnowledgeBase.learn_object` |
| Visual comparison | TeachMe `/knowledge/objects/recognize` → `KnowledgeBase.recognize_visual`, matching model/version-specific persisted prototypes |
| Semantic comparison | `generate_embedding` / shared `embed_text` → persisted `KnowledgeItem.embedding` → `_rebuild_embedding_index` → `search_by_embedding` / `EmbeddingIndex.search` |

`test.py` was inspected including its AST/imports and dynamic-call sites. It has
no Vision/Audio/TeachMe inference imports, SQLite access, model imports, candidate
mutation, or embedding generation. Its camera/microphone capture and request
orchestration are client responsibilities. HTTPS uses the configured CA and
documented internal service header; no `verify=False` was introduced.

## Live HTTPS evidence

Real service-local venvs ran Central, Vision, Audio, TeachMe and Enrollment against
isolated stores. Certificates and the normal configured token path were used.
No acceptance inference or biometric persistence was performed via Python imports.
Empty temporary schemas were initialized before service startup; user/knowledge
records were created and removed exclusively through REST.

- Vision: genuine face produces a finite nonzero vector, <128D dimension verified>.
  Blank image returns zero faces and no embedding, not a whole-frame fake face.
- Enrollment: exact image bytes under a different filename reuse validation
  without another Vision request; temporary upload directory empties after success
  and failed decoding.
- Vision: a disposable side-by-side fixture containing two copies of a real
  photo returns two distinct same-class boxes;
  <64D P3 dimension verified> and <512D instance dimension verified> for each.
  Selected-ROI signature also passes finite/nonzero validation.
- Central → TeachMe: the selected observation is transported intact. Stored P3
  and instance vectors equal the original Vision vectors exactly. Semantic
  <384D dimension verified> is a separate field, never resized/mixed into visual
  space. Supplied observations bypass another camera observation.
- Audio: three real microphone utterances produce <256D dimension verified>.
  Central stores all three in `voice_embeddings: list[list[float]]`.
  Sync reports `users_seen=1`, `users_with_voice_data=1`, `users_loaded=1`,
  `users_skipped=0`. A distinct fourth utterance matches the synchronized user
  with cosine similarity **0.9095**. This compact contract check is not an
  independent multi-speaker accuracy/calibration benchmark.
- Central, Audio and TeachMe restart: canonical user samples reload unchanged;
  speaker identification, instance recognition, and semantic retrieval against
  the persisted item succeed without re-enrollment or re-teaching.
- Missing and invalid credentials are rejected on protected Vision, Audio and
  TeachMe endpoints. API deletion uses the required trusted-user context.
- After REST deletion, sync loads zero speakers, the query returns unknown with
  no identity token, and TeachMe has zero test objects. Original persistent-file
  checksums remain unchanged.

## Proven cleanup defects corrected

1. Three Enrollment workflows cleaned ordinary exceptions but not cancellation.
   Reproductions left ten files behind each. The existing cleanup now runs once
   in `finally`, including `CancelledError`; original exceptions still propagate.
2. Enrollment's upload writer left a partial file when disk writing failed before
   returning its path. A failed-write reproduction proved this; writer-level
   `finally` now removes incomplete output.
3. Audio upload read failures/cancellation left `mkstemp` descriptors open, so
   Windows rejected deletion with `WinError 32`. Reproduced in process-voice,
   verify-speaker and transcribe. `os.fdopen` context managers now close handles
   before the existing cleanup, without changing inference or successful payloads.
4. Removed two unreachable duplicate blocks in `advanced_routes.py`: old sync
   below an unconditional delegating return, and old embedding extraction below
   the current response return. Compatibility wrapper and all mounted routes stay.

Vision upload inference uses decoded memory, not a service-created photo file;
FastAPI/Starlette owns and closes multipart spooled uploads. Audio request WAVs
are removed in `finally`. Face diagnostics remain opt-in under ignored
`logs/face-validation`; enrollment console captures use a temporary directory by
default. Intentional encrypted embeddings and explicit VAD recordings are not
temporary-upload leaks. The face cache stays version+content-hash keyed, bounded
to configured entries/TTL, in memory, with no raw images or vector logging.

No dependencies were removed: an absent direct import does not prove absence of
transitive, optional hardware, migration or documented workflow requirements.
No production models, credentials, real users or application databases were deleted.

## Final regression and cleanup

The same protected command was run after live acceptance:

```powershell
& .\venv\Scripts\python.exe -m pytest -q --deselect=tests/test_phase4.py::test_retrieval_labeled_hometown_evaluation_with_real_embeddings
```

Result: **149 passed, 0 failed, 0 skipped, 1 existing hometown deselection**,
226.98 seconds. The new cleanup reproductions failed before their fixes and now
pass. No regression detected in the protected suite; this does not assert
coverage of excluded interactive/hardware or design-reference tests.

Removed 146 inventoried disposable files under `logs/`, 14 old temporary service
logs, the interrupted preflight's 11 generated runtime files, and the acceptance
helper. Successful acceptance runtimes were removed by their temporary-directory
cleanup. No benchmark users or taught objects remain, and no acceptance-owned
service listeners remain. Files were permanently deleted, not moved to trash.
Required reference utilities remain, but their private reference media is gone;
future diagnostic reruns require explicitly supplied/captured photos.

Final intended changes are three production cleanup files, two regression-test
files, and this documentation. `test.py`, models, thresholds, REST contracts,
service authentication and recognition architecture remain unchanged. No commit.
