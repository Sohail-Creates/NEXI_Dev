# NEXI backend

NEXI is a seven-service Python 3.11 backend for a robot assistant. The current
native deployment uses one isolated virtual environment per service. Central's
authoritative application is `01_central_server/main.py` (`main:app`).

## Start here

1. Install Python 3.11 and clone the repository.
2. Copy `.env.example` to `.env` and provide deployment-owned credentials.
3. Follow [`run.txt`](run.txt) from the repository root. Open one PowerShell
   terminal per service and use the section for that service.
4. When all seven services are running, execute:

   ```powershell
   & .\01_central_server\venv\Scripts\Activate.ps1
   python .\scripts\health_check_all.py
   ```

The health gate accepts HTTP 200 with either `healthy` or an honest `degraded`
body. A timeout, connection failure, or non-200 response fails the gate.

## Service map

| Service | Port | Application | Health |
|---|---:|---|---|
| Central | 8000 | `main:app` | `/health` |
| Vision | 8001 | `vision_service.app:app` | `/health` |
| Audio | 8002 | `main:app` | `/health` |
| TTS | 8003 | `tts_service.app:app` | `/health` |
| TeachMe | 8004 | `teachme_service.app:app` | `/health` |
| Enrollment | 8005 | `app.main:app` | `/health` |
| LLM | 8006 | `main:app` | `/api/v1/health` |

Each service installs only its own numbered directory's `requirements.txt`.
The root `requirements.txt` and root `venv` are for the consolidated test and
development toolchain, not for running production service processes.

## Configuration and security

- TLS is enabled through the shared `config.ssl_config` settings. Native clients
  verify the configured CA; do not disable certificate verification.
- Internal calls use the shared service-trust credential. External per-user
  access uses signed session tokens whose subject is the validated `user_id`.
- Biometric stores require Fernet encryption. Never commit `.env`, key files,
  local databases, model caches, recordings, or verification logs.
- Local self-signed certificates are for development. Production CA
  certificates, secret storage/rotation, provider credentials, and OpenRouter
  billing are operator responsibilities.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for current topology and decisions.
Historical audits and plans are retained under [`docs/archive/`](docs/archive/).

## Tests

Create the root development environment and run the protected suite:

```powershell
python -m venv .\venv
& .\venv\Scripts\Activate.ps1
python -m pip install -r .\requirements.txt
python -m pytest tests/test_phase4.py tests/test_phase5.py tests/test_phase6.py tests/test_phase7_cloud_sync.py tests/test_route_naming_normalization.py tests/test_phase8_unit.py tests/test_phase8_contracts.py tests/test_phase8_e2e.py tests/test_phase8_resilience.py tests/phase9_security_verification.py -x -v -s -o junit_logging=all
```

The protected baseline is 62 passing tests: UNIT 11, CONTRACT 20,
INTEGRATION 22, RESILIENCE 8, and E2E 1.

## Known environment-dependent limitations

Health may honestly report degraded when physical camera/microphone hardware,
DeepFace, Porcupine access, Piper Jenny weights, or paid OpenRouter generation
credit is unavailable. Automated speech tests use the established injected
synthesized-speech transport; they do not claim physical microphone coverage.

Docker files remain in the repository, but the final Docker build/Compose/fresh-
checkout acceptance gate requires Docker Desktop and has not been executed on
this host. Native deployment is the verified workflow until that gate is run.
