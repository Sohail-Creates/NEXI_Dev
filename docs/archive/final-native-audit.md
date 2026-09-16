# Final isolated-install audit, status re-check, cleanup, and run guide

## Latest close-out: rotation instead of shared-history rewrite

Approved TODO for this pass:

- [x] Keep Item 1's readiness implementation and accepted 62/62 gate unchanged.
- [x] Rotate both local exposed Fernet keys using the shared dual-key mechanism; close previous-key access.
- [x] Remove Vision emotion capability and Central live conversation mood; prove before/after and targeted parity.
- [x] run.txt created; literal Central and Vision commands passed, corrections=0, shell exit=0.
- [x] Complete a new fresh continuous seven-service install/import/HTTPS-health audit; all seven passed, shell exit=0.

No Git command that mutates history, index, or remotes is authorized or performed
in this pass. The developer works in a public fork and intends a later PR to the
friend’s upstream repository. A PR does not scrub existing shared key history.
History remediation remains a separately coordinated human decision.

### Item 2: real local key remediation

Preflight resolved the configured key file to `06_enrollment_service/encryption.key`.
The second exposed local key file contained a different key. No key bytes were
logged. Live Central users: 0; encrypted Enrollment metadata: 0; Audio speaker
store: absent. No running Uvicorn consumers were found during rotation.
Both local key files now contain the newly generated current Fernet key;
`.env` uses the new current value, with both previous-value and previous-file
settings removed. These are ignored local operational credentials, not shipped
secrets. Rotation used `Fernet.generate_key`, `SecretPair`, and `RotatingFernet`.

Actual output (`logs/exposed-fernet-rotation.txt`):

```text
LIVE_PREFLIGHT central_users=0 enrollment_records=0 speaker_store_absent=True
EXPOSED_KEY_1 window_previous_read=PASS new_write_current_only=PASS rewrap_parity=PASS
EXPOSED_KEY_2 window_previous_read=PASS new_write_current_only=PASS rewrap_parity=PASS
CENTRAL_NORMAL_REWRAP {'examined': 1, 'encrypted': 1, 'unchanged': 0}
AUDIO_NORMAL_REWRAP {'examined': 1, 'updated': 1, 'unchanged': 0}
ENROLLMENT_NORMAL_REWRAP examined=1 updated=1 parity=True
WINDOW_CLOSED previous=None keyfiles_new=2 current_decrypt=PASS old1_decrypt=REJECT old2_decrypt=REJECT migrated_fixture_records=3
LIVE_MIGRATION examined=0 updated=0 parity=True; no live ciphertext depended on either retired key
HISTORY_UNTOUCHED=True historical_ciphertext_and_backups_not_revoked_by_rotation=True
```

The three populated records were a controlled fixture, not existing live user
data. Actual normal migration functions were Central `ensure_users_encrypted`,
Audio `migrate_legacy_pickle` on encrypted JSON (no pickle deserialization), and
Enrollment `EncryptionManager.rotate_file`. An independent exit-0 final check
confirmed previous=None, both key files match current, and current encryption
round-trip succeeds. A harmless dotenv warning about removing an already-absent
previous-file setting caused PowerShell's merged-stderr pipeline to report a
native warning; all rotation assertions completed, and the separate final check
returned 0. No old key was retained as active configuration.

The exposed values no longer decrypt this checkout's current configured stores
or newly written ciphertext. They can still decrypt historical ciphertext/backups
encrypted with those keys: cryptographic rotation cannot revoke old ciphertext.
This pass does not rotate the upstream owner's deployment. Git history retains
old key bytes; coordination with that owner is required for history remediation.

### Item 3: S2-04 response cleanup

Local native configuration check found `.env` lacked the Phase 5 JWT and service
secrets and enforcement flag. Provisioned only absent values using the existing
`secrets.token_urlsafe` pattern; preserved all existing credential values.
Set existing config flags to enforced auth, enabled TLS, disabled plaintext.
No authentication code or contract changed and no secrets were printed.
Actual exit-0 proof: `LOCAL_NATIVE_CONFIG enforced_auth=True trusted_client_headers=True signed_session_round_trip=PASS TLS=True plaintext=False secrets_logged=False`.
The existing configured TLS certificate validated through 2026-10-11T19:06:32Z.

Live conversation-store cleanup returned:
`LIVE_CONVERSATION_SCHEMA_CLEANUP before_records=0 after_records=0 before_mood_fields=0 after_mood_fields=0 parity=True`.

The caller scan found Central's POST/storage writer and legacy migration fixture
fields, but no live reader consuming mood for a decision. Removed the optional
argument and stored field from `add_conversation` and the route writer/examples.
The persistence boundary strips legacy mood from responses and subsequent writes.
The archival JSON importer accepts both historical and current shapes; archival
parity is preserved, not silently rewritten. Vision root no longer advertises
emotion_analysis. No face, camera, embedding, or model behavior changed.

Live HTTPS before/after bodies: `logs/s204-before-corrected.txt` and
`logs/s204-after.txt`. Before: root features contained emotion_analysis; stored
conversation contained mood happy. After: root features omit it; two conversation
records (one injected historical, one new) omit mood in both response and SQLite.
Actual storage check: `RAW_STORAGE legacy_and_new_rows=2 mood_fields=0 parity=True`.
The first before-probe missed the trusted internal user header and received an
honest 401; the corrected probe supplied both trust layers, without relaxing auth.

Targeted command:
`venv/Scripts/python.exe -m pytest tests/test_phase6.py::test_phase2_persistence_regression tests/test_phase7_cloud_sync.py::test_c_outbox_migration_twice_and_conversation_round_trip tests/test_route_naming_normalization.py -v -s --junitxml=logs/s204-targeted-regression.xml`.
Result: **8 passed in 5.32s**, CONTRACT 6, INTEGRATION 1, RESILIENCE 1,
zero failed/skipped. Full transcript: `logs/s204-targeted-regression.txt`.

### Item 4: run.txt literal walkthrough

`run.txt` has seven per-service PowerShell sections: create/activate own
`venv-audit-handover`, install only own requirements, pip check, real HTTPS Uvicorn
entrypoint, and health URL. Central initializes its configured SQLite/outbox;
TeachMe initializes its configured schema and documents loading/ready/503 behavior.
The final command is the existing `scripts/health_check_all.py` using Central's
environment. Prerequisites explicitly preserve .env/keys, require Python 3.11,
provision CA-verified certificates and MiniLM cache, and disclose missing models.
The host's `py -3.11` launcher returned "No installed Python found"; the guide uses
the verified `python` on PATH (3.11.9), not that launcher.

Literal sections were read from the file and executed without command edits in
two separate hidden PowerShell processes at the repository root, each using its
fresh audited environment. Temporary CA/data/test JWT+service credentials were
inherited as a disclosed test profile; the actual newly rotated Fernet setting
came from .env. No live data was altered, and all owned service processes stopped.
Actual output (`logs/run-txt-literal-walkthrough-completed.txt`, full commands and
process output):

