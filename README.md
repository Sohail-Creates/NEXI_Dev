# NEXI - Intelligent Personal Assistant Robot

Multimodal voice-enabled conversational AI system with speaker verification, emotion awareness, and context-aware knowledge management.

**System Version:** 3.2 | **Last Updated:** May 4, 2026 | **Status:** Production-Ready for Controlled Deployments

---

## What is NEXI?

NEXI is a distributed microservices architecture that combines:
- Real-time voice interaction (wake word detection, speaker verification, speech recognition)
- Visual perception (facial expression analysis, object detection, face recognition)
- Conversational intelligence (context-aware language model with knowledge base integration)
- Resource coordination (camera/microphone allocation with priority management)
- Hybrid operation (online via OpenRouter API for quality; offline via SmolLM2-1.7B local model)

**7 Microservices Operating on Localhost:**
- Central Server (Port 8000) - Orchestration and user management
- Vision Service (Port 8001) - Face detection, emotion analysis, object detection
- Audio Service (Port 8002) - Wake word detection, speaker verification, speech recognition
- TTS Service (Port 8003) - Speech synthesis (English + Urdu)
- TeachMe Service (Port 8004) - Knowledge base and semantic search
- Enrollment Service (Port 8005) - User registration and biometric collection
- LLM Service (Port 8006) - Conversational AI with hybrid cloud/local inference

---

## CRITICAL INSTALLATION REQUIREMENTS

**This system will NOT work without these prerequisites being properly installed.** Follow every step below exactly.

### Step 1: System Requirements

- **Operating System:** Windows, Linux, or macOS
- **Python:** Version 3.9 or higher (3.11 recommended)
- **RAM:** 8 GB minimum recommended (3-4 GB absolute minimum, may be insufficient)
- **CPU:** Multi-core processor (4+ cores recommended for ML models)
- **Storage:** 10 GB available (for models, dependencies, voice cache)
- **Internet:** Recommended for LLM inference (OpenRouter API), but system operates offline if needed

### Step 2: Python Virtual Environment

Create and activate a virtual environment before any other steps:

**On Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**On Linux/macOS (Bash):**
```bash
python3 -m venv venv
source venv/bin/activate
```

Verify activation - your terminal prompt should show `(venv)`.

### Step 3: Platform-Specific Requirements

#### Windows (REQUIRED - System will not work without this)

**Visual C++ Build Tools (for Resemblyzer speaker embedding library)**

Resemblyzer requires C++ compilation. Visual C++ Build Tools must be installed.

**Installation Steps:**
1. Download from: https://visualstudio.microsoft.com/visual-cpp-build-tools/
2. Run the installer
3. Select: "Desktop development with C++"
4. Select: "MSVC v143 - VS 2022 C++ x64/x86 build tools" (or latest available)
5. Complete the installation (~2-3 GB download, ~5-10 minutes)
6. **Restart your computer after installation**
7. Reopen PowerShell and reactivate the virtual environment

**Verify Installation:**
```powershell
cl.exe --version
```
If command is recognized, installation succeeded.

#### Linux (Optional - For PortAudio Support)

If you plan to use PortAudio-based audio recording:

**Ubuntu/Debian:**
```bash
sudo apt-get install portaudio19-dev
```

**Fedora/RHEL:**
```bash
sudo dnf install portaudio-devel
```

#### macOS

Standard development tools are typically sufficient. If audio issues occur, install Xcode Command Line Tools:
```bash
xcode-select --install
```

### Step 4: Install Python Dependencies

With virtual environment activated and platform prerequisites installed:

