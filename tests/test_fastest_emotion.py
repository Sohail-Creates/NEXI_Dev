"""
FASTEST Emotion Detection Test
===============================
- Face detection: LOCAL (OpenCV Cascade) - INSTANT
- Emotion detection: API (only face region) - FAST
- Result: 25+ FPS smooth real-time display
"""

import cv2
import requests
import numpy as np
import time
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# CONFIG
API_URL = "http://localhost:8001/api/v1/detect/faces/upload"
DISPLAY_SIZE = (800, 600)

# Load OpenCV cascade for LOCAL face detection (INSTANT!)
cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
face_cascade = cv2.CascadeClassifier(cascade_path)

if face_cascade.empty():
    logger.error("Cascade classifier not loaded!")
    exit(1)

logger.info(f"✓ OpenCV Cascade loaded from {cascade_path}")

class FastEmotionTest:
    def __init__(self):
        logger.info("Initializing Fast Emotion Test...")
        
        # Initialize camera
        self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        self.frame_count = 0
        self.last_emotion_api_call = 0
        self.running = True
        self.current_fps = 0
        
        # Cached emotion data
        self.cached_emotions = {}
        
        # Check Vision Service
        try:
            r = requests.get("http://localhost:8001/health", timeout=2)
            if r.status_code == 200:
                logger.info("✓ Vision Service is READY")
        except:
            logger.error("✗ Vision Service not running!")
            raise
    
    def run(self):
        """Main loop - LOCAL face detection + emotion API"""
        logger.info("Starting FAST emotion detection...")
        logger.info("Face detection: LOCAL (instant)")
        logger.info("Emotion detection: API (face region only)")
        logger.info("Press 'Q' to quit")
        logger.info("")
        
        cv2.namedWindow("Emotion Detection", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Emotion Detection", DISPLAY_SIZE[0], DISPLAY_SIZE[1])
        
        fps_time = time.time()
        fps_count = 0
        frame_stats_time = time.time()
        
        try:
            while self.running:
                ret, frame = self.cap.read()
                if not ret:
                    continue
                
                self.frame_count += 1
                frame_start = time.time()
                
                # ==== STEP 1: LOCAL FACE DETECTION (INSTANT!) ====
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray, 1.3, 5)
                
                faces_detected = len(faces)
                dominant_emotion = "unknown"
                
                # ==== STEP 2: EMOTION DETECTION (API - only if face found) ====
                time_since_emotion_api = time.time() - self.last_emotion_api_call
                
                if faces_detected > 0 and time_since_emotion_api > 1.0:
                    # Get largest face
                    largest_face = max(faces, key=lambda f: f[2] * f[3])
                    x, y, w, h = largest_face
                    
                    # Extract and send only face region
                    face_roi = frame[max(0, y-10):min(frame.shape[0], y+h+10),
                                     max(0, x-10):min(frame.shape[1], x+w+10)]
                    
                    if face_roi.size > 0:
                        self.last_emotion_api_call = time.time()
                        
                        # Send face region to API
                        _, buffer = cv2.imencode('.jpg', face_roi, [cv2.IMWRITE_JPEG_QUALITY, 80])
                        
                        try:
                            files = {'file': ('face.jpg', buffer.tobytes(), 'image/jpeg')}
                            params = {
                                'detector_backend': 'opencv',
                                'model_name': 'Facenet',
                                'analyze_emotions': True
                            }
                            
                            r = requests.post(API_URL, files=files, params=params, timeout=10)
                            
                            if r.status_code == 200:
                                data = r.json()
                                faces_list = data.get('faces', [])
                                
                                if faces_list:
                                    emotion = faces_list[0].get('dominant_emotion', 'unknown')
                                    conf = faces_list[0].get('confidence', 0)
                                    self.cached_emotions = {
                                        'emotion': emotion,
                                        'confidence': conf
                                    }
                                    dominant_emotion = emotion
                            else:
                                logger.debug(f"API error: {r.status_code}")
                        except Exception as e:
                            logger.debug(f"API error: {e}")
                
                # Use cached emotion if available
                if not dominant_emotion or dominant_emotion == "unknown":
                    if self.cached_emotions:
                        dominant_emotion = self.cached_emotions.get('emotion', 'unknown')
                
                # ==== STEP 3: DRAW DETECTIONS ====
                display_frame = cv2.resize(frame, DISPLAY_SIZE)
                
                # Draw bounding boxes
                for (x, y, w, h) in faces:
                    # Scale coordinates to display size
                    scale_x = DISPLAY_SIZE[0] / frame.shape[1]
                    scale_y = DISPLAY_SIZE[1] / frame.shape[0]
                    
                    x_disp = int(x * scale_x)
                    y_disp = int(y * scale_y)
                    w_disp = int(w * scale_x)
                    h_disp = int(h * scale_y)
                    
                    # Get emotion color
                    colors = {
                        'happy': (0, 255, 0),      # Green
                        'sad': (255, 0, 0),        # Blue
                        'angry': (0, 0, 255),      # Red
                        'fear': (0, 165, 255),     # Orange
                        'surprise': (0, 255, 255),# Yellow
                        'disgust': (128, 0, 128),  # Purple
                        'neutral': (200, 200, 200) # Gray
                    }
                    color = colors.get(dominant_emotion.lower() if dominant_emotion else 'neutral', (200, 200, 200))
                    
                    # Draw box
                    cv2.rectangle(display_frame, (x_disp, y_disp), 
                                 (x_disp + w_disp, y_disp + h_disp), color, 3)
                    
                    # Draw emotion label
                    if dominant_emotion and dominant_emotion != "unknown":
                        label = f"{dominant_emotion.upper()}"
                        if self.cached_emotions and 'confidence' in self.cached_emotions:
                            label += f" ({self.cached_emotions['confidence']:.2f})"
                        
                        cv2.rectangle(display_frame, 
                                     (x_disp, max(0, y_disp - 30)), 
                                     (x_disp + len(label) * 10, y_disp), 
                                     color, -1)
                        cv2.putText(display_frame, label, 
                                   (x_disp + 5, y_disp - 8), 
                                   0, 0.7, (255, 255, 255), 2)
                
                # Draw stats
                h_disp, w_disp = display_frame.shape[:2]
                cv2.rectangle(display_frame, (0, 0), (w_disp, 80), (0, 0, 0), -1)
                cv2.rectangle(display_frame, (0, 0), (w_disp, 80), (0, 255, 0), 2)
                
                fps_count += 1
                elapsed = time.time() - fps_time
                if elapsed >= 1:
                    self.current_fps = fps_count / elapsed
                    fps_time = time.time()
                    fps_count = 0
                
                info1 = f"FPS: {self.current_fps:.1f} | Faces: {faces_detected} | Mood: {dominant_emotion.upper()}"
                info2 = "METHOD: Local face detection + API emotion | Q=Quit | S=Save"
                cv2.putText(display_frame, info1, (10, 25), 0, 0.7, (0, 255, 0), 2)
                cv2.putText(display_frame, info2, (10, 60), 0, 0.5, (0, 165, 255), 1)
                
                # Show frame
                cv2.imshow("Emotion Detection", display_frame)
                
                # Log stats every 5 seconds
                if time.time() - frame_stats_time > 5:
                    logger.info(f"Status: FPS={self.current_fps:.1f} | Face Count={faces_detected} | Emotion={dominant_emotion}")
                    frame_stats_time = time.time()
                
                # Handle keyboard
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == 27:
                    self.running = False
                elif key == ord('s'):
                    filename = f"emotion_frame_{int(time.time())}.jpg"
                    cv2.imwrite(filename, display_frame)
                    logger.info(f"Saved: {filename}")
        
        except KeyboardInterrupt:
            logger.info("Test stopped by user")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Cleanup resources"""
        logger.info("Cleaning up...")
        self.cap.release()
        cv2.destroyAllWindows()
        logger.info("Done!")

if __name__ == "__main__":
    test = FastEmotionTest()
    test.run()
