# Phase 9 verification report

Verification date: 2026-09-12. Evidence source: `logs/phase9-final.xml`; captured stdout is pasted below without inventing successful provider or physical-hardware outcomes.

| # | Item | Status (DONE/PARTIAL/BLOCKED) | Files changed | Verification command | Verification result (actual output) | Deferred work |
|---|---|---|---|---|---|---|
| A | TLS, all seven services | DONE | `config/ssl_config.py`; authoritative service entrypoints/configs; active shared and service-local clients; `nexctl.py`; compose/wait/health/OpenAPI scripts; generated specs; `.env.example`; `.gitignore` | FINAL, `test_a_https_plaintext_transition_and_bad_ca` | HTTPS 200: seven services; plaintext rejected: seven; transition listener closed; wrong CA rejected by actual client | Commercial CA/domain/renewal; Docker runtime not verified |
| B | Biometric encryption at rest | DONE | `shared/secure_storage.py`; Central `sqlite_store.py`, migration/startup; Audio `speaker_service.py`; Enrollment encryption and both storage helpers | FINAL, `test_b_biometric_ciphertext_and_round_trips`; original persistence/speaker checks | Three ciphertext proofs and three normal round trips PASS; Central migration 1 updated then 0 | Secure provisioning/backups; legacy retired artifacts not deleted |
| C | Four dual-active credential classes | DONE | `shared/credential_rotation.py`, `secure_storage.py`, `jwt_manager.py`, `security.py`; Enrollment `encryption.py`; LLM `openrouter_client.py`; `.env.example`; `DEPLOYMENT.md` | FINAL, four `test_c_*` cases; targeted close-out recheck below | Old/new accepted; closed-old rejected/new accepted for Fernet/JWT/service trust and controlled HTTPS provider; all three stores survive rewrap | Real-account OpenRouter rotation is a permanent operator runbook item, not a code deliverable |
| D | Log redaction | DONE | `shared/utils/logging_setup.py` | FINAL, `test_d_redaction_negative_controls` | OFF plaintext / ON masked for credentials, biometrics, transcripts; nested/multiline/exception/access logs PASS | Arbitrary unlabeled prose is not a semantic PII detector |
| E | Correlation and latency | DONE | `shared/request_middleware.py`, `utils/trace_context.py`, `security.py`; clients and all seven apps | FINAL, `test_e_live_correlation_and_all_service_latencies` | Same ID: Central -> TeachMe -> LLM; seven latency samples; seven 401 traces; actual provider failure stays 502 | Real provider successful-generation trace unavailable |
| F | Dependency vulnerability scan | PARTIAL | `scripts/scan_dependencies.py`; `requirements.txt`; deployment guide | `.\venv\Scripts\python.exe scripts/scan_dependencies.py`; FINAL scanner negative control | SCAN_RESULT manifests=7 findings=118 errors=3 exit=FAIL; process exit 1 | Manifest resolution repair and vulnerability triage/remediation |
| G | Protected regression | DONE | `tests/conftest.py`, `test_phase4.py`, `test_phase8_resilience.py`; nine opt-in proofs in `phase9_security_verification.py` | FINAL | `62 passed in 217.36s`; protected baseline retained `53/53`; missing `0`; extra `9`; unique `62` | Physical microphone/webcam/Piper and real paid provider access |

FINAL (the actual executed command):

```powershell
.\venv\Scripts\python.exe -m pytest -x tests/test_phase4.py tests/test_phase5.py tests/test_phase6.py tests/test_phase7_cloud_sync.py tests/test_route_naming_normalization.py tests/test_phase8_unit.py tests/test_phase8_contracts.py tests/test_phase8_e2e.py tests/test_phase8_resilience.py tests/phase9_security_verification.py --junitxml=logs/phase9-final.xml -o junit_logging=all
```

## A — HTTPS, transition, plaintext and certificate negative controls

```text
A_HTTPS service=central status=200 body={"status":"healthy","service":"central_server"}
A_HTTPS service=vision status=200 body={"status":"degraded","camera":"unavailable","face_model":"unavailable","opencv_version":"4.11.0","emotion_detection":"disabled","timestamp":"2026-09-12T04:06:18.676452"}
A_HTTPS service=audio status=200 body={"status":"degraded","service":"audio-service","version":"1.0.0","stop_word_detector":{"status":"unavailable","initialized":false},"queue_processor":{"running":true}}
A_HTTPS service=tts status=200 body={"status":"degraded","voice_model":"unavailable","service":"NEXI TTS","version":"1.0.0","timestamp":1789185980.2424867}
A_HTTPS service=teachme status=200 body={"status":"healthy","timestamp":"2026-09-12T04:06:22.292686","checks":{"knowledge_base":{"status":"healthy","items_count":0,"objects":0,"facts":0},"vision_service":{"status":"unavailable","circuit_state":"closed","successful_calls":0,"failed_calls":2,"avg_response_time_ms":0.0,"url":"https://localhost:8001"}},"http_code":200}
A_HTTPS service=enrollment status=200 body={"status":"healthy","version":"3.0.0"}
A_HTTPS service=llm status=200 body={"status":"degraded","openrouter":false}
A_PLAINTEXT_CLOSED service=central rejected=True
A_PLAINTEXT_CLOSED service=vision rejected=True
A_PLAINTEXT_CLOSED service=audio rejected=True
A_PLAINTEXT_CLOSED service=tts rejected=True
A_PLAINTEXT_CLOSED service=teachme rejected=True
A_PLAINTEXT_CLOSED service=enrollment rejected=True
A_PLAINTEXT_CLOSED service=llm rejected=True
A_WRONG_CA rejected=True type=SSLError verification_disabled=False
A_INTERSERVICE_CLIENT wrong_ca=REJECT trusted_ca=ACCEPT client=LLMServiceClient
A_TRANSITION status=200 body={"status":"healthy","service":"central_server"}
2026-09-12 09:06:24,841 WARNING central.request PLAINTEXT_TRANSITION service=central method=GET path=/health correlation_id=0d653137-0614-4062-a842-778adc5bd6a2
A_TRANSITION_CLOSED plaintext_listener=8090 rejected=True
```

## B — Raw ciphertext and normal application round trips

```text
B_CENTRAL_RAW nexi-fernet-v1:gAAAAABqpM_CphUKfSFtL1DDzBCwezBZge9WISad-ql7AcznLbT2MU0aoiS3-Oc9MIP2ZovxoaK plaintext_user_present=False
B_CENTRAL_ROUND_TRIP PASS first={'examined': 1, 'encrypted': 1, 'unchanged': 0} second={'examined': 1, 'encrypted': 0, 'unchanged': 1}
B_AUDIO_RAW b'nexi-fernet-v1:gAAAAABqpM_DpuC-qU5HJvWPob-OtuzNIQYjq3oIY_9O40aQ3mqB5mxvnnC7gGlBbgBwY_uSk_i' plaintext_user_present=False
B_AUDIO_ROUND_TRIP PASS speakers=1
B_ENROLLMENT_RAW b'nexi-fernet-v1:gAAAAABqpM_D0Yi1xQJ8cba643EuLT3Fnd3QEqFvlzgVLnmE-dI2DXFSF1nijkUFk7r3cFgEGKA' plaintext_fields_present=False
B_ENROLLMENT_ROUND_TRIP PASS mandatory=True
```

The original speaker-store migration/verification and Phase 2 persistence regression also passed in FINAL:

```text
G_MIGRATION_FIRST {'examined': 1, 'updated': 1, 'unchanged': 0}
G_MIGRATION_SECOND {'examined': 1, 'updated': 0, 'unchanged': 1}
G_SAFE_FORMAT schema=json pickle_load_in_normal_path=False
G_VERIFY user_id=user-a confidence=1.0000
```

```text
users: JSON=1 SQLite=1 action=imported parity=True
conversations: JSON=1 SQLite=1 action=imported parity=True
users: JSON=1 SQLite=1 action=unchanged parity=True
conversations: JSON=1 SQLite=1 action=unchanged parity=True
CENTRAL_MIGRATION_IDEMPOTENCY PASS
knowledge: JSON=1 SQLite=1 action=imported parity=True metadata_parity=True
knowledge: JSON=1 SQLite=1 action=unchanged parity=True metadata_parity=True
TEACHME_MIGRATION_IDEMPOTENCY PASS
ENROLLMENT_RECOVERY_FAIL_SAFE PASS missing=voice_embeddings record_preserved=True
PHASE2_PERSISTENCE_RESULT passed=3 failed=0
PHASE2_COMBINED_RESULT passed=8 failed=0 enforcement=ON
```

`schema=json` describes the decrypted schema; the new on-disk speaker store is Fernet-wrapped JSON, not plaintext JSON. Encryption scope excludes TeachMe and conversations.

## C — Rotation cycles and on-disk key retirement

```text
C_STORE_ROTATION store=central-users previous_read=PASS rewrap=PASS closed_current_read=PASS record_parity=1:1
C_STORE_ROTATION store=audio-speakers previous_read=PASS rewrap=PASS closed_current_read=PASS record_parity=1:1
C_STORE_ROTATION store=enrollment-metadata previous_read=PASS rewrap=PASS closed_current_read=PASS record_parity=1:1
```

```text
C_FERNET window_old=ACCEPT window_new=ACCEPT closed_old=REJECT closed_new=ACCEPT
C_FERNET_REWRAP previous_ciphertext_migrated=True readable_after_window_close=True
C_JWT window_old=ACCEPT window_new=ACCEPT closed_old=REJECT closed_new=ACCEPT
C_SERVICE_TRUST window_old=ACCEPT window_new=ACCEPT closed_old=REJECT closed_new=ACCEPT
```

```text
C_OPENROUTER window_old=ACCEPT window_new=ACCEPT closed_old=REJECT closed_new=ACCEPT local_https_provider_fixture=True real_provider_keys_rotated=False
```

```text
C_LIVE_WINDOW HTTPS service_old=200 service_new=200 jwt_old=200 jwt_new=200
C_LIVE_CLOSED HTTPS service_old=401 service_new=200 jwt_old=401 jwt_new=200
```

These are independently signed/encrypted test credentials, not a rotation of your deployed secrets. The OpenRouter cycle uses the real adapter and a controlled HTTPS provider, not real vendor provisioning. Removing the previous environment value does not revoke an upstream API key. The deployment guide specifies accept-before-issue staging, rolling restarts, rewrapping all biometric stores before key retirement, and upstream revocation.

## D — Redaction OFF/ON negative controls

All values below are test-only fixtures.

```text
D_CREDENTIAL OFF='Authorization=Bearer sk-or-v1-0123456789abcdef0123456789abcdef' ON='Authorization=[REDACTED] [REDACTED]'
D_BIOMETRIC OFF='embedding=[0.123456, 0.987654]' ON='embedding=[REDACTED]'
D_TRANSCRIPTION OFF='transcription=My private spoken sentence' ON='transcription=[REDACTED]'
D_PRODUCTION_TRANSCRIBE OFF="[AudioClient] transcribe SUCCESS - text: 'My private spoken sentence...'" ON='[AudioClient] transcribe SUCCESS - text: [REDACTED]'
D_NESTED_BIOMETRIC OFF='voice_embeddings=[[0.123456,0.987654],[0.654321,0.456789]]' ON='voice_embeddings=[REDACTED]'
D_CONFIGURED_SECRET OFF='secret=fixturejwtsecret spacecomponent' ON='secret=[REDACTED]'
D_MULTILINE_TRANSCRIPTION OFF='transcription=private-first-line\nprivate-second-line' ON='transcription=[REDACTED]'
D_UNLABELLED_API_KEY OFF='diagnostic sk-or-v1-0123456789abcdef0123456789abcdef' ON='diagnostic [REDACTED]'
D_UNLABELLED_FERNET_KEY OFF='diagnostic lvl7f3kGOwfy8j52uU6IJ62UupzfeGE22xVGuxBmc9U=' ON='diagnostic [REDACTED]'
D_PRODUCTION_TRANSCRIPTION_COMPLETE OFF="Transcription complete: text='private-speech', language=en" ON='Transcription complete: [REDACTED]'
D_PRODUCTION_TRANSCRIBED_LANGUAGE OFF='Transcribed (en): private-speech...' ON='Transcribed (en): [REDACTED]'
D_PRODUCTION_SPEECH_SYNTHESIS OFF='Synthesizing speech (user-a): private-speech...' ON='Synthesizing speech (user-a): [REDACTED]'
D_PRODUCTION_RAG_QUERY OFF="teachme_no_match query='private-question'" ON='teachme_no_match query=[REDACTED]'
D_PRODUCTION_QUEUE_QUERY OFF="TeachMe queue full, returning empty results for 'private-question'" ON='TeachMe queue full, returning empty results for [REDACTED]'
D_PRODUCTION_RESPONSE_BODY OFF='Response text: {"text":"private-speech","user_id":"private-user"}' ON='Response text: [REDACTED]'
D_STRUCTURED_BODY_EXTRA_EXCEPTION sensitive_values=REDACTED
D_ROUTE_METADATA path=/transcribe status=200 duration_ms=1.0 preserved=True
D_UVICORN_ACCESS correlation_id=phase9-access-log 127.0.0.1:12345 - "GET /health?api_key=[REDACTED] HTTP/1.1" 200 OK
```

Additional structural red controls found and fixed during verification:

```text
AssertionError: auth rejection bypassed observability: central
assert None == 'phase9-denied-central'
AssertionError: assert ('[REDACTED]' in 'diagnostic sk-or-v1-0123456789abcdef0123456789abcdef')
ValueError: not enough values to unpack (expected 5, got 0)
```

The green proofs above cover the corrected message patterns and Uvicorn's five-argument access-formatter contract. Middleware ordering is fixed without changing auth/CORS/upload/rate-limit order relative to one another.

## E — Actual log trace and per-service latency