```text
GUIDE_HEALTH Central 200 {"status":"healthy","service":"central_server"}
GUIDE_HEALTH Vision 200 {"status":"degraded","camera":"unavailable","face_model":"unavailable","opencv_version":"4.8.0","emotion_detection":"disabled","timestamp":"2026-09-14T09:59:09.513519"}
RUN_TXT_LITERAL_WALKTHROUGH PASS services=2 corrections=0
GUIDE_PROCESS_EXIT=0
```

Both per-section install commands reported already satisfied (fresh installation
was independently proven by the audit); both pip checks were clean. The guide's
TLS helper validates configured files and enabled HTTPS, not verify=False.
An initial orchestration helper waited without running service commands because
PowerShell Tee-Object logs were UTF-16 rather than UTF-8. Corrected its log reader
and stopped that owned helper; the application, audit, and guide were unchanged.
This is not recorded as a failed service or silently corrected guide command.

### Item 5: completed fresh continuous seven-service audit

Command (one continuous process, seven newly created isolated environments):

```powershell
.\venv\Scripts\python.exe scripts/audit_isolated_services.py --venv-name venv-audit-handover 2>&1 | Tee-Object logs/final-handover-seven-service-audit.txt
$auditExit = $LASTEXITCODE
Write-Output "AUDIT_PROCESS_EXIT=$auditExit"
exit $auditExit
```

Full install, pip-check, direct application import, actual HTTPS startup logs,
and response transcript: `logs/final-handover-seven-service-audit.txt`.
The transcript is PowerShell UTF-16LE. Each service installed ONLY its own
requirements.txt into its new `venv-audit-handover`. Tests used temporary stores,
CA-verified local TLS, enforced service authentication and test session secrets.
Services were started and stopped sequentially; this is an isolated install
audit, not a claim that downstream dependencies were simultaneously available.
No dependency pins, accepted readiness implementation, or Git history changed.

| Service | Install exit | pip check | Direct real application import | Health HTTP |
|---|---:|---|---|---:|
| Central | 0 | No broken requirements found. | REAL_APP_IMPORT=PASS | 200 |
| Vision | 0 | No broken requirements found. | REAL_APP_IMPORT=PASS | 200 |
| Audio | 0 | No broken requirements found. | REAL_APP_IMPORT=PASS | 200 |
| TTS | 0 | No broken requirements found. | REAL_APP_IMPORT=PASS | 200 |
| TeachMe | 0 | No broken requirements found. | REAL_APP_IMPORT=PASS | 200 |
| Enrollment | 0 | No broken requirements found. | REAL_APP_IMPORT=PASS | 200 |
| LLM | 0 | No broken requirements found. | REAL_APP_IMPORT=PASS | 200 |

Complete actual health bodies, in audit order:

```text
Central HTTP 200 {"status":"healthy","service":"central_server"}
Vision HTTP 200 {"status":"degraded","camera":"unavailable","face_model":"unavailable","opencv_version":"4.8.0","emotion_detection":"disabled","timestamp":"2026-09-14T09:48:33.229041"}
Audio HTTP 200 {"status":"degraded","service":"audio-service","version":"1.0.0","stop_word_detector":{"status":"unavailable","initialized":false},"queue_processor":{"running":true}}
TTS HTTP 200 {"status":"degraded","voice_model":"unavailable","service":"NEXI TTS","version":"1.0.0","timestamp":1789380157.497705}
TeachMe HTTP 200 {"status":"degraded","timestamp":"2026-09-14T10:11:52.712470","checks":{"embedding_model":"loading","knowledge_base":{"status":"healthy","items_count":0,"objects":0,"facts":0},"vision_service":{"status":"unavailable","circuit_state":"closed","successful_calls":0,"failed_calls":0,"avg_response_time_ms":0.0,"url":"https://localhost:8001"}},"http_code":200}
Enrollment HTTP 200 {"status":"healthy","version":"3.0.0"}
LLM HTTP 200 {"status":"healthy","openrouter":true}
AUDIT_PROCESS_EXIT=0
```

An independent BOM-aware parser asserted all seven recorded install codes,
pip checks, actual import markers, and HTTP status codes; exit 0:

```text
AUDIT_COMPLETE services=7 installs=7 pip_checks=7 real_imports=7 HTTPS_200=7 failures=0
```

TeachMe responded while its semantic model was honestly loading; no additional
model readiness wait or timeout increase was needed. LLM's actual live body was
healthy with openrouter=true; this does not prove paid generation credits.
Camera/face recognition, Porcupine/stop-word detection, Piper voice weights,
and paid provider generation still require their hardware/artifacts/account.
The accepted 62/62 protected regression was deliberately not rerun. The eight
targeted response/persistence tests above passed after this pass's code edits.
Docker F/G/H remain pending Docker Desktop. This proves native installation
and HTTPS startup on this Windows/Python 3.11 host, not blanket production
security certification or physical functional verification.

All current close-out items are complete. The historical sections below retain
earlier observations only; their stop/TODO states are superseded by this section.

## 2026-09-14 close-out TODO (historical, superseded)

- [x] Decouple TeachMe semantic warm-up from blocking ASGI startup; preserve schemas and pins.
- [x] Verify loading health, prompt learning/search 503s, immediate fact listing, and ready round trip.
- [ ] Complete one fresh continuous seven-service audit and the protected 62-test regression.
- [ ] Establish remote/history status before any key-history rewrite; preserve local keys and rotate exposed material.
- [ ] Remove emotion capability and unused conversation mood with before/after proofs.
- [ ] Create run.txt and literally verify two service sections.

### Close-out stop: repository was already pushed

Protected regression command:
`venv/Scripts/python.exe -m pytest tests/test_phase4.py tests/test_phase5.py tests/test_phase6.py tests/test_phase7_cloud_sync.py tests/test_route_naming_normalization.py tests/test_phase8_unit.py tests/test_phase8_contracts.py tests/test_phase8_e2e.py tests/test_phase8_resilience.py tests/phase9_security_verification.py -x -v -s --junitxml=logs/final-decoupled-regression.xml -o junit_logging=all`.
Actual pytest result: **62 passed in 280.27s**; UNIT 11, CONTRACT 20,
INTEGRATION 22, RESILIENCE 8, E2E 1; zero failures/skips. The real HTTP
learn/search test and all-seven forced-kill/restart scenario passed.
Full transcript: `logs/final-decoupled-regression.txt`; machine-readable result:
`logs/final-decoupled-regression.xml`. PowerShell's merged native-stderr pipeline
reported NativeCommandError for progress-bar output despite pytest's green
result; this is not reported as a clean shell exit-code proof.

The fresh continuous install audit was still installing Central when the
following stop condition was discovered. It is **not** a completed seven-service
install proof. Partial approved-network transcript:
`logs/final-decoupled-seven-service-audit-network.txt`.

