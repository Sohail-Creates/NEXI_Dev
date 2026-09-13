# NEXI Robot — Complete Setup Guide

## Verified deployment status (Phase 10, 2026-09-13)

The native Phase 10 close-out is recorded by user acceptance of the revised scope;
Docker tasks F/G/H remain pending. Central's corrected per-service requirements
were installed into a fresh isolated environment, and its real application started
and returned HTTP 200 from `/health`.

Vision's required-only environment now installs successfully, passes `pip check`,
and imports and starts the real application over CA-verified HTTPS. Its health
response remains honestly degraded with `face_model: unavailable`; YOLO loads.
DeepFace and Keras remain optional. The protected suite passes 62/62 after the
authorized FastAPI/Pydantic/NumPy alignment and shared runtime additions.

Service environments are independent: Vision explicitly pins `anyio==4.15.1`,
while Central, TeachMe, and root retain `4.12.1`. Cross-service version equality
is not an acceptance requirement. Vision's explicitly pinned manifest was freshly
installed and its real app import and HTTPS health check passed again.

The recorded acceptance is not a blanket production-readiness certification.
This limited verification does not prove seven independent fresh installations
or completion of previously unexecuted retry consolidation and dead-code cleanup.

Docker Desktop must be installed and running on the host before Phase 10's
container builds, Compose verification, and fresh-checkout container acceptance
can execute. These tasks have not been verified. The Docker and native setup
instructions below are historical guidance, not a validated handover procedure;
do not rely on their one-command deployment claims until the remaining gates
pass. See [the verification record](docs/phase9-verification.md).

---

## ⚡ QUICK START (TL;DR)

```bash
# 1. Clone & enter
git clone https://github.com/hammadf23/NEXI_Dev.git
cd NEXI_Dev

# 2. Configure API keys (REQUIRED)
cp .env.example .env
# Edit .env with your 3 API keys (see below)

# 3. Launch everything (Docker)
docker compose up --build

# 4. In another terminal, run the CLI
docker compose run --rm nexctl
```

---

## 🔑 REQUIRED API KEYS (Get these first)

| Key | Service | Purpose | Get it at |
|-----|---------|---------|-----------|
| `OpenRouter_API_Key` | LLM (OpenRouter) | Conversational AI, formatting | https://openrouter.ai/keys |
| `GROQ_API_KEY` | Audio STT (Groq) | Speech-to-text transcription | https://console.groq.com/keys |
| `PORCUPINE_ACCESS_KEY` | Wake-word (Picovoice) | "Hey Nexi" detection | https://console.picovoice.ai/ |

> **Note:** Porcupine key is optional — without it, wake-word falls back to SPACEBAR press.

---

## 💻 LOCAL DEVELOPMENT SETUP (Without Docker)

### Prerequisites
- **Python 3.11+** (3.11 recommended, 3.12/3.13 may have wheel issues)
- **Git**
- **FFmpeg** (for audio/video processing)
- **PortAudio** (for PyAudio/microphone)
- **CMake + Build Tools** (for native wheels)

### Windows Setup
```powershell
# 1. Install system deps (run in Administrator PowerShell)
winget install FFmpeg
winget install Microsoft.VisualStudio.2022.BuildTools  # or "Desktop development with C++"
# Or install via chocolatey: choco install ffmpeg cmake visualstudio2022buildtools

# 2. Clone & setup
git clone https://github.com/hammadf23/NEXI_Dev.git
cd NEXI_Dev
git checkout refactoring

# 3. Create virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 4. Install dependencies
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# 5. Configure API keys
cp .env.example .env
# Edit .env with your API keys

# 6. Run services (each in separate terminal)
# Terminal 1: Central Server
cd 01_central_server && python main.py
# Terminal 2: Vision
cd 02_vision_service && python main.py
# Terminal 3: Audio
cd 03_audio_service && python main.py
# Terminal 4: TTS
cd 04_tts_service && python main.py
# Terminal 5: TeachMe
cd 05_teachme_service && python main.py
# Terminal 6: Enrollment
cd 06_enrollment_service/app && python -m uvicorn app.main:app --port 8005
# Terminal 7: LLM
cd 07_llm_service && python main.py

# 8. Run CLI (in another terminal)
python nexctl.py
```

### Linux/macOS Setup
```bash
# System deps (Ubuntu/Debian)
sudo apt-get update && sudo apt-get install -y \
    ffmpeg portaudio19-dev libasound2-dev \
    cmake build-essential pkg-config \
    libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1 \
    libsndfile1 libjpeg-dev libpng-dev

# macOS
brew install ffmpeg portaudio cmake pkg-config

# Then same Python steps as Windows
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# ... run services
```

---

## 🐳 DOCKER DEPLOYMENT (Recommended)

### First Run (downloads ~2GB models)
```bash
docker compose up --build
# First run: downloads ~2GB models (SigLIP2 ~500MB, YOLOv8n ~6MB, DeepFace ~100MB, Piper Jenny ~60MB)
# Subsequent runs: uses cached volumes (~30s startup)
```

### Run CLI
```bash
# In another terminal
docker compose run --rm nexctl
```

### Useful Commands
```bash
# View logs
docker compose logs -f vision

# Restart single service
docker compose restart vision

# Run tests
docker compose run --rm nexctl --test

# Clean everything (removes all volumes)
docker compose down -v

# Skip model downloads (use pre-cached volumes)
DOWNLOAD_MODELS=false docker compose up --build
```

---

## 🖥️ HARDWARE REQUIREMENTS