```text
E_EXTERNAL_RAG status=502 body={"error":{"status_code":502,"code":"LLM_FAILURE","message":"LLM service HTTP 500","request_id":"phase9-end-to-end-trace"}}
E_TRACE central 2026-09-12 09:06:32,888 INFO central.request REQUEST_START service=central method=POST path=/api/v1/rag/query correlation_id=phase9-end-to-end-trace
E_TRACE central 2026-09-12 09:06:34,071 INFO central.request REQUEST_END service=central method=POST path=/api/v1/rag/query status=502 duration_ms=1184.303 correlation_id=phase9-end-to-end-trace
E_TRACE teachme 2026-09-12 09:06:33,671 - teachme.request - INFO - REQUEST_START service=teachme method=POST path=/knowledge/search/embedding correlation_id=phase9-end-to-end-trace
E_TRACE teachme 2026-09-12 09:06:33,710 - teachme.request - INFO - REQUEST_END service=teachme method=POST path=/knowledge/search/embedding status=200 duration_ms=34.098 correlation_id=phase9-end-to-end-trace
E_TRACE llm 2026-09-12 09:06:34,042 - llm.request - INFO - REQUEST_START service=llm method=POST path=/api/v1/generate correlation_id=phase9-end-to-end-trace
E_TRACE llm 2026-09-12 09:06:34,071 - llm.request - INFO - REQUEST_END service=llm method=POST path=/api/v1/generate status=500 duration_ms=31.907 correlation_id=phase9-end-to-end-trace
E_LATENCY central 2026-09-12 09:06:34,071 INFO central.request REQUEST_END service=central method=POST path=/api/v1/rag/query status=502 duration_ms=1184.303 correlation_id=phase9-end-to-end-trace
E_LATENCY vision 2026-09-12 09:06:26,657 - vision.request - INFO - REQUEST_END service=vision method=GET path=/health status=200 duration_ms=6103.963 correlation_id=15a14abf-4769-42cc-80de-539b0cf7813c
E_LATENCY audio 2026-09-12 09:06:20,209 - audio.request - INFO - REQUEST_END service=audio method=GET path=/health status=200 duration_ms=14.047 correlation_id=2d942266-dc7a-483b-b920-05d54f73b02c
E_LATENCY tts 2026-09-12 09:06:20,242 - tts.request - INFO - REQUEST_END service=tts method=GET path=/health status=200 duration_ms=16.622 correlation_id=457dac7f-4ce5-4111-a3a1-c766e7d2f22a
E_LATENCY teachme 2026-09-12 09:06:33,710 - teachme.request - INFO - REQUEST_END service=teachme method=POST path=/knowledge/search/embedding status=200 duration_ms=34.098 correlation_id=phase9-end-to-end-trace
E_LATENCY enrollment 2026-09-12 09:06:22,341 INFO enrollment.request REQUEST_END service=enrollment method=GET path=/health status=200 duration_ms=18.138 correlation_id=5e91fad5-9b34-4d97-8ebd-94159c093c10
E_LATENCY llm 2026-09-12 09:06:34,071 - llm.request - INFO - REQUEST_END service=llm method=POST path=/api/v1/generate status=500 duration_ms=31.907 correlation_id=phase9-end-to-end-trace
E_REJECTED_TRACE central 2026-09-12 09:06:34,204 INFO central.request REQUEST_END service=central method=GET path=/resources/status status=401 duration_ms=2.098 correlation_id=phase9-denied-central
E_REJECTED_TRACE vision 2026-09-12 09:06:34,239 - vision.request - INFO - REQUEST_END service=vision method=POST path=/api/v1/detect/faces status=401 duration_ms=2.003 correlation_id=phase9-denied-vision
E_REJECTED_TRACE audio 2026-09-12 09:06:34,272 - audio.request - INFO - REQUEST_END service=audio method=POST path=/api/v1/process-voice status=401 duration_ms=2.053 correlation_id=phase9-denied-audio
E_REJECTED_TRACE tts 2026-09-12 09:06:34,304 - tts.request - INFO - REQUEST_END service=tts method=POST path=/speak status=401 duration_ms=1.974 correlation_id=phase9-denied-tts
E_REJECTED_TRACE teachme 2026-09-12 09:06:34,337 - teachme.request - INFO - REQUEST_END service=teachme method=POST path=/learn status=401 duration_ms=2.448 correlation_id=phase9-denied-teachme
E_REJECTED_TRACE enrollment 2026-09-12 09:06:34,369 INFO enrollment.request REQUEST_END service=enrollment method=GET path=/enrollment/storage/list status=401 duration_ms=3.418 correlation_id=phase9-denied-enrollment
E_REJECTED_TRACE llm 2026-09-12 09:06:34,407 - llm.request - INFO - REQUEST_END service=llm method=POST path=/api/v1/generate status=401 duration_ms=1.529 correlation_id=phase9-denied-llm
```

LLM health at this verification was `degraded`, `openrouter=false`. The external RAG request received an honest shared-envelope 502, never a canned successful answer.

## F — Standalone dependency scan

The standalone scan ran against the final pinned manifests and exited 1. Full output below is reproduced using the scanner's unchanged renderer and the persisted `logs/dependency-audit.json`; no resolver errors or advisory entries are omitted. PyPI's audit response does not include CVSS severity: entries are explicitly UNASSESSED and conservatively blocked as high, not asserted to have an invented high/critical score.