`git remote -v` returned:

```text
origin   https://github.com/Sohail-Creates/NEXI_Dev.git (fetch)
origin   https://github.com/Sohail-Creates/NEXI_Dev.git (push)
upstream https://github.com/hammadf23/NEXI_Dev.git (fetch)
upstream https://github.com/hammadf23/NEXI_Dev.git (push)
```

`git reflog show --all --format='%h %gs'` included:

```text
31abb51 update by push
ecac2f6 update by push
42b6914 update by push
dff0ead update by push
f7d7ebc update by push
f8e0134 update by push
abc5f4f update by push
22fb0cb update by push
93b74c1 update by push
062d4d4 update by push
```

`git log --all --full-history --format='%h %ad %s' --date=iso -- 06_enrollment_service/encryption.key 06_enrollment_service/06_enrollment_service/encryption.key`
returned commits abc5f4f (2026-09-10 Phase 5) and 062d4d4 (2026-09-09 Phase 1).
No secret bytes were printed. The reflog is evidence of prior pushes; no claim
is made that this repository was never shared. The user's explicit stop condition
therefore applies. No filter-repo/history rewrite or real-key rotation was
performed; local key files and approved architecture remain untouched.
The unfinished owned audit was stopped. Items 3 and 4 were not implemented.
Coordinated shared-history remediation and exposed-key rotation require an
operator/team decision before close-out can continue.

The prior thread-contention stop below is historical and superseded by the
user-approved readiness decoupling. No thread or dependency setting was changed.
`teachme_service/app.py` schedules semantic warm-up off the event loop, exposes
`checks.embedding_model` as loading/ready/unavailable, and guards model-dependent
learning/search/batch/related routes with the existing 503 error envelope.
Health serves the latest background Vision probe instead of awaiting networking.

Live command/output: `logs/teachme-decoupled-readiness.txt` (includes full startup log).
First HTTP 200: 2.781 seconds from process launch, 0.531 seconds for the HTTPS
request; body reported degraded, embedding_model loading, knowledge_base healthy,
Vision unavailable, http_code 200. The request met the two-second responding
deadline once listening; total process-launch time was **not** under two seconds.
Loading learn returned 503 in 0.016 seconds; embedding search returned 503 in
0.015 seconds; both messages were "Embedding model still loading". Fact listing
returned 200 with count 0. At 14.906 seconds from launch, health reported ready;
learn returned 201 and semantic search 200 with mango and similarity 0.8419.

The Phase 4 real-HTTP fixture now separately polls semantic readiness, at two-second
intervals within a bounded 120-second readiness window; its original listening
deadline, learn/search payloads, and assertions are unchanged. This is an explicit
readiness predicate, not a longer blind startup sleep.

The first fresh install attempt was blocked by sandbox networking (WinError 10013),
not by a dependency resolution conflict. Full evidence:
`logs/final-decoupled-seven-service-audit.txt`. A new fresh audit was requested
with network approval; no failed environment is reused as clean-install evidence.

Audit started 2026-09-13. This is an execution record, not a production-readiness
certificate. Only commands run in this audit count toward the tables below.
Existing user data and credentials are not modified by the install/startup audit.
The audit uses new per-service venvs, temporary databases, test credentials,
CA-verified HTTPS, and rejects an occupied service port before launching.

## Part 1 — isolated installations and real startup

Re-runnable driver: `venv/Scripts/python.exe scripts/audit_isolated_services.py`.
It stops at the first failed check. A new `--venv-name venv-audit-NN` is required
for each fresh re-verification; existing environments are never silently reused.
Virtual environments named `venv-audit-*` are gitignored.

| Service | Install exit code | pip check result | Real import result | Health HTTP status | Health body |
|---|---|---|---|---|---|
| Central | `0` | `No broken requirements found.` | `REAL_APP_IMPORT=PASS` | `200` | `{"status":"healthy","service":"central_server"}` |
| Vision | `0` | `No broken requirements found.` | `REAL_APP_IMPORT=PASS` | `200` | `{"status":"degraded","camera":"unavailable","face_model":"unavailable","opencv_version":"4.8.0","emotion_detection":"disabled","timestamp":"2026-09-13T08:53:07.742284"}` |
| Audio | `0` | `No broken requirements found.` | `REAL_APP_IMPORT=PASS` (optional Resemblyzer unavailable; energy VAD active) | `200` | `{"status":"degraded","service":"audio-service","version":"1.0.0","stop_word_detector":{"status":"unavailable","initialized":false},"queue_processor":{"running":true}}` |
| TTS | `0` | `No broken requirements found.` | `REAL_APP_IMPORT=PASS` | `200` | `{"status":"degraded","voice_model":"unavailable","service":"NEXI TTS","version":"1.0.0","timestamp":1789291374.021714}` |
| TeachMe | `0` | `No broken requirements found.` | `REAL_APP_IMPORT=PASS` | `200` | `{"status":"healthy","timestamp":"2026-09-13T09:52:17.482329","checks":{"knowledge_base":{"status":"healthy","items_count":0,"objects":0,"facts":0},"vision_service":{"status":"unavailable","circuit_state":"closed","successful_calls":0,"failed_calls":2,"avg_response_time_ms":0.0,"url":"https://localhost:8001"}},"http_code":200}` |
| Enrollment | `0` | `No broken requirements found.` | `REAL_APP_IMPORT=PASS` | `200` | `{"status":"healthy","version":"3.0.0"}` |
| LLM | `0` | `No broken requirements found.` | `REAL_APP_IMPORT=PASS` | `200` | `{"status":"healthy","openrouter":true}` |

Central's initial fresh audit installed successfully and passed `pip check`, but
the import correctly failed on an unmigrated temporary database:

```text
RuntimeError: Central SQLite store missing; run migrate_sqlite.py before startup
EXIT_CODE=1
```

The correction was running the existing first-run migration, not weakening the
store's fail-closed behavior. All five checks were repeated in another fresh venv:

```powershell
.\venv\Scripts\python.exe scripts/audit_isolated_services.py --service Central --venv-name venv-audit-02
```

```text
ISOLATED_INTERPRETER=D:\Internship\Nexi\NEXI_Dev\01_central_server\venv-audit-02\Scripts\python.exe
EXIT_CODE=0
No broken requirements found.
conversations: before=0 after=0 parity=True added=synced,batch_id,sync_attempted_at,sync_succeeded_at
REAL_APP_IMPORT=PASS
Application startup complete.
Uvicorn running on https://127.0.0.1:8000 (Press CTRL+C to quit)
"GET /health HTTP/1.1" 200 OK
{"status":"healthy","service":"central_server"}
```

Audio's first check stopped before installation:

```text
AUDIT_STOP=missing service manifest: D:\Internship\Nexi\NEXI_Dev\03_audio_service\requirements.txt
```