| Component | Required | Notes |
|-----------|----------|-------|
| **Camera** | Yes | USB webcam (`/dev/video0` on Linux, auto on Windows) |
| **Microphone** | Yes | Any USB/built-in mic |
| **Speakers** | Yes | For TTS playback |
| **GPU** | Optional | NVIDIA GPU + `nvidia-container-toolkit` for faster Vision |
| **RAM** | 8GB+ | 16GB recommended for ML models |
| **Disk** | 10GB+ | Models + Docker images + data |

### Camera/Microphone Access
- **Linux**: User must be in `video` and `audio` groups: `sudo usermod -aG video,audio $USER`
- **Windows**: Docker Desktop → Settings → Resources → File Sharing → enable drive
- **Docker**: Camera/mic access auto-configured via `--device=/dev/video0` and PulseAudio socket

---

## 🔍 VERIFICATION CHECKLIST

After startup, verify all services:

```bash
# 1. Health checks (all should return 200 OK)
curl http://localhost:8000/health  # Central
curl http://localhost:8001/health  # Vision
curl http://localhost:8002/health  # Audio
curl http://localhost:8003/health  # TTS
curl http://localhost:8004/health  # TeachMe
curl http://localhost:8005/health  # Enrollment
curl http://localhost:8006/        # LLM (root endpoint)
```

### Test Full Pipeline (via nexctl)
```bash
# Run CLI
docker compose run --rm nexctl
# Or locally: python nexctl.py

# In menu:
# 1. Select "4) TeachMe (RAG)" → "4.1) Teach new object"
#    → Point camera at object, press SPACE, label "apple"
# 2. Select "4.2) Recall / Query"
#    → Point camera at same object, ask "What is this?"
#    → Should return match with confidence ~1.0
# 3. Select "7) TTS" → "7.1) Synthesize speech"
#    → Enter text → Should play via speakers
```

---

## 📁 DATA PERSISTENCE

| Data | Location (Docker) | Location (Local) |
|------|-------------------|------------------|
| Models | `vision_models/`, `tts_models/`, `audio_models/` | `./models/` |
| TeachMe Knowledge | `teachme_data/`, `teachme_indexes/` | `05_teachme_service/teachme_service/data/` |
| Enrollment Data | `enrollment_data/` | `06_enrollment_service/enrollment_data/` |
| Logs | `logs/` | `logs/` |
| Config | `.env` | `.env` |

> **Tip:** `docker compose down -v` removes ALL data. Use `docker compose down` to keep volumes.

---

## 🐛 TROUBLESHOOTING

| Issue | Solution |
|-------|----------|
| **Camera not found** | Linux: `sudo usermod -aG video $USER && newgrp video` / Windows: Docker Desktop → Settings → Resources → enable drive |
| **Audio not working** | Check PulseAudio: `pavucontrol` on host; verify `/run/pulse/native` mount in container |
| **GPU not detected** | Install `nvidia-container-toolkit`; add `deploy.resources.reservations.devices` in compose |
| **Model download fails** | Set `DOWNLOAD_MODELS=false` in `.env`; pre-download manually via `docker compose run --rm vision python /app/scripts/download_models.py` |
| **Porcupine key invalid** | Get free key at https://console.picovoice.ai/; wake-word falls back to SPACEBAR |
| **Docker build fails (Windows)** | Use Docker Desktop with WSL2 backend; enable "Use WSL 2 based engine" |
| **PyAudio install fails** | Windows: `pip install pipwin && pipwin install pyaudio` / Linux: `sudo apt-get install portaudio19-dev` |
| **Model download stuck** | First run downloads ~2GB; check `docker compose logs -f vision` for progress |
| **nexctl import errors (local)** | `pip install opencv-python-headless pyaudio requests pillow numpy` |

---

## 🔧 DEVELOPMENT WORKFLOW

### Hot-reload Code Changes
```bash
# Mount local code for live editing
docker compose -f docker-compose.yml -f docker-compose.override.yml up --build
```

### Run Tests
```bash
# RAG pipeline test
docker compose run --rm nexctl --test

# Full system test
docker compose run --rm nexctl  # then run demo_robot_flow.py manually
```

### Add New Service
1. Create `docker/<service>.Dockerfile`
2. Add service to `docker-compose.yml`
3. Add health check endpoint `/health`
4. Update `nexctl.py` ServiceClient

---

## 📦 PROJECT STRUCTURE

```
nex-i-robot/
├── docker/                    # Dockerfiles for all 8 services
├── docker-compose.yml         # Main orchestration
├── .env.example               # API key template
├── nexctl.py                  # Interactive CLI
├── 01_central_server/         # User mgmt, orchestration
├── 02_vision_service/         # Face/object detection
├── 03_audio_service/          # Wake-word, STT, speaker ID
├── 04_tts_service/            # Piper TTS
├── 05_teachme_service/        # RAG (SigLIP2 + FAISS)
├── 06_enrollment_service/     # User enrollment
├── 07_llm_service/            # OpenRouter LLM
├── shared/                    # Shared clients, utils, middleware
├── config/                    # Root config
├── scripts/                   # Utility scripts
├── tests/                     # Test suite
└── docker-compose.yml         # Main orchestration
```

---

## 📄 LICENSE
MIT

---

## 🤝 CONTRIBUTING

1. Fork → Create feature branch → Commit → Push → PR
2. CI builds multi-arch images on push
3. All services must have `/health` endpoint
4. Follow existing code style (type hints, docstrings)

---

**Need help?** Check `DEPLOYMENT.md` for comprehensive architecture details, or open an issue on GitHub.
