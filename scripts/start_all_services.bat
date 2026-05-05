@echo off
REM Start all NEXI services in separate PowerShell windows (Windows batch)
REM This ensures services run independently without blocking each other

echo.
echo ============================================================
echo NEXI Backend - Multi-Service Startup Script
echo ============================================================
echo.
echo Starting 6 services in separate terminals...
echo.

REM Set the root directory
set ROOT_DIR=%~dp0
cd /d "%ROOT_DIR%"

REM Define ports
set CENTRAL_PORT=8000
set VISION_PORT=8001
set AUDIO_PORT=8002
set TTS_PORT=8003
set TEACHME_PORT=8004
set ENROLLMENT_PORT=8005

echo [1/6] Starting Mock Services (Tests)...
start "Mock Services" cmd /k "cd /d %ROOT_DIR% && python tests/mocks/mock_all_services.py"
timeout /t 2

echo [2/6] Starting Central Server (Port %CENTRAL_PORT%)...
start "Central Server" cmd /k "cd /d %ROOT_DIR%01_central_server && python main.py"
timeout /t 2

echo [3/6] Starting Vision Service (Port %VISION_PORT%)...
start "Vision Service" cmd /k "cd /d %ROOT_DIR%02_vision_service && python main.py"
timeout /t 2

echo [4/6] Starting Audio Service (Port %AUDIO_PORT%)...
start "Audio Service" cmd /k "cd /d %ROOT_DIR%03_audio_service && python main.py"
timeout /t 2

echo [5/6] Starting TTS Service (Port %TTS_PORT%)...
start "TTS Service" cmd /k "cd /d %ROOT_DIR%04_tts_service && python main.py"
timeout /t 2

echo [6/6] Starting TeachMe Service (Port %TEACHME_PORT%)...
start "TeachMe Service" cmd /k "cd /d %ROOT_DIR%05_teachme_service && python main.py"
timeout /t 2

echo [7/7] Starting Enrollment Service (Port %ENROLLMENT_PORT%)...
start "Enrollment Service" cmd /k "cd /d %ROOT_DIR%06_enrollment_service && python -m uvicorn app.main:app --port %ENROLLMENT_PORT% --host 127.0.0.1"

echo.
echo ============================================================
echo All services started in separate terminals!
echo ============================================================
echo.
echo Service Status:
echo   - Mock Services:       http://localhost:8000/health (mocks)
echo   - Central Server:      http://localhost:%CENTRAL_PORT%/health
echo   - Vision Service:      http://localhost:%VISION_PORT%/health
echo   - Audio Service:       http://localhost:%AUDIO_PORT%/health
echo   - TTS Service:         http://localhost:%TTS_PORT%/health
echo   - TeachMe Service:     http://localhost:%TEACHME_PORT%/health
echo   - Enrollment Service:  http://localhost:%ENROLLMENT_PORT%/health
echo.
echo Each service runs in its own terminal and will NOT block others.
echo Close individual terminals to stop specific services.
echo.
pause