The missing file was created from an AST import inventory and exact versions from
the recorded working environment, including its Groq STT, librosa/MFCC, audio I/O,
shared auth/TLS/HTTP, and preprocessing imports. No root or other service pins were
changed. Correction: the recorded freeze DOES contain `Resemblyzer==0.1.4`;
the initial case-sensitive lookup missed that capitalized distribution name.
The mounted advanced speaker service requires Resemblyzer and does not provide
an MFCC fallback. Its manifest now includes recorded Resemblyzer 0.1.4, torch
2.10.0, webrtcvad 2.0.10, and typing 3.7.4.3. The earlier five-check result below
proves only the previous manifest's import/health, not working neural speaker
verification. The corrected fresh audit is recorded separately in
`logs/final-native-audio-corrected.txt`; no success is claimed until it completes.
Physical microphone verification remains unperformed.

```powershell
.\venv\Scripts\python.exe scripts/audit_isolated_services.py --service Audio
```

```text
EXIT_CODE=0
No broken requirements found.
REAL_APP_IMPORT=PASS
Application startup complete.
Uvicorn running on https://127.0.0.1:8002 (Press CTRL+C to quit)
{"status":"degraded","service":"audio-service","version":"1.0.0","stop_word_detector":{"status":"unavailable","initialized":false},"queue_processor":{"running":true}}
```

TTS's first fresh install succeeded and `pip check` was clean, but its real
application import failed through the shared request middleware's TLS dependency:

```text
File "04_tts_service/tts_service/app.py", line 21
    from shared.request_middleware import install_request_observability
File "shared/request_middleware.py", line 10
    from config.ssl_config import get_tls_config
File "config/ssl_config.py", line 13
    from cryptography import x509
ModuleNotFoundError: No module named 'cryptography'
EXIT_CODE=1
```

Added `cryptography==46.0.5`, the already-recorded working version, to TTS's
manifest. No existing TTS dependency version was changed. A completely new
`04_tts_service/venv-audit-02` was used to repeat all five checks successfully:

```powershell
.\venv\Scripts\python.exe scripts/audit_isolated_services.py --service TTS --venv-name venv-audit-02
```

Pip also warned that its existing `torchaudio==2.0.0` pin is yanked for an incorrect
Torch dependency. This warning is recorded, not silently suppressed or resolved
by changing package versions.

TeachMe's initial real import failed on `pydantic_settings`; declared the missing
shared settings and TLS dependencies at `2.13.0` and `46.0.5`. Its second fresh
install, `pip check`, and real import passed, but startup failed:

```text
teachme_service/app.py:213 startup_event
    await asyncio.to_thread(knowledge_base.embedding_client.embed_query, "NEXI readiness")
shared/semantic_embeddings.py:15 _model
    from sentence_transformers import SentenceTransformer
ModuleNotFoundError: No module named 'sentence_transformers'
ERROR: Application startup failed. Exiting.
AUDIT_STOP=startup exited with 3
```

The required semantic readiness gate is retained. Declared `sentence-transformers==6.0.1`,
`torch==2.10.0`, and `transformers==5.17.0` using the recorded working versions.
No existing TeachMe pin was changed. The third fresh environment installed,
passed `pip check`, and imported the real app, but did not reach health within
the audit's 120-second limit. Its log stopped at semantic readiness with no
exception. A direct diagnostic of that same existing function subsequently
completed:

```text
SEMANTIC_DIAGNOSTIC_START
Loading weights: 100% (103/103)
SEMANTIC_DIMENSION=384
SEMANTIC_ELAPSED_SECONDS=18.781
```

The audit-only `--no-compile` pip optimization was removed. The app, readiness
check, and 120-second health limit are unchanged. All five checks are being
repeated in a fourth fresh environment with ordinary pip installation:

```powershell
.\venv\Scripts\python.exe scripts/audit_isolated_services.py --service TeachMe --venv-name venv-audit-04
```

```text
EXIT_CODE=0
No broken requirements found.
REAL_APP_IMPORT=PASS
2026-09-13 14:51:49,862 Query history cleanup is disabled; retention policy is deferred
2026-09-13 14:52:13,292 Semantic embedding model initialized
2026-09-13 14:52:15,308 Graceful shutdown system initialized
Application startup complete.
Uvicorn running on https://127.0.0.1:8004 (Press CTRL+C to quit)
"GET /health HTTP/1.1" 200 OK
```

Normal pip installation resolved the audit-only cold-start issue without changing
the application, weakening readiness, or increasing the health timeout.

Enrollment's initial install and dependency check passed, but its real import
failed through `shared/request_middleware.py -> config/__init__.py -> config/settings.py`:

```text
from pydantic_settings import BaseSettings
ModuleNotFoundError: No module named 'pydantic_settings'
EXIT_CODE=1
```

Declared `pydantic-settings==2.2.1` (the compatible version already proven by the
TTS real import), `PyJWT==2.10.1` for its active claim-based ownership and issuance,
and `cryptography==46.0.5` for directly consumed shared TLS/biometric encryption.
Existing Enrollment pins are unchanged. All five checks are being repeated in
`06_enrollment_service/venv-audit-02`, and passed:

```powershell
.\venv\Scripts\python.exe scripts/audit_isolated_services.py --service Enrollment --venv-name venv-audit-02
```

```text
EXIT_CODE=0
No broken requirements found.
REAL_APP_IMPORT=PASS
Application startup complete.
Uvicorn running on https://127.0.0.1:8005 (Press CTRL+C to quit)
[ENCRYPT] true
[STORAGE] C:\Users\asdfg\AppData\Local\Temp\nexi-isolated-audit-ghxoxqc5\Enrollment\enrollment
"GET /health HTTP/1.1" 200 OK
{"status":"healthy","version":"3.0.0"}
```

LLM's initial fresh install and `pip check` passed, but its real `from main import app`
failed through shared middleware and `config.settings`:

```text
ModuleNotFoundError: No module named 'pydantic_settings'
EXIT_CODE=1
```

Declared missing `pydantic-settings==2.13.0` and `cryptography==46.0.5` using the
recorded working versions, without changing any existing LLM pin. All five checks
were repeated successfully in `07_llm_service/venv-audit-02`. The real OpenRouter account
key is neither changed nor rotated.

## Part 2 — S2-01 through S2-13

Part 1 passed for all seven services. Live requirement re-verification is in progress;
no old phase outcome is carried forward as a new proof. LLM's isolated health returned
`{"status":"healthy","openrouter":true}`, which proves connectivity, not generation credit.

The functional re-check caught a Central manifest gap despite successful startup:

```powershell
.\01_central_server\venv-audit-02\Scripts\python.exe -c "from shared.semantic_embeddings import embed_text; print('CENTRAL_SEMANTIC_DIMENSION='+str(len(embed_text('NEXI readiness'))))"
```

```text
shared/semantic_embeddings.py:15
from sentence_transformers import SentenceTransformer
ModuleNotFoundError: No module named 'sentence_transformers'
```