```text
NEXI DEPENDENCY VULNERABILITY SCAN
policy=exit_nonzero_on_high_critical_or_unassessed severity_source=pip-audit/PyPI
MANIFEST requirements.txt ERROR dependency resolution/audit exceeded 180 seconds; manifest NOT cleared
MANIFEST requirements.txt findings=0
MANIFEST 01_central_server\requirements.txt ERROR ERROR:pip_audit._virtual_env:internal pip failure: ERROR: Ignored the following yanked versions: 4.6.2

ERROR: Could not find a version that satisfies the requirement anyio==4.1.1 (from versions: 1.0.0a1, 1.0.0a2, 1.0.0b1, 1.0.0b2, 1.0.0rc1, 1.0.0rc2, 1.0.0, 1.1.0, 1.2.0, 1.2.1, 1.2.2, 1.2.3, 1.3.0, 1.3.1, 1.4.0, 2.0.0b1, 2.0.0b2, 2.0.0rc1, 2.0.0rc2, 2.0.0, 2.0.1, 2.0.2, 2.1.0, 2.2.0, 3.0.0rc1, 3.0.0rc2, 3.0.0rc3, 3.0.0rc4, 3.0.0, 3.0.1, 3.1.0, 3.2.0, 3.2.1, 3.3.0, 3.3.1, 3.3.2, 3.3.3, 3.3.4, 3.4.0, 3.5.0, 3.6.0, 3.6.1, 3.6.2, 3.7.0rc1, 3.7.0, 3.7.1, 4.0.0rc1, 4.0.0, 4.1.0, 4.2.0, 4.3.0, 4.4.0, 4.5.0, 4.5.1, 4.5.2, 4.6.0, 4.6.1, 4.6.2.post1, 4.7.0, 4.8.0, 4.9.0, 4.10.0, 4.11.0, 4.12.0, 4.12.1, 4.13.0, 4.14.0, 4.14.1, 4.14.2, 4.15.0, 4.15.1)

ERROR: No matching distribution found for anyio==4.1.1


ERROR:pip_audit._cli:Failed to install packages: ['C:\\Users\\asdfg\\AppData\\Local\\Temp\\tmp3m004sv_\\Scripts\\python.exe', '-m', 'pip', 'install', '--no-input', '--keyring-provider=subprocess', '--dry-run', '--report', 'C:\\Users\\asdfg\\AppData\\Local\\Temp\\tmp8iib5lpo\\tmpbtsddroa', '-r', 'D:\\Internship\\Nexi\\NEXI_Dev\\01_central_server\\requirements.txt']
MANIFEST 01_central_server\requirements.txt findings=0
MANIFEST 02_vision_service\requirements.txt ERROR ERROR:pip_audit._virtual_env:internal pip failure: ERROR: Cannot install -r D:\Internship\Nexi\NEXI_Dev\02_vision_service\requirements.txt (line 1), -r D:\Internship\Nexi\NEXI_Dev\02_vision_service\requirements.txt (line 16), -r D:\Internship\Nexi\NEXI_Dev\02_vision_service\requirements.txt (line 3), pydantic and tensorflow because these package versions have conflicting dependencies.

ERROR: ResolutionImpossible: for help visit https://pip.pypa.io/en/latest/topics/dependency-resolution/#dealing-with-dependency-conflicts


ERROR:pip_audit._cli:Failed to install packages: ['C:\\Users\\asdfg\\AppData\\Local\\Temp\\tmpc4dqno0q\\Scripts\\python.exe', '-m', 'pip', 'install', '--no-input', '--keyring-provider=subprocess', '--dry-run', '--report', 'C:\\Users\\asdfg\\AppData\\Local\\Temp\\tmpq7y7nd9l\\tmpxzr0c6g9', '-r', 'D:\\Internship\\Nexi\\NEXI_Dev\\02_vision_service\\requirements.txt']
MANIFEST 02_vision_service\requirements.txt findings=0
MANIFEST 04_tts_service\requirements.txt findings=61
  torch==2.0.0 PYSEC-2024-251 severity=UNASSESSED_TREATED_AS_HIGH fixes=2.2.0
  torch==2.0.0 PYSEC-2025-191 severity=UNASSESSED_TREATED_AS_HIGH fixes=2.7.1rc1
  torch==2.0.0 PYSEC-2026-1970 severity=UNASSESSED_TREATED_AS_HIGH fixes=2.8.0
  torch==2.0.0 PYSEC-2025-41 severity=UNASSESSED_TREATED_AS_HIGH fixes=2.6.0
  torch==2.0.0 PYSEC-2024-250 severity=UNASSESSED_TREATED_AS_HIGH fixes=2.2.0
  torch==2.0.0 PYSEC-2024-252 severity=UNASSESSED_TREATED_AS_HIGH fixes=2.2.0
  torch==2.0.0 PYSEC-2024-259 severity=UNASSESSED_TREATED_AS_HIGH fixes=2.5.0
  torch==2.0.0 PYSEC-2025-205 severity=UNASSESSED_TREATED_AS_HIGH fixes=2.7.1
  torch==2.0.0 PYSEC-2025-206 severity=UNASSESSED_TREATED_AS_HIGH fixes=2.9.0
  torch==2.0.0 PYSEC-2025-207 severity=UNASSESSED_TREATED_AS_HIGH fixes=2.7.1
  torch==2.0.0 PYSEC-2025-204 severity=UNASSESSED_TREATED_AS_HIGH fixes=2.9.0
  torch==2.0.0 PYSEC-2026-139 severity=UNASSESSED_TREATED_AS_HIGH fixes=none
  torch==2.0.0 PYSEC-2025-209 severity=UNASSESSED_TREATED_AS_HIGH fixes=2.7.1
  torch==2.0.0 PYSEC-2025-208 severity=UNASSESSED_TREATED_AS_HIGH fixes=2.7.1
  torch==2.0.0 PYSEC-2025-198 severity=UNASSESSED_TREATED_AS_HIGH fixes=2.7.0
  torch==2.0.0 PYSEC-2025-203 severity=UNASSESSED_TREATED_AS_HIGH fixes=2.9.0
  torch==2.0.0 PYSEC-2025-189 severity=UNASSESSED_TREATED_AS_HIGH fixes=none
  torch==2.0.0 PYSEC-2025-190 severity=UNASSESSED_TREATED_AS_HIGH fixes=none
  torch==2.0.0 PYSEC-2025-192 severity=UNASSESSED_TREATED_AS_HIGH fixes=none
  torch==2.0.0 PYSEC-2025-193 severity=UNASSESSED_TREATED_AS_HIGH fixes=2.9.1
  torch==2.0.0 PYSEC-2025-194 severity=UNASSESSED_TREATED_AS_HIGH fixes=2.13.0
  torch==2.0.0 PYSEC-2025-195 severity=UNASSESSED_TREATED_AS_HIGH fixes=2.10.0
  torch==2.0.0 PYSEC-2026-2286 severity=UNASSESSED_TREATED_AS_HIGH fixes=2.10.0
  transformers==4.30.0 PYSEC-2025-217 severity=UNASSESSED_TREATED_AS_HIGH fixes=none
  transformers==4.30.0 PYSEC-2023-300 severity=UNASSESSED_TREATED_AS_HIGH fixes=4.36.0
  transformers==4.30.0 PYSEC-2023-301 severity=UNASSESSED_TREATED_AS_HIGH fixes=4.36.0
  transformers==4.30.0 PYSEC-2026-1978 severity=UNASSESSED_TREATED_AS_HIGH fixes=4.38.0
  transformers==4.30.0 PYSEC-2026-1982 severity=UNASSESSED_TREATED_AS_HIGH fixes=4.48.0
  transformers==4.30.0 PYSEC-2026-1984 severity=UNASSESSED_TREATED_AS_HIGH fixes=4.50.0
  transformers==4.30.0 PYSEC-2024-227 severity=UNASSESSED_TREATED_AS_HIGH fixes=4.48.0
  transformers==4.30.0 PYSEC-2024-228 severity=UNASSESSED_TREATED_AS_HIGH fixes=4.48.0
  transformers==4.30.0 PYSEC-2024-229 severity=UNASSESSED_TREATED_AS_HIGH fixes=4.48.0
  transformers==4.30.0 PYSEC-2025-40 severity=UNASSESSED_TREATED_AS_HIGH fixes=4.50.0
  transformers==4.30.0 PYSEC-2026-1987 severity=UNASSESSED_TREATED_AS_HIGH fixes=4.51.0
  transformers==4.30.0 PYSEC-2026-1985 severity=UNASSESSED_TREATED_AS_HIGH fixes=4.51.0
  transformers==4.30.0 PYSEC-2026-1986 severity=UNASSESSED_TREATED_AS_HIGH fixes=4.52.1
  transformers==4.30.0 PYSEC-2026-1977 severity=UNASSESSED_TREATED_AS_HIGH fixes=4.52.1
  transformers==4.30.0 PYSEC-2026-1983 severity=UNASSESSED_TREATED_AS_HIGH fixes=4.53.0
  transformers==4.30.0 PYSEC-2026-1981 severity=UNASSESSED_TREATED_AS_HIGH fixes=4.53.0
  transformers==4.30.0 PYSEC-2026-1988 severity=UNASSESSED_TREATED_AS_HIGH fixes=4.53.0
  transformers==4.30.0 PYSEC-2026-1980 severity=UNASSESSED_TREATED_AS_HIGH fixes=4.53.0
  transformers==4.30.0 PYSEC-2026-2288 severity=UNASSESSED_TREATED_AS_HIGH fixes=5.0.0rc3
  transformers==4.30.0 PYSEC-2025-214 severity=UNASSESSED_TREATED_AS_HIGH fixes=none
  transformers==4.30.0 PYSEC-2025-218 severity=UNASSESSED_TREATED_AS_HIGH fixes=none
  transformers==4.30.0 PYSEC-2025-211 severity=UNASSESSED_TREATED_AS_HIGH fixes=none
  transformers==4.30.0 PYSEC-2025-212 severity=UNASSESSED_TREATED_AS_HIGH fixes=none
  transformers==4.30.0 PYSEC-2025-213 severity=UNASSESSED_TREATED_AS_HIGH fixes=none
  transformers==4.30.0 PYSEC-2025-215 severity=UNASSESSED_TREATED_AS_HIGH fixes=none
  transformers==4.30.0 PYSEC-2025-216 severity=UNASSESSED_TREATED_AS_HIGH fixes=none
  transformers==4.30.0 PYSEC-2026-2289 severity=UNASSESSED_TREATED_AS_HIGH fixes=5.3.0
  transformers==4.30.0 PYSEC-2026-2290 severity=UNASSESSED_TREATED_AS_HIGH fixes=none
  transformers==4.30.0 PYSEC-2026-3929 severity=UNASSESSED_TREATED_AS_HIGH fixes=5.10.0
  python-dotenv==1.0.0 PYSEC-2026-2270 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.2.2
  h11==0.14.0 PYSEC-2026-348 severity=UNASSESSED_TREATED_AS_HIGH fixes=0.16.0
  starlette==0.37.2 PYSEC-2026-1943 severity=UNASSESSED_TREATED_AS_HIGH fixes=0.40.0
  starlette==0.37.2 PYSEC-2026-1941 severity=UNASSESSED_TREATED_AS_HIGH fixes=0.47.2
  starlette==0.37.2 PYSEC-2026-161 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.0.1
  starlette==0.37.2 PYSEC-2026-2281 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.1.0
  starlette==0.37.2 PYSEC-2026-2280 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.1.0
  starlette==0.37.2 PYSEC-2026-249 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.3.1
  starlette==0.37.2 PYSEC-2026-248 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.3.0
MANIFEST 05_teachme_service\requirements.txt findings=7
  click==8.3.1 PYSEC-2026-2132 severity=UNASSESSED_TREATED_AS_HIGH fixes=8.3.3
  starlette==0.50.0 PYSEC-2026-161 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.0.1
  starlette==0.50.0 PYSEC-2026-2281 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.1.0
  starlette==0.50.0 PYSEC-2026-2280 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.1.0
  starlette==0.50.0 PYSEC-2026-249 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.3.1
  starlette==0.50.0 PYSEC-2026-248 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.3.0
  idna==3.11 PYSEC-2026-215 severity=UNASSESSED_TREATED_AS_HIGH fixes=3.15
MANIFEST 06_enrollment_service\requirements.txt findings=43
  fastapi==0.104.1 PYSEC-2024-38 severity=UNASSESSED_TREATED_AS_HIGH fixes=0.109.1
  python-multipart==0.0.6 PYSEC-2024-38 severity=UNASSESSED_TREATED_AS_HIGH fixes=0.0.7
  python-multipart==0.0.6 PYSEC-2026-1851 severity=UNASSESSED_TREATED_AS_HIGH fixes=0.0.18
  python-multipart==0.0.6 PYSEC-2026-1852 severity=UNASSESSED_TREATED_AS_HIGH fixes=0.0.22
  python-multipart==0.0.6 PYSEC-2026-3038 severity=UNASSESSED_TREATED_AS_HIGH fixes=0.0.26
  python-multipart==0.0.6 PYSEC-2026-3039 severity=UNASSESSED_TREATED_AS_HIGH fixes=0.0.27
  python-multipart==0.0.6 PYSEC-2026-3040 severity=UNASSESSED_TREATED_AS_HIGH fixes=0.0.31
  python-multipart==0.0.6 PYSEC-2026-3036 severity=UNASSESSED_TREATED_AS_HIGH fixes=0.0.30
  python-multipart==0.0.6 PYSEC-2026-3037 severity=UNASSESSED_TREATED_AS_HIGH fixes=0.0.30
  python-multipart==0.0.6 PYSEC-2026-1850 severity=UNASSESSED_TREATED_AS_HIGH fixes=0.0.7
  python-dotenv==1.0.0 PYSEC-2026-2270 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.2.2
  pillow==10.1.0 PYSEC-2026-457 severity=UNASSESSED_TREATED_AS_HIGH fixes=10.2.0
  pillow==10.1.0 PYSEC-2026-1793 severity=UNASSESSED_TREATED_AS_HIGH fixes=10.3.0
  pillow==10.1.0 PYSEC-2026-165 severity=UNASSESSED_TREATED_AS_HIGH fixes=12.2.0
  pillow==10.1.0 PYSEC-2026-2874 severity=UNASSESSED_TREATED_AS_HIGH fixes=12.2.0
  pillow==10.1.0 PYSEC-2026-2253 severity=UNASSESSED_TREATED_AS_HIGH fixes=12.3.0
  pillow==10.1.0 PYSEC-2026-2255 severity=UNASSESSED_TREATED_AS_HIGH fixes=12.3.0
  pillow==10.1.0 PYSEC-2026-2257 severity=UNASSESSED_TREATED_AS_HIGH fixes=12.3.0
  pillow==10.1.0 PYSEC-2026-2256 severity=UNASSESSED_TREATED_AS_HIGH fixes=12.3.0
  pillow==10.1.0 PYSEC-2026-2254 severity=UNASSESSED_TREATED_AS_HIGH fixes=12.3.0
  pillow==10.1.0 PYSEC-2026-3453 severity=UNASSESSED_TREATED_AS_HIGH fixes=12.3.0
  pillow==10.1.0 PYSEC-2026-3451 severity=UNASSESSED_TREATED_AS_HIGH fixes=12.3.0
  pillow==10.1.0 PYSEC-2026-3493 severity=UNASSESSED_TREATED_AS_HIGH fixes=12.3.0
  pillow==10.1.0 PYSEC-2026-3454 severity=UNASSESSED_TREATED_AS_HIGH fixes=12.3.0
  pillow==10.1.0 PYSEC-2026-3494 severity=UNASSESSED_TREATED_AS_HIGH fixes=12.3.0
  pillow==10.1.0 PYSEC-2026-3495 severity=UNASSESSED_TREATED_AS_HIGH fixes=12.3.0
  pillow==10.1.0 PYSEC-2026-3496 severity=UNASSESSED_TREATED_AS_HIGH fixes=12.3.0
  streamlit==1.28.0 PYSEC-2024-153 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.37.0
  streamlit==1.28.0 PYSEC-2026-2285 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.54.0
  streamlit==1.28.0 PYSEC-2026-212 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.53.1
  streamlit==1.28.0 GHSA-8qw9-gf7w-42x5 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.30.0
  requests==2.31.0 PYSEC-2026-1873 severity=UNASSESSED_TREATED_AS_HIGH fixes=2.32.0
  requests==2.31.0 PYSEC-2026-1872 severity=UNASSESSED_TREATED_AS_HIGH fixes=2.32.4
  requests==2.31.0 PYSEC-2026-2275 severity=UNASSESSED_TREATED_AS_HIGH fixes=2.33.0
  h11==0.14.0 PYSEC-2026-348 severity=UNASSESSED_TREATED_AS_HIGH fixes=0.16.0
  protobuf==4.25.9 PYSEC-2026-1805 severity=UNASSESSED_TREATED_AS_HIGH fixes=5.29.6,6.33.5
  starlette==0.27.0 PYSEC-2026-1943 severity=UNASSESSED_TREATED_AS_HIGH fixes=0.40.0
  starlette==0.27.0 PYSEC-2026-1941 severity=UNASSESSED_TREATED_AS_HIGH fixes=0.47.2
  starlette==0.27.0 PYSEC-2026-161 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.0.1
  starlette==0.27.0 PYSEC-2026-2281 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.1.0
  starlette==0.27.0 PYSEC-2026-2280 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.1.0
  starlette==0.27.0 PYSEC-2026-249 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.3.1
  starlette==0.27.0 PYSEC-2026-248 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.3.0
MANIFEST 07_llm_service\requirements.txt findings=7
  python-dotenv==1.0.0 PYSEC-2026-2270 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.2.2
  requests==2.32.5 PYSEC-2026-2275 severity=UNASSESSED_TREATED_AS_HIGH fixes=2.33.0
  starlette==0.52.1 PYSEC-2026-161 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.0.1
  starlette==0.52.1 PYSEC-2026-2281 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.1.0
  starlette==0.52.1 PYSEC-2026-2280 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.1.0
  starlette==0.52.1 PYSEC-2026-249 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.3.1
  starlette==0.52.1 PYSEC-2026-248 severity=UNASSESSED_TREATED_AS_HIGH fixes=1.3.0
REPORT D:\Internship\Nexi\NEXI_Dev\logs\dependency-audit.json
SCAN_RESULT manifests=7 findings=118 errors=3 exit=FAIL
```

New findings: 118 manifest/advisory entries. TTS=61, TeachMe=7, Enrollment=43, LLM=7. Root/Audio timed out at 180 seconds; Central references unavailable `anyio==4.1.1`; Vision pins conflict. Those three manifests remain NOT CLEARED. Vulnerability upgrades and manifest repair were not silently performed; they require coordinated remediation.

```text
F_AUDIT_NEGATIVE_CONTROL skipped_package=FAIL_CLOSED known_finding=PRESERVED duplicate_advisory=DEDUPED severity_not_invented=True
```

Audit-tool pins were checked against installed metadata: `pip-audit==2.10.1`, `CacheControl==0.14.4`, `boolean.py==5.0`, `cyclonedx-python-lib==11.12.0`, `defusedxml==0.7.1`, `license-expression==30.4.4`, `packageurl-python==0.17.6`, `pip-api==0.0.35`, `pip-requirements-parser==32.0.1`, `py-serializable==2.1.0`, `sortedcontainers==2.4.0`, `tomli==2.4.1`, `tomli-w==1.2.0`.

## G — Full executed test results and baseline reconciliation

The following is the complete executed case list from the passing JUnit report, not an inferred coverage count.

