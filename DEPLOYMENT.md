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