Declared the same recorded working semantic dependencies used by TeachMe:
`sentence-transformers==6.0.1`, `torch==2.10.0`, `transformers==5.17.0`.
No existing Central pin or application logic was changed. Fresh Central
re-installation and real runtime embedding verification are required before cleanup.

Central's corrected semantic manifest was installed in a new environment and all
five checks passed again:

```powershell
.\venv\Scripts\python.exe scripts/audit_isolated_services.py --service Central --venv-name venv-audit-03
.\01_central_server\venv-audit-03\Scripts\python.exe -c "from shared.semantic_embeddings import embed_text, SEMANTIC_EMBEDDING_DIMENSION; vector=embed_text('NEXI readiness'); assert len(vector)==SEMANTIC_EMBEDDING_DIMENSION; print('CENTRAL_SEMANTIC_DIMENSION='+str(len(vector)))"
```

```text
EXIT_CODE=0
No broken requirements found.
REAL_APP_IMPORT=PASS
Application startup complete.
"GET /health HTTP/1.1" 200 OK
{"status":"healthy","service":"central_server"}
CENTRAL_SEMANTIC_DIMENSION=384
```

The protected regression command was run during this audit, not copied from an
earlier phase report:

```powershell
.\venv\Scripts\python.exe -m pytest -x -v -s tests/test_phase4.py tests/test_phase5.py tests/test_phase6.py tests/test_phase7_cloud_sync.py tests/test_route_naming_normalization.py tests/test_phase8_unit.py tests/test_phase8_contracts.py tests/test_phase8_e2e.py tests/test_phase8_resilience.py tests/phase9_security_verification.py --junitxml=logs/final-native-regression.xml -o junit_logging=all | Tee-Object -FilePath logs/final-native-regression.txt
```

Full stdout is retained in `logs/final-native-regression.txt`; JUnit evidence is
in `logs/final-native-regression.xml`. These are local ignored audit artifacts.
The run used the existing development interpreter and temporary fixture stores;
it is not represented as a run inside all seven newly isolated interpreters.

```text
[OK] Central Server            - healthy
[ERROR] Vision Service         -
[OK] Audio Service             - degraded
[OK] TTS Service               - degraded
[OK] TeachMe Service           - healthy
[OK] Enrollment Service        - healthy
[OK] LLM Service               - healthy
RESULT: PARTIAL HEALTH (6/7)
FAILED tests/test_phase8_resilience.py::test_resilience_all_seven_services_forced_kill_and_restart
UNIT: selected=11 passed=11
CONTRACT: selected=20 passed=20
INTEGRATION: selected=22 passed=22
RESILIENCE: selected=8 passed=7 failed=1
E2E: selected=0
1 failed, 60 passed in 327.54s
```

The seven-service cold-start smoke assertion failed. The later E2E test did not
run because `-x` stopped execution. This is not a 62/62 pass and not an accepted
degraded health response: Vision timed out in the smoke harness. No cleanup had
been applied. Its root cause remains under diagnosis; increasing the timeout or
ignoring the failure is not an audit fix.

The previously unrun E2E file was then executed independently:

```powershell
.\venv\Scripts\python.exe -m pytest -v -s tests/test_phase8_e2e.py
```

```text
E2E_STAGE_1_ENROLL HTTP=200 user_id=user_fa65e3f55b87 persisted=True
E2E_STAGE_2_VERIFY HTTP=200 method=synthesized-speech user_id=user_fa65e3f55b87 confidence=0.99 token_issued=True
E2E_STAGE_3_TEACH HTTP=200 item_id=fact-e2e type=fact
E2E_STAGE_4_RAG HTTP=200 source=teachme_grounded llm_calls=1 trusted_user=user_fa65e3f55b87 response='NEXI charging dock is beside the blue sofa'
E2E_STAGE_5_DURABILITY POST=200 GET=200 conversation_id=conv_503284e0d36d count=1
E2E_STAGE_6_SYNC_ELIGIBILITY HTTP=200 pending_records=1 synced=0 conversation_id=conv_503284e0d36d
E2E_RESULT PASS stages=6 physical_hardware=False synthesized_speech=True
1 passed in 22.64s
```

This is an in-process orchestration test using injected speaker, TeachMe, and LLM
doubles. Its printed `method=synthesized-speech` does not mean a physical microphone,
real waveform matcher, or billable model generation was verified. It does not erase
the separate seven-process smoke failure or constitute a combined 62/62 pass.

Current provider evidence from this audit's actual service log:

```text
2026-09-13 15:19:09,419 llm_service.services.openrouter_client WARNING correlation_id=phase9-end-to-end-trace OpenRouter error 402
2026-09-13 15:19:09,423 llm.request INFO REQUEST_END service=llm method=POST path=/api/v1/generate status=500 duration_ms=1148.126 correlation_id=phase9-end-to-end-trace
```

Central returned HTTP 502 with `code=LLM_FAILURE` for this request. The account key
was not changed or rotated. Healthy public-model connectivity does not establish
generation credit. Billing remains an operator/provider-tier limitation.

The seven-process restart test was also run with its assertions unchanged and
only its test launcher retargeted to each service's freshly audited interpreter.
Full stdout: `logs/final-native-stack.txt`; service logs:
`%TEMP%/nexi-native-stack-e_8_uce1/`. This is a disclosed test-launcher adaptation,
not a change to application imports, health criteria, or timeout values.

```text
[OK] Central Server            - healthy
[OK] Vision Service            - degraded
[OK] Audio Service             - degraded
[OK] TTS Service               - degraded
[OK] TeachMe Service           - healthy
[OK] Enrollment Service        - healthy
[OK] LLM Service               - healthy
RESULT: ALL SERVICES RESPONSIVE (7/7)
RESILIENCE_COLD_START_SMOKE PASS services=7 HTTP200=7
RESILIENCE_RESTART central    forced_kill=True old_pid=14420 new_pid=13108 HTTP=200 status=healthy
RESILIENCE_RESTART vision     forced_kill=True old_pid=13820 new_pid=7500 HTTP=200 status=degraded
RESILIENCE_RESTART audio      forced_kill=True old_pid=3544 new_pid=13628 HTTP=200 status=degraded
RESILIENCE_RESTART tts        forced_kill=True old_pid=14964 new_pid=15168 HTTP=200 status=degraded
RESILIENCE_RESTART teachme    forced_kill=True old_pid=10964 new_pid=10232 HTTP=200 status=healthy
RESILIENCE_RESTART enrollment forced_kill=True old_pid=13972 new_pid=2424 HTTP=200 status=healthy
RESILIENCE_RESTART llm        forced_kill=True old_pid=13460 new_pid=12928 HTTP=200 status=healthy
RESILIENCE_FORCED_KILL_RESTART_RESULT PASS services=7 restarted=7 manual_intervention=0
1 passed in 120.46s
NATIVE_STACK_EXIT=0
```

