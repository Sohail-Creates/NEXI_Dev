"""
Audio Service Test Suite - Comprehensive Version
Interactive testing interface for all audio service features.

This test suite covers:

EXISTING FEATURES (Week 1-3):
- Wake word detection with power management and VAD
- Speaker enrollment and verification
- Speech-to-text transcription with circuit breaker protection
- Power mode management
- Statistics and monitoring
- Error handling and resilience features

NEW INTEGRATED FEATURES:
- Offline queue management (SQLite-based)
- Backend service communication with circuit breaker
- Queue processor for automatic background processing
- Local Whisper transcription for offline mode
- Silence-based recording with auto-stop
- Complete pipeline orchestration endpoint

Author: Integration Testing Team
"""

import requests
import sounddevice as sd
import soundfile as sf
import numpy as np
import time
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any

# API Configuration
BASE_URL = "http://127.0.0.1:8002"
API_V1 = f"{BASE_URL}/api/v1"

# Test state management
last_enrolled_user: Optional[str] = None
last_recorded_file: Optional[str] = None
server_connected: bool = False

# Console formatting helpers
def print_header(text: str):
    """Print a formatted header"""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)

def print_success(text: str):
    """Print success message"""
    print(f"[OK] {text}")

def print_error(text: str):
    """Print error message"""
    print(f"[ERROR] {text}")

def print_info(text: str):
    """Print info message"""
    print(f"[INFO]  {text}")

def print_warning(text: str):
    """Print warning message"""
    print(f"[WARNING]  {text}")

def print_stats(label: str, value: Any):
    """Print statistics"""
    print(f"[STAT] {label}: {value}")

# Audio recording utility
def record_audio(duration: int = 3, sample_rate: int = 16000, filename: str = "test_audio.wav") -> str:
    """Record audio from microphone"""
    global last_recorded_file
    
    print_info(f"Recording for {duration} seconds... Speak now!")
    audio = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype='float32')
    sd.wait()
    
    # Save to file with absolute path
    import os
    absolute_path = os.path.abspath(filename)
    sf.write(absolute_path, audio, sample_rate)
    last_recorded_file = absolute_path
    print_success(f"Audio recorded and saved to {filename}")
    
    return absolute_path

# Server connectivity test
def test_server_connection() -> bool:
    """Test if the server is running"""
    global server_connected
    
    print_header("Testing Server Connection")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=30)
        if response.status_code == 200:
            print_success("Server is running!")
            server_connected = True
            return True
        else:
            print_error(f"Server returned status code: {response.status_code}")
            server_connected = False
            return False
    except requests.exceptions.ConnectionError:
        print_error("Cannot connect to server. Is it running?")
        print_info("Start the server with: python main.py")
        server_connected = False
        return False
    except Exception as e:
        print_error(f"Error: {str(e)}")
        server_connected = False
        return False

# Week 3 Feature Tests