```text
tests.test_phase4::test_b_every_basic_command_bypasses_teachme_and_llm PASSED
tests.test_phase4::test_c_genuine_no_match_never_calls_llm PASSED
tests.test_phase4::test_d_server_prompt_extra_field_rejection_and_english_gate PASSED
tests.test_phase4::test_f_ungrounded_output_is_caught PASSED
tests.test_phase4::test_phase4_adversarial_25_cases PASSED
tests.test_phase5::test_j_match_issues_token_no_match_does_not_and_expiry_fails PASSED
tests.test_phase7_cloud_sync::test_d_static_boundary_negative_control_then_clean PASSED
tests.test_phase8_unit::test_unit_jwt_session_validation_preserves_subject PASSED
tests.test_phase8_unit::test_unit_outbox_acknowledgement_transitions_state PASSED
tests.test_phase8_unit::test_unit_rag_grounding_containment_rejects_extra_claims PASSED
tests.test_phase8_unit::test_unit_resource_authority_grant_priority_and_release PASSED
tests.test_phase4::test_a_real_http_learn_then_search PASSED
tests.test_phase4::test_d_audio_uses_central_policy_and_preserves_focus_check PASSED
tests.test_phase4::test_e_client_response_shape_and_failure_propagation PASSED
tests.test_phase4::test_e_llm_contract_clamps_and_provider_failure_is_failure PASSED
tests.test_phase5::test_j_new_central_route_wraps_existing_audio_client PASSED
tests.test_phase6::test_identity_contract_uses_user_id_end_to_end PASSED
tests.test_phase6::test_phase2_protected_llm_contract PASSED
tests.test_phase7_cloud_sync::test_a_provider_agnostic_client_deduplicates_and_swaps_config PASSED
tests.test_phase8_contracts::test_contract_audio_central_restricted_rag_boundary PASSED
tests.test_phase8_contracts::test_contract_central_llm_generation_shape PASSED
tests.test_phase8_contracts::test_contract_central_teachme_payload_and_embedding_dimension PASSED
tests.test_phase8_contracts::test_contract_enrollment_audio_process_voice_shape PASSED
tests.test_phase8_contracts::test_contract_enrollment_central_registration PASSED
tests.test_phase8_contracts::test_contract_enrollment_vision_upload_and_response PASSED
tests.test_route_naming_normalization::test_b_registration_routes_and_old_route_retired PASSED
tests.test_route_naming_normalization::test_c_user_creation_alias_is_identical_and_callers_migrated PASSED
tests.test_route_naming_normalization::test_d_embedded_history_is_gone_and_durable_route_serves_data PASSED
tests.test_route_naming_normalization::test_e_registration_with_embeddings_alias_is_identical PASSED
tests.test_route_naming_normalization::test_f_teachme_search_aliases_are_identical PASSED
tests.test_route_naming_normalization::test_g_openapi_documents_only_primary_paths PASSED
tests.phase9_security_verification::test_a_https_plaintext_transition_and_bad_ca PASSED
tests.phase9_security_verification::test_b_biometric_ciphertext_and_round_trips PASSED
tests.phase9_security_verification::test_c_all_biometric_stores_survive_previous_key_retirement PASSED
tests.phase9_security_verification::test_c_local_fernet_jwt_and_service_rotation PASSED
tests.phase9_security_verification::test_c_openrouter_rotation_with_https_provider_fixture PASSED
tests.phase9_security_verification::test_c_shared_credentials_live_transition_and_close PASSED
tests.phase9_security_verification::test_d_redaction_negative_controls PASSED
tests.phase9_security_verification::test_e_live_correlation_and_all_service_latencies PASSED
tests.phase9_security_verification::test_f_auditor_cannot_clear_skipped_packages_or_hide_known_findings PASSED
tests.test_phase4::test_a_reembedding_migration_is_idempotent PASSED
tests.test_phase4::test_e_preserves_phase3_llm_focus_deferral PASSED
tests.test_phase5::test_b_shared_internal_trust_rejects_missing_and_accepts_real_credential PASSED
tests.test_phase5::test_c_claim_ownership_no_token_cross_user_own_and_expired PASSED
tests.test_phase5::test_d_teachme_shared_auth_and_missing_jwt_fail_closed PASSED
tests.test_phase5::test_e_explicit_cors_allowlist PASSED
tests.test_phase5::test_f_upload_rejected_before_handler_and_path_traversal PASSED
tests.test_phase5::test_g_pickle_migration_twice_and_existing_verification_flow PASSED
tests.test_phase6::test_phase3_wake_word_during_teachme_combined PASSED
tests.test_phase6::test_shared_error_handler_covers_rate_limit_and_unexpected_failure PASSED
tests.test_phase6::test_video_call_preemption_release_and_screenshot PASSED
tests.test_phase7_cloud_sync::test_c_outbox_migration_twice_and_conversation_round_trip PASSED
tests.test_phase7_cloud_sync::test_g_status_endpoint_is_accurate_and_internally_authenticated PASSED
tests.test_phase5::test_h_rate_limiter_sustains_burst_without_500[central] PASSED
tests.test_phase5::test_h_rate_limiter_sustains_burst_without_500[vision] PASSED
tests.test_phase6::test_phase2_persistence_regression PASSED
tests.test_phase6::test_phase2_resource_authority_regression PASSED
tests.test_phase7_cloud_sync::test_b_shared_retry_failure_then_recovery_timing PASSED
tests.test_phase7_cloud_sync::test_e_supervision_survives_and_restart_uses_persisted_time PASSED
tests.test_phase7_cloud_sync::test_f_ten_batches_failure_retry_and_duplicate_delivery PASSED
tests.test_phase8_resilience::test_resilience_all_seven_services_forced_kill_and_restart PASSED
tests.test_phase8_e2e::test_e2e_enroll_verify_grounded_answer_persist_and_sync_eligible PASSED
```

```text
UNIT       selected=11 passed=11 failed=0 skipped=0
CONTRACT   selected=20 passed=20 failed=0 skipped=0
INTEGRATION selected=22 passed=22 failed=0 skipped=0
RESILIENCE selected=8 passed=8 failed=0 skipped=0
E2E        selected=1 passed=1 failed=0 skipped=0
62 passed in 217.36s (0:03:37)
RECONCILIATION baseline=53 retained=53 missing=0 additional=9 unique=62 failures=0 errors=0
```

| Layer | Phase 8 baseline | Retained baseline | New security checks | Final |
|---|---:|---:|---:|---:|
| Unit | 11 | 11 | 0 | 11 |
| Contract | 20 | 20 | 0 | 20 |
| Integration | 13 | 13 | 9 | 22 |
| Resilience | 8 | 8 | 0 | 8 |
| E2E | 1 | 1 | 0 | 1 |
| Total | 53 | 53 | 9 | 62 |

Recorded red startup/read-deadline evidence (before correction):

```text
AssertionError: TeachMe did not become ready
INFO:     Application startup complete.
INFO:     Uvicorn running on https://127.0.0.1:8014 (Press CTRL+C to quit)
2026-09-12 08:51:21,783 - teachme.request - INFO - REQUEST_END service=teachme method=GET path=/health status=200 duration_ms=2046.473 correlation_id=d053b348-9fb6-4a47-ab84-8767a1933024
2026-09-12 08:51:24,012 - teachme.request - INFO - REQUEST_END service=teachme method=GET path=/health status=200 duration_ms=2008.227 correlation_id=cdb7fe5d-6155-46b6-8200-855da40fdc55
```

Disclosed harness changes: CA-verified HTTPS URLs/listener arguments; a deterministic test-only Fernet key; the existing fake HTTP client's constructor accepts verification options; the isolated TeachMe health caller's read deadline changes from 2 to 5 seconds. Actual startup logs showed existing HTTP 200 responses taking 2.008-2.046 seconds because health includes Vision's existing bounded 2-second probe; the overall 60-second startup deadline and outcome assertions are unchanged. The redaction factory's Uvicorn formatting bug was fixed in application logging, not suppressed.

Sanity checks:

```text
SYNTAX_RESULT files=61 passed=61 failed=0
git diff --check exit_code=0
VERIFICATION_LISTENERS_REMAINING=0
```

## Deployment boundary

Repository controls proven here: verified TLS trust, closed steady-state plaintext listeners, biometric ciphertext with normal application access, dual-key local consumers, redaction negative controls, trace propagation, unchanged baseline behavior. This is not a blanket production-security certification: real CA certificates/domain renewal, restrictive key-file ACLs, secret-management infrastructure, secure legacy backups, vendor key issuance/revocation, vulnerability remediation timelines, Docker deployment validation, and physical hardware remain deployment/external work. Existing committed legacy Enrollment keys are not production secrets and were not deleted or represented as safe.

PHASE 9 NOT CLOSED — the dependency assessment has unresolved manifest errors.

## Approved close-out and Phase 10 preflight

Step 0 is APPROVED CLOSED: the installation transcript shows only
"Successfully installed" lines for the 13 audit-only packages and zero
"Uninstalling" lines, which is real evidence no existing package was
replaced during that install — this is accepted as sufficient, while
explicitly not claiming it is equivalent to a full before/after
resolved-dependency freeze comparison, which does not exist and cannot
now be reconstructed.

Step 1 targeted command (no full-suite rerun):

```powershell
.\venv\Scripts\python.exe -m pytest -q -s tests/phase9_security_verification.py::test_c_openrouter_rotation_with_https_provider_fixture
```

```text
C_OPENROUTER window_old=ACCEPT window_new=ACCEPT closed_old=REJECT closed_new=ACCEPT local_https_provider_fixture=True real_provider_keys_rotated=False
1 passed in 3.79s
```

Real OpenRouter account keys were never rotated. Real-account rotation is a
permanent operator runbook item, not a code deliverable. Billing configuration
does not block acceptance of this tested mechanism.

Step 2 non-installing diagnostics used the existing Python 3.11.9 environment:

```powershell
.\venv\Scripts\python.exe -m pip install --dry-run --ignore-installed --disable-pip-version-check --progress-bar off -r requirements.txt
.\venv\Scripts\python.exe -m pip install --dry-run --ignore-installed --disable-pip-version-check --progress-bar off -r 01_central_server/requirements.txt
.\venv\Scripts\python.exe -m pip install --dry-run --ignore-installed --disable-pip-version-check --progress-bar off -r 02_vision_service/requirements.txt
```

Root/Audio resolution exited 0. Actual resolver excerpts:

```text
INFO: pip is looking at multiple versions of tensorflow to determine which version is compatible with other requirements. This could take a while.
INFO: pip is looking at multiple versions of facenet-pytorch to determine which version is compatible with other requirements. This could take a while.
INFO: pip is looking at multiple versions of opencv-contrib-python to determine which version is compatible with other requirements. This could take a while.
```

This establishes bounded successful resolution here, not a successful install
or vulnerability assessment. The original scanner only recorded its aggregate
180-second deadline, so its original resolution-versus-advisory timing cannot
be reconstructed. No timeout or dependency pin was changed.

Central diagnostic exited 1. Actual error:

```text
ERROR: No matching distribution found for anyio==4.1.1
```

Vision diagnostic exited 1. Actual conflict explanation:

```text
The conflict is caused by:
    fastapi 0.104.1 depends on typing-extensions>=4.8.0
    pydantic 2.5.0 depends on typing-extensions>=4.6.1
    torch 2.0.1 depends on typing-extensions
    pydantic-core 2.14.1 depends on typing-extensions!=4.7.0 and >=4.6.0
    tensorflow-intel 2.13.1 depends on typing-extensions<4.6.0 and >=3.6.6
ERROR: ResolutionImpossible: for help visit https://pip.pypa.io/en/latest/topics/dependency-resolution/#dealing-with-dependency-conflicts
```

Neither manifest can be repaired with a scanner flag. Repairs are stopped under
the explicit no-dependency-version-change rule. They are not clean scans.

Phase 10 preflight found no Docker runtime command:

```text
docker : The term 'docker' is not recognized as the name of a cmdlet, function, script file, or operable program.
```

Neither docker-compose nor podman was found; the usual Docker Desktop executable
path was absent. No container build, compose health, or clean-checkout Docker
acceptance is claimed. No application files, package pins, or deletion candidates
were changed during this close-out. Phase 10 A-I remain uncompleted.

Root-only audit retry completed with the unchanged 180-second limit in 158.671 seconds. It returned 121 findings and no audit error. The diagnostic wrapper exited 0 because it prints the result; the scanner's finding policy remains FAIL. No package version, scanner flag, or timeout changed.

Full root retry findings (rendered from actual JSON output; severity for each is UNASSESSED_TREATED_AS_HIGH):