The isolated stack passed; the earlier shared-development-environment failure is
still recorded and its exact timing cause is not claimed fixed. One opportunistic
Vision information probe hit its deliberate kill/restart interval and received
connection refused; the restart test subsequently confirmed Vision HTTP 200.
Successful live probes while the native stack was running:

```text
VISION_INFORMATION_HTTP=200
{"service":"Vision Service","version":"4.0.0","status":"operational","features":["face_detection","face_embeddings","emotion_analysis","video_streaming"],"timestamp":"2026-09-13T10:38:17.290745"}
TTS_VOICES_HTTP=200
{"voices":[],"default":"jenny","count":0,"english_count":0,"urdu_count":0}
NATIVE_USER_CREATE 200 {"status":"success","message":"User Final native audit user enrolled","user_id":"native-audit-user"}
NATIVE_QA_WRITE 200 {"status":"success","message":"Conversation stored for user native-audit-user","user_id":"native-audit-user","timestamp":"2026-09-13T10:38:36.032800"}
NATIVE_QA_READ 200 {"user_id":"native-audit-user","conversations":[{"conversation_id":"conv_ef30e2d45751","user_id":"native-audit-user","timestamp":"2026-09-13T10:38:36.016169","user_message":"What is the audit fixture?","assistant_response":"The audit fixture is temporary.","mood":"neutral","language":"en","metadata":{}}],"count":1,"limit":10,"start_date":null,"end_date":null}
NATIVE_SYNC_STATUS 200 {"last_successful_sync":null,"pending_records":1,"last_error":null,"enabled":false,"worker_running":false,"next_run_in_seconds":null}
```

| Requirement | Actual status in this audit | Command / live evidence | Remaining limitation |
|---|---|---|---|
| S2-01 restricted RAG | Partially working | Protected run, `tests/test_phase4.py`: `ADVERSARIAL_RESULT passed=25 failed=0`, commands `teachme=0 llm=0`, no-match `teachme=1 llm=0`; native Central semantic dimension `384` | Guard and retrieval proofs pass; real answer generation receives provider HTTP 402. Basic commands remain pending product sign-off. |
| S2-02 single online LLM | Partially working | Protected LLM check: model-info HTTP 200 `provider=openrouter model=openai/gpt-4o-mini`; real correlated generation `OpenRouter error 402` -> LLM 500 -> Central 502 | No provider-failure-as-success; account credits unavailable. Dead local-loader artifacts require reference-backed cleanup. |
| S2-03 wake failure lifecycle | Partially working | `tests/test_phase6.py::test_phase3_wake_word_during_teachme_combined`: `wake_word_spoken=false voice_frames=8 stopped_by=silence elapsed=0.0630s`, `authority_query=None`, `PHASE3_COMBINED_RESULT=PASS enforcement=ON`; Audio real startup config 10.0 seconds | Injected speech/VAD transport, not physical mic; Porcupine stop-word initialization unavailable. |
| S2-04 remove mood/emotion, retain face | Partially working | Native GET `/` Vision HTTP 200 still advertises `emotion_analysis`; native conversation GET HTTP 200 still includes `mood=neutral`; Vision health face_model unavailable | Removal is incomplete, not just hardware degradation. Face embeddings unavailable. No success schema changed in this audit. |
| S2-05 durable identity/time/Q&A and sync state | Genuinely working for ordinary-Q&A storage | Native user create + Q&A write/read HTTP 200 above; outbox migration `run1_before=3 run1_after=3 run2_before=3 run2_after=3 parity=true`; status pending_records 1 | This proves explicit conversation storage, not automatic storage on every successful RAG call. |
| S2-06 local TeachMe / Q&A separation | Genuinely working within repository sync scope | `tests/test_phase7_cloud_sync.py::test_d_static_boundary_negative_control_then_clean`: disallowed import EXPECTED_FAIL, repaired PASS import_graph=clean sql_tables=allowlisted | Unknown external vendor is not verified. |
| S2-07 TeachMe focus/resource cooperation | Genuinely working with injected hardware transport | Resource suite `passed=5 failed=0`; focus `baseline=0.0000s active_teachme=0.1090s delta=0.1090s`; combined session release confirmed | Physical camera/mic preemption not verified; earlier shared-venv smoke timeout remains recorded separately. |
| S2-08 obsolete-code removal | Partially working | Fresh repository source listing still contains api_v2, managers, context_builder, enhanced enrollment/storage, and Vision queue modules | Fresh caller inventory and safe-removal decisions follow in Part 3; no file presence is called successful cleanup. |
| S2-09 online-only LLM | Genuinely working for mounted LLM failure semantics | `tests/test_phase4.py` provider failure HTTP 500 and `CLIENT_FAILURE success=False`; native real provider HTTP 402 propagates as failure, not a local answer | Blanket removal of local perception/speech was never approved (ADR-002); legacy verification scripts still describe offline fallback. |
| S2-10 Jenny-only TTS | Partially working | Native `/voices` HTTP 200 `default=jenny count=0`; native `/health` voice_model unavailable | Jenny weights absent; actual speech synthesis not verified. Internal multi-voice/language debt is not hidden by the public default. |
| S2-11 English gate | Genuinely working for tested policy fixtures | Protected `tests/test_phase4.py` input rejection + all 25 adversarial cases pass; caller system_prompt extra field rejected | Paid generation remains unavailable; this does not claim all multilingual internal speech branches removed. |
| S2-12 call state/preemption/hooks | Partially working | `tests/test_phase6.py`: CALL_ACTIVE HTTP 200 release confirmed by injected camera; screenshot decoded 48x32 / 654 bytes; call end restores background | Simulated camera frame, not a physical webcam; media/signaling belong to the video team. |
| S2-13 supervised Q&A cloud sync | Partially working | `tests/test_phase7_cloud_sync.py`: ten batches/ten records synced, failure retry preserves batch_id, dedupe succeeds, supervised exception/restart checks pass; native status accurately reports disabled/pending 1 | Local receiver is a verification fixture only; real vendor URL/auth/receiver guarantees unresolved, production worker not enabled in this audit. |

Known hardware/provider-tier limitations are face embeddings, real camera/microphone
verification, Porcupine initialization, Piper Jenny weights, and OpenRouter credits.
These do not invalidate honest HTTP 200 degraded health. Mood/emotion leftovers,
dead-code debt, and an actual smoke timeout are distinct implementation/audit findings,
not relabeled as those accepted external limitations.

## Part 3 — reference-backed cleanup

Fresh AST imports/short-string inspection and repository-wide reference searches
were run before selecting any deletion. Historical report mentions are distinguished
from executable callers. Findings listed before cleanup:

