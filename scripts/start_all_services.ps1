# Start all NEXI services in separate PowerShell windows (Windows PowerShell)
# This ensures services run independently without blocking each other

Write-Host ""
Write-Host "============================================================"
Write-Host "NEXI Backend - Multi-Service Startup Script (PowerShell)"
Write-Host "============================================================"
Write-Host ""
Write-Host "Starting 6 services in separate terminals..."
Write-Host ""

# Get root directory
$ROOT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$ROOT_DIR = (Split-Path -Parent $ROOT_DIR) + "\"
Set-Location $ROOT_DIR

# Define ports
$CENTRAL_PORT = 8000
$VISION_PORT = 8001
$AUDIO_PORT = 8002
$TTS_PORT = 8003
$TEACHME_PORT = 8004
$ENROLLMENT_PORT = 8005

# Function to start a service in a new PowerShell window
function Start-ServiceWindow {
    param(
        [string]$ServiceName,
        [string]$Command,
        [int]$Number,
        [int]$Total
    )
    Write-Host "[$Number/$Total] Starting $ServiceName..."
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $Command -WindowStyle Normal
    Start-Sleep -Seconds 2
}

# Start Mock Services
Start-ServiceWindow -ServiceName "Mock Services" `
    -Command "Set-Location '$ROOT_DIR'; python tests/mocks/mock_all_services.py" `
    -Number 1 -Total 7

# Start Central Server
Start-ServiceWindow -ServiceName "Central Server (Port $CENTRAL_PORT)" `
    -Command "Set-Location '$ROOT_DIR\01_central_server'; python main.py" `
    -Number 2 -Total 7

# Start Vision Service
Start-ServiceWindow -ServiceName "Vision Service (Port $VISION_PORT)" `
    -Command "Set-Location '$ROOT_DIR\02_vision_service'; python main.py" `
    -Number 3 -Total 7

# Start Audio Service
Start-ServiceWindow -ServiceName "Audio Service (Port $AUDIO_PORT)" `
    -Command "Set-Location '$ROOT_DIR\03_audio_service'; python main.py" `
    -Number 4 -Total 7

# Start TTS Service
Start-ServiceWindow -ServiceName "TTS Service (Port $TTS_PORT)" `
    -Command "Set-Location '$ROOT_DIR\04_tts_service'; python main.py" `
    -Number 5 -Total 7

# Start TeachMe Service
Start-ServiceWindow -ServiceName "TeachMe Service (Port $TEACHME_PORT)" `
    -Command "Set-Location '$ROOT_DIR\05_teachme_service'; python main.py" `
    -Number 6 -Total 7

# Start Enrollment Service
Start-ServiceWindow -ServiceName "Enrollment Service (Port $ENROLLMENT_PORT)" `
    -Command "Set-Location '$ROOT_DIR\06_enrollment_service'; python -m uvicorn app.main:app --port $ENROLLMENT_PORT --host 127.0.0.1" `
    -Number 7 -Total 7

Write-Host ""
Write-Host "============================================================"
Write-Host "All services started in separate terminals!"
Write-Host "============================================================"
Write-Host ""
Write-Host "Service Status:"
Write-Host "  - Mock Services:       http://localhost:8000/health (mocks)"
Write-Host "  - Central Server:      http://localhost:$CENTRAL_PORT/health"
Write-Host "  - Vision Service:      http://localhost:$VISION_PORT/health"
Write-Host "  - Audio Service:       http://localhost:$AUDIO_PORT/health"
Write-Host "  - TTS Service:         http://localhost:$TTS_PORT/health"
Write-Host "  - TeachMe Service:     http://localhost:$TEACHME_PORT/health"
Write-Host "  - Enrollment Service:  http://localhost:$ENROLLMENT_PORT/health"
Write-Host ""
Write-Host "Each service runs in its own terminal and will NOT block others."
Write-Host "Close individual terminals to stop specific services."
Write-Host ""