```text
torch==2.10.0 PYSEC-2026-139 fixes=none
torch==2.10.0 PYSEC-2025-194 fixes=2.13.0
opencv-python==4.8.0.76 PYSEC-2023-183 fixes=4.8.1.78
opencv-python==4.8.0.76 GHSA-qr4w-53vh-m672 fixes=4.8.1.78
pillow==12.1.1 PYSEC-2026-2250 fixes=12.2.0
pillow==12.1.1 PYSEC-2026-165 fixes=12.2.0
pillow==12.1.1 PYSEC-2026-2251 fixes=12.2.0
pillow==12.1.1 PYSEC-2026-2874 fixes=12.2.0
pillow==12.1.1 PYSEC-2026-2252 fixes=12.2.0
pillow==12.1.1 PYSEC-2026-2253 fixes=12.3.0
pillow==12.1.1 PYSEC-2026-2255 fixes=12.3.0
pillow==12.1.1 PYSEC-2026-2257 fixes=12.3.0
pillow==12.1.1 PYSEC-2026-2256 fixes=12.3.0
pillow==12.1.1 PYSEC-2026-2254 fixes=12.3.0
pillow==12.1.1 PYSEC-2026-3453 fixes=12.3.0
pillow==12.1.1 PYSEC-2026-3451 fixes=12.3.0
pillow==12.1.1 PYSEC-2026-3452 fixes=12.3.0
pillow==12.1.1 PYSEC-2026-3493 fixes=12.3.0
pillow==12.1.1 PYSEC-2026-3454 fixes=12.3.0
pillow==12.1.1 PYSEC-2026-3494 fixes=12.3.0
pillow==12.1.1 PYSEC-2026-3495 fixes=12.3.0
pillow==12.1.1 PYSEC-2026-3496 fixes=12.3.0
starlette==0.52.1 PYSEC-2026-161 fixes=1.0.1
starlette==0.52.1 PYSEC-2026-2281 fixes=1.1.0
starlette==0.52.1 PYSEC-2026-2280 fixes=1.1.0
starlette==0.52.1 PYSEC-2026-249 fixes=1.3.1
starlette==0.52.1 PYSEC-2026-248 fixes=1.3.0
pytest==7.4.3 PYSEC-2026-1845 fixes=9.0.3
msgpack==1.1.2 PYSEC-2026-3625 fixes=1.2.1
requests==2.32.5 PYSEC-2026-2275 fixes=2.33.0
idna==3.11 PYSEC-2026-215 fixes=3.15
urllib3==2.6.3 PYSEC-2026-141 fixes=2.7.0
urllib3==2.6.3 PYSEC-2026-142 fixes=2.7.0
httplib2==0.31.2 PYSEC-2026-3444 fixes=0.32.0
aiohttp==3.13.3 PYSEC-2026-2097 fixes=3.13.4
aiohttp==3.13.3 PYSEC-2026-2095 fixes=3.13.4
aiohttp==3.13.3 PYSEC-2026-2098 fixes=3.13.4
aiohttp==3.13.3 PYSEC-2026-2099 fixes=3.13.4
aiohttp==3.13.3 PYSEC-2026-2101 fixes=3.13.4
aiohttp==3.13.3 PYSEC-2026-2100 fixes=3.13.4
aiohttp==3.13.3 PYSEC-2026-2102 fixes=3.13.4
aiohttp==3.13.3 PYSEC-2026-2103 fixes=3.13.4
aiohttp==3.13.3 PYSEC-2026-2094 fixes=3.13.4
aiohttp==3.13.3 PYSEC-2026-2096 fixes=3.13.4
aiohttp==3.13.3 PYSEC-2026-2104 fixes=3.14.0
aiohttp==3.13.3 PYSEC-2026-2105 fixes=3.14.0
aiohttp==3.13.3 PYSEC-2026-2107 fixes=3.14.1
aiohttp==3.13.3 PYSEC-2026-2112 fixes=3.14.1
aiohttp==3.13.3 PYSEC-2026-2110 fixes=3.14.1
aiohttp==3.13.3 PYSEC-2026-2106 fixes=3.14.0
aiohttp==3.13.3 PYSEC-2026-2109 fixes=3.14.1
aiohttp==3.13.3 PYSEC-2026-2111 fixes=3.14.1
aiohttp==3.13.3 PYSEC-2026-2113 fixes=3.14.1
aiohttp==3.13.3 PYSEC-2026-2108 fixes=3.14.1
aiohttp==3.13.3 PYSEC-2026-237 fixes=3.14.1
aiohttp==3.13.3 PYSEC-2026-3547 fixes=3.14.2
aiohttp==3.13.3 PYSEC-2026-3546 fixes=3.14.2
aiohttp==3.13.3 PYSEC-2026-3545 fixes=3.14.3
click==8.3.1 PYSEC-2026-2132 fixes=8.3.3
cryptography==46.0.5 PYSEC-2026-35 fixes=46.0.6
cryptography==46.0.5 PYSEC-2026-36 fixes=46.0.7
cryptography==46.0.5 PYSEC-2026-3554 fixes=49.0.0
cryptography==46.0.5 PYSEC-2026-3552 fixes=50.0.0
cryptography==46.0.5 PYSEC-2026-3553 fixes=49.0.0
cryptography==46.0.5 GHSA-537c-gmf6-5ccf fixes=48.0.1
gdown==5.2.1 PYSEC-2026-2158 fixes=5.2.2
gitpython==3.1.46 PYSEC-2026-2160 fixes=3.1.47
gitpython==3.1.46 PYSEC-2026-2161 fixes=3.1.47
gitpython==3.1.46 PYSEC-2026-2163 fixes=3.1.49
gitpython==3.1.46 PYSEC-2026-2162 fixes=3.1.48
gitpython==3.1.46 PYSEC-2026-3783 fixes=3.1.58
gitpython==3.1.46 PYSEC-2026-3785 fixes=3.1.59
gitpython==3.1.46 PYSEC-2026-3786 fixes=3.1.59
gitpython==3.1.46 PYSEC-2026-3787 fixes=3.1.59
gitpython==3.1.46 PYSEC-2026-3788 fixes=3.1.59
gitpython==3.1.46 PYSEC-2026-3784 fixes=3.1.58
gitpython==3.1.46 PYSEC-2026-3840 fixes=3.1.58
gitpython==3.1.46 PYSEC-2026-3836 fixes=3.1.51
gitpython==3.1.46 PYSEC-2026-3838 fixes=3.1.58
gitpython==3.1.46 PYSEC-2026-3839 fixes=3.1.51
gitpython==3.1.46 PYSEC-2026-3841 fixes=3.1.58
gitpython==3.1.46 PYSEC-2026-3837 fixes=3.1.59
gitpython==3.1.46 PYSEC-2026-3843 fixes=3.1.58
gitpython==3.1.46 PYSEC-2026-3949 fixes=3.1.57
gitpython==3.1.46 PYSEC-2026-3951 fixes=3.1.55
gitpython==3.1.46 PYSEC-2026-3953 fixes=3.1.54
gitpython==3.1.46 PYSEC-2026-3952 fixes=3.1.54
gitpython==3.1.46 PYSEC-2026-3950 fixes=3.1.56
gitpython==3.1.46 PYSEC-2026-3948 fixes=3.1.57
gitpython==3.1.46 CVE-2026-67326 fixes=3.1.50
gitpython==3.1.46 CVE-2026-69097 fixes=3.1.53
gitpython==3.1.46 CVE-2026-73624 fixes=3.1.54
pyasn1==0.6.2 PYSEC-2026-2263 fixes=0.6.3
pyasn1==0.6.2 PYSEC-2026-3456 fixes=0.6.4
pyasn1==0.6.2 PYSEC-2026-3457 fixes=0.6.4
pyasn1==0.6.2 PYSEC-2026-3455 fixes=0.6.4
pydantic-settings==2.13.0 CVE-2026-58203 fixes=2.14.2
pygments==2.19.2 PYSEC-2026-2987 fixes=2.20.0
python-dotenv==1.2.1 PYSEC-2026-2270 fixes=1.2.2
python-multipart==0.0.22 PYSEC-2026-3038 fixes=0.0.26
python-multipart==0.0.22 PYSEC-2026-3039 fixes=0.0.27
python-multipart==0.0.22 PYSEC-2026-3040 fixes=0.0.31
python-multipart==0.0.22 PYSEC-2026-3036 fixes=0.0.30
python-multipart==0.0.22 PYSEC-2026-3037 fixes=0.0.30
soupsieve==2.8.3 PYSEC-2026-3072 fixes=2.8.4
soupsieve==2.8.3 PYSEC-2026-3071 fixes=2.8.4
tornado==6.5.4 PYSEC-2026-2287 fixes=6.5.5
tornado==6.5.4 PYSEC-2026-140 fixes=6.5.5
tornado==6.5.4 PYSEC-2026-3388 fixes=6.5.6
tornado==6.5.4 PYSEC-2026-3387 fixes=6.5.6
tornado==6.5.4 PYSEC-2026-3389 fixes=6.5.6
tornado==6.5.4 PYSEC-2026-3928 fixes=6.5.8
tornado==6.5.4 GHSA-pw6j-qg29-8w7f fixes=6.5.7
tornado==6.5.4 GHSA-8423-8fgw-73vq fixes=6.5.8
pyjwt==2.10.1 PYSEC-2026-120 fixes=2.12.0
pyjwt==2.10.1 PYSEC-2025-183 fixes=none
pyjwt==2.10.1 PYSEC-2026-179 fixes=2.13.0
pyjwt==2.10.1 PYSEC-2026-175 fixes=2.13.0
pyjwt==2.10.1 PYSEC-2026-177 fixes=2.13.0
pyjwt==2.10.1 PYSEC-2026-178 fixes=2.13.0
pyjwt==2.10.1 PYSEC-2026-176 fixes=2.12.1
```

Updated accumulated assessment (four previous successful scans retained, Central/Vision errors reconfirmed, root result replaced; not a fresh seven-manifest run):

```text
BEFORE manifests=7 findings=118 errors=3 exit=FAIL
AFTER manifests=7 findings=239 errors=2 exit=FAIL
```

PHASE 10 NOT CLOSED — Central's unavailable anyio pin and Vision's incompatible typing-extensions constraints require dependency changes prohibited by the current stop condition; Docker is unavailable for the required build and clean-checkout acceptance.

## Phase 10 ground-truth resume

The existing `venv` used for the accepted Phase 9 suite was queried before manifest edits. This is a current snapshot, not a reconstructed historical freeze. Full command output:

```powershell
.\venv\Scripts\python.exe -m pip freeze
```

```text
absl-py==2.4.0
aiofiles==25.1.0
aiohappyeyeballs==2.6.1
aiohttp==3.13.3
aiosignal==1.4.0
altair==6.0.0
annotated-doc==0.0.4
annotated-types==0.7.0
anyio==4.12.1
astunparse==1.6.3
attrs==25.4.0
audioread==3.1.0
beautifulsoup4==4.14.3
blinker==1.9.0
boolean.py==5.0
CacheControl==0.14.4
cachetools==6.2.6
certifi==2026.1.4
cffi==2.0.0
charset-normalizer==3.4.4
click==8.3.1
colorama==0.4.6
contourpy==1.3.3
cryptography==46.0.5
cycler==0.12.1
cyclonedx-python-lib==11.12.0
decorator==4.4.2
deepface==0.0.98
defusedxml==0.7.1
distro==1.9.0
facenet-pytorch==2.5.3
fastapi==0.129.0
fer==22.5.1
ffmpeg==1.4
filelock==3.24.3
fire==0.7.1
Flask==3.1.3
flask-cors==6.0.2
flatbuffers==25.12.19
fonttools==4.61.1
frozenlist==1.8.0
fsspec==2026.2.0
gast==0.4.0
gdown==5.2.1
gitdb==4.0.12
GitPython==3.1.46
google-ai-generativelanguage==0.6.15
google-api-core==2.30.0
google-api-python-client==2.190.0
google-auth==2.48.0
google-auth-httplib2==0.3.0
google-auth-oauthlib==1.0.0
google-genai==1.65.0
google-pasta==0.2.0
googleapis-common-protos==1.72.0
groq==1.0.0
grpcio==1.74.0
grpcio-status==1.71.2
gunicorn==25.1.0
h11==0.16.0
h5py==3.15.1
hf-xet==1.3.2
httpcore==1.0.9
httplib2==0.31.2
httpx==0.28.1
huggingface_hub==1.5.0
idna==3.11
ImageIO==2.37.2
imageio-ffmpeg==0.6.0
iniconfig==2.3.0
itsdangerous==2.2.0
Jinja2==3.1.6
joblib==1.5.3
jsonschema==4.26.0
jsonschema-specifications==2025.9.1
keras==3.15.1
keyboard==0.13.5
kiwisolver==1.4.9
langdetect==1.0.9
lazy_loader==0.4
libclang==18.1.1
librosa==0.11.0
license-expression==30.4.4
lightdsa==0.0.3
lightecc==0.0.4
lightphe==0.0.20
llvmlite==0.46.0
lz4==4.4.5
Markdown==3.10.2
markdown-it-py==4.0.0
MarkupSafe==3.0.3
matplotlib==3.10.8
mdurl==0.1.2
ml_dtypes==0.5.4
more-itertools==10.8.0
moviepy==1.0.3
mpmath==1.3.0
msgpack==1.1.2
mtcnn==1.0.0
multidict==6.7.1
namex==0.1.0
narwhals==2.16.0
networkx==3.6.1
noisereduce==3.0.3
numba==0.64.0
numpy==1.26.4
oauthlib==3.3.1
onnxruntime==1.24.2
opencv-contrib-python==4.11.0.86
opencv-python==4.8.0.76
opt_einsum==3.4.0
optree==0.18.0
packageurl-python==0.17.6
packaging==26.0
pandas==2.3.3
pillow==12.1.1
pip-requirements-parser==32.0.1
pip_api==0.0.35
pip_audit==2.10.1
piper-tts==1.4.1
platformdirs==4.9.2
pluggy==1.6.0
polars==1.38.1
polars-runtime-32==1.38.1
pooch==1.9.0
proglog==0.1.12
prometheus-client==0.19.0
propcache==0.4.1
proto-plus==1.27.1
protobuf==5.29.6
psutil==7.2.2
pvporcupine==4.0.2
py-serializable==2.1.0
pyarrow==23.0.1
pyasn1==0.6.2
pyasn1_modules==0.4.2
PyAudio==0.2.14
pycparser==3.0
pydantic==2.12.5
pydantic-settings==2.13.0
pydantic_core==2.41.5
pydeck==0.9.1
Pygments==2.19.2
PyJWT==2.10.1
pyparsing==3.3.2
PySocks==1.7.1
pytest==7.4.3
pytest-asyncio==0.21.1
python-dateutil==2.9.0.post0
python-dotenv==1.2.1
python-multipart==0.0.22
pytz==2025.2
PyYAML==6.0.3
referencing==0.37.0
regex==2026.1.15
requests==2.32.5
requests-oauthlib==2.0.0
Resemblyzer==0.1.4
retina-face==0.0.17
rich==14.3.3
rpds-py==0.30.0
rsa==4.9.1
safetensors==0.8.0
scikit-image==0.26.0
scikit-learn==1.8.0
scipy==1.11.4
sentence-transformers==6.0.1
shellingham==1.5.4
six==1.17.0
smmap==5.0.2
sniffio==1.3.1
sortedcontainers==2.4.0
sounddevice==0.5.5
soundfile==0.13.1
soupsieve==2.8.3
soxr==1.0.0
starlette==0.52.1
streamlit==1.54.0
sympy==1.14.0
tenacity==9.1.4
tensorboard==2.20.0
tensorboard-data-server==0.7.2
tensorflow==2.20.0
termcolor==3.3.0
threadpoolctl==3.6.0
tifffile==2026.2.16
tiktoken==0.12.0
tokenizers==0.23.2
toml==0.10.2
tomli==2.4.1
tomli_w==1.2.0
torch==2.10.0
torchaudio==2.10.0
torchvision==0.25.0
tornado==6.5.4
tqdm==4.67.3
transformers==5.17.0
typer==0.24.1
typer-slim==0.24.0
typing==3.7.4.3
typing-inspection==0.4.2
typing_extensions==4.15.0
tzdata==2025.3
ultralytics==8.4.19
ultralytics-thop==2.0.18
uritemplate==4.2.0
urllib3==2.6.3
uvicorn==0.41.0
watchdog==6.0.0
webrtcvad==2.0.10
webrtcvad-wheels==2.0.14
websockets==16.0
Werkzeug==3.1.6
wrapt==2.1.1
yarl==1.22.0
```

Only Central's `anyio==4.1.1` was changed to installed `anyio==4.12.1`, and Vision's explicit `tensorflow==2.13.1` line was removed. Other pins and the tested environment were not changed.

Central standalone install into a fresh temporary venv succeeded. Actual checks:

```text
No broken requirements found.
SHARED_REQUIRED_IMPORTS {'jwt': False, 'cryptography': False, 'numpy': False, 'langdetect': False}
ModuleNotFoundError: No module named 'pydantic_settings'
```

The last error is from importing `main` in that clean environment; successful pip installation does not establish application startup. Existing requirements omit runtime dependencies. This contradicts the premise that the per-service dependency inventory had already passed; it had not.

AST inspection covered 222 Python files under the seven services and shared. There were zero direct TensorFlow/Keras imports; four DeepFace imports occur in Vision's face detector/face streaming paths. Ground truth includes TensorFlow 2.20.0 and Keras 3.15.1. DeepFace declares TensorFlow>=1.9.0 and Keras>=2.2.0, so removing Vision's explicit pin does not eliminate its transitive TensorFlow dependency.

