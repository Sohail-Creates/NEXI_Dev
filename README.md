# NEXI Robot — Docker Deployment

**One-command deployment** of the full NEXI autonomous robot stack.

## Quick Start

```bash
# 1. Clone
git clone https://github.com/hammadf23/NEXI_Dev.git
cd NEXI_Dev

# 2. Configure API keys (required)
cp .env.example .env
# Edit .env with your API keys (see below)

# 3. Launch everything
docker compose up --build

# 4. In another terminal, run the CLI
docker compose run --rm nexctl
```

### Required API Keys
| Key | Service | Get it at |
|-----|---------|-----------|
| `OpenRouter_API_Key` | LLM (OpenRouter) | https://openrouter.ai/keys |
| `GROQ_API_KEY` | Audio STT (Groq) | https://console.groq.com/keys |
| `PORCUPINE_ACCESS_KEY` | Wake-word (Picovoice) | https://console.picovoice.ai/ |

### First Run
1. First run downloads ~2GB of models (SigLIP2, YOLO, DeepFace, Piper Jenny)
2. Subsequent runs use cached models
3. `nexctl` starts automatically in interactive mode

### Useful Commands
```bash
# View logs
docker compose logs -f vision

# Restart single service
docker compose restart vision

# Run tests
docker compose run --rm nexctl --test

# Clean everything
docker compose down -v
```

### Hardware Access
- **Camera**: `--device=/dev/video0` (auto-configured)
- **Audio**: ALSA + PulseAudio (auto-configured)
- **GPU**: Add `deploy.resources.reservations.devices` in compose for NVIDIA

## Architecture

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

## Services

| Service | Port | Description |
|---------|------|-------------|
| Central | 8000 | User management, orchestration |
| Vision | 8001 | Face detection, object detection, MJPEG streaming |
| Audio | 8002 | Wake-word, STT (Groq), speaker verification |
| TTS | 8003 | Piper TTS (Jenny voice) |
| TeachMe | 8004 | RAG: teach/recall with SigLIP2+FAISS |
| Enrollment | 8005 | User enrollment (5 photos + 5 voice) |
| LLM | 8006 | OpenRouter + /format endpoint |
| nexctl | - | Interactive CLI for all services |

## Development

### Hot-reload code changes
```bash
# Mount local code for live editing
docker compose -f docker-compose.yml -f docker-compose.override.yml up --build
```

### Run tests
```bash
docker compose run --rm nexctl --test
```

### Clean everything
```bash
docker compose down -v  # Removes all volumes
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Camera not found | Ensure `--device=/dev/video0` and user in `video` group |
| Audio not working | Check PulseAudio socket mount; run `pavucontrol` on host |
| GPU not detected | Install `nvidia-container-toolkit`; enable in compose |
| Model download fails | Set `DOWNLOAD_MODELS=false` and pre-download manually |
| Porcupine key invalid | Get key from https://console.picovoice.ai/ |

## License
MIT