| Path | What / why flagged | Recommended action |
|---|---|---|
| `01_central_server/api_v2.py` | Retired alternate app; executable callers found: 0; old PROJECT_REPORT still describes it | Delete after individual zero-caller proof; retain historical audit report with archival warning. |
| `01_central_server/camera_manager.py` | Superseded camera authority; executable callers found: 0 | Delete after individual proof. |
| `01_central_server/hardware_resource_manager.py` | Superseded authority; executable callers found: 0 | Delete after individual proof. |
| `01_central_server/services/context_builder.py` | Imported by retired api_v2; substring match against distinct root llm_context_builder is not this module | Remove only after api_v2 deletion and a fresh exact-module proof. |
| `01_central_server/routes/llm_routes.py` | Unmounted alternate orchestrator; executable callers found: 0 | Delete after individual proof. |
| `test_nexi_system_enhanced.py` | Design reference, but standing naming test reads it at line 169 | RETAIN: real remaining reference; do not silently rewrite the regression assertion to enable deletion. |
| `06_enrollment_service/app/services/enrollment_service_enhanced.py` | No import callers; feature comparison found standalone complete_voice_flow / verify_speaker_runtime APIs absent from normal EnrollmentService | RETAIN: strict feature parity is not established. Matching is owned by Audio now, but this does not prove identical legacy orchestration responses. |
| `06_enrollment_service/app/storage/enrollment_storage.py` | No qualified import callers; legacy plaintext users.json with automatic backups/restore/atomic replacement differs from current encrypted per-user enrollment store | RETAIN: backup/restore feature parity is not established; not wired to the application. |
| `02_vision_service/vision_service/services/queue_processor.py` | No imported VisionQueueProcessor; queue_service only mentioned in a docstring/type prose | Delete after individual proof; Audio queue processor is active and NOT selected. |
| `02_vision_service/vision_service/services/queue_service.py` | No imported VisionQueueService | Delete after individual proof. |
| Central `add_user`, `add-embeddings`, conversation-history and TeachMe search aliases | Standing naming tests still call/assert every transition path; main also protects add_user prefix | RETAIN: real remaining references. Closing the transition requires an explicitly authorized test-contract migration. |
| `06_enrollment_service/encryption.key` | `git ls-files` confirms tracked secret material | Ignore and untrack without deleting local file; operator review/rotation needed because Git history remains. Never print value. |
| `06_enrollment_service/06_enrollment_service/encryption.key` | Second tracked key path | Same preservation/untracking/history warning. |
| `backups/phase2-pre-migration-20260909T140150Z/` | Migration snapshot with TeachMe knowledge JSON | Preserve: potentially contains original user knowledge; review/archive outside distributable repository, not blind deletion. |
| `backups/phase2-pre-migration-20260909T191040Z/` | Second migration snapshot | Same preservation/archive recommendation. |
| `05_teachme_service/knowledge_data.json`, `knowledge_data.sqlite3` | Default/legacy knowledge stores, not proven disposable fixtures | Preserve user data; separate local runtime data from source distribution. |
| Root `yolov8n.pt` | Newly untracked model produced by runtime loading during audit | Preserve until deployment config points unambiguously at the service model; dynamic fallback model loading makes a literal zero-reference grep insufficient. |
| `logs/phase9-*.xml`, `logs/final-native-*.txt`, `logs/final-native-regression.xml` | Local verification transcripts/artifacts | Already ignored; preserve this audit's evidence locally, not source distribution. |
| `tests/__pycache__/` and `venv-audit-*` directories | Local bytecode / fresh audit environments | Already ignored; needed by the requested run guide, not shipped artifacts. |
| `docs/PROJECT_REPORT.md` | Describes api_v2 as possibly active; obsolete managers; old architecture | Add archival warning, do not delete the historical evidence. |
| `docs/NEXI_FLOW.md` | Must be checked against current single-app / restricted RAG / HTTPS behavior | Flag specific contradictions before changing documentation. |

No key value, user knowledge, or biometric record is printed in this audit.

The entrypoint AST import graph is re-runnable with:

```powershell
.\venv\Scripts\python.exe scripts/audit_isolated_services.py --imports
```

Full current output is in `logs/final-native-import-graph.txt`. Package initializers
and function-local imports are traced; optional branches are included. Candidates
are not automatically called unused: a library's dependencies, CLI entrypoints,
multipart parser, and first-run deployment dependencies remain necessary even
without a direct application import.

| Manifest | Packages flagged / reason | Action selected before editing |
|---|---|---|
| Central | anyio, requests, torch, transformers: absent direct imports in entrypoint graph | Retain: async/semantic-model dependency closure; only required missing semantic packages were added. |
| Vision | anyio, httpx, dotenv, multipart, scikit-image, scipy, torch, torchvision | Retain runtime/YOLO dependencies; review optional legacy-image processing rather than infer safe deletion from top-level imports. |
| Audio | httpx, psutil, multipart, soundfile, tenacity | Retain: client/speaker/upload and third-party audio dependency closure; optional imports were reported separately. |
| TTS | torch, torchaudio, transformers, safetensors, huggingface-hub | Remove these five unused ML entries: whole-service Python reference search returned no matches (exit 1). Piper's ONNX runtime remains declared. No version bump. |
| TTS | httpx, onnxruntime, uvicorn | Retain HTTP dependency, ONNX synthesis engine, and server CLI. |
| TeachMe | explicit transitive framework/HTTP/auth/FAISS/semantic-model pins | Retain as dependency closure, not obsolete inference infrastructure. |
| Enrollment | Streamlit, WebRTC, AV, Pillow, sounddevice, soundfile and requests absent from API entrypoint graph | Whole-service Python caller checks also returned zero for each of these seven packages; remove these unused entries, not application features. The presumed native UI is not present in this service's source. |
| LLM | No review candidates | No removal. |

The whole-service package checks were individually run before the manifest edit:

```text
ENROLLMENT_PACKAGE_CHECK streamlit RG_EXIT=1 OUTPUT=''
ENROLLMENT_PACKAGE_CHECK streamlit_webrtc RG_EXIT=1 OUTPUT=''
ENROLLMENT_PACKAGE_CHECK av RG_EXIT=1 OUTPUT=''
ENROLLMENT_PACKAGE_CHECK PIL RG_EXIT=1 OUTPUT=''
ENROLLMENT_PACKAGE_CHECK sounddevice RG_EXIT=1 OUTPUT=''
ENROLLMENT_PACKAGE_CHECK soundfile RG_EXIT=1 OUTPUT=''
ENROLLMENT_PACKAGE_CHECK requests RG_EXIT=1 OUTPUT=''
```

Piper's installed package metadata confirms Torch is a `train` extra, not a
runtime dependency; `onnxruntime<2,>=1` is its runtime dependency and is retained.

Seven confirmed-dead modules were physically removed, each with an individual
zero-executable-caller result before removal: Central api_v2, camera_manager,
hardware_resource_manager, services/context_builder, routes/llm_routes, and
Vision queue_processor / queue_service. Historical audit mentions are retained,
not treated as launchers. Context-builder was checked again after api_v2 removal;
queue-service was checked again after removing its only prose reference in the
unused queue-processor. These files remain recoverable from Git; no user data was
deleted. The enhanced harness, both Enrollment legacy modules, and transition
aliases were retained for the reasons above.