The corrected in-process Vision comparison used local YOLO weights and actual inference, with TensorFlow imports blocked in a fresh process for the second run:

```text
VISION_HEALTH baseline 200 {"status":"degraded","camera":"unavailable","face_model":"unavailable","opencv_version":"4.11.0","emotion_detection":"disabled","timestamp":"2026-09-12T10:07:42.473527"}
YOLO_AVAILABLE True
YOLO_REAL_INFERENCE {'objects_detected': 0, 'detections': []}
TENSORFLOW_IMPORTED True
VISION_HEALTH blocked 200 {"status":"degraded","camera":"unavailable","face_model":"unavailable","opencv_version":"4.11.0","emotion_detection":"disabled","timestamp":"2026-09-12T10:08:05.380741"}
YOLO_AVAILABLE True
YOLO_REAL_INFERENCE {'objects_detected': 0, 'detections': []}
TENSORFLOW_IMPORTED False
```

This proves startup and PyTorch YOLO inference do not require TensorFlow here. It does not claim physical camera or working face recognition. The initial diagnostic had an import alias mistake and attempted a model download from the repository root; it was corrected to use `importlib.import_module` and the service directory's existing weights. No application code was patched around those diagnostic failures.

Actual anyio consistency output:

```text
requirements.txt: anyio==4.12.1
01_central_server\requirements.txt: anyio==4.12.1
05_teachme_service\requirements.txt: anyio==4.12.0
```

TeachMe remains inconsistent; changing its pin is outside this narrow authorization. Vision's FastAPI 0.104.1 additionally resolves anyio<4.0.0,>=3.7.1, so matching root's 4.12.1 across services is not possible while retaining all other pins.

Vision's corrected manifest still failed non-installing standalone resolution (exit 1). Actual final resolver output:

```text
ERROR: Cannot install -r 02_vision_service/requirements.txt (line 11), deepface and keras==2.13.1 because these package versions have conflicting dependencies.

The conflict is caused by:
    The user requested keras==2.13.1
    deepface 0.0.79 depends on keras>=2.2.0
    tensorflow 2.21.0 depends on keras>=3.12.0
    tensorflow 2.20.0 depends on keras>=3.10.0
    tensorflow 2.19.1 depends on keras>=3.5.0
    tensorflow 2.19.0 depends on keras>=3.5.0
    tensorflow 2.18.1 depends on keras>=3.5.0

Additionally, some packages in these conflicts have no matching distributions available for your environment:
    keras

To fix this you could try to:
1. loosen the range of package versions you've specified
2. remove package versions to allow pip to attempt to solve the dependency conflict

ERROR: ResolutionImpossible: for help visit https://pip.pypa.io/en/latest/topics/dependency-resolution/#dealing-with-dependency-conflicts
```

This triggers the explicit stop condition: changing the remaining Keras pin or
the DeepFace package would exceed the authorized anyio/TensorFlow changes.
No such change was made. Vision's clean installation/import verification cannot
be claimed to pass. Central's clean install passes but its application import
fails because its manifest is incomplete, as shown above.

Step 5 commands were both attempted:

```powershell
docker version
docker compose version
```

Both returned `CommandNotFoundException`: the term `docker` is not recognized.
Docker Desktop/environment setup remains a human action. Step 6 was not started.

| Step | Item | Status | Files changed | Verification command | Verification result | Deferred work |
|---|---|---|---|---|---|---|
| 1 | Ground-truth freeze | DONE | This report | `venv/Scripts/python.exe -m pip freeze` | Full current freeze above | None |
| 2 | Central anyio correction | DONE | `01_central_server/requirements.txt` | Clean temporary venv install; `pip check` | Installation succeeded; no broken requirements | Separate application import gap in step 4 |
| 3 | TensorFlow necessity and explicit pin | PARTIAL | `02_vision_service/requirements.txt` | AST, exclusion probe, Vision resolver | Same face degradation; YOLO inference works without TensorFlow; remaining Keras constraint prevents clean installation | Scope decision for Keras/DeepFace dependencies |
| 4 | Standalone imports and consistency | BLOCKED | None | Clean `import main`; anyio comparison | Missing pydantic_settings; jwt/crypto/numpy/langdetect absent; TeachMe anyio differs | Complete dependency inventory with approved scope |
| 5 | Docker availability | BLOCKED | None | `docker version`; `docker compose version` | Both CommandNotFoundException | Install/configure Docker Desktop |
| 6 | Remaining Phase 10 execution | BLOCKED | None | Not run | Dependency stop and Docker unavailable | C-I implementation and acceptance |

Post-edit real HTTPS probe of the authoritative Vision app, using the unchanged
verified environment and certificate verification, completed successfully:

```text
VISION_LIVE_HTTPS 200 {"status":"degraded","camera":"unavailable","face_model":"unavailable","opencv_version":"4.11.0","emotion_detection":"disabled","timestamp":"2026-09-12T10:27:02.940708"}
YOLO yolov8n loaded successfully
Object detection is available (yolov8n)
Uvicorn running on https://127.0.0.1:8011
GET /health HTTP/1.1 200 OK
```

The first HTTPS diagnostic failed because its subprocess output pipe was not
drained during polling; logs showed the listener bound and the health request
started before logging stalled. The corrected diagnostic drains output in a
thread and passes with the same 90-second deadline. The temporary listener was
stopped and waited for after the probe. This is not verification in a clean
Vision environment; that environment remains blocked by dependency resolution.

Final comparison: all 215 lines of the verified environment's pip freeze are
unchanged. No application packages were installed into that environment. The
isolated Central installation remains under the system temporary directory
`nexi-central-install-24029579781c477ab6b0ab9a618d7e69` for reproducible inspection.

PHASE 10 NOT CLOSED — Vision's remaining Keras/DeepFace dependency conflict requires changes outside the authorized scope; Central's manifest lacks runtime dependencies; cross-service anyio versions remain inconsistent; Docker is unavailable.

## Phase 10 final-fix resume (2026-09-13)

This section supersedes the preceding dependency blockers where explicitly
verified below. No application code, retry implementation, tests, or dead-code
candidates were changed in this resume. The original verified venv was not used
as an installation target. No existing version was changed except the approved
TeachMe anyio alignment; Central's anyio correction and Vision's TensorFlow-pin
removal were already present when this resume began.

| # | Item | Status | Files changed | Verification command | Verification result (actual output) | Deferred work |
|---|---|---|---|---|---|---|
| Fix 1 | Central runtime manifest | DONE | `01_central_server/requirements.txt` | Fresh venv, `pip install -r 01_central_server/requirements.txt`, `pip check`; migrate temporary DB, import `main`, start Uvicorn, HTTP `/health` | `No broken requirements found.`; `CENTRAL_REAL_APP_IMPORT=PASS`; `CENTRAL_HEALTH_HTTP=200`; `{"status":"healthy","service":"central_server"}` | Full isolated RAG/provider behavior was not tested by this startup probe |
| Fix 2 | anyio alignment | DONE | `05_teachme_service/requirements.txt` | Parse root and all per-service requirement files, assert one explicit anyio version | `ANYIO_EXPLICIT_PIN_CONSISTENCY=PASS` | Other packages' cross-service versions remain outside this narrow check |
| Fix 3 | Optional DeepFace | PARTIAL | `02_vision_service/requirements.txt` | Clean required-only install, `pip check`, actual YOLO inference, actual app import; existing-venv HTTPS health with DeepFace unavailable | Required-only `pip check` and inference pass; clean app import fails: `ModuleNotFoundError: No module named 'pydantic_settings'` | Additional manifest/runtime settings conflict requires approval; clean-environment health cannot pass yet |
| C | Retry/circuit-breaker consolidation | BLOCKED | None | Not run | Not executed after the prerequisite startup failure | Consolidation and its separate 53-test gate |
| D | Individually proven dead-code removal | BLOCKED | None | Read-only caller searches only | Naming-alias regression callers and a test reading the enhanced harness were found; no files deleted | Individual proofs, parity checks, authorized removals and separate 62-test gate |
| E | Remaining stale dependencies | BLOCKED | None beyond Fix 3's optional face-model entries | No independent post-cleanup service verification | Not executed | Scoped import proofs and startup/regression checks |
| I | Native docs/OpenAPI finalization | PARTIAL | `README.md`, this record | Document actual verification state | README explicitly distinguishes passing installs/inference from failing Vision startup and unverified Docker guidance | Final OpenAPI generation and verified setup walkthrough after the dependency decision |

### Fix 1: tested versions and real isolated startup

Current tested-environment metadata query:

```text
pydantic-settings==2.13.0
PyJWT==2.10.1
cryptography==46.0.5
numpy==1.26.4
langdetect==1.0.9
psutil==7.2.2
anyio==4.12.1
```

The five requested runtime entries were added at exactly these versions. The
first real app import, after initializing a temporary SQLite/outbox database,
also exposed `ModuleNotFoundError: No module named 'psutil'` at
`resource_authority.py:13`. Its existing tested version, `psutil==7.2.2`, was
added without changing authority code or another existing package pin.

Verification environment:
`C:\Users\asdfg\AppData\Local\Temp\nexi-central-fixed-1992a072fcfa44a69820717c67270a68`.

```text
Successfully installed psutil-7.2.2
No broken requirements found.
conversations: before=0 after=0 parity=True added=synced,batch_id,sync_attempted_at,sync_succeeded_at
conversations: before=0 after=0 parity=True added=none
CENTRAL_REAL_APP_IMPORT=PASS
Application startup complete.
Uvicorn running on http://127.0.0.1:18700
CENTRAL_HEALTH_HTTP=200
{"status":"healthy","service":"central_server"}
Application shutdown complete.
```

This was an isolated diagnostic listener, with a temporary DB and fake Fernet
fixture value, not a change to the production TLS launcher. Its thread was
stopped and joined. The premature import attempted while installation was
still running is not counted as a manifest failure; the uninitialized-DB probe
was corrected using the existing outbox migration before startup.

### Fix 2: explicit-pin consistency

```text
01_central_server\requirements.txt | anyio | 4.12.1
05_teachme_service\requirements.txt | anyio | 4.12.1
requirements.txt | anyio | 4.12.1
ANYIO_EXPLICIT_PIN_CONSISTENCY=PASS
```

This proves explicit pins, not equal transitive resolved versions in every
service. Vision's historical FastAPI pin resolves anyio 3.7.1 independently.

### Fix 3: required-only environment and unchanged face degradation

DeepFace and Keras are now commented optional historical entries, excluded from
normal `pip install -r requirements.txt`. They are not advertised as a tested
compatible optional stack. Existing startup model-error handling was unchanged.

Verification environment:
`C:\Users\asdfg\AppData\Local\Temp\nexi-vision-required-fb21b2f2e0aa49bea1257ac329cd1b78`.
An initial PyPI wheel download timed out with
`ReadTimeoutError: HTTPSConnectionPool(host='files.pythonhosted.org', port=443): Read timed out.`
The install was retried with a 60-second pip network-read timeout and unchanged
pins; subsequent verification of the resulting environment gave:

```text
No broken requirements found.
fastapi==0.104.1
pydantic==2.5.0
numpy==1.24.3
torch==2.0.1
torchvision==0.15.2
ultralytics==8.0.196
deepface=NOT_INSTALLED
keras=NOT_INSTALLED
tensorflow=NOT_INSTALLED
pydantic-settings=NOT_INSTALLED
cryptography=NOT_INSTALLED
psutil==7.2.2
VISION_ISOLATED_REQUIRED_REAL_YOLO_INFERENCE={'objects_detected': 0, 'detections': []}
```

Inference loaded the actual `object_detector.py` using importlib so that it
could be verified independently of the failing package/app import. It ran real
local YOLO weights against a generated 320x320 image; it was not a mocked model
or a claim of camera hardware coverage. An earlier diagnostic used the wrong
method name `detect_objects`; the actual method `detect` was used for the
passing verification above.

Clean actual app import:

```text
Traceback (most recent call last):
  File "<string>", line 1, in <module>
  File "D:\Internship\Nexi\NEXI_Dev\02_vision_service\vision_service\__init__.py", line 9, in <module>
    from .app import app, create_app
  File "D:\Internship\Nexi\NEXI_Dev\02_vision_service\vision_service\app.py", line 15, in <module>
    from shared.request_middleware import install_request_observability
  File "D:\Internship\Nexi\NEXI_Dev\shared\request_middleware.py", line 10, in <module>
    from config.ssl_config import get_tls_config
  File "D:\Internship\Nexi\NEXI_Dev\config\__init__.py", line 3, in <module>
    from config.settings import Settings
  File "D:\Internship\Nexi\NEXI_Dev\config\settings.py", line 9, in <module>
    from pydantic_settings import BaseSettings
ModuleNotFoundError: No module named 'pydantic_settings'
```

Non-installing resolver check:
`venv/Scripts/python.exe -m pip install --dry-run --ignore-installed pydantic==2.5.0 pydantic-settings==2.13.0`:

```text
ERROR: Cannot install pydantic-settings==2.13.0 and pydantic==2.5.0 because these package versions have conflicting dependencies.
The conflict is caused by:
    The user requested pydantic==2.5.0
    pydantic-settings 2.13.0 depends on pydantic>=2.7.0
ERROR: ResolutionImpossible
```

Separate existing-tested-environment probe, with `deepface` explicitly made
unavailable and certificate verification against the configured CA:

```text
VISION_NO_DEEPFACE_REAL_YOLO_INFERENCE={'objects_detected': 0, 'detections': []}
Critical error loading embedding model: import of deepface halted; None in sys.modules
Service continuing but may have limited functionality
YOLO yolov8n loaded successfully
Object detection is available (yolov8n)
Application startup complete.
Uvicorn running on https://127.0.0.1:18701
GET /health HTTP/1.1 200 OK
VISION_LIVE_HTTPS=200 {"status":"degraded","camera":"unavailable","face_model":"unavailable","opencv_version":"4.11.0","emotion_detection":"disabled","timestamp":"2026-09-13T00:45:14.975305"}
Application shutdown complete.
```

