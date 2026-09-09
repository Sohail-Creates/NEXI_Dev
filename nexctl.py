#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
NEXI Robot Control Terminal (nexctl)
A menu-driven CLI for full system control across all 7 microservices.

Usage:
    # Local development
    cd /path/to/nex-i-robot
    source venv/bin/activate  # or .\\venv\\Scripts\\Activate.ps1 on Windows
    python nexctl.py
    
    # Docker
    docker compose run --rm nexctl
"""

from __future__ import annotations
import os
import sys
import time
import json
import logging
import traceback
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import base64
import wave
import io

# Core dependencies
try:
    import cv2
    import numpy as np
    import requests
    import pyaudio
    from PIL import Image
except ImportError as e:
    print(f"FATAL: Missing dependency: {e}")
    print("Install dependencies: pip install -r requirements.txt")
    sys.exit(1)

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, use system env

# ============================================================================
# CONFIGURATION
# ============================================================================

# Service base URLs (default, can be overridden via .env)
# In Docker, services communicate via Docker DNS names (central, vision, etc.)
# Locally, use localhost
def get_service_urls() -> Dict[str, str]:
    """Get service URLs from environment or defaults."""
    # Check if running in Docker (Docker sets HOSTNAME to container ID)
    in_docker = os.path.exists('/.dockerenv') or os.environ.get('IN_DOCKER') == 'true'
    
    if in_docker:
        # Docker internal networking
        return {
            "central": "http://central:8000",
            "vision": "http://vision:8001",
            "audio": "http://audio:8002",
            "tts": "http://tts:8003",
            "teachme": "http://teachme:8004",
            "enrollment": "http://enrollment:8005",
            "llm": "http://llm:8006",
        }
    else:
        # Local development - use localhost with configurable ports
        return {
            "central": os.getenv("CENTRAL_SERVER_URL", "http://localhost:8000"),
            "vision": os.getenv("VISION_SERVICE_URL", "http://localhost:8001"),
            "audio": os.getenv("AUDIO_SERVICE_URL", "http://localhost:8002"),
            "tts": os.getenv("TTS_SERVICE_URL", "http://localhost:8003"),
            "teachme": os.getenv("TEACHME_SERVICE_URL", "http://localhost:8004"),
            "enrollment": os.getenv("ENROLLMENT_SERVICE_URL", "http://localhost:8005"),
            "llm": os.getenv("LLM_SERVICE_URL", "http://localhost:8006"),
        }

DEFAULT_SERVICE_URLS = get_service_urls()

# Project directories - configurable via env
PROJECT_ROOT = Path(os.getenv("NEXI_PROJECT_ROOT", Path(__file__).parent.resolve()))
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Temp directories for audio/images
TEMP_DIR = PROJECT_ROOT / "temp"
TEMP_DIR.mkdir(exist_ok=True)
TEMP_AUDIO_DIR = TEMP_DIR / "audio"
TEMP_AUDIO_DIR.mkdir(exist_ok=True)

# Audio recording settings
AUDIO_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_FORMAT = pyaudio.paInt16
AUDIO_CHUNK_SIZE = 1024


# ============================================================================
# LOGGING SETUP
# ============================================================================

class ConsoleHandler(logging.Handler):
    """Minimal console handler for menu mode."""
    def __init__(self):
        super().__init__()
        self.setLevel(logging.INFO)
        fmt = logging.Formatter('%(message)s')
        self.setFormatter(fmt)
    
    def emit(self, record):
        try:
            msg = self.format(record)
            if record.levelno >= logging.WARNING:
                print(f"\033[93m{msg}\033[0m")  # Yellow
            elif record.levelno >= logging.ERROR:
                print(f"\033[91m{msg}\033[0m")  # Red
            else:
                print(msg)
        except Exception:
            pass


class FileHandler(logging.Handler):
    """Log to file with full tracebacks."""
    def __init__(self):
        super().__init__()
        self.setLevel(logging.DEBUG)
        log_file = LOG_DIR / f"nexctl_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self.file = open(log_file, 'w', encoding='utf-8')
        fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s\n%(exc_info)s')
        self.setFormatter(fmt)
    
    def emit(self, record):
        try:
            if record.exc_info:
                self.file.write(self.format(record) + '\n')
            else:
                self.file.write(self.format(record) + '\n')
            self.file.flush()
        except Exception:
            pass


logger = logging.getLogger("nexctl")
logger.setLevel(logging.DEBUG)
logger.addHandler(ConsoleHandler())
logger.addHandler(FileHandler())


# ============================================================================
# SERVICE CLIENT
# ============================================================================

class ServiceClient:
    """Unified HTTP client for all NEXI services."""
    
    def __init__(self):
        # Load from .env or use defaults
        self.base_urls = DEFAULT_SERVICE_URLS.copy()
        self._load_env()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "NEXI-CLI/1.0"})
    
    def _load_env(self):
        """Load service URLs from .env file if exists."""
        env_file = PROJECT_ROOT / ".env"
        if env_file.exists():
            try:
                import dotenv
                dotenv.load_dotenv(env_file)
                self.base_urls["central"] = os.getenv("CENTRAL_SERVER_URL", DEFAULT_SERVICE_URLS["central"])
                self.base_urls["vision"] = os.getenv("VISION_SERVICE_URL", DEFAULT_SERVICE_URLS["vision"])
                self.base_urls["audio"] = os.getenv("AUDIO_SERVICE_URL", DEFAULT_SERVICE_URLS["audio"])
                self.base_urls["tts"] = os.getenv("TTS_SERVICE_URL", DEFAULT_SERVICE_URLS["tts"])
                self.base_urls["teachme"] = os.getenv("TEACHME_SERVICE_URL", DEFAULT_SERVICE_URLS["teachme"])
                self.base_urls["enrollment"] = os.getenv("ENROLLMENT_SERVICE_URL", DEFAULT_SERVICE_URLS["enrollment"])
                self.base_urls["llm"] = os.getenv("LLM_SERVICE_URL", DEFAULT_SERVICE_URLS["llm"])
                logger.info("Service URLs loaded from .env")
            except Exception as e:
                logger.warning(f"Could not load .env: {e}")
    
    def get_url(self, service: str) -> str:
        return self.base_urls.get(service, DEFAULT_SERVICE_URLS.get(service, f"http://localhost:8000"))
    
    def _request(self, method: str, service: str, path: str, **kwargs) -> Optional[Dict]:
        """Low-level HTTP request with error handling."""
        url = self.get_url(service) + path
        try:
            if method.upper() == "GET":
                resp = self.session.get(url, timeout=15, **kwargs)
            elif method.upper() == "POST":
                resp = self.session.post(url, timeout=30, **kwargs)
            elif method.upper() == "PUT":
                resp = self.session.put(url, timeout=30, **kwargs)
            elif method.upper() == "DELETE":
                resp = self.session.delete(url, timeout=15, **kwargs)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            if resp.status_code >= 400:
                try:
                    return {"error": f"HTTP {resp.status_code}: {resp.json()}"}
                except:
                    return {"error": f"HTTP {resp.status_code}: {resp.text}"}
            
            return resp.json()
        except requests.exceptions.ConnectionError:
            return {"error": f"Service '{service}' unreachable at {url}"}
        except requests.exceptions.Timeout:
            return {"error": f"Request to '{service}' timed out"}
        except Exception as e:
            return {"error": f"Unexpected error: {e}"}
    
    def get(self, service: str, path: str) -> Optional[Dict]:
        return self._request("GET", service, path)
    
    def post(self, service: str, path: str, json: Dict = None, files: Dict = None) -> Optional[Dict]:
        if json and files:
            return self._request("POST", service, path, data=json, files=files)
        return self._request("POST", service, path, json=json)
    
    def check_health(self, service: str) -> Dict:
        """Quick health check for a service."""
        # Service-specific health endpoints
        health_paths = {
            "llm": "/api/v1/health",
        }
        path = health_paths.get(service, "/health")
        
        try:
            url = self.get_url(service)
            resp = self.session.get(url + path, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return {"healthy": True, "status": data}
            return {"healthy": False, "status": f"HTTP {resp.status_code}"}
        except:
            return {"healthy": False, "status": "unreachable"}


# ============================================================================
# CAMERA CAPTURE
# ============================================================================

class CameraCapture:
    """Helper for camera operations with GUI preview."""
    
    def __init__(self):
        self.cap = None
        self.preview_window = "NEXI Camera - Press SPACE to capture, ESC to cancel"
    
    def open(self):
        """Open default camera."""
        if self.cap is None:
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                raise RuntimeError("Could not open camera. Check camera permissions.")
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        return self.cap
    
    def close(self):
        """Close camera and destroy windows."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        cv2.destroyAllWindows()
    
    def capture_photo(self, label: str = "Press SPACE to capture, ESC to cancel") -> Optional[str]:
        """Capture single photo with GUI preview. Returns base64 JPEG."""
        self.open()
        try:
            frame_count = 0
            while True:
                ret, frame = self.cap.read()
                if not ret:
                    logger.warning("Failed to read frame from camera")
                    return None
                
                frame_count += 1
                if frame_count % 5 == 0:  # Show label every 5 frames
                    cv2.putText(frame, label, (20, 40),
                               cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
                
                cv2.imshow(self.preview_window, frame)
                
                key = cv2.waitKey(30) & 0xFF
                if key == 32:  # SPACE
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    b64 = base64.b64encode(buffer).decode('utf-8')
                    return b64
                elif key == 27:  # ESC
                    return None
        finally:
            self.close()
    
    def capture_multiple(self, count: int, label_prefix: str = "Photo") -> List[str]:
        """Capture multiple photos. Returns list of base64 JPEGs."""
        self.open()
        photos = []
        try:
            for i in range(count):
                while True:
                    ret, frame = self.cap.read()
                    if not ret:
                        continue
                    
                    label = f"{label_prefix} {i+1}/{count} - Press SPACE, ESC to cancel"
                    cv2.putText(frame, label, (20, 40),
                               cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
                    cv2.imshow(self.preview_window, frame)
                    
                    key = cv2.waitKey(30) & 0xFF
                    if key == 32:  # SPACE
                        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                        b64 = base64.b64encode(buffer).decode('utf-8')
                        photos.append(b64)
                        logger.info(f"Captured {label_prefix} {i+1}/{count}")
                        time.sleep(0.5)  # Brief pause before next
                        break
                    elif key == 27:  # ESC
                        self.close()
                        return photos
        finally:
            self.close()
        return photos
    
    def capture_with_detection(self, detector_backend: str = "opencv") -> Optional[str]:
        """Capture photo with real-time face detection overlay."""
        self.open()
        try:
            while True:
                ret, frame = self.cap.read()
                if not ret:
                    continue
                
                # Draw detection hint
                cv2.putText(frame, "Detecting faces... (SPACE to capture)", (20, 40),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
                
                # Try face detection (non-blocking)
                try:
                    from deepface import DeepFace
                    faces = DeepFace.extract_faces(frame, detector_backend=detector_backend, enforce_detection=False, align=True)
                    for face in faces:
                        area = face.get('facial_area', {})
                        x, y, w, h = area.get('x', 0), area.get('y', 0), area.get('w', 0), area.get('h', 0)
                        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                except Exception as e:
                    cv2.putText(frame, f"Detection: {e}", (20, 70),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 1)
                
                cv2.imshow(self.preview_window, frame)
                
                key = cv2.waitKey(30) & 0xFF
                if key == 32:
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    return base64.b64encode(buffer).decode('utf-8')
                elif key == 27:
                    return None
        finally:
            self.close()


# ============================================================================
# AUDIO CAPTURE
# ============================================================================

class AudioCapture:
    """Helper for audio recording with pyaudio."""
    
    def __init__(self, rate: int = AUDIO_RATE, channels: int = AUDIO_CHANNELS, 
                 format_: int = AUDIO_FORMAT, chunk_size: int = AUDIO_CHUNK_SIZE):
        self.rate = rate
        self.channels = channels
        self.format = format_
        self.chunk_size = chunk_size
        self.audio = pyaudio.PyAudio()
        self.stream = None
    
    def record_wav(self, duration: float = 3.0, output_path: Optional[str] = None) -> Optional[str]:
        """Record audio to WAV file. Returns file path."""
        if output_path is None:
            output_path = str(PROJECT_ROOT / "temp_audio" / f"record_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav")
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        logger.info(f"Recording {duration}s audio to {output_path}...")
        logger.info("Press SPACE in camera window to trigger, or wait for auto-stop")
        
        try:
            self.stream = self.audio.open(format=self.format, channels=self.channels,
                                         rate=self.rate, input=True,
                                         frames_per_buffer=self.chunk_size)
            frames = []
            start_time = time.time()
            
            # Simple timeout-based recording (can be improved with keyboard trigger)
            while time.time() - start_time < duration:
                data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                frames.append(data)
            
            self.stream.stop_stream()
            
            with wave.open(output_path, 'wb') as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(self.audio.get_sample_size(self.format))
                wf.setframerate(self.rate)
                wf.writeframes(b''.join(frames))
            
            logger.info(f"Audio saved: {output_path} ({os.path.getsize(output_path)} bytes)")
            return output_path
        except Exception as e:
            logger.error(f"Audio recording failed: {e}")
            return None
        finally:
            if self.stream:
                try:
                    self.stream.stop_stream()
                    self.stream.close()
                except:
                    pass
    
    def record_multiple(self, count: int, duration: float = 3.0) -> List[str]:
        """Record multiple audio samples. Returns list of file paths."""
        paths = []
        for i in range(count):
            path = str(PROJECT_ROOT / "temp_audio" / f"sample_{i+1}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav")
            result = self.record_wav(duration=duration, output_path=path)
            if result:
                paths.append(result)
        return paths
    
    def close(self):
        """Close audio stream."""
        try:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
            self.audio.terminate()
        except:
            pass


# ============================================================================
# MENU CLASSES
# ============================================================================

class MenuSection:
    """Base class for menu sections."""
    def __init__(self, cli: 'NexusCLI'):
        self.cli = cli
        self.client = cli.client
    
    def run(self):
        """Main entry point. Returns True to continue, False to exit."""
        while True:
            self.show_menu()
            choice = input("\nSelect option (or 'b' to back): ").strip()
            if choice.lower() == 'b':
                return True
            if choice.lower() == 'q':
                return False
            self.handle_choice(choice)
    
    def show_menu(self):
        """Override in subclass."""
        pass
    
    def handle_choice(self, choice: str):
        """Override in subclass."""
        pass
    
    def wait(self, msg: str = "Press ENTER to continue..."):
        """Wait for user input."""
        input(f"\n\033[96m{msg}\033[0m")


class SystemMenu(MenuSection):
    """System health and status."""
    
    def show_menu(self):
        print("\n" + "="*60)
        print("  1) SYSTEM HEALTH & STATUS")
        print("="*60)
        print("  1.1) Check all services health")
        print("  1.2) Central Server - List users")
        print("  1.3) Enrollment - Storage stats")
        print("  1.4) TeachMe - Knowledge stats")
        print("  1.5) Vision - Stream status")
        print("  1.6) Audio - Conversation state")
        print()
    
    def handle_choice(self, choice: str):
        if choice == "1.1":
            print("\nChecking all services...")
            for svc in ["central", "vision", "audio", "tts", "teachme", "enrollment", "llm"]:
                result = self.client.check_health(svc)
                if result.get("healthy"):
                    print(f"  ✓ {svc.upper():12} -> HTTP 200")
                else:
                    print(f"  ✗ {svc.upper():12} -> {result.get('status', 'unreachable')}")
        elif choice == "1.2":
            result = self.client.get("central", "/users/list")
            if result and "users" in result:
                print(f"\n  Found {len(result['users'])} users:")
                for u in result['users']:
                    print(f"    - {u.get('user_name')} (ID: {u.get('user_id')})")
                    print(f"      Faces: {u.get('sample_count', {}).get('images', 0)}, Audio: {u.get('sample_count', {}).get('audio', 0)}")
            else:
                print(f"\n  Error: {result}")
        elif choice == "1.3":
            result = self.client.get("enrollment", "/enrollment/storage/stats")
            if result and "status" in result:
                print(f"\n  Storage stats: {json.dumps(result, indent=2)}")
            else:
                print(f"\n  Error: {result}")
        elif choice == "1.4":
            # TeachMe stats
            result = self.client.get("teachme", "/api/v1/objects/test_user")
            count = len(result) if isinstance(result, list) else 0
            print(f"\n  TeachMe objects (test_user): {count}")
        elif choice == "1.5":
            print("\n  Vision stream available at:")
            print("    http://localhost:8001/stream")
            print("    http://localhost:8001/live  (HTML viewer)")
        elif choice == "1.6":
            result = self.client.get("audio", "/api/v1/conversation/state")
            if result:
                print(f"\n  Conversation state: {result}")
            else:
                print("\n  Audio service may not have conversation routes")
        else:
            print("\n  Invalid choice")


class EnrollmentMenu(MenuSection):
    """User enrollment and management."""
    
    def show_menu(self):
        print("\n" + "="*60)
        print("  2) USER ENROLLMENT & MANAGEMENT")
        print("="*60)
        print("  2.1) Enroll new user (5 photos + 5 voice)")
        print("  2.2) Enroll with voice only (3 samples)")
        print("  2.3) Check if user exists")
        print("  2.4) List all enrollments")
        print("  2.5) View enrollment details")
        print("  2.6) Improve training (add 5+5)")
        print("  2.7) Re-enroll (replace all)")
        print("  2.8) Delete enrollment")
        print("  2.9) Delete user everywhere")
        print("  2.10) Central Server user CRUD")
        print()
    
    def handle_choice(self, choice: str):
        if choice == "2.1":
            name = input("\n  Enter user name: ").strip()
            if not name:
                print("  Name required")
                return
            print("\n  Capturing 5 photos...")
            cam = CameraCapture()
            photos = cam.capture_multiple(5, "Photo")
            cam.close()
            if len(photos) < 5:
                print(f"  Only captured {len(photos)} photos (need 5)")
                return
            
            print("\n  Recording 5 voice samples...")
            audio = AudioCapture()
            audio_paths = audio.record_multiple(5, duration=3.0)
            audio.close()
            if len(audio_paths) < 5:
                print(f"  Only recorded {len(audio_paths)} samples (need 5)")
                return
            
            # Convert to files for multipart upload
            files = []
            for p in audio_paths:
                files.append(('voice_samples', (os.path.basename(p), open(p, 'rb'), 'audio/wav')))
            for i, p in enumerate(photos):
                img_data = base64.b64decode(p)
                img_bytes = io.BytesIO(img_data)
                files.append(('photos', (f"photo_{i}.jpg", img_bytes, 'image/jpeg')))
            
            print("\n  Uploading to Enrollment Service...")
            result = self.client.post("enrollment", "/enrollment/enroll", files=files)
            print(f"\n  Result: {json.dumps(result, indent=2)}")
            
        elif choice == "2.2":
            name = input("\n  Enter user name: ").strip()
            if not name:
                print("  Name required")
                return
            print("\n  Recording 3 voice samples...")
            audio = AudioCapture()
            audio_paths = audio.record_multiple(3, duration=3.0)
            audio.close()
            if len(audio_paths) < 3:
                print(f"  Only recorded {len(audio_paths)} samples")
                return
            
            files = []
            for p in audio_paths:
                files.append(('audio_sample1' if p == audio_paths[0] else 'audio_sample2' if p == audio_paths[1] else 'audio_sample3', 
                             (os.path.basename(p), open(p, 'rb'), 'audio/wav')))
            
            result = self.client.post("central", "/users/register-with-voice", files=files)
            print(f"\n  Result: {json.dumps(result, indent=2)}")
            
        elif choice == "2.3":
            name = input("\n  Enter user name to check: ").strip()
            result = self.client.get("enrollment", f"/enrollment/check-user?name={name}")
            if result:
                exists = result.get("exists", False)
                if exists:
                    print(f"\n  User '{name}' exists with ID: {result.get('user_id')}")
                else:
                    print(f"\n  User '{name}' not found")
            else:
                print("\n  Error: Could not check user")
                
        elif choice == "2.4":
            result = self.client.get("enrollment", "/enrollment/storage/list")
            if result and "user_ids" in result:
                print(f"\n  Found {len(result['user_ids'])} enrollments:")
                for uid in result['user_ids']:
                    print(f"    - {uid}")
            else:
                print(f"\n  Error: {result}")
                
        elif choice == "2.5":
            uid = input("\n  Enter user_id: ").strip()
            result = self.client.get("enrollment", f"/enrollment/storage/{uid}")
            if result and "user_id" in result:
                print(f"\n  Enrollment data for {result.get('user_name')}:")
                print(f"    Saved at: {result.get('saved_at')}")
                # Extract sample counts
                data = result.get("enrollment_data", {})
                print(f"    Photos: {len(data.get('photos', []))}")
                print(f"    Voice samples: {len(data.get('voice_samples', []))}")
            else:
                print(f"\n  Error: {result}")
                
        elif choice in ["2.6", "2.7", "2.8", "2.9"]:
            print("\n  This feature requires user_id")
            uid = input("  Enter user_id: ").strip()
            
            if choice == "2.6":
                print("  Improving training with 5+5 samples...")
                audio = AudioCapture()
                audio_paths = audio.record_multiple(5, duration=3.0)
                audio.close()
                files = []
                for p in audio_paths:
                    files.append(('additional_voice_samples', (os.path.basename(p), open(p, 'rb'), 'audio/wav')))
                result = self.client.post("enrollment", f"/enrollment/improve-training/{uid}", files=files)
                print(f"  Result: {result}")
                
            elif choice == "2.7":
                print("  Re-enrolling (replacing all)...")
                audio = AudioCapture()
                audio_paths = audio.record_multiple(5, duration=3.0)
                audio.close()
                files = []
                for p in audio_paths:
                    files.append(('new_voice_samples', (os.path.basename(p), open(p, 'rb'), 'audio/wav')))
                result = self.client.post("enrollment", f"/enrollment/update-model/{uid}", files=files)
                print(f"  Result: {result}")
                
            elif choice == "2.8":
                confirm = input(f"  Delete enrollment {uid}? (yes/no): ").strip().lower()
                if confirm == "yes":
                    result = self.client.delete("enrollment", f"/enrollment/storage/{uid}")
                    print(f"  Result: {result}")
                    
            elif choice == "2.9":
                user_name = input("  Enter user name: ").strip()
                result = self.client.delete("enrollment", f"/enrollment/delete-user/{user_name}")
                print(f"  Result: {result}")
                
        elif choice == "2.10":
            print("\n  Central Server user operations:")
            print("    GET /users/check?name={name}")
            print("    POST /users/register")
            print("    DELETE /users/{user_id}")
            self.wait()
        else:
            print("\n  Invalid choice")


class VisionMenu(MenuSection):
    """Vision and camera operations."""
    
    def show_menu(self):
        print("\n" + "="*60)
        print("  3) VISION & CAMERA")
        print("="*60)
        print("  3.1) Start MJPEG stream viewer")
        print("  3.2) Capture single frame + detect faces")
        print("  3.3) Upload image + detect faces")
        print("  3.4) Complete analysis (faces + objects)")
        print("  3.5) Object detection only")
        print("  3.6) Pause/Resume camera")
        print("  3.7) Camera health")
        print()
    
    def handle_choice(self, choice: str):
        if choice == "3.1":
            import webbrowser
            url = "http://localhost:8001/live"
            print(f"\n  Opening {url} in browser...")
            webbrowser.open(url)
            self.wait()
            
        elif choice == "3.2":
            print("\n  Opening camera for capture...")
            cam = CameraCapture()
            b64_img = cam.capture_photo()
            cam.close()
            if b64_img:
                result = self.client.post("vision", "/api/v1/detect/faces", 
                                         json={"image_base64": b64_img})
                if result:
                    faces = result.get("faces_detected", 0)
                    print(f"\n  Detected {faces} faces")
                    if faces > 0:
                        print(f"  First face confidence: {result.get('faces', [{}])[0].get('confidence', 0):.2f}")
            else:
                print("\n  Capture cancelled")
                
        elif choice == "3.3":
            path = input("\n  Enter image path: ").strip()
            if os.path.exists(path):
                with open(path, 'rb') as f:
                    img_data = base64.b64encode(f.read()).decode()
                result = self.client.post("vision", "/api/v1/detect/faces/upload",
                                         json={"file": img_data})
                print(f"\n  Result: {result}")
            else:
                print("\n  File not found")
                
        elif choice == "3.4":
            print("\n  Performing complete analysis...")
            result = self.client.post("vision", "/api/v1/analyze/complete")
            if result:
                print(f"\n  Faces detected: {result.get('faces_detected', 0)}")
                print(f"  Objects detected: {result.get('objects_detected', 0)}")
            else:
                print(f"\n  Error: {result}")
                
        elif choice == "3.5":
            print("\n  Running object detection...")
            result = self.client.post("vision", "/api/v1/detect/objects")
            print(f"\n  Result: {result}")
            
        elif choice == "3.6":
            print("\n  Pausing camera...")
            result = self.client.post("vision", "/api/v1/camera/pause")
            print(f"  Result: {result}")
            input("  Press ENTER to resume...")
            result = self.client.post("vision", "/api/v1/camera/resume")
            print(f"  Result: {result}")
            
        elif choice == "3.7":
            result = self.client.check_health("vision")
            print(f"\n  Vision service: {result}")
        else:
            print("\n  Invalid choice")


class TeachMeMenu(MenuSection):
    """TeachMe RAG pipeline."""
    
    def show_menu(self):
        print("\n" + "="*60)
        print("  4) TEACHME (RAG PIPELINE)")
        print("="*60)
        print("  4.1) Teach new object (camera → embed → store)")
        print("  4.2) Recall / Query (camera → embed → search)")
        print("  4.3) List taught objects")
        print("  4.4) Delete object")
        print("  4.5) View knowledge base stats")
        print("  4.6) Clear knowledge base (dev)")
        print()
    
    def handle_choice(self, choice: str):
        owner_id = "demo_user"
        
        if choice == "4.1":
            print("\n  Capturing object image...")
            cam = CameraCapture()
            b64_img = cam.capture_photo("Press SPACE to capture object, ESC to cancel")
            cam.close()
            if not b64_img:
                print("\n  Capture cancelled")
                return
            
            label = input("  Enter object label (e.g., 'apple'): ").strip()
            if not label:
                print("\n  Label required")
                return
            
            category = input("  Enter category (press ENTER for 'general'): ").strip() or "general"
            
            data = {
                "owner_id": owner_id,
                "image_base64": b64_img,
                "label_text": label,
                "metadata": {"category": category}
            }
            
            print("\n  Teaching object...")
            result = self.client.post("teachme", "/api/v1/teach", json=data)
            
            if result:
                status = result.get("status")
                if status == "stored":
                    print(f"\n  ✓ Object '{label}' stored successfully")
                    print(f"    ID: {result.get('object_id')}")
                elif status == "conflict":
                    print(f"\n  ⚠ Object already exists")
                    print(f"    ID: {result.get('existing_id')}")
                else:
                    print(f"\n  Result: {result}")
                    
        elif choice == "4.2":
            print("\n  Capturing query image...")
            cam = CameraCapture()
            b64_img = cam.capture_photo("Press SPACE to capture query, ESC to cancel")
            cam.close()
            if not b64_img:
                print("\n  Capture cancelled")
                return
            
            query = input("  Enter query (e.g., 'What is this?'): ").strip()
            if not query:
                print("\n  Query required")
                return
            
            data = {
                "owner_id": owner_id,
                "image_base64": b64_img,
                "query_text": query
            }
            
            print("\n  Querying knowledge base...")
            result = self.client.post("teachme", "/api/v1/query", json=data)
            
            if result:
                status = result.get("status")
                if status == "match":
                    print(f"\n  ✓ Match found with confidence {result.get('confidence', 0):.2f}")
                    obj = result.get("object_id", {})
                    print(f"    Object: {obj.get('data', {}).get('name', 'unknown')}")
                elif status == "no_match":
                    print(f"\n  ⚠ No match found")
                else:
                    print(f"\n  Result: {result}")
                    
        elif choice == "4.3":
            result = self.client.get("teachme", f"/api/v1/objects/{owner_id}")
            if isinstance(result, list):
                print(f"\n  Found {len(result)} objects:")
                for obj in result:
                    data = obj.get("data", {})
                    print(f"    - {data.get('name', 'unknown')} (ID: {obj.get('id')})")
            else:
                print(f"\n  Error: {result}")
                
        elif choice == "4.4":
            obj_id = input("\n  Enter object_id to delete: ").strip()
            result = self.client.delete("teachme", f"/api/v1/objects/{obj_id}")
            print(f"\n  Result: {result}")
            
        elif choice == "4.5":
            # Custom stats endpoint
            result = self.client.get("teachme", f"/api/v1/objects/{owner_id}")
            count = len(result) if isinstance(result, list) else 0
            print(f"\n  Knowledge base stats:")
            print(f"    Objects: {count}")
            print(f"    Owner: {owner_id}")
            self.wait()
            
        elif choice == "4.6":
            confirm = input("\n  WARNING: This clears all objects. Continue? (yes/no): ").strip().lower()
            if confirm == "yes":
                # For now, just list objects
                result = self.client.get("teachme", f"/api/v1/objects/{owner_id}")
                if isinstance(result, list):
                    for obj in result:
                        self.client.delete("teachme", f"/api/v1/objects/{obj.get('id')}")
                    print("\n  Cleared all objects")
                else:
                    print(f"\n  Error: {result}")
            else:
                print("\n  Cancelled")
        else:
            print("\n  Invalid choice")


class AudioMenu(MenuSection):
    """Audio and conversation."""
    
    def show_menu(self):
        print("\n" + "="*60)
        print("  5) AUDIO & CONVERSATION")
        print("="*60)
        print("  5.1) Start wake-word listening")
        print("  5.2) Stop wake-word")
        print("  5.3) Detect wake-word once (blocking)")
        print("  5.4) Detect + record once")
        print("  5.5) Continuous conversation mode")
        print("  5.6) Record until silence (VAD)")
        print("  5.7) Speaker verification")
        print("  5.8) STT (transcribe)")
        print("  5.9) Full pipeline: wake → record → STT → LLM → TTS")
        print("  5.10) List enrolled speakers")
        print("  5.11) Conversation state")
        print()
    
    def handle_choice(self, choice: str):
        if choice == "5.1":
            print("\n  Starting wake-word detection...")
            result = self.client.post("audio", "/api/v1/wake-word/start")
            print(f"  Result: {result}")
            self.wait()
            print("\n  Stopping...")
            result = self.client.post("audio", "/api/v1/wake-word/stop")
            print(f"  Result: {result}")
            
        elif choice == "5.2":
            result = self.client.post("audio", "/api/v1/wake-word/stop")
            print(f"  Result: {result}")
            
        elif choice == "5.3":
            result = self.client.post("audio", "/api/v1/wake-word/detect")
            print(f"  Result: {result}")
            
        elif choice == "5.4":
            result = self.client.post("audio", "/api/v1/wake-word/detect-and-record")
            print(f"  Result: {result}")
            
        elif choice == "5.5":
            print("\n  Entering conversation mode...")
            result = self.client.post("audio", "/api/v1/set-detection-mode",
                                     json={"mode": "conversation"})
            print(f"  Result: {result}")
            input("  Press ENTER to exit conversation mode...")
            result = self.client.post("audio", "/api/v1/set-detection-mode",
                                     json={"mode": "idle"})
            print(f"  Result: {result}")
            
        elif choice == "5.6":
            audio = AudioCapture()
            duration = float(input("  Max duration (seconds): ").strip() or "5")
            path = audio.record_wav(duration=duration)
            audio.close()
            if path:
                print(f"\n  Audio saved: {path}")
                
        elif choice == "5.7":
            print("\n  Speaker verification endpoints:")
            print("    POST /api/v1/speaker/enroll")
            print("    POST /api/v1/speaker/verify")
            self.wait()
            
        elif choice == "5.8":
            path = input("\n  Enter audio file path: ").strip()
            if os.path.exists(path):
                with open(path, 'rb') as f:
                    files = {'audio': (os.path.basename(path), f, 'audio/wav')}
                result = self.client.post("audio", "/api/v1/stt/transcribe", files=files)
                print(f"\n  Transcription: {result}")
            else:
                print("\n  File not found")
                
        elif choice == "5.9":
            print("\n  Full pipeline (wake → record → STT → LLM → TTS):")
            print("  Step 1: Start wake-word listening...")
            result = self.client.post("audio", "/api/v1/wake-word/start")
            print(f"    {result}")
            input("  Press ENTER when wake word is detected...")
            print("  Step 2: Stop listening...")
            result = self.client.post("audio", "/api/v1/wake-word/stop")
            print(f"    {result}")
            print("  Step 3: Recording command...")
            audio = AudioCapture()
            path = audio.record_wav(duration=5.0)
            audio.close()
            if path:
                print(f"  Audio saved: {path}")
                print("  Step 4: Transcribing...")
                with open(path, 'rb') as f:
                    files = {'audio': (os.path.basename(path), f, 'audio/wav')}
                result = self.client.post("audio", "/api/v1/stt/transcribe", files=files)
                if result and "text" in result:
                    text = result["text"]
                    print(f"  Transcription: '{text}'")
                    print("  Step 5: Generating response (LLM)...")
                    llm_result = self.client.post("llm", "/api/v1/generate",
                                                 json={"query": text})
                    if llm_result and "text" in llm_result:
                        response = llm_result["text"]
                        print(f"  LLM Response: '{response}'")
                        print("  Step 6: Synthesizing speech (TTS)...")
                        tts_result = self.client.post("tts", "/api/v1/tts",
                                                     json={"text": response, "voice_id": "jenny"})
                        if tts_result:
                            print(f"  TTS Status: {tts_result}")
                            if "audio" in tts_result:
                                # Save and play audio
                                audio_data = base64.b64decode(tts_result["audio"])
                                audio_path = str(PROJECT_ROOT / "temp_audio" / "tts_response.wav")
                                os.makedirs(os.path.dirname(audio_path), exist_ok=True)
                                with open(audio_path, 'wb') as f:
                                    f.write(audio_data)
                                print(f"  Audio saved: {audio_path}")
                                print("  Playing...")
                                # Simple playback with pyaudio
                                self._play_audio(audio_path)
                    else:
                        print(f"  LLM Error: {llm_result}")
                else:
                    print(f"  STT Error: {result}")
            else:
                print("\n  Recording failed")
                
        elif choice == "5.10":
            result = self.client.get("audio", "/api/v1/speaker/list")
            print(f"  Result: {result}")
            
        elif choice == "5.11":
            result = self.client.get("audio", "/api/v1/conversation/state")
            print(f"  Result: {result}")
            
        else:
            print("\n  Invalid choice")
    
    def _play_audio(self, path: str):
        """Simple audio playback."""
        try:
            wf = wave.open(path, 'rb')
            p = pyaudio.PyAudio()
            stream = p.open(format=p.get_format_from_width(wf.getsampwidth()),
                          channels=wf.getnchannels(),
                          rate=wf.getframerate(),
                          output=True)
            data = wf.readframes(1024)
            while data:
                stream.write(data)
                data = wf.readframes(1024)
            stream.stop_stream()
            stream.close()
            p.terminate()
        except Exception as e:
            logger.error(f"Audio playback failed: {e}")


class LLMMenu(MenuSection):
    """LLM and formatting."""
    
    def show_menu(self):
        print("\n" + "="*60)
        print("  6) LLM & FORMATTING")
        print("="*60)
        print("  6.1) Free-form generation")
        print("  6.2) Format recall response (template/constrained)")
        print("  6.3) LLM health")
        print("  6.4) Test recall → format pipeline")
        print()
    
    def handle_choice(self, choice: str):
        if choice == "6.1":
            query = input("\n  Enter your query: ").strip()
            if query:
                result = self.client.post("llm", "/api/v1/generate",
                                         json={"query": query})
                if result and "text" in result:
                    print(f"\n  LLM Response: {result['text']}")
                else:
                    print(f"\n  Error: {result}")
                    
        elif choice == "6.2":
            label = input("  Enter object label: ").strip()
            category = input("  Enter category (press ENTER for 'general'): ").strip() or "general"
            
            result = self.client.post("llm", "/api/v1/format",
                                     json={
                                         "mode": "personal_match",
                                         "label": label,
                                         "metadata": {"category": category}
                                     })
            print(f"\n  Formatted response: {result}")
            
        elif choice == "6.3":
            result = self.client.check_health("llm")
            print(f"  LLM Service: {result}")
            
        elif choice == "6.4":
            print("\n  Testing recall → format pipeline:")
            owner_id = "demo_user"
            
            # Teach
            print("  Step 1: Teaching apple...")
            cam = CameraCapture()
            b64 = cam.capture_photo()
            cam.close()
            if b64:
                teach_result = self.client.post("teachme", "/api/v1/teach",
                                               json={"owner_id": owner_id, "image_base64": b64,
                                                    "label_text": "apple", "metadata": {"category": "fruit"}})
                print(f"    Teach result: {teach_result}")
                
                # Recall
                print("  Step 2: Querying...")
                query_result = self.client.post("teachme", "/api/v1/query",
                                               json={"owner_id": owner_id, "image_base64": b64,
                                                    "query_text": "What is this?"})
                print(f"    Query result: {query_result}")
                
                # Format
                if query_result and query_result.get("status") == "match":
                    obj_id = query_result.get("object_id", {})
                    label = obj_id.get("data", {}).get("name", "unknown")
                    result = self.client.post("llm", "/api/v1/format",
                                             json={
                                                 "mode": "personal_match",
                                                 "label": label,
                                                 "metadata": {"category": "fruit"}
                                             })
                    print(f"    Formatted: {result}")
                else:
                    print("  No match for formatting")
            else:
                print("\n  Capture cancelled")
        else:
            print("\n  Invalid choice")


class TTMenu(MenuSection):
    """Text-to-Speech."""
    
    def show_menu(self):
        print("\n" + "="*60)
        print("  7) TTS (TEXT-TO-SPEECH)")
        print("="*60)
        print("  7.1) Synthesize speech (Jenny)")
        print("  7.2) List available voices")
        print("  7.3) Play last synthesis")
        print("  7.4) TTS health")
        print()
    
    def handle_choice(self, choice: str):
        if choice == "7.1":
            text = input("\n  Enter text to synthesize: ").strip()
            if text:
                result = self.client.post("tts", "/api/v1/tts",
                                         json={"text": text, "voice_id": "jenny"})
                if result and "audio" in result:
                    audio_data = base64.b64decode(result["audio"])
                    audio_path = str(PROJECT_ROOT / "temp_audio" / "tts_response.wav")
                    os.makedirs(os.path.dirname(audio_path), exist_ok=True)
                    with open(audio_path, 'wb') as f:
                        f.write(audio_data)
                    print(f"\n  Audio saved: {audio_path}")
                    self._play_audio(audio_path)
                else:
                    print(f"\n  Error: {result}")
                    
        elif choice == "7.2":
            result = self.client.get("tts", "/api/v1/voices")
            print(f"\n  Available voices: {result}")
            
        elif choice == "7.3":
            # Find latest TTS audio
            audio_dir = PROJECT_ROOT / "temp_audio"
            if audio_dir.exists():
                files = list(audio_dir.glob("tts_*.wav"))
                if files:
                    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                    print(f"\n  Playing: {files[0].name}")
                    self._play_audio(str(files[0]))
                else:
                    print("\n  No TTS audio found")
            else:
                print("\n  No audio directory")
                
        elif choice == "7.4":
            result = self.client.check_health("tts")
            print(f"  TTS Service: {result}")
            
        else:
            print("\n  Invalid choice")
    
    def _play_audio(self, path: str):
        """Simple audio playback."""
        try:
            wf = wave.open(path, 'rb')
            p = pyaudio.PyAudio()
            stream = p.open(format=p.get_format_from_width(wf.getsampwidth()),
                          channels=wf.getnchannels(),
                          rate=wf.getframerate(),
                          output=True)
            data = wf.readframes(1024)
            while data:
                stream.write(data)
                data = wf.readframes(1024)
            stream.stop_stream()
            stream.close()
            p.terminate()
        except Exception as e:
            logger.error(f"Audio playback failed: {e}")


class UtilitiesMenu(MenuSection):
    """System utilities."""
    
    def show_menu(self):
        print("\n" + "="*60)
        print("  8) SYSTEM UTILITIES")
        print("="*60)
        print("  8.1) Restart all services")
        print("  8.2) Stop all services")
        print("  8.3) View service logs")
        print("  8.4) Clear TeachMe knowledge")
        print("  8.5) Clear enrollment data")
        print("  8.6) Run RAG pipeline test")
        print("  8.7) Run demo robot flow")
        print()
    
    def handle_choice(self, choice: str):
        if choice == "8.1":
            print("\n  Restarting all services...")
            import subprocess
            script = PROJECT_ROOT / "scripts" / "demo_start.py"
            if script.exists():
                print(f"  Running: python {script}")
                subprocess.Popen([sys.executable, str(script)],
                               cwd=str(PROJECT_ROOT),
                               creationflags=subprocess.DETACHED_PROCESS)
                print("  Services restarting...")
                self.wait()
            else:
                print("  demo_start.py not found")
                
        elif choice == "8.2":
            print("\n  Stopping all services...")
            import subprocess
            subprocess.run(["taskkill", "/F", "/IM", "python.exe", "/FI", 
                          f"WINDOWTITLE eq *8000*|*8001*|*8002*|*8003*|*8004*|*8005*|*8006*"],
                          shell=True, capture_output=True)
            print("  Processes stopped")
            self.wait()
            
        elif choice == "8.3":
            print("\n  Latest logs:")
            log_files = sorted(LOG_DIR.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True)
            if log_files:
                for f in log_files[:5]:
                    print(f"    {f.name} ({f.stat().st_size} bytes)")
                choice = input("  View which? (filename or 'c' to cancel): ").strip()
                if choice != 'c':
                    log_file = LOG_DIR / choice
                    if log_file.exists():
                        with open(log_file, 'r', encoding='utf-8') as f:
                            lines = f.readlines()[-50:]
                            print("\n" + "".join(lines))
            else:
                print("  No logs found")
            self.wait()
            
        elif choice == "8.4":
            confirm = input("\n  Clear TeachMe knowledge base? (yes/no): ").strip().lower()
            if confirm == "yes":
                knowledge_file = PROJECT_ROOT / "05_teachme_service" / "teachme_service" / "data" / "teachme_knowledge.json"
                if knowledge_file.exists():
                    knowledge_file.unlink()
                    print("  Deleted: teachme_knowledge.json")
                else:
                    print("  File not found")
                    
                index_dir = PROJECT_ROOT / "05_teachme_service" / "teachme_service" / "data" / "indexes"
                if index_dir.exists():
                    for f in index_dir.glob("*.faiss"):
                        f.unlink()
                    print(f"  Deleted {len(list(index_dir.glob('*.faiss')))} FAISS indexes")
                    
        elif choice == "8.5":
            confirm = input("\n  Clear enrollment data? (yes/no): ").strip().lower()
            if confirm == "yes":
                enrollment_dir = PROJECT_ROOT / "06_enrollment_service" / "enrollment_data"
                if enrollment_dir.exists():
                    import shutil
                    shutil.rmtree(enrollment_dir)
                    print("  Deleted enrollment_data/")
                else:
                    print("  Directory not found")
                    
        elif choice == "8.6":
            print("\n  Running RAG pipeline test...")
            test_file = PROJECT_ROOT / "tests" / "test_rag_pipeline.py"
            if test_file.exists():
                subprocess.run([sys.executable, str(test_file)], cwd=str(PROJECT_ROOT))
            else:
                print("  test_rag_pipeline.py not found")
            self.wait()
            
        elif choice == "8.7":
            print("\n  Running demo robot flow...")
            demo_file = PROJECT_ROOT / "tests" / "demo_robot_flow.py"
            if demo_file.exists():
                subprocess.run([sys.executable, str(demo_file)], cwd=str(PROJECT_ROOT))
            else:
                print("  demo_robot_flow.py not found")
            self.wait()
            
        else:
            print("\n  Invalid choice")


# ============================================================================
# MAIN CLI
# ============================================================================

class NexusCLI:
    """Main CLI application."""
    
    def __init__(self):
        self.client = ServiceClient()
        self.running = True
        
        # Menu sections
        self.menus = {
            "1": SystemMenu(self),
            "2": EnrollmentMenu(self),
            "3": VisionMenu(self),
            "4": TeachMeMenu(self),
            "5": AudioMenu(self),
            "6": LLMMenu(self),
            "7": TTMenu(self),
            "8": UtilitiesMenu(self),
        }
        
        logger.info("NEXI CLI initialized")
        print("\n" + "="*60)
        print("  NEXI Robot Control Terminal (nexctl)")
        print("  v1.0.0 - All microservices integrated")
        print("="*60)
        print(f"  Project: {PROJECT_ROOT}")
        print(f"  Logs: {LOG_DIR}")
        print()
        
        # Check services
        print("  Checking service availability...")
        all_ok = True
        for svc in ["central", "vision", "audio", "tts", "teachme", "enrollment", "llm"]:
            result = self.client.check_health(svc)
            status = "[OK]" if result.get("healthy") else "[FAIL]"
            print(f"    {status} {svc.upper():12} {result.get('status', 'unreachable')}")
            if not result.get("healthy"):
                all_ok = False
        print()
        
        if not all_ok:
            print("  [WARN] Some services are not responding. Start them with: python scripts/demo_start.py")
            print()
        
        self.wait_for_enter("Press ENTER to continue...")
    
    def wait_for_enter(self, msg: str = "Press ENTER to continue..."):
        """Wait for user input with prompt."""
        if not sys.stdin.isatty():
            return
        try:
            input(f"\n\033[96m{msg}\033[0m")
        except EOFError:
            pass
    
    def show_main_menu(self):
        """Show main menu."""
        print("\n" + "="*60)
        print("  MAIN MENU")
        print("="*60)
        print("  1) System Health & Status")
        print("  2) User Enrollment & Management")
        print("  3) Vision & Camera")
        print("  4) TeachMe (RAG) — Teach / Recall / Objects")
        print("  5) Audio & Conversation")
        print("  6) LLM & Formatting")
        print("  7) TTS (Text-to-Speech)")
        print("  8) System Utilities")
        print()
        print("  0) Exit")
        print("-"*60)
    
    def run(self):
        """Main loop."""
        while self.running:
            self.show_main_menu()
            choice = input("\n  Select [0-8]: ").strip()
            
            if choice == "0":
                print("\n  Goodbye!")
                logger.info("CLI exited by user")
                self.running = False
            elif choice in self.menus:
                cont = self.menus[choice].run()
                if not cont:
                    self.running = False
            else:
                print("\n  Invalid choice. Please select 0-8.")
                time.sleep(1)
    
    def run_test(self):
        """Run automated test."""
        print("\n  Running quick system test...")
        for svc in ["central", "vision", "audio", "tts", "teachme", "enrollment", "llm"]:
            result = self.client.check_health(svc)
            print(f"    {svc}: {'OK' if result.get('healthy') else 'FAIL'}")


if __name__ == "__main__":
    try:
        cli = NexusCLI()
        if len(sys.argv) > 1 and sys.argv[1] == "--test":
            cli.run_test()
        else:
            cli.run()
    except KeyboardInterrupt:
        print("\n\n  Goodbye!")
        logger.info("CLI exited via KeyboardInterrupt")
        sys.exit(0)
    except Exception as e:
        logger.error(f"FATAL ERROR: {e}")
        logger.error(f"Traceback:\n{''.join(traceback.format_exc())}")
        print(f"\n\n  FATAL ERROR: {e}")
        print("  Check logs in logs/ folder")
        sys.exit(1)