Both tracked keys were removed from the index, not from disk:

```powershell
git rm --cached -- 06_enrollment_service/encryption.key 06_enrollment_service/06_enrollment_service/encryption.key
git ls-files -- 06_enrollment_service/encryption.key 06_enrollment_service/06_enrollment_service/encryption.key
git check-ignore 06_enrollment_service/encryption.key 06_enrollment_service/06_enrollment_service/encryption.key
```

```text
rm '06_enrollment_service/06_enrollment_service/encryption.key'
rm '06_enrollment_service/encryption.key'
git ls-files: no output
06_enrollment_service/encryption.key
06_enrollment_service/06_enrollment_service/encryption.key
Test-Path (each local key): True
```

Git history still contains these keys. Operator exposure review and a safe
dual-key rotation procedure are required; no history rewrite or real-key rotation
was performed. The old reports now have explicit archival warnings for their
HTTP/emotion/Urdu/hybrid-offline/alternate-app and production-readiness claims.

The health-all helper now loads `.env` without overriding explicit environment
values and includes exception types in failure output. Its 10-second deadline,
HTTP 200 healthy/degraded scoring, CA verification, and nonzero failure exit are
unchanged. This corrects manual custom-CA configuration and the earlier blank
error message; it does not mask or retry a failed health request.

Post-cleanup protected regression was run with the same ten test files and `-x`:

```text
FAILED tests/test_phase4.py::test_a_real_http_learn_then_search
AssertionError: TeachMe did not become ready
UNIT selected=11 passed=11
CONTRACT selected=1 passed=0 failed=1
INTEGRATION selected=0
RESILIENCE selected=0
E2E selected=0
1 failed, 11 passed in 260.05s
```

Full output: `logs/final-native-post-cleanup-regression.txt`. The startup log had
no traceback and stopped at semantic readiness. TeachMe application code was not
modified or deleted. Host measurements at that time: CPU 100%, four logical CPUs,
available RAM about 5.2 GB, disk free about 20.7 GB; VS Code, Defender, and Python
were active CPU consumers. A direct root-environment semantic diagnostic completed
normally with dimension 384 in 33.188 seconds. These measurements show host load;
they do not establish an exact cause for the missed deadline. Timeout values and
assertions were not increased or weakened. A targeted readiness re-check is being
run with the same two-thread OpenMP/MKL environment used by the successful native
stack audit, not a change to the application or retrieval logic.

## Part 4 — run.txt and literal walkthrough

Not started. No run guide is claimed created or verified yet.

## Resume: final isolated audit stop

Command: `venv/Scripts/python.exe scripts/audit_isolated_services.py --venv-name venv-audit-final`
Full transcript: `logs/final-native-post-cleanup.txt`.

```text
Central: install=0; pip check=No broken requirements found.; real import=PASS; HTTP=200; status=healthy
Vision: install=0; pip check=No broken requirements found.; real import=PASS; HTTP=200; status=degraded; face_model=unavailable
TTS: install=0; pip check=No broken requirements found.; real import=PASS; HTTP=200; status=degraded; voice_model=unavailable
TeachMe: install=0; pip check=No broken requirements found.; REAL_APP_IMPORT=PASS
INFO:     Started server process [17116]
INFO:     Waiting for application startup.
2026-09-14 06:00:59,342 - teachme_service.services.query_rotation_policy - INFO - Query history cleanup is disabled; retention policy is deferred
AUDIT_STOP=health readiness deadline exceeded
```

The final seven-service audit stopped at TeachMe. Enrollment and LLM were not
reached in this run. Its final Audio row predates the corrected neural-speaker
dependencies and must not be used as proof of the current Audio manifest. The
separate fresh corrected Audio audit is recorded in
`logs/final-native-audio-corrected.txt`.

TeachMe startup awaits its existing semantic-model readiness initialization;
this run did not produce a traceback or a reachable health endpoint. The exact
cause of the missed deadline remains unproven. No timeout, readiness assertion,
TLS verification, authentication rule, or application behavior was relaxed.
Phase 10 is not closed: final seven-service verification and the protected
regression gate are not clean. Docker tasks F/G/H remain pending Docker Desktop.

## Targeted startup investigation: stop condition

The corrected Audio audit has now completed: install exit 0, pip check
`No broken requirements found.`, `REAL_APP_IMPORT=PASS`, HTTPS `/health` 200
with the existing degraded stop-word-detector body. Full output:
`logs/final-native-audio-corrected.txt`.

TeachMe was started through its actual Uvicorn entry point, with verified TLS,
temporary SQLite/credentials, and unchanged 120-second readiness deadline.
Both experiments constrained `OMP_NUM_THREADS=2` and `MKL_NUM_THREADS=2`.
The load experiment additionally started one owned CPU-bound Python process;
that process was terminated after the measurement.

| Experiment | Elapsed seconds | HTTP | Status | SentenceTransformers cumulative import seconds |
|---|---:|---:|---|---:|
| Two-thread baseline, no dummy load | 75.250 | 200 | healthy | 63.864 |
| Two-thread startup plus one dummy CPU process | 21.922 | 200 | healthy | 14.318 |

Full results and health bodies: `logs/teachme-startup-contention.txt`.
Complete import profiles: `logs/teachme-threads2-baseline.log` and
`logs/teachme-threads2-load1.log`.

The baseline model initialization ran from 10:30:18.058 to 10:30:18.898;
the load-case initialization ran from 10:30:40.879 to 10:30:41.314.
The long delay occurs before these steps, in Python dependency imports,
not in the model's inference thread pool. An independent 20-second
faulthandler snapshot captured:

```text
fetch__all__
create_import_structure_from_path
define_import_structure
transformers.models.__init__
transformers.quantizers.auto
transformers.modeling_utils
sentence_transformers.base.model
shared.semantic_embeddings._model (line 15)
shared.semantic_embeddings.embed_text (line 34)
SEMANTIC_RESULT 384 SECONDS 24.312000000005355
```

Full diagnostic: `logs/teachme-semantic-stack-diagnostic.txt`. Its timed stack
dump is diagnostic output, not evidence of a model exception; the call completed
with dimension 384. The trace implicates Transformers' Python import-structure
initialization. It does not establish why import duration varies or explain
every earlier missed deadline. CPU-load testing did not reproduce that failure.
There is no evidence supporting an OpenMP/MKL-thread-limit fix.

The user explicitly requires stopping if the cause is deeper than inference
thread contention. No dependency version, application readiness behavior,
startup deadline, or regression assertion was changed. Items 2-4 and the fresh
continuous seven-service/regression gates were not started after this finding.
Resolving the import-initialization/readiness path requires a decision before
the phase can be closed; no Git history rewrite or real credential rotation
was attempted in this targeted investigation.
