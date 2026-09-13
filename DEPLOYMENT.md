# NEXI Robot — Deployment & Portability Plan

## Executive Summary

This document describes the complete Docker-based deployment strategy for the NEXI autonomous robot stack. The goal: **single-command deployment** on any Linux/macOS/WSL2 host with Docker.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      DOCKER COMPOSE STACK                       │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  central    │  │  vision     │  │  audio      │             │
│  │  :8000      │  │  :8001      │  │  :8002      │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────┐ │
│  │  tts        │  │  teachme    │  │  enrollment │  │ nexctl │ │
│  │  :8003      │  │  :8004      │  │  :8005      │  │ :8006  │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └────────┘ │
├─────────────────────────────────────────────────────────────────┤
│  Volumes: models/, knowledge/, enrollments/, logs/, .env       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Repository Structure

```
nex-i-robot/
├── .github/
│   └── workflows/
│       └── docker-build.yml       # CI: multi-arch builds
├── docker/
│   ├── base.Dockerfile            # Shared base: python3.11 + system deps
│   ├── central.Dockerfile
│   ├── vision.Dockerfile
│   ├── audio.Dockerfile
│   ├── tts.Dockerfile
│   ├── teachme.Dockerfile
│   ├── enrollment.Dockerfile
│   ├── llm.Dockerfile
│   ├── nexctl.Dockerfile          # CLI runner
│   └── scripts/
│       ├── entrypoint.sh          # Common entrypoint
│       ├── download_models.py     # Model downloader
│       └── wait-for-services.sh   # Health check waiter
├── docker-compose.yml
├── docker-compose.override.yml.example
├── .env.example
├── .dockerignore
├── nexctl.py
├── README.md
├── DEPLOYMENT.md
├── .dockerignore
└── .gitignore
```

---

## Phase 2: Docker Files

### Base Image (`docker/base.Dockerfile`)
- Python 3.11 slim
- System deps: OpenCV, PortAudio, ALSA, build tools
- Non-root user (UID 1000)

### Service Images
| Service | Key Dependencies |
|---------|------------------|
| central | FastAPI, aiohttp, httpx |
| vision | TensorFlow 2.13, DeepFace, YOLOv8, OpenCV |
| audio | PyAudio, pvporcupine, Groq, Resemblyzer |
| tts | Piper TTS, ONNX Runtime, Piper Jenny model |
| teachme | FAISS, SigLIP2 (transformers), FastAPI |
| enrollment | Streamlit, Streamlit-webrtc, av |
| llm | OpenRouter, outlines (constrained decoding) |
| nexctl | OpenCV, PyAudio, requests |

---

## Phase 3: Entrypoint & Model Management

### Entrypoint (`docker/scripts/entrypoint.sh`)
1. Loads `.env`
2. **Prompts for missing API keys** interactively
3. Downloads models if `DOWNLOAD_MODELS=true`
4. Waits for dependent services
5. Executes command

### Model Downloader (`docker/scripts/download_models.py`)
Pre-downloads at build/startup:
- Piper Jenny voice (~60MB)
- SigLIP2 (~500MB)
- YOLOv8n (~6MB)
- DeepFace Facenet (~100MB)

---

## Phase 4: Docker Compose

### Key Features
- **Health checks** for all services
- **Service dependencies** with `depends_on` + health conditions
- **Volume persistence** for models, knowledge, enrollments
- **Device mapping**: `/dev/video0`, `/dev/snd`
- **GPU support** (optional NVIDIA)
- **PulseAudio** for audio in containers

### Service Dependencies
```
central (no deps)
    ↓
vision, audio, tts, enrollment (depend on central)
    ↓
teachme (depends on vision)
    ↓
nexctl (depends on all)
```

---

## Phase 5: Configuration

### `.env.example` (template)
```bash
OpenRouter_API_Key=YOUR_OPENROUTER_KEY_HERE
GROQ_API_KEY=YOUR_GROQ_KEY_HERE
PORCUPINE_ACCESS_KEY=YOUR_PORCUPINE_KEY_HERE
DOWNLOAD_MODELS=true
```

### Portability Features
- **No hardcoded paths** — all via environment variables
- **Docker DNS** for service discovery (`http://vision:8001`)
- **Volume mounts** for persistent data
- **Multi-arch builds** (amd64/arm64 via Buildx)

---

## Phase 6: CI/CD Pipeline

### `.github/workflows/docker-build.yml`
- Multi-service matrix build
- Buildx for multi-arch
- GHA cache for layer caching
- Pushes to GHCR on push/tag

---

## Phase 7: Teammate Onboarding

### Prerequisites
- Docker Desktop / Docker Engine + Compose v2
- Git
- 3 API keys (OpenRouter, Groq, Picovoice)

### Onboarding Steps
| Step | Command | Time |
|------|---------|------|
| 1. Clone | `git clone https://github.com/hammadf23/NEXI_Dev.git` | 30s |
| 2. Config | `cp .env.example .env` + edit | 2 min |
| 3. Build & Run | `docker compose up --build` | 5-15 min |
| 4. Launch CLI | `docker compose run --rm nexctl` | Instant |