```powershell
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

This installs all required packages including FastAPI, Whisper, DeepFace, PyTorch, and others.

**Verify Installation:**
```powershell
pip list | grep fastapi
pip list | grep torch
pip list | grep deepface
```

### Step 5: Environment Configuration

Copy the example environment file and configure it:

```powershell
cp .env.example .env
```

Edit `.env` with your configuration:

**PORCUPINE_ACCESS_KEY (Recommended)**
- Service: Wake word detection
- How to get: Sign up at https://console.picovoice.co/
- If not provided: System can run without it, but wake word behavior may differ
- Format: `PORCUPINE_ACCESS_KEY=your_access_key_here`

**GROQ_API_KEY (Optional)**
- Service: Faster speech-to-text processing
- How to get: Sign up at https://console.groq.com/
- If not provided: System uses local Whisper for transcription (slower, still works)
- Format: `GROQ_API_KEY=your_groq_api_key_here`

**OpenRouter API Key (Optional but recommended for quality)**
- Service: Cloud-based LLM inference (faster, better quality)
- How to get: Create account at https://openrouter.ai/
- If not provided: System uses local SmolLM2-1.7B model (slower but offline)
- Format: `OPENROUTER_API_KEY=your_openrouter_key_here`

Example `.env` file:
```
PORCUPINE_ACCESS_KEY=your_porcupine_key_here
GROQ_API_KEY=your_groq_key_here
OPENROUTER_API_KEY=your_openrouter_key_here
```

If keys are not available, you can still run the system - it will operate with reduced functionality (local inference only).

---

## How to Run All 7 Services

**Open 7 separate terminal windows** and start services in this exact order. Activate the virtual environment in each terminal.

### Terminal 1: Central Server (Port 8000)

```powershell
cd 01_central_server
python main.py
```

Expected output:
```
INFO:     Started server process [xxxx]
INFO:     Uvicorn running on http://127.0.0.1:8000
```

### Terminal 2: Vision Service (Port 8001)

```powershell
cd 02_vision_service
python main.py
```

Expected output:
```
VISION SERVICE - STARTUP
Service Port: 8001
Uvicorn running on http://127.0.0.1:8001
```

### Terminal 3: Audio Service (Port 8002)

```powershell
cd 03_audio_service
python main.py
```

Expected output:
```
Audio Service initializing...
Uvicorn running on http://127.0.0.1:8002
```

### Terminal 4: TTS Service (Port 8003)

```powershell
cd 04_tts_service
python main.py
```

Expected output:
```
Uvicorn running on http://127.0.0.1:8003
```

### Terminal 5: TeachMe Service (Port 8004)

```powershell
cd 05_teachme_service
python main.py
```

Expected output:
```
Starting TeachMe Service v4.0.0
Uvicorn running on http://127.0.0.1:8004
```

### Terminal 6: Enrollment Service (Port 8005)

```powershell
cd 06_enrollment_service
python orchestrator.py
```

Expected output:
```
Enrollment Service starting...
Uvicorn running on http://127.0.0.1:8005
```

### Terminal 7: LLM Service (Port 8006)

```powershell
cd 07_llm_service
python main.py
```

Expected output:
```
LLM Service starting...
Uvicorn running on http://127.0.0.1:8006
```

---

## Verify All Services Are Running

Once all 7 services have started, verify they are responding. In a new terminal:

```powershell
# Check each service health endpoint
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
curl http://localhost:8004/health
curl http://localhost:8005/health
curl http://localhost:8006/health
```

If all return HTTP 200 with health status, the system is ready.

---

## System Architecture

### How the System Works

**Voice Interaction Flow:**
1. Wake word detected locally ("Hey Nexi" via Porcupine)
2. Audio recorded and speaker verified (Resemblyzer embeddings)
3. Speech transcribed to text (Whisper or Groq API)
4. Facial emotion analyzed (FER2013 model)
5. Knowledge base searched for relevant context (TeachMe service)
6. Conversational response generated:
   - Primary: OpenRouter API (cloud, 2-3 seconds, better quality)
   - Fallback: SmolLM2-1.7B (local, 3-8 seconds, always available)
7. Response synthesized to speech (Piper TTS for English, Rehnuma for Urdu)
8. Audio played to user

**Total Latency:** 12-15 seconds (online), 20-25 seconds (offline, all local inference)

### Hybrid Architecture Benefits

- **High Availability:** Works without internet (fallback to local LLM)
- **Performance:** Uses cloud LLM when available for speed and quality
- **Privacy:** Core operations (voice, vision, knowledge) are local-only
- **Cost-Effective:** Reduces API calls by using local models as fallback
- **Resilience:** No single point of failure

### Service Communication

All services communicate via HTTP REST APIs on localhost. Central Server (8000) orchestrates requests to other services and aggregates results for context-aware LLM prompts.

---

## Core Capabilities

### Enrollment
Captures and stores user biometric data:
- 5 face samples for facial recognition
- 5 voice samples for speaker verification
- User profile with metadata

### Speaker Verification
Identifies returning users by voice with Resemblyzer speaker embeddings. Confidence scores determine verification outcome.

### Vision Capabilities
- Real-time face detection and recognition
- Facial expression analysis (7 emotions)
- Object detection and classification (80+ object types via YOLOv8)

### Knowledge Base
User-taught objects with visual embeddings. System retrieves relevant knowledge during conversation context building.

### Conversational AI
- Multi-turn context management with token-aware sliding window
- Hybrid LLM inference (cloud primary, local fallback)
- Emotion-aware response generation
- Bilingual support (English + Urdu)

### Resource Management
- Priority-based camera/microphone allocation
- Concurrent request handling with graceful degradation
- Circuit breaker pattern for fault tolerance

---

## File Structure

```
d:/Internship/TN_Team/Nexi_Robo/
├── 01_central_server/       # Orchestration hub and user database
├── 02_vision_service/       # Face/emotion/object detection
├── 03_audio_service/        # Voice I/O and speaker verification
├── 04_tts_service/          # Speech synthesis (English + Urdu)
├── 05_teachme_service/      # Knowledge base and semantic search
├── 06_enrollment_service/   # User biometric registration
├── 07_llm_service/          # Conversational AI (OpenRouter + SmolLM2)
├── docs/
│   ├── PROJECT_REPORT.md    # Technical report for management
│   └── NEXI_FLOW.md         # Complete operational documentation
├── shared/                  # Shared utilities and models
├── config/                  # Configuration files
├── tests/                   # Integration tests
├── .env.example             # Environment variable template
├── README.md                # This file
└── requirements.txt         # Python dependencies
```

For complete technical details, architecture diagrams, and operational flows, see:
- [PROJECT_REPORT.md](docs/PROJECT_REPORT.md) - Senior management technical report
- [NEXI_FLOW.md](docs/NEXI_FLOW.md) - Complete operational reference

---

## Troubleshooting

### Port Already in Use

If a service fails to start with "Address already in use":

```powershell
# Find what's using the port
netstat -ano | findstr :8000

