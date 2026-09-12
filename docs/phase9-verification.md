# Phase 9 verification report

Verification date: 2026-09-12. Evidence source: `logs/phase9-final.xml`; captured stdout is pasted below without inventing successful provider or physical-hardware outcomes.

| # | Item | Status (DONE/PARTIAL/BLOCKED) | Files changed | Verification command | Verification result (actual output) | Deferred work |
|---|---|---|---|---|---|---|
| A | TLS, all seven services | DONE | `config/ssl_config.py`; authoritative service entrypoints/configs; active shared and service-local clients; `nexctl.py`; compose/wait/health/OpenAPI scripts; generated specs; `.env.example`; `.gitignore` | FINAL, `test_a_https_plaintext_transition_and_bad_ca` | HTTPS 200: seven services; plaintext rejected: seven; transition listener closed; wrong CA rejected by actual client | Commercial CA/domain/renewal; Docker runtime not verified |
| B | Biometric encryption at rest | DONE | `shared/secure_storage.py`; Central `sqlite_store.py`, migration/startup; Audio `speaker_service.py`; Enrollment encryption and both storage helpers | FINAL, `test_b_biometric_ciphertext_and_round_trips`; original persistence/speaker checks | Three ciphertext proofs and three normal round trips PASS; Central migration 1 updated then 0 | Secure provisioning/backups; legacy retired artifacts not deleted |
| C | Four dual-active credential classes | PARTIAL | `shared/credential_rotation.py`, `secure_storage.py`, `jwt_manager.py`, `security.py`; Enrollment `encryption.py`; LLM `openrouter_client.py`; `.env.example`; `DEPLOYMENT.md` | FINAL, four `test_c_*` cases | Old/new accepted; closed-old rejected/new accepted for Fernet/JWT/service trust and controlled HTTPS provider; all three stores survive rewrap | Actual OpenRouter account key issuance/revocation was not performed |
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

PHASE 9 NOT CLOSED — real OpenRouter account rotation remains unverified and the dependency assessment has unresolved manifest errors.