### First-Run Downloads (~2GB)
- SigLIP2: ~500MB
- YOLOv8n: ~6MB
- DeepFace Facenet: ~100MB
- Piper Jenny: ~60MB
- HF cache: ~500MB

---

## Critical Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Multi-stage builds | Smaller images; build deps separated |
| Shared base image | DRY, consistent deps, faster rebuilds |
| Health checks | Compose waits correctly |
| Volume mounts | Persists across restarts; shares HF cache |
| GPU reservation | Optional NVIDIA support |
| Entrypoint prompts | No secrets in image; interactive setup |
| Pre-download option | `DOWNLOAD_MODELS=false` to skip |

---

## Known Limitations & Mitigations

| Issue | Mitigation |
|-------|------------|
| `pvporcupine` wheels may not exist for ARM | Document x86_64 requirement; keyboard fallback |
| Camera in Docker | Requires `--device=/dev/video0`; works on Linux/WSL2 |
| PulseAudio in container | Mount `/run/pulse/native`; document host setup |
| Large model downloads | `DOWNLOAD_MODELS=false` to skip; manual download |
| GPU in CI | Skip GPU tests; document local GPU usage |

---

## Migration Checklist for Teammate

- [ ] Clone repo
- [ ] Install Docker + Compose v2
- [ ] `cp .env.example .env` → add 3 API keys
- [ ] `docker compose up --build` (coffee break)
- [ ] `docker compose run --rm nexctl` → verify menu
- [ ] Test: Enroll user → Teach object → Recall → Speak
- [ ] Push any local changes to repo

---

## File Checklist

```
✅ nexctl.py
✅ docker-compose.yml
✅ .env.example
✅ .dockerignore
✅ .github/workflows/docker-build.yml
✅ docker/base.Dockerfile
✅ docker/central.Dockerfile
✅ docker/vision.Dockerfile
✅ docker/audio.Dockerfile
✅ docker/tts.Dockerfile
✅ docker/teachme.Dockerfile
✅ docker/enrollment.Dockerfile
✅ docker/llm.Dockerfile
✅ docker/nexctl.Dockerfile
✅ docker/scripts/entrypoint.sh
✅ docker/scripts/download_models.py
✅ docker/scripts/wait-for-services.sh
✅ docker-compose.override.yml.example
✅ README.md
✅ DEPLOYMENT.md
✅ .github/workflows/docker-build.yml
✅ .dockerignore
✅ .gitignore
```

---

## Next Steps

1. Push to GitHub → CI builds images
2. Teammate clones → runs `docker compose up --build`
3. Iterate on any issues
4. Document any host-specific quirks

## Phase 9 security rollout and rotation

The older quick-start instructions above are not a production-security claim.
The verified stack runs locally in the Python virtual environment. Existing Docker
image/layout and dependency-manifest defects remain deployment blockers; Docker
images have not been verified by the Phase 9 local HTTPS tests.

All seven Python service entry points use `config.ssl_config.TLSConfig`. Generate
local-verification certificates once from the repository root:

```powershell
.\venv\Scripts\python.exe -m config.ssl_config --generate-local
```

Set `NEXI_TLS_ENABLED=true`, `NEXI_TLS_CERT_FILE`, `NEXI_TLS_KEY_FILE`, and
`NEXI_TLS_CA_FILE` on every service. Defaults resolve to `config/certificates`.
Clients need only the public CA bundle, never the CA private key. Certificates
must cover the actual DNS names used by clients. These certificates expire after
30 days and are local verification material, not commercial certificates. Do not
regenerate them during a rolling rollout: distribute trust first, then the leaf
certificates. Private keys are ignored by git and must have restrictive host ACLs.

Use each service's `python main.py` entry point, or supply the same certificate/key
paths explicitly to uvicorn. Bare `uvicorn main:app` is not a TLS launcher. During
a controlled migration, an additional HTTP listener may run on a separate port
with `NEXI_TLS_ALLOW_PLAINTEXT=true`; it logs `PLAINTEXT_TRANSITION`. Migrate clients
to CA-verified HTTPS, stop that listener, close its firewall port, and reset the
flag to false. The steady-state HTTPS listener rejects HTTP; HTTPS clients never
use `verify=False`. The flag does not create another listener by itself.

Central user records and Audio speaker records are encrypted through shared
`RotatingFernet`; Enrollment delegates to the same implementation. Supply
`NEXI_FERNET_KEY` or `NEXI_FERNET_KEY_FILE` (legacy `ENCRYPTION_KEY_FILE` is accepted
as a migration source). There is no generated fallback secret. Missing/invalid
keys fail closed. `ENABLE_ENCRYPTION=false` is rejected. Central startup encrypts
legacy users and vacuums old SQLite pages; Audio startup converts its legacy JSON
store in place. Enrollment legacy Fernet ciphertext remains readable. Existing
plaintext enrollment metadata, if any, requires an explicit controlled migration
before mandatory-encryption startup; it is not silently treated as ciphertext.
Conversations and TeachMe are intentionally not encrypted by this phase.

One rotation pattern applies to all four credential classes:

| Credential | Current | Previous |
| --- | --- | --- |
| Biometric/Enrollment Fernet | `NEXI_FERNET_KEY` / `NEXI_FERNET_KEY_FILE` | `NEXI_FERNET_PREVIOUS_KEY` / `NEXI_FERNET_PREVIOUS_KEY_FILE` |
| OpenRouter | environment variable named by `OPENROUTER_API_KEY_ENV` | same variable name plus `_PREVIOUS` |
| Session JWT | `NEXI_JWT_SECRET` | `NEXI_JWT_SECRET_PREVIOUS` |
| Internal trust | `NEXI_INTERNAL_SERVICE_TOKEN` | `NEXI_INTERNAL_SERVICE_TOKEN_PREVIOUS` |

1. Back up data and keys securely. Provision the new value without retiring old.
2. Stage every consumer to accept the new value while still issuing/writing the
   old value (old as current, new as previous), rolling-restart services, and
   verify both. Then roll to new as current, old as previous. This preliminary
   stage prevents a new sender reaching an old-only receiver mid-rollout.
3. During the window, JWTs sign with current, internal clients send current,
   Fernet writes use current, and both keys validate/decrypt. OpenRouter sends
   current first and tries previous only on 401/403, never on a provider failure.
   Each OpenRouter key must be independently active at the real provider.
4. Rewrap all old-key biometric records before removing previous. Restart Central
   and Audio with both values configured; Central rewraps user rows and Audio
   rewrites speaker records. Quiesce Enrollment metadata writes and rewrap
   **all** metadata files using `EncryptionManager.rotate_file`, then resume.
   Reads do not silently rewrite metadata or race with normal updates.
   Verify no record still requires the old key. Retain secure backup keys under
   the organization's recovery policy. Merely waiting does not rotate stored data.
5. Wait at least the maximum lifetime of issued JWTs (session default 30 minutes,
   plus any other token types actually issued), and confirm every internal sender
   has rolled. Remove previous everywhere and rolling-restart. Revoke the old
   OpenRouter credential upstream once all clients use current. Verify old
   rejection and new acceptance locally for JWT/internal trust/Fernet and at the
   provider for OpenRouter; removing a local variable cannot revoke a vendor key.

Do not use the legacy Fernet keys already committed in repository history as
production secrets. Phase 9 verification uses independent test-only keys; it does
not rotate your deployed secrets or erase repository history. Real key issuance,
provider revocation, backups, secret-management infrastructure, CA provisioning,
domain/renewal, and vulnerability-remediation deadlines are deployment decisions.

The logger redacts sensitive fields, message patterns, and configured credential
values by default, and propagates `X-Correlation-ID` across internal calls. Keep
`NEXI_LOG_REDACTION_ENABLED=true`. Its false setting exists for the explicit
negative-control fixture, not normal operation. Request start/end timestamps and
duration are logged without dumping request bodies.

Verification commands from the repository root:

```powershell
.\venv\Scripts\python.exe -m pytest -q -s tests/phase9_security_verification.py
.\venv\Scripts\python.exe -m pytest
.\venv\Scripts\python.exe scripts/scan_dependencies.py
```

The scan audits each service manifest (Audio uses the root aggregate), emits all
findings and a JSON report at `logs/dependency-audit.json`, and exits nonzero on
high/critical, unavailable severity (conservatively treated as high), or an
unresolvable manifest. An audit error is **not** a clean bill of health. Findings
are not ignored or automatically upgraded. `pip-audit==2.10.1` is pinned in the
root requirements; service manifests still need separately coordinated repair.
The local HTTPS OpenRouter fixture proves adapter rotation behavior only; real
provider keys can only be issued/revoked by their owner and provider.
Real-account OpenRouter rotation is a permanent operator runbook item, not a
repository code deliverable. Before deployment, the operator provisions the
funded current key, stages any previous key for the transition, verifies access,
and revokes the previous key with the provider before removing it from config.
Repository verification uses fake non-billing credentials only.

Phase 9's protected baseline retains all 53 Phase 8 test identities and outcome
assertions. Disclosed harness adaptations are CA-verified HTTPS URLs and listener
arguments, a test-only biometric key, and accepting the HTTPS client's constructor
configuration in the existing fake client. The isolated TeachMe health caller's
read deadline is 5 seconds rather than 2: captured HTTP 200 logs showed the
existing bounded Vision probe completing in 2.008-2.046 seconds. The overall
60-second startup deadline is unchanged; this does not hide a hung startup.
Nine opt-in security verification tests supplement, rather than replace, the
baseline. Authentication, ownership, expiry, CORS, upload guards, and resource
mechanics retain their previous assertions. The shared observer wraps these
gates so denied requests also receive correlation IDs and latency logs.

All 13 packages installed for the audit tool are exact-pinned in the root
manifest and checked against the virtual environment. An unresolved manifest
or timed-out audit still blocks a complete dependency assessment. In particular,
Central's `anyio==4.1.1` is unavailable and Vision's existing dependency pins
conflict; do not reinterpret those resolution failures as vulnerability-free.
