#!/usr/bin/env python3
"""
NEXI Vision Service - Fixed Integration Tests
- Shows all 7 emotions
- Prevents camera conflicts
- Proper resource cleanup
- ASCII-safe output for Windows compatibility
"""

import requests
import time
import sys
import os

BASE_URL = "http://localhost:8001"
TIMEOUT = 30

def print_result(name, status=""):
    """Print test result with ASCII-safe characters"""
    symbol = "[PASS]" if status == "PASS" else "[FAIL]" if status == "FAIL" else "[....]"
    print(f"{symbol} {name}")

def test_health():
    """Test /health endpoint"""
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        assert response.status_code == 200, response.text
        if response.status_code == 200:
            data = response.json()
            assert data['camera'] in ('available', 'unavailable'), data
            assert data['face_model'] in ('loaded', 'unavailable'), data
            expected = 'healthy' if data['camera'] == 'available' and data['face_model'] == 'loaded' else 'degraded'
            assert data['status'] == expected, data
            print_result(f"Health Check: {data['status']}", "PASS")
            print(f"  - Camera: {data.get('camera', 'unknown')}")
            print(f"  - Emotions: {data.get('emotion_detection', 'unknown')}")
            return True
    except Exception as e:
        print_result(f"Health Check Failed: {str(e)[:50]}", "FAIL")
        raise
    return False

def test_face_detection():
    """Test /detect/faces endpoint"""
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/detect/faces",
            params={"detector_backend": "opencv", "model_name": "Facenet"},
            timeout=TIMEOUT
        )
        assert response.status_code == 200, response.text
        if response.status_code == 200:
            data = response.json()
            assert data['status'] == 'success', data
            assert data['faces_detected'] == len(data['faces']), data
            faces = data.get('faces_detected', 0)
            print_result(f"Face Detection: {faces} face(s) detected", "PASS")
            return True
    except Exception as e:
        print_result(f"Face Detection Failed: {str(e)[:50]}", "FAIL")
        raise
    return False

def test_emotions_all_7():
    """Test /analyze/complete endpoint - shows ALL 7 emotions"""
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/analyze/complete",
            params={"detector_backend": "opencv", "analyze_emotions": True},
            timeout=TIMEOUT
        )
        assert response.status_code == 200, response.text
        if response.status_code == 200:
            data = response.json()
            assert data['status'] == 'success', data
            assert data['faces_detected'] > 0, 'Emotion test requires a detected face'
            assert all(face.get('emotion_scores') for face in data['faces']), data
            faces = data.get('faces_detected', 0)
            print_result(f"Emotion Detection: {faces} face(s) detected", "PASS")
            
            if faces > 0:
                face = data['faces'][0]
                emotion = face.get('dominant_emotion', 'unknown')
                print(f"  - Primary emotion: {emotion}")
                
                scores = face.get('emotion_scores', {})
                if scores:
                    print(f"  - All 7 Emotion Scores (sorted by confidence):")
                    for emo, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
                        bar_length = int(score * 30)
                        bar = "[" + "#" * bar_length + "-" * (30 - bar_length) + "]"
                        percentage = f"{score*100:6.2f}%"
                        print(f"      {emo.capitalize():12s} {bar} {percentage}")
            
            return True
    except Exception as e:
        print_result(f"Emotion Detection Failed: {str(e)[:50]}", "FAIL")
        raise
    return False

def test_camera_controls():
    """Test /camera/pause and /camera/resume endpoints"""
    try:
        # Test pause
        response = requests.post(f"{BASE_URL}/camera/pause", timeout=5)
        assert response.status_code == 200, response.text
        data = response.json()
        status = data.get('status', '')
        
        if status != 'paused':
            print_result(f"Camera Controls: Pause Failed (got {status})", "FAIL")
            raise AssertionError(f"Expected paused, got {status!r}")
        
        time.sleep(0.5)
        
        # Test resume
        response = requests.post(f"{BASE_URL}/camera/resume", timeout=5)
        assert response.status_code == 200, response.text
        data = response.json()
        status = data.get('status', '')
        
        # Accept both 'resumed' and 'active' as valid states
        if status not in ['resumed', 'active']:
            print_result(f"Camera Controls: Resume Failed (got {status})", "FAIL")
            raise AssertionError(f"Expected resumed or active, got {status!r}")
        
        print_result(f"Camera Controls: Pause/Resume Working", "PASS")
        return True
        
    except Exception as e:
        print_result(f"Camera Controls Failed: {str(e)[:50]}", "FAIL")
        raise

def test_live_ui():
    """Test /live endpoint"""
    try:
        response = requests.get(f"{BASE_URL}/live", timeout=5)
        assert response.status_code == 200, response.text
        assert "html" in response.text.lower(), 'Expected HTML live UI'
        if response.status_code == 200 and "html" in response.text.lower():
            print_result(f"Live UI Endpoint: Available", "PASS")
            return True
    except Exception as e:
        print_result(f"Live UI Failed: {str(e)[:50]}", "FAIL")
        raise
    return False

def run_all_tests():
    """Run all tests and show summary"""
    print("\n" + "="*70)
    print("  NEXI VISION SERVICE - COMPREHENSIVE TEST SUITE")
    print("="*70)
    print(f"\nTarget: {BASE_URL}")
    print(f"Timeout: {TIMEOUT}s\n")
    
    print("Running Tests...")
    print("-"*70)
    
    results = []
    results.append(("Health Check", test_health()))
    results.append(("Face Detection", test_face_detection()))
    results.append(("Emotion Detection (All 7)", test_emotions_all_7()))
    results.append(("Camera Controls", test_camera_controls()))
    results.append(("Live UI", test_live_ui()))
    
    # Summary
    passed = sum(1 for _, r in results if r)
    failed = sum(1 for _, r in results if not r)
    total = len(results)
    
    print("-"*70)
    print(f"\nSummary: {passed}/{total} tests passed")
    if failed > 0:
        print(f"[FAIL] {failed} test(s) failed")
        for name, result in results:
            if not result:
                print(f"  - {name}")
        return 1
    else:
        print("[PASS] All tests completed successfully!")
        return 0

def main():
    try:
        exit_code = run_all_tests()
        print("="*70 + "\n")
        return exit_code
    except KeyboardInterrupt:
        print("\n[FAIL] Test interrupted by user")
        return 1
    except Exception as e:
        print(f"\n[FAIL] Unexpected error: {str(e)[:100]}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