def test_power_modes():
    """Test different power modes"""
    print_header("Testing Power Modes")
    
    if not server_connected:
        print_error("Server not connected. Run option 1 first.")
        return
    
    modes = ["low_power", "balanced", "high_performance"]
    
    print_info("Available power modes:")
    print("  1. low_power - Maximum power saving (VAD enabled, 100ms sleep)")
    print("  2. balanced - Balanced performance/power (VAD enabled, 50ms sleep)")
    print("  3. high_performance - Maximum accuracy (VAD disabled, no sleep)")
    
    mode_choice = input("\nSelect mode (1-3) or 'all' to test all: ").strip()
    
    if mode_choice == 'all':
        test_modes = modes
    else:
        mode_idx = int(mode_choice) - 1
        if 0 <= mode_idx < len(modes):
            test_modes = [modes[mode_idx]]
        else:
            print_error("Invalid choice")
            return
    
    for mode in test_modes:
        try:
            print_info(f"\nTesting {mode} mode...")
            response = requests.post(
                f"{API_V1}/wake-word/power-mode",
                json={"mode": mode},
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success(f"Power mode set to: {mode}")
                print_stats("Mode", data.get("mode", "unknown"))
                print_stats("VAD Enabled", data.get("vad_enabled", "unknown"))
                print_stats("Sleep Duration", f"{data.get('sleep_duration_ms', 0)}ms")
            else:
                print_error(f"Failed to set power mode: {response.text}")
                
        except Exception as e:
            print_error(f"Error testing power mode: {str(e)}")
    
    print_info("\nRecommendation: Use 'balanced' for most cases")

def test_wake_word_statistics():
    """View wake word detection statistics"""
    print_header("Wake Word Detection Statistics")
    
    if not server_connected:
        print_error("Server not connected. Run option 1 first.")
        return
    
    try:
        response = requests.get(f"{API_V1}/wake-word/stats", timeout=5)
        
        if response.status_code == 200:
            stats = response.json()
            print_success("Statistics retrieved!")
            print("\n[STAT] Detection Statistics:")
            print_stats("Total Frames Processed", stats.get("total_frames", 0))
            print_stats("Speech Frames", stats.get("speech_frames", 0))
            print_stats("Silence Frames", stats.get("silence_frames", 0))
            print_stats("Wake Word Detections", stats.get("detections", 0))
            
            # Calculate percentages
            total = stats.get("total_frames", 0)
            if total > 0:
                speech_pct = (stats.get("speech_frames", 0) / total) * 100
                silence_pct = (stats.get("silence_frames", 0) / total) * 100
                print_stats("Speech Percentage", f"{speech_pct:.1f}%")
                print_stats("Silence Percentage", f"{silence_pct:.1f}%")
            
            print_stats("Current Power Mode", stats.get("power_mode", "unknown"))
            print_stats("VAD Enabled", stats.get("vad_enabled", "unknown"))
            
        else:
            print_error(f"Failed to get statistics: {response.text}")
            
    except Exception as e:
        print_error(f"Error getting statistics: {str(e)}")

def test_circuit_breaker_status():
    """Check circuit breaker status"""
    print_header("Circuit Breaker Status")
    
    if not server_connected:
        print_error("Server not connected. Run option 1 first.")
        return
    
    try:
        response = requests.get(f"{API_V1}/stt/circuit-breaker-status", timeout=5)
        
        if response.status_code == 200:
            status = response.json()
            print_success("Circuit breaker status retrieved!")
            
            state = status.get("state", "unknown")
            print_stats("State", state)
            
            # Color code the state
            if state == "CLOSED":
                print_success("Circuit is healthy - all systems operational")
            elif state == "OPEN":
                print_error("Circuit is OPEN - API calls are blocked")
                print_warning("Service is in recovery mode")
            elif state == "HALF_OPEN":
                print_warning("Circuit is testing recovery")
            
            print_stats("Failure Count", status.get("failure_count", 0))
            print_stats("Success Count", status.get("success_count", 0))
            print_stats("Last Failure Time", status.get("last_failure_time", "N/A"))
            
            if state == "OPEN":
                print_info(f"Circuit will auto-recover in {status.get('recovery_timeout', 60)}s")
            
        else:
            print_error(f"Failed to get circuit breaker status: {response.text}")
            
    except Exception as e:
        print_error(f"Error getting circuit breaker status: {str(e)}")

def test_error_handling_demo():
    """Demonstrate error handling capabilities"""
    print_header("Error Handling & Recovery Demo")
    
    if not server_connected:
        print_error("Server not connected. Run option 1 first.")
        return
    
    print_info("This test demonstrates the error handling system")
    print("\nError scenarios available:")
    print("  1. Test invalid audio file")
    print("  2. Test missing user enrollment")
    print("  3. Test API timeout simulation")
    print("  4. View error recovery suggestions")
    
    choice = input("\nSelect test (1-4): ").strip()
    
    if choice == "1":
        # Test invalid audio
        print_info("\nTesting invalid audio file handling...")
        try:
            # Create an empty file
            invalid_file = "invalid_audio.wav"
            with open(invalid_file, 'w') as f:
                f.write("not audio data")
            
            with open(invalid_file, 'rb') as f:
                response = requests.post(
                    f"{API_V1}/transcribe",
                    files={"file": f},
                    timeout=10
                )
            
            if response.status_code >= 400:
                error_data = response.json()
                print_error("Error caught successfully!")
                print_info(f"Error: {error_data.get('detail', 'Unknown error')}")
                if 'recovery_suggestion' in error_data:
                    print_success(f"Recovery: {error_data['recovery_suggestion']}")
            
            os.remove(invalid_file)
            
        except Exception as e:
            print_error(f"Test error: {str(e)}")
    
    elif choice == "2":
        # Test missing enrollment
        print_info("\nTesting missing user enrollment handling...")
        try:
            response = requests.post(
                f"{API_V1}/verify-speaker",
                files={"file": ("test.wav", b"fake audio data")},
                data={"user_id": "nonexistent_user_12345"},
                timeout=10
            )
            
            if response.status_code >= 400:
                error_data = response.json()
                print_error("Error caught successfully!")
                print_info(f"Error: {error_data.get('detail', 'Unknown error')}")
                if 'recovery_suggestion' in error_data:
                    print_success(f"Recovery: {error_data['recovery_suggestion']}")
        
        except Exception as e:
            print_error(f"Test error: {str(e)}")
    
    elif choice == "4":
        print_info("\nCommon error recovery suggestions:")
        print("\n Microphone Errors:")
        print("   - Check microphone permissions")
        print("   - Ensure microphone is not used by another app")
        print("   - Try unplugging and replugging USB microphone")
        
        print("\n Transcription Errors:")
        print("   - Speak clearly and reduce background noise")
        print("   - Check internet connection for API access")
        print("   - Ensure audio is at least 1 second long")
        
        print("\n Wake Word Errors:")
        print("   - Say 'Hi Nexi' clearly with 1-2 second pause after")
        print("   - Adjust microphone sensitivity")
        print("   - Reduce background noise")

def test_quality_validation():
    """Test transcription quality validation"""
    print_header("Transcription Quality Validation")
    
    if not server_connected:
        print_error("Server not connected. Run option 1 first.")
        return
    
    print_info("This test shows quality validation features")
    print("Record audio and see quality analysis...")
    
    # Language selection
    print("\n Language Options:")
    print("  1. Auto-detect (recommended)")
    print("  2. Force English")
    print("  3. Force Urdu")
    
    lang_choice = input("\nSelect language (1-3, default 1): ").strip() or "1"
    language_map = {
        "1": "auto",
        "2": "en",
        "3": "ur"
    }
    language = language_map.get(lang_choice, "auto")
    
    if language != "auto":
        print_info(f"Forcing language: {language}")
    
    duration = int(input("\nRecording duration (seconds, 3-10): ") or "3")
    filename = record_audio(duration=duration)
    
    try:
        print_info("Transcribing with quality validation...")
        response = requests.post(
            f"{API_V1}/transcribe",
            json={"audio_file": filename, "language": language},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            print_success("Transcription completed!")
            
            print("\n Transcription Result:")
            print(f"   Text: \"{data.get('text', '')}\"")
            
            # Show quality metrics if available
            if 'quality_score' in data and data['quality_score'] is not None:
                print_stats("Quality Score", f"{data['quality_score']:.2f}")
            
            if 'confidence' in data and data['confidence'] is not None:
                print_stats("Confidence", f"{data['confidence']:.2f}")
            
            if 'language' in data:
                print_stats("Detected Language", data['language'])
            
            # Quality feedback
            text = data.get('text', '')
            if len(text) < 5:
                print_warning("Transcription seems short - audio may be unclear")
            elif len(text.split()) < 2:
                print_warning("Only one word detected - try speaking more")
            else:
                print_success("Good quality transcription!")
        
        else:
            print_error(f"Transcription failed: {response.text}")
    
    except Exception as e:
        print_error(f"Error: {str(e)}")

# Original Week 2 Tests (Enhanced)

def test_wake_word_detection():
    """Test wake word detection with enhanced monitoring"""
    print_header("Wake Word Detection Test")
    
    if not server_connected:
        print_error("Server not connected. Run option 1 first.")
        return
    
    try:
        # Get current power mode
        response = requests.get(f"{API_V1}/wake-word/power-mode", timeout=5)
        if response.status_code == 200:
            mode_info = response.json()
            print_info(f"Current Mode: {mode_info.get('mode', 'unknown')}")
            print_info(f"VAD Enabled: {mode_info.get('vad_enabled', False)}")
        
        print_info("Starting wake word detection...")
        print_info("Say 'Hi Nexi' to trigger detection (or press Ctrl+C to stop)")
        
        response = requests.post(f"{API_V1}/wake-word/detect", timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            print_success(" Wake word detected!")
            print_stats("Keyword", data.get("keyword", "unknown"))
            print_stats("Detection Time", f"{data.get('detection_time', 0):.2f}s")
            
            # Show detection statistics
            if 'frames_processed' in data:
                print_stats("Frames Processed", data['frames_processed'])
            if 'speech_frames' in data:
                print_stats("Speech Frames", data['speech_frames'])
        else:
            print_error(f"Detection failed: {response.text}")
            
    except requests.exceptions.Timeout:
        print_warning("Detection timed out - no wake word detected")
    except KeyboardInterrupt:
        print_warning("\nDetection cancelled by user")
    except Exception as e:
        print_error(f"Error: {str(e)}")

def test_speaker_enrollment():
    """Test speaker enrollment"""
    global last_enrolled_user
    
    print_header("Speaker Enrollment Test")
    
    if not server_connected:
        print_error("Server not connected. Run option 1 first.")
        return
    
    user_id = input("Enter user ID to enroll: ").strip()
    if not user_id:
        print_error("User ID cannot be empty")
        return
    
    print_info("You will record 3 audio samples for enrollment")
    
    samples = []
    for i in range(3):
        print(f"\n--- Sample {i+1}/3 ---")
        filename = record_audio(duration=3, filename=f"enrollment_{i+1}.wav")
        samples.append(filename)
        time.sleep(0.5)
    
    try:
        print_info("Enrolling speaker...")
        response = requests.post(
            f"{API_V1}/enroll-speaker-files",
            json={"user_id": user_id, "audio_files": samples},
            timeout=30
        )
        
        if response.status_code == 201 or response.status_code == 200:
            data = response.json()
            print_success(f"[OK] Speaker enrolled successfully!")
            print_stats("User ID", data.get("user_id"))
            print_stats("Embedding Size", data.get("embedding_size"))
            last_enrolled_user = user_id
        else:
            print_error(f"Enrollment failed: {response.text}")
        
        # Cleanup
        for sample in samples:
            try:
                os.remove(sample)
            except FileNotFoundError:
                pass  # File already deleted, ignore
            except OSError as e:
                print(f"Warning: Could not delete {sample}: {e}")
                
    except Exception as e:
        print_error(f"Error: {str(e)}")

def test_speaker_verification():
    """Test speaker verification"""
    print_header("Speaker Verification Test")
    
    if not server_connected:
        print_error("Server not connected. Run option 1 first.")
        return
    
    user_id = input(f"Enter user ID to verify [{last_enrolled_user or 'none'}]: ").strip()
    if not user_id and last_enrolled_user:
        user_id = last_enrolled_user
    elif not user_id:
        print_error("User ID cannot be empty")
        return
    
    filename = record_audio(duration=3, filename="verification.wav")
    
    try:
        print_info("Verifying speaker...")
        response = requests.post(
            f"{API_V1}/verify-speaker",
            json={"audio_file": filename},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            identified_user = data.get("user_id", "unknown")
            is_verified = data.get("is_verified", False)
            confidence = data.get("confidence", 0)
            
            if is_verified and identified_user == user_id:
                print_success(f"[OK] Speaker verified as {identified_user}!")
                print_stats("Confidence", f"{confidence:.2%}")
            elif is_verified:
                print_warning(f"Speaker identified as {identified_user} (not {user_id})")
                print_stats("Confidence", f"{confidence:.2%}")
            else:
                print_error("Speaker not verified - unknown or low confidence")
                print_stats("Identified as", identified_user)
                print_stats("Confidence", f"{confidence:.2%}")
        else:
            print_error(f"Verification failed: {response.text}")
        
        # Cleanup
        try:
            os.remove(filename)
        except:
            pass
            
    except Exception as e:
        print_error(f"Error: {str(e)}")

def test_speech_to_text():
    """Test speech-to-text with circuit breaker monitoring"""
    print_header("Speech-to-Text Test")
    
    if not server_connected:
        print_error("Server not connected. Run option 1 first.")
        return
    
    # Check circuit breaker first
    try:
        cb_response = requests.get(f"{API_V1}/stt/circuit-breaker-status", timeout=5)
        if cb_response.status_code == 200:
            cb_status = cb_response.json()
            if cb_status.get("state") == "OPEN":
                print_error("Circuit breaker is OPEN - STT service is recovering")
                print_info("Please wait for recovery or try again later")
                return
    except (requests.RequestException, ValueError) as e:
        print(f"Warning: Could not check circuit breaker status: {e}")
    
    # Language selection
    print("\n Language Options:")
    print("  1. Auto-detect (recommended)")
    print("  2. Force English")
    print("  3. Force Urdu")
    
    lang_choice = input("\nSelect language (1-3, default 1): ").strip() or "1"
    language_map = {
        "1": "auto",
        "2": "en",
        "3": "ur"
    }
    language = language_map.get(lang_choice, "auto")
    
    if language != "auto":
        print_info(f"Forcing language: {language}")
    
    duration = int(input("Recording duration (seconds, default 3): ") or "3")
    filename = record_audio(duration=duration, filename="stt_test.wav")
    
    try:
        print_info("[STT] Transcribing audio...")
        response = requests.post(
            f"{API_V1}/transcribe",
            json={"audio_file": filename, "language": language},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            print_success("Transcription completed!")
            print(f"\n Text: \"{data.get('text', '')}\"")
            
            if 'language' in data:
                print_stats("Language", data['language'])
            if 'processing_time' in data:
                print_stats("Processing Time", f"{data['processing_time']:.2f}s")
        else:
            print_error(f"Transcription failed: Status {response.status_code}")
            try:
                error_data = response.json()
                print_error(f"Error details: {error_data}")
            except ValueError as e:
                print_error(f"Could not parse error response (not JSON)")
                print_error(f"Response text: {response.text}")
        
        # Cleanup
        try:
            os.remove(filename)
        except FileNotFoundError:
            pass  # File not created, no cleanup needed
        except OSError as e:
            print(f"Warning: Could not cleanup {filename}: {e}")
            
    except Exception as e:
        print_error(f"Error: {str(e)}")
        import traceback
        print_error(f"Full traceback: {traceback.format_exc()}")

def test_manual_pipeline():
    """Test complete audio processing pipeline (manual step-by-step)"""
    print_header("Manual Pipeline Test (Step-by-Step)")
    
    if not server_connected:
        print_error("Server not connected. Run option 1 first.")
        return
    
    user_id = input(f"Enter user ID [{last_enrolled_user or 'none'}]: ").strip()
    if not user_id and last_enrolled_user:
        user_id = last_enrolled_user
    elif not user_id:
        print_error("User ID required for pipeline test")
        return
    
    try:
        # Step 1: Wake word detection
        print_info("\n[Step 1/3] Wake Word Detection")
        print_info("Say 'Hi Nexi' to continue...")
        
        response = requests.post(f"{API_V1}/wake-word/detect", timeout=30)
        if response.status_code != 200:
            print_error("Wake word detection failed")
            return
        
        print_success(" Wake word detected!")
        
        # Step 2: Speaker verification
        print_info("\n[Step 2/3] Speaker Verification")
        filename = record_audio(duration=3, filename="pipeline_verification.wav")
        
        response = requests.post(
            f"{API_V1}/verify-speaker",
            json={"audio_file": filename},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            identified_user = data.get("user_id", "unknown")
            is_verified = data.get("is_verified", False)
            
            if is_verified and identified_user == user_id:
                print_success(f"[OK] Speaker verified as {user_id}!")
            elif is_verified:
                print_warning(f"Speaker is {identified_user}, not {user_id}")
                print_info("Continuing with identified user...")
            else:
                print_error("Speaker verification failed - unknown speaker")
                os.remove(filename)
                return
        else:
            print_error("Speaker verification failed")
            os.remove(filename)
            return
        os.remove(filename)
        
        # Step 3: Command transcription
        print_info("\n[Step 3/3] Command Transcription")
        filename = record_audio(duration=5, filename="pipeline_command.wav")
        
        response = requests.post(
            f"{API_V1}/transcribe",
            json={"audio_file": filename},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            print_success("[OK] Command transcribed!")
            print(f"\n Command: \"{data.get('text', '')}\"")
            
            print_success("\n Complete pipeline executed successfully!")
        else:
            print_error("Command transcription failed")
        
        os.remove(filename)
        
    except KeyboardInterrupt:
        print_warning("\nPipeline cancelled by user")
    except Exception as e:
        print_error(f"Pipeline error: {str(e)}")

def test_automated_full_pipeline():
    """Automated pipeline test using pre-recorded audio"""
    print_header("Automated Full Pipeline Test")
    
    if not server_connected:
        print_error("Server not connected. Run option 1 first.")
        return
    
    print_info("This test uses pre-recorded audio files")
    print_warning("Make sure you have audio files or record new ones")
    
    # Check if we have recorded audio
    if not last_recorded_file or not os.path.exists(last_recorded_file):
        print_info("No audio file found. Recording new sample...")
        filename = record_audio(duration=3)
    else:
        filename = last_recorded_file
    
    user_id = input(f"Enter user ID [{last_enrolled_user or 'test_user'}]: ").strip() or "test_user"
    
    try:
        # Copy the recorded/test file into the server's data directory so the
        # server-side endpoints can access it by path. This keeps the test
        # deterministic when running client and server on the same machine.
        from pathlib import Path
        import shutil

        server_data_dir = Path("audio_service") / "data"
        server_data_dir.mkdir(parents=True, exist_ok=True)

        dest_name = f"automated_{int(time.time())}.wav"
        dest_path = server_data_dir / dest_name
        shutil.copyfile(filename, dest_path)
        filename_for_server = str(dest_path.resolve())

        # Test each component
        print_info("\n[Testing STT]")
        response = requests.post(
            f"{API_V1}/transcribe",
            json={"audio_file": filename_for_server},
            timeout=30
        )
        if response.status_code == 200:
            print_success(f"STT: \"{response.json().get('text', '')}\"")
        else:
            print_error("STT failed")
        
        print_success("\n[OK] Automated tests completed!")
        
    except Exception as e:
        print_error(f"Error: {str(e)}")

# NEW INTEGRATED FEATURES TESTS

def test_queue_service():
    """Test offline queue management"""
    print_header("Testing Offline Queue Service")
    
    if not server_connected:
        print_error("Server not connected. Run option 1 first.")
        return
    
    try:
        # Get queue status
        print_info("Fetching queue status...")
        response = requests.get(f"{BASE_URL}/queue/status", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print_success("Queue service is operational")
            print_stats("Queue Size", data.get("queue_size", 0))
            print_stats("Pending", data.get("pending", 0))
            print_stats("Processing", data.get("processing", 0))
            print_stats("Failed", data.get("failed", 0))
            print_stats("Completed", data.get("completed", 0))
            
            # Test manual queue processing
            if data.get("pending", 0) > 0:
                process = input("\nProcess pending items now? (y/n): ").strip().lower()
                if process == 'y':
                    response = requests.post(f"{BASE_URL}/queue/process-now", timeout=30)
                    if response.status_code == 200:
                        result = response.json()
                        print_success(f"Processed {result.get('processed', 0)} items")
                    else:
                        print_error("Failed to process queue")
        else:
            print_error(f"Failed to get queue status: {response.text}")
            
    except Exception as e:
        print_error(f"Queue service error: {str(e)}")

def test_backend_connectivity():
    """Test backend service connectivity"""
    print_header("Testing Backend Service Connectivity")
    
    if not server_connected:
        print_error("Server not connected. Run option 1 first.")
        return
    
    try:
        print_info("Testing backend communication...")
        
        # This endpoint should show circuit breaker status for backend service
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print_success("Service is healthy")
            
            # Check if backend circuit breaker info is included
            if 'backend_status' in data:
                print_stats("Backend State", data['backend_status'].get('state', 'unknown'))
                print_stats("Backend Available", data['backend_status'].get('available', False))
            else:
                print_info("Backend status not reported in health endpoint")
                print_info("Backend service is configured for: BACKEND_URL in .env")
        else:
            print_error(f"Health check failed: {response.text}")
            
    except Exception as e:
        print_error(f"Backend connectivity error: {str(e)}")

def test_local_whisper():
    """Test local Whisper transcription (offline mode)"""
    print_header("Testing Local Whisper (Offline STT)")
    
    if not server_connected:
        print_error("Server not connected. Run option 1 first.")
        return
    
    print_warning("This test requires the openai-whisper package installed")
    print_info("The service will use local Whisper model (no API calls)")
    
    try:
        # Record audio for transcription
        print_info("\nRecording audio for local transcription...")
        filename = record_audio(duration=5, filename="local_whisper_test.wav")
        
        print_info("Transcribing with local Whisper (this may take a moment)...")
        print_info("Note: First run will download the model")
        
        # Call transcribe endpoint with offline flag
        response = requests.post(
            f"{API_V1}/transcribe",
            json={
                "audio_file": filename,
                "use_local": True  # This triggers local Whisper
            },
            timeout=120  # Longer timeout for model loading
        )
        
        if response.status_code == 200:
            data = response.json()
            print_success("Local transcription completed!")
            print(f"\n Transcribed Text: \"{data.get('text', '')}\"")
            print_stats("Processing Time", f"{data.get('processing_time', 0):.2f}s")
            print_stats("Method", data.get("method", "unknown"))
        else:
            print_error(f"Local transcription failed: {response.text}")
            
        os.remove(filename)
        
    except Exception as e:
        print_error(f"Local Whisper error: {str(e)}")
        import traceback
        traceback.print_exc()

def test_silence_detection():
    """Test silence-based recording with auto-stop"""
    print_header("Testing Silence-Based Recording")
    
    if not server_connected:
        print_error("Server not connected. Run option 1 first.")
        return
    
    print_info("This test uses VAD-based silence detection")
    print_info("Recording will automatically stop after detecting silence")
    print_info("Speak naturally, then pause...")
    
    try:
        # Note: This requires a special endpoint or the wake word service method
        # For now, we'll demonstrate with a timed recording
        print_warning("Simulating with 10-second recording (speak then pause)")
        filename = record_audio(duration=10, filename="silence_detection_test.wav")
        
        print_success("Recording completed")
        print_info("In production, this would auto-stop after silence is detected")
        
        # Optionally transcribe
        transcribe = input("\nTranscribe this recording? (y/n): ").strip().lower()
        if transcribe == 'y':
            response = requests.post(
                f"{API_V1}/transcribe",
                json={"audio_file": filename},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"\n Transcription: \"{data.get('text', '')}\"")
                
        os.remove(filename)
        
    except Exception as e:
        print_error(f"Silence detection error: {str(e)}")

def test_complete_pipeline():
    """Test the complete integrated pipeline endpoint"""
    print_header("Testing Complete Integrated Pipeline")
    
    if not server_connected:
        print_error("Server not connected. Run option 1 first.")
        return
    
    print_info("This tests the NEW integrated pipeline endpoint:")
    print_info("  1. Wake word detection")
    print_info("  2. Audio recording with silence detection")
    print_info("  3. Transcription (with fallback to local)")
    print_info("  4. Backend submission (with queue fallback)")
    
    print_warning("\nThis will start listening for wake word...")
    confirm = input("Start pipeline test? (y/n): ").strip().lower()
    
    if confirm != 'y':
        print_info("Test cancelled")
        return
    
    try:
        print_info("\nStarting complete pipeline...")
        print_info("Say the wake word 'Hey Nexi' to trigger recording")
        
        # Call the integrated pipeline endpoint
        response = requests.post(
            f"{API_V1}/process-pipeline",
            json={
                "timeout": 30,
                "offline_mode": False
            },
            timeout=60
        )
        
        if response.status_code == 200:
            data = response.json()
            status_val = data.get("status", "unknown")
            
            if status_val == "completed":
                print_success("Pipeline completed successfully!")
            elif status_val == "failed":
                print_error("Pipeline failed at one or more steps")
            else:
                print_warning(f"Pipeline status: {status_val}")
            
            # Show results from each step
            steps = data.get("steps", {})
            
            # Wake word
            if "wake_word" in steps:
                ww = steps["wake_word"]
                if ww.get("status") == "success":
                    print_stats("Wake Word", f"{ww.get('keyword', 'Unknown')}")
                else:
                    print_error(f"Wake word failed: {ww.get('error', 'Unknown')}")
            
            # Transcription
            if "transcription" in steps:
                trans = steps["transcription"]
                if trans.get("status") == "success":
                    print_stats("Transcription", f"\"{trans.get('text', 'N/A')}\"")
                    print_stats("Language", trans.get("language", "unknown"))
                else:
                    print_error(f"Transcription failed: {trans.get('error', 'Unknown')}")
            
            # Backend
            if "backend" in steps:
                backend = steps["backend"]
                backend_status = backend.get("status", "unknown")
                if backend_status == "success":
                    print_stats("Backend", " Sent successfully")
                elif backend_status == "queued":
                    print_warning(f"Queued (backend offline) - Queue ID: {backend.get('queue_id')}")
                elif backend_status == "skipped":
                    print_info(f"Backend skipped: {backend.get('reason')}")
                else:
                    print_error(f"Backend failed: {backend.get('error', 'Unknown')}")
            
            print_stats("Total Duration", f"{data.get('pipeline_duration', 0):.2f}s")
            
        else:
            print_error(f"Pipeline failed: {response.text}")
            
    except KeyboardInterrupt:
        print_warning("\nPipeline cancelled by user")
    except Exception as e:
        print_error(f"Pipeline error: {str(e)}")
        import traceback
        traceback.print_exc()

def test_integration_health():
    """Comprehensive health check of all integrated components"""
    print_header("Integration Health Check")
    
    if not server_connected:
        print_error("Server not connected. Run option 1 first.")
        return
    
    print_info("Checking all integrated components...\n")
    
    checks = {
        "Server Health": (f"{BASE_URL}/health", "GET"),
        "Queue Status": (f"{BASE_URL}/queue/status", "GET"),
        "Wake Word Stats": (f"{API_V1}/wake-word/stats", "GET"),
        "Circuit Breaker": (f"{API_V1}/stt/circuit-breaker-status", "GET")
    }
    
    results = []
    
    for check_name, (url, method) in checks.items():
        try:
            if method == "GET":
                response = requests.get(url, timeout=5)
            else:
                response = requests.post(url, timeout=5)
                
            if response.status_code == 200:
                print_success(f"{check_name}: Operational")
                results.append(True)
            else:
                print_error(f"{check_name}: Failed ({response.status_code})")
                results.append(False)
                
        except Exception as e:
            print_error(f"{check_name}: Error - {str(e)}")
            results.append(False)
    
    # Summary
    passed = sum(results)
    total = len(results)
    success_rate = (passed / total) * 100
    
    print(f"\n Results: {passed}/{total} checks passed ({success_rate:.0f}%)")
    
    if success_rate == 100:
        print_success("All systems operational!")
    elif success_rate >= 75:
        print_warning("Most systems operational, some issues detected")
    else:
        print_error("Multiple systems have issues, review configuration")

def display_main_menu():
    """Display the main menu"""
    print("\n" + "=" * 60)
    print("    AUDIO SERVICE TEST SUITE - INTEGRATED VERSION")
    print("=" * 60)
    
    print("\n Connection & Setup:")
    print("  1. Test Server Connection")
    
    print("\n Core Features (Week 1-2):")
    print("  2. Test Wake Word Detection")
    print("  3. Test Speaker Enrollment")
    print("  4. Test Speaker Verification")
    print("  5. Test Speech-to-Text")
    
    print("\n Week 3 Features:")
    print("  6. Test Power Modes")
    print("  7. View Wake Word Statistics")
    print("  8. Check Circuit Breaker Status")
    print("  9. Error Handling Demo")
    print("  10. Test Quality Validation")
    
    print("\n NEW INTEGRATED FEATURES:")
    print("  11. Test Offline Queue Service")
    print("  12. Test Backend Connectivity")
    print("  13. Test Local Whisper (Offline STT)")
    print("  14. Test Silence-Based Recording")
    print("  15. Test Complete Integrated Pipeline")
    print("  16. Integration Health Check")
    
    print("\n Exit:")
    print("  0. Exit")
    
    print("\n" + "=" * 60)
    
    # Show connection status
    if server_connected:
        print_success("Server: Connected ")
    else:
        print_warning("Server: Not Connected (Run option 1)")
    
    if last_enrolled_user:
        print_info(f"Last Enrolled User: {last_enrolled_user}")
    
    print("=" * 60)

def main():
    """Main test loop"""
    print_header("  Audio Service Interactive Test Suite")
    print_info("Welcome! This suite tests all audio service features.")
    print_info("Week 3 Enhanced: Power modes, statistics, error handling, quality validation")
    print_info("NEW: Offline queue, backend service, local Whisper, complete pipeline")
    
    # Auto-connect to server on startup
    print_info("Connecting to server...")
    test_server_connection()
    
    while True:
        display_main_menu()

        choice = input("\nEnter your choice (0-16): ").strip()

        if choice == "0":
            print_header("Goodbye!")
            break
        elif choice == "1":
            test_server_connection()
        elif choice == "2":
            test_wake_word_detection()
        elif choice == "3":
            test_speaker_enrollment()
        elif choice == "4":
            test_speaker_verification()
        elif choice == "5":
            test_speech_to_text()
        elif choice == "6":
            test_power_modes()
        elif choice == "7":
            test_wake_word_statistics()
        elif choice == "8":
            test_circuit_breaker_status()
        elif choice == "9":
            test_error_handling_demo()
        elif choice == "10":
            test_quality_validation()
        elif choice == "11":
            test_queue_service()
        elif choice == "12":
            test_backend_connectivity()
        elif choice == "13":
            test_local_whisper()
        elif choice == "14":
            test_silence_detection()
        elif choice == "15":
            test_complete_pipeline()
        elif choice == "16":
            test_integration_health()
        else:
            print_error("Invalid choice. Please select 0-16.")

        input("\nPress Enter to continue...")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n")
        print_header("Interrupted by user - Goodbye!")
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