# Kill the process (replace PID with actual process ID)
taskkill /PID <PID> /F
```

### Missing Dependencies

If pip install fails:

```powershell
# Upgrade pip first
pip install --upgrade pip setuptools wheel

# Try install again
pip install -r requirements.txt

# If specific package fails, check error message
# Common issue on Windows: Visual C++ Build Tools not installed
```

### Visual C++ Build Tools Error (Windows)

Error like "error: Microsoft Visual C++ 14.0 is required":

1. Ensure Visual C++ Build Tools are installed (see Step 3 above)
2. Restart your computer after installation
3. Reactivate your virtual environment
4. Run: `pip install --upgrade pip setuptools wheel`
5. Retry: `pip install -r requirements.txt`

### Service Won't Start or Crashes

1. Verify all dependencies: `pip list | grep <package_name>`
2. Check Python version: `python --version` (should be 3.9+)
3. Ensure virtual environment is activated: prompt shows `(venv)`
4. Check port is available: `netstat -ano | findstr :<port>`
5. Review service logs for error messages
6. Verify .env file has correct format and keys (if needed)

### Audio/Microphone Issues

- Ensure microphone is connected and recognized by system
- Check audio input levels in system settings
- Verify PORCUPINE_ACCESS_KEY is set for wake word detection
- Test with standalone audio recording tools first

### Vision Service Loads Slowly

Vision Service takes 15-20 seconds to load (loading face/emotion/object detection models). This is normal. Be patient on first startup.

### LLM Service No Response

Check if internet is available:
- Online: Waiting for OpenRouter API response (2-3 seconds normal)
- Offline: Using local SmolLM2 model (3-8 seconds, may be slow)

If neither works, check .env configuration and API keys.

---

## For Complete Documentation

For operational procedures, debugging guides, and detailed technical specifications, see:

- **[docs/NEXI_FLOW.md](docs/NEXI_FLOW.md)** - Complete operational reference with all 7 service scenarios and error handling
- **[docs/PROJECT_REPORT.md](docs/PROJECT_REPORT.md)** - Professional technical report with system analysis and deployment readiness

---

## Notes

- This is a production-ready prototype suitable for controlled deployments (up to ~50 concurrent users with JSON database)
- Database persistence uses JSON files; upgrade to PostgreSQL/MongoDB for scaling
- All core ML models and voice processing are local (offline-capable)
- LLM responses require cloud API when online mode is preferred; local fallback always available
- Resource management ensures graceful degradation if individual services fail