The diagnostic listener was stopped and joined. Its initial invocation omitted
the absolute repository path after changing cwd; that diagnostic was corrected
without changing application code. This live health proof is expressly NOT a
clean required-only environment startup proof.

No Pydantic pin was changed and no settings import was bypassed in application
code. Further changes require an explicit dependency-scope decision. Docker
Desktop must be installed and running on the host machine before F/G/H can
execute; no Docker-dependent task was attempted.

PHASE 10 NOT CLOSED — Vision's clean application startup requires resolving its shared settings dependency versus pydantic==2.5.0 under an approved scope; C/D/E and final verification remain unexecuted; Docker-dependent F/G/H require Docker Desktop.

## Phase 10 Fix 4 and protected re-verification (2026-09-13)

This section records only new results and supersedes the preceding Vision import
blocker. The recorded 215-package freeze was used without recapturing it. No
application code, tests, vision-specific package versions, or optional face-model
entries were changed. No packages were installed into the protected test venv.

### Fix 4 manifest changes

```diff
-fastapi==0.104.1
+fastapi==0.129.0
-pydantic==2.5.0
+pydantic==2.12.5
+pydantic-settings==2.13.0
+cryptography==46.0.5
+python-multipart==0.0.22
-numpy==1.24.3
+numpy==1.26.4
```

The additional `python-multipart` line closes a real runtime gap exposed by the
required real-app import, not a YOLO-only import. Its version is from the existing
freeze (above). Before adding it, the new isolated installation passed `pip check`
but the actual app import failed while registering the existing upload route:

```text
No broken requirements found.
  File "02_vision_service/vision_service/routes/detection.py", line 143, in <module>
    @router.post("/detect/faces/upload", response_model=FaceDetectionResponse)
RuntimeError: Form data requires "python-multipart" to be installed.
```

### 1. Isolated required-only installation

Fresh environment:
`C:\Users\asdfg\AppData\Local\Temp\nexi-vision-fix4-5cd9ba4a3a254a5da681821bf72d9b55`.
It was created with `venv/Scripts/python.exe -m venv`; the only installation input
was Vision's required manifest. After the runtime gap above was corrected, the
same manifest was installed again into that new environment.

```powershell
& 'C:\Users\asdfg\AppData\Local\Temp\nexi-vision-fix4-5cd9ba4a3a254a5da681821bf72d9b55\Scripts\python.exe' -m pip install -r 02_vision_service/requirements.txt
& 'C:\Users\asdfg\AppData\Local\Temp\nexi-vision-fix4-5cd9ba4a3a254a5da681821bf72d9b55\Scripts\python.exe' -m pip check
```

```text
Successfully installed MarkupSafe-3.0.3 Pillow-10.0.1 PyWavelets-1.9.0 annotated-doc-0.0.5 annotated-types-0.8.0 anyio-4.15.1 certifi-2026.7.22 cffi-2.1.1 charset_normalizer-3.5.1 click-8.5.0 colorama-0.4.6 contourpy-1.3.3 cryptography-46.0.5 cycler-0.12.1 fastapi-0.129.0 filelock-3.32.6 fonttools-4.65.0 h11-0.14.0 httpcore-0.18.0 httptools-0.8.0 httpx-0.25.0 idna-3.19 imageio-2.37.4 jinja2-3.1.6 kiwisolver-1.5.1 lazy_loader-0.5 matplotlib-3.11.2 mpmath-1.3.0 networkx-3.6.1 numpy-1.26.4 opencv-python-4.8.0.76 packaging-26.3 pandas-3.0.5 psutil-7.2.2 py-cpuinfo-9.0.0 pycparser-3.0 pydantic-2.12.5 pydantic-core-2.41.5 pydantic-settings-2.13.0 pyparsing-3.3.2 python-dateutil-2.9.0.post0 python-dotenv-1.0.0 pyyaml-6.0.3 requests-2.34.2 scikit-image-0.21.0 scipy-1.11.2 seaborn-0.13.2 six-1.17.0 sniffio-1.3.1 starlette-0.52.1 sympy-1.14.0 thop-0.1.1.post2209072238 tifffile-2026.3.3 torch-2.0.1 torchvision-0.15.2 tqdm-4.70.1 typing-extensions-4.16.0 typing-inspection-0.4.4 tzdata-2026.4 ultralytics-8.0.196 urllib3-2.7.0 uvicorn-0.24.0 watchfiles-1.2.0 websockets-17.1
Successfully installed python-multipart-0.0.22
No broken requirements found.
```

Both installation commands completed with exit code 0 and no resolution errors.
The success lines are from the initial fresh install and the subsequent one-package
completion; they are not claimed to be a single installation transcript.

### 2. Real application import

```powershell
& 'C:\Users\asdfg\AppData\Local\Temp\nexi-vision-fix4-5cd9ba4a3a254a5da681821bf72d9b55\Scripts\python.exe' -c "import sys; from pathlib import Path; root=Path.cwd(); sys.path.insert(0,str(root/'02_vision_service')); from vision_service.app import app; print('VISION_REAL_APP_IMPORT=PASS app=' + app.title)"
```

```text
2026-09-13 06:06:40,928 - vision_service.app - INFO - FastAPI application created with all routes registered
VISION_REAL_APP_IMPORT=PASS app=NEXI Vision Service
```

Exit code 0. No importlib workaround or fake DeepFace module was used.

### 3. Real startup and CA-verified HTTPS health

The following diagnostic was executed through the isolated interpreter. Its fake
internal credential is test-only. The listener was shut down and joined afterward.

```powershell
@'
import os
import sys
import threading
import time
from pathlib import Path
from importlib.metadata import version
root = Path.cwd()
sys.path.insert(0, str(root / '02_vision_service'))
os.environ.update({'AUTH_ENFORCEMENT_ENABLED': 'true', 'NEXI_INTERNAL_SERVICE_TOKEN': 'fix4-isolated-test-service', 'NEXI_TLS_ENABLED': 'true'})
os.chdir(root / '02_vision_service')
import torch
torch.set_num_threads(2)
from vision_service.app import app
from config.ssl_config import get_tls_config
import httpx
import uvicorn
print('VISION_REAL_APP_IMPORT=PASS app=' + app.title, flush=True)
tls = get_tls_config()
server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=18701, log_level='info', **tls.uvicorn_kwargs()))
worker = threading.Thread(target=server.run, daemon=True)
worker.start()
try:
    deadline = time.monotonic() + 90
    with httpx.Client(verify=str(tls.ca_file), trust_env=False, timeout=15) as client:
        while time.monotonic() < deadline:
            if not worker.is_alive():
                raise RuntimeError('Vision exited before readiness')
            try:
                response = client.get('https://127.0.0.1:18701/health')
                if response.status_code == 200:
                    print('VISION_ISOLATED_HEALTH_HTTP=' + str(response.status_code), flush=True)
                    print(response.text, flush=True)
                    assert response.json()['status'] == 'degraded'
                    assert response.json()['face_model'] == 'unavailable'
                    print('VISION_RESOLVED_ANYIO=' + version('anyio'), flush=True)
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.25)
        else:
            raise RuntimeError('Vision health readiness deadline exceeded')
finally:
    server.should_exit = True
    worker.join(timeout=20)
    assert not worker.is_alive(), 'Vision diagnostic failed to shut down'
'@ | & 'C:\Users\asdfg\AppData\Local\Temp\nexi-vision-fix4-5cd9ba4a3a254a5da681821bf72d9b55\Scripts\python.exe' -
```

Actual startup/health/shutdown results:

```text
VISION_REAL_APP_IMPORT=PASS app=NEXI Vision Service
Critical error loading embedding model: No module named 'deepface'
Service continuing but may have limited functionality
YOLO yolov8n loaded successfully
Object detection is available (yolov8n)
Application startup complete.
Uvicorn running on https://127.0.0.1:18701 (Press CTRL+C to quit)
VISION_ISOLATED_HEALTH_HTTP=200
{"status":"degraded","camera":"unavailable","face_model":"unavailable","opencv_version":"4.8.0","emotion_detection":"disabled","timestamp":"2026-09-13T01:07:17.743743"}
VISION_RESOLVED_ANYIO=4.15.1
Application shutdown complete.
Finished server process [10236]
```

The face-model status is unchanged. The OpenCV version is the unchanged required
pin's version, not the monolithic venv's 4.11.0. Camera access failed closed while
Central was not running during this isolated check. Physical hardware was not
verified. Matplotlib logged an inability to save its font cache under the sandbox;
model loading and application startup nevertheless completed successfully.

### 4. Resolved anyio consistency and protected-environment dependency check

```powershell
@'
import subprocess
from pathlib import Path
interpreters = {
    'Central isolated': Path(r'C:\Users\asdfg\AppData\Local\Temp\nexi-central-fixed-1992a072fcfa44a69820717c67270a68\Scripts\python.exe'),
    'Vision isolated': Path(r'C:\Users\asdfg\AppData\Local\Temp\nexi-vision-fix4-5cd9ba4a3a254a5da681821bf72d9b55\Scripts\python.exe'),
    'Protected stack': Path('venv/Scripts/python.exe'),
}
versions = {}
for name, interpreter in interpreters.items():
    versions[name] = subprocess.check_output([str(interpreter), '-c', "from importlib.metadata import version; print(version('anyio'))"], text=True).strip()
    print(f'{name} | resolved anyio | {versions[name]}')
print('RESOLVED_ANYIO_CONSISTENCY=' + ('PASS' if len(set(versions.values())) == 1 else 'FAIL'))
for manifest in [Path('requirements.txt'), Path('01_central_server/requirements.txt'), Path('05_teachme_service/requirements.txt')]:
    for line in manifest.read_text(encoding='utf-8').splitlines():
        if line.startswith('anyio=='):
            print(f'{manifest} | explicit pin | {line}')
'@ | .\venv\Scripts\python.exe -
.\venv\Scripts\python.exe -m pip check
```

```text
Central isolated | resolved anyio | 4.12.1
Vision isolated | resolved anyio | 4.15.1
Protected stack | resolved anyio | 4.12.1
RESOLVED_ANYIO_CONSISTENCY=FAIL
requirements.txt | explicit pin | anyio==4.12.1
01_central_server\requirements.txt | explicit pin | anyio==4.12.1
05_teachme_service\requirements.txt | explicit pin | anyio==4.12.1
No broken requirements found.
```

The three-environment comparison disproves identical resolution across all seven;
it is not represented as a fresh check of seven isolated installs. The comparison
prints FAIL but does not set a nonzero exit code. No anyio-specific edit or hidden
installation constraint was introduced. No before/after freeze was reconstructed.

### 5. Exact protected 62-test rerun

```powershell
.\venv\Scripts\python.exe -m pytest -x tests/test_phase4.py tests/test_phase5.py tests/test_phase6.py tests/test_phase7_cloud_sync.py tests/test_route_naming_normalization.py tests/test_phase8_unit.py tests/test_phase8_contracts.py tests/test_phase8_e2e.py tests/test_phase8_resilience.py tests/phase9_security_verification.py --junitxml=logs/phase9-final.xml -o junit_logging=all
```

Actual output from one uninterrupted pytest process:

```text
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-7.4.3, pluggy-1.6.0 -- D:\Internship\Nexi\NEXI_Dev\venv\Scripts\python.exe
rootdir: D:\Internship\Nexi\NEXI_Dev
configfile: pytest.ini
plugins: anyio-4.12.1, asyncio-0.21.1
asyncio: mode=Mode.AUTO
collected 62 items

tests/test_phase4.py::test_b_every_basic_command_bypasses_teachme_and_llm PASSED [  1%]
tests/test_phase4.py::test_c_genuine_no_match_never_calls_llm PASSED     [  3%]
tests/test_phase4.py::test_d_server_prompt_extra_field_rejection_and_english_gate PASSED [  4%]
tests/test_phase4.py::test_f_ungrounded_output_is_caught PASSED          [  6%]
tests/test_phase4.py::test_phase4_adversarial_25_cases PASSED            [  8%]
tests/test_phase5.py::test_j_match_issues_token_no_match_does_not_and_expiry_fails PASSED [  9%]
tests/test_phase7_cloud_sync.py::test_d_static_boundary_negative_control_then_clean PASSED [ 11%]
tests/test_phase8_unit.py::test_unit_jwt_session_validation_preserves_subject PASSED [ 12%]
tests/test_phase8_unit.py::test_unit_outbox_acknowledgement_transitions_state PASSED [ 14%]
tests/test_phase8_unit.py::test_unit_rag_grounding_containment_rejects_extra_claims PASSED [ 16%]
tests/test_phase8_unit.py::test_unit_resource_authority_grant_priority_and_release PASSED [ 17%]
tests/test_phase4.py::test_a_real_http_learn_then_search PASSED          [ 19%]
tests/test_phase4.py::test_d_audio_uses_central_policy_and_preserves_focus_check PASSED [ 20%]
tests/test_phase4.py::test_e_client_response_shape_and_failure_propagation PASSED [ 22%]
tests/test_phase4.py::test_e_llm_contract_clamps_and_provider_failure_is_failure PASSED [ 24%]
tests/test_phase5.py::test_j_new_central_route_wraps_existing_audio_client PASSED [ 25%]
tests/test_phase6.py::test_identity_contract_uses_user_id_end_to_end PASSED [ 27%]
tests/test_phase6.py::test_phase2_protected_llm_contract PASSED          [ 29%]
tests/test_phase7_cloud_sync.py::test_a_provider_agnostic_client_deduplicates_and_swaps_config PASSED [ 30%]
tests/test_phase8_contracts.py::test_contract_audio_central_restricted_rag_boundary PASSED [ 32%]
tests/test_phase8_contracts.py::test_contract_central_llm_generation_shape PASSED [ 33%]
tests/test_phase8_contracts.py::test_contract_central_teachme_payload_and_embedding_dimension PASSED [ 35%]
tests/test_phase8_contracts.py::test_contract_enrollment_audio_process_voice_shape PASSED [ 37%]
tests/test_phase8_contracts.py::test_contract_enrollment_central_registration PASSED [ 38%]
tests/test_phase8_contracts.py::test_contract_enrollment_vision_upload_and_response PASSED [ 40%]
tests/test_route_naming_normalization.py::test_b_registration_routes_and_old_route_retired PASSED [ 41%]
tests/test_route_naming_normalization.py::test_c_user_creation_alias_is_identical_and_callers_migrated PASSED [ 43%]
tests/test_route_naming_normalization.py::test_d_embedded_history_is_gone_and_durable_route_serves_data PASSED [ 45%]
tests/test_route_naming_normalization.py::test_e_registration_with_embeddings_alias_is_identical PASSED [ 46%]
tests/test_route_naming_normalization.py::test_f_teachme_search_aliases_are_identical PASSED [ 48%]
tests/test_route_naming_normalization.py::test_g_openapi_documents_only_primary_paths PASSED [ 50%]
tests/phase9_security_verification.py::test_a_https_plaintext_transition_and_bad_ca PASSED [ 51%]
tests/phase9_security_verification.py::test_b_biometric_ciphertext_and_round_trips PASSED [ 53%]
tests/phase9_security_verification.py::test_c_all_biometric_stores_survive_previous_key_retirement PASSED [ 54%]
tests/phase9_security_verification.py::test_c_local_fernet_jwt_and_service_rotation PASSED [ 56%]
tests/phase9_security_verification.py::test_c_openrouter_rotation_with_https_provider_fixture PASSED [ 58%]
tests/phase9_security_verification.py::test_c_shared_credentials_live_transition_and_close PASSED [ 59%]
tests/phase9_security_verification.py::test_d_redaction_negative_controls PASSED [ 61%]
tests/phase9_security_verification.py::test_e_live_correlation_and_all_service_latencies PASSED [ 62%]
tests/phase9_security_verification.py::test_f_auditor_cannot_clear_skipped_packages_or_hide_known_findings PASSED [ 64%]
tests/test_phase4.py::test_a_reembedding_migration_is_idempotent PASSED  [ 66%]
tests/test_phase4.py::test_e_preserves_phase3_llm_focus_deferral PASSED  [ 67%]
tests/test_phase5.py::test_b_shared_internal_trust_rejects_missing_and_accepts_real_credential PASSED [ 69%]
tests/test_phase5.py::test_c_claim_ownership_no_token_cross_user_own_and_expired PASSED [ 70%]
tests/test_phase5.py::test_d_teachme_shared_auth_and_missing_jwt_fail_closed PASSED [ 72%]
tests/test_phase5.py::test_e_explicit_cors_allowlist PASSED              [ 74%]
tests/test_phase5.py::test_f_upload_rejected_before_handler_and_path_traversal PASSED [ 75%]
tests/test_phase5.py::test_g_pickle_migration_twice_and_existing_verification_flow PASSED [ 77%]
tests/test_phase6.py::test_phase3_wake_word_during_teachme_combined PASSED [ 79%]
tests/test_phase6.py::test_shared_error_handler_covers_rate_limit_and_unexpected_failure PASSED [ 80%]
tests/test_phase6.py::test_video_call_preemption_release_and_screenshot PASSED [ 82%]
tests/test_phase7_cloud_sync.py::test_c_outbox_migration_twice_and_conversation_round_trip PASSED [ 83%]
tests/test_phase7_cloud_sync.py::test_g_status_endpoint_is_accurate_and_internally_authenticated PASSED [ 85%]
tests/test_phase5.py::test_h_rate_limiter_sustains_burst_without_500[central] PASSED [ 87%]
tests/test_phase5.py::test_h_rate_limiter_sustains_burst_without_500[vision] PASSED [ 88%]
tests/test_phase6.py::test_phase2_persistence_regression PASSED          [ 90%]
tests/test_phase6.py::test_phase2_resource_authority_regression PASSED   [ 91%]
tests/test_phase7_cloud_sync.py::test_b_shared_retry_failure_then_recovery_timing PASSED [ 93%]
tests/test_phase7_cloud_sync.py::test_e_supervision_survives_and_restart_uses_persisted_time PASSED [ 95%]
tests/test_phase7_cloud_sync.py::test_f_ten_batches_failure_retry_and_duplicate_delivery PASSED [ 96%]
tests/test_phase8_resilience.py::test_resilience_all_seven_services_forced_kill_and_restart PASSED [ 98%]
tests/test_phase8_e2e.py::test_e2e_enroll_verify_grounded_answer_persist_and_sync_eligible PASSED [100%]

---- generated xml file: D:\Internship\Nexi\NEXI_Dev\logs\phase9-final.xml ----
=========================== PHASE 8 PYRAMID SUMMARY ===========================
UNIT       selected=11 passed=11 failed=0 skipped=0
CONTRACT   selected=20 passed=20 failed=0 skipped=0
INTEGRATION selected=22 passed=22 failed=0 skipped=0
RESILIENCE selected=8 passed=8 failed=0 skipped=0
E2E        selected=1 passed=1 failed=0 skipped=0
======================= 62 passed in 266.86s (0:04:26) ========================
```

Exit code 0: the previous 62/62 outcome is preserved, with no weakened or skipped
tests. The suite runs in the existing verified venv, as prescribed; it is not a
62-test run inside Vision's new isolated environment. Its live-stack and restart
checks confirm all seven services respond in that protected environment, not that
seven independent manifests have been freshly installed and validated here.

No retry consolidation, dead-code deletion, stale-manifest cleanup, or OpenAPI
regeneration was performed in this manifest-only close-out. The earlier C/D/E/I
completion gaps cannot be marked closed on the strength of these checks alone.
The requested enterprise-ready claim for the root manifest plus all seven isolated
manifests is not established by an installed-environment `pip check` or the 62-test
rerun. F/G/H require Docker Desktop installed and running on the host; no container
behavior was simulated.

PHASE 10 NOT CLOSED — the required resolved-anyio consistency check fails (Vision 4.15.1 versus Central/protected stack 4.12.1); previously unexecuted non-container C/D/E/I work remains unclosed; F/G/H require Docker Desktop installed and running.

## Final native close-out acceptance and explicit Vision anyio pin (2026-09-13)

This section supersedes the preceding anyio-equality acceptance requirement.
The user explicitly approved independent per-service dependency versions and
requested closure of the non-Docker scope. That acceptance is recorded here;
it is not represented as additional engineering work or a production certification.
Previously recorded implementation/proof gaps remain historical facts, not newly
completed tasks. Docker tasks F/G/H remain pending Docker Desktop installed and
running on the host. No Docker command, investigation, cleanup, other manifest
change, or protected-suite rerun was performed in this final pin-only verification.

Only application manifest change in this final step:

```diff
 httpx==0.25.0
+anyio==4.15.1
```

Central, TeachMe, and root anyio pins were not changed. Matching their versions
is no longer a blocker. This explicitly fixes Vision's anyio version; it does
not lock every other transitive dependency or prove installation on every platform.

### Fresh required-only installation

Actual PowerShell command:

```powershell
$visionPinEnv = Join-Path ([System.IO.Path]::GetTempPath()) ('nexi-vision-anyio-pinned-' + [guid]::NewGuid().ToString('N'))
.\venv\Scripts\python.exe -m venv $visionPinEnv
Write-Output ('VISION_PIN_ENV=' + $visionPinEnv)
& (Join-Path $visionPinEnv 'Scripts\python.exe') -m pip install -r 02_vision_service/requirements.txt
```

Actual output (environment and complete success line):

```text
VISION_PIN_ENV=C:\Users\asdfg\AppData\Local\Temp\nexi-vision-anyio-pinned-00d67ff3962c4af596acd7517f92d4d6
Successfully installed MarkupSafe-3.0.3 Pillow-10.0.1 PyWavelets-1.9.0 annotated-doc-0.0.5 annotated-types-0.8.0 anyio-4.15.1 certifi-2026.7.22 cffi-2.1.1 charset_normalizer-3.5.1 click-8.5.0 colorama-0.4.6 contourpy-1.3.3 cryptography-46.0.5 cycler-0.12.1 fastapi-0.129.0 filelock-3.32.6 fonttools-4.65.0 h11-0.14.0 httpcore-0.18.0 httptools-0.8.0 httpx-0.25.0 idna-3.19 imageio-2.37.4 jinja2-3.1.6 kiwisolver-1.5.1 lazy_loader-0.5 matplotlib-3.11.2 mpmath-1.3.0 networkx-3.6.1 numpy-1.26.4 opencv-python-4.8.0.76 packaging-26.3 pandas-3.0.5 psutil-7.2.2 py-cpuinfo-9.0.0 pycparser-3.0 pydantic-2.12.5 pydantic-core-2.41.5 pydantic-settings-2.13.0 pyparsing-3.3.2 python-dateutil-2.9.0.post0 python-dotenv-1.0.0 python-multipart-0.0.22 pyyaml-6.0.3 requests-2.34.2 scikit-image-0.21.0 scipy-1.11.2 seaborn-0.13.2 six-1.17.0 sniffio-1.3.1 starlette-0.52.1 sympy-1.14.0 thop-0.1.1.post2209072238 tifffile-2026.3.3 torch-2.0.1 torchvision-0.15.2 tqdm-4.70.1 typing-extensions-4.16.0 typing-inspection-0.4.4 tzdata-2026.4 ultralytics-8.0.196 urllib3-2.7.0 uvicorn-0.24.0 watchfiles-1.2.0 websockets-17.1
```

Exit code 0. No resolution errors. No packages were installed into the original
protected venv; optional DeepFace/Keras entries remained excluded.

### Dependency check, real app import, and HTTPS health

The isolated interpreter executed the following command. This uses the real app,
real lifespan, existing local CA, and existing YOLO weights; no importlib-only
workaround or simulated face library was used. The test credential is not a real
secret. The temporary server was stopped and joined after verification.

```powershell
& 'C:\Users\asdfg\AppData\Local\Temp\nexi-vision-anyio-pinned-00d67ff3962c4af596acd7517f92d4d6\Scripts\python.exe' -m pip check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
@'
import os
import sys
import threading
import time
from pathlib import Path
from importlib.metadata import version
root = Path.cwd()
sys.path.insert(0, str(root / '02_vision_service'))
os.environ.update({'AUTH_ENFORCEMENT_ENABLED': 'true', 'NEXI_INTERNAL_SERVICE_TOKEN': 'vision-pin-isolated-test-service', 'NEXI_TLS_ENABLED': 'true'})
os.chdir(root / '02_vision_service')
import torch
torch.set_num_threads(2)
from vision_service.app import app
from config.ssl_config import get_tls_config
import httpx
import uvicorn
print('VISION_REAL_APP_IMPORT=PASS app=' + app.title, flush=True)
print('VISION_PINNED_ANYIO=' + version('anyio'), flush=True)
assert version('anyio') == '4.15.1'
tls = get_tls_config()
server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=18701, log_level='info', **tls.uvicorn_kwargs()))
worker = threading.Thread(target=server.run, daemon=True)
worker.start()
try:
    deadline = time.monotonic() + 90
    with httpx.Client(verify=str(tls.ca_file), trust_env=False, timeout=15) as client:
        while time.monotonic() < deadline:
            if not worker.is_alive():
                raise RuntimeError('Vision exited before readiness')
            try:
                response = client.get('https://127.0.0.1:18701/health')
                if response.status_code == 200:
                    print('VISION_ISOLATED_HEALTH_HTTP=' + str(response.status_code), flush=True)
                    print(response.text, flush=True)
                    assert response.json()['status'] == 'degraded'
                    assert response.json()['face_model'] == 'unavailable'
                    print('VISION_PIN_VERIFICATION=PASS', flush=True)
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.25)
        else:
            raise RuntimeError('Vision health readiness deadline exceeded')
finally:
    server.should_exit = True
    worker.join(timeout=20)
    assert not worker.is_alive(), 'Vision diagnostic failed to shut down'
'@ | & 'C:\Users\asdfg\AppData\Local\Temp\nexi-vision-anyio-pinned-00d67ff3962c4af596acd7517f92d4d6\Scripts\python.exe' -
```

Actual verification output:

```text
No broken requirements found.
VISION_REAL_APP_IMPORT=PASS app=NEXI Vision Service
VISION_PINNED_ANYIO=4.15.1
Critical error loading embedding model: No module named 'deepface'
Service continuing but may have limited functionality
YOLO yolov8n loaded successfully
Object detection is available (yolov8n)
Application startup complete.
Uvicorn running on https://127.0.0.1:18701 (Press CTRL+C to quit)
VISION_ISOLATED_HEALTH_HTTP=200
{"status":"degraded","camera":"unavailable","face_model":"unavailable","opencv_version":"4.8.0","emotion_detection":"disabled","timestamp":"2026-09-13T01:32:52.391826"}
VISION_PIN_VERIFICATION=PASS
Application shutdown complete.
Finished server process [2804]
```

Exit code 0. Camera access failed closed because Central was not running in this
isolated check. The expected face-model degradation is unchanged. No physical
hardware verification or real provider billing check is claimed. The earlier
62/62 protected result remains recorded above and was not rerun.

PHASE 10 NATIVE CLOSE-OUT RECORDED BY USER ACCEPTANCE; VISION PIN VERIFIED; DOCKERIZATION PENDING DOCKER DESKTOP INSTALLATION. This is not a certification of all seven fresh isolated installs or production readiness.
