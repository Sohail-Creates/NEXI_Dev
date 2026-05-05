"""
Vision Service Video Streaming Routes
MJPEG streaming with real-time face detection overlays
Simplified production implementation from Vision-Nexus
"""

import cv2
import logging
from datetime import datetime
from typing import List, Tuple
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse

from ..config import Config
from ..services.resource_pool import ResourcePool
from .camera import is_camera_paused

logger = logging.getLogger(__name__)
router = APIRouter()

# Global resource pool reference
_resource_pool: ResourcePool = None

# Global state for real-time data
latest_face_data = {
    'face_count': 0,
    'emotions': [],
    'confidences': [],
    'last_update': datetime.now().isoformat()
}


def set_resource_pool(pool: ResourcePool):
    """Set the global resource pool reference"""
    global _resource_pool
    _resource_pool = pool


def generate_frames():
    """
    Generator function that yields MJPEG frames
    Includes real-time face detection overlays
    From Vision-Nexus streaming logic
    """
    global latest_face_data
    
    if _resource_pool is None:
        logger.error("Resource pool not initialized")
        return
    
    frame_count = 0
    error_count = 0
    max_consecutive_errors = 5
    
    try:
        with _resource_pool.get_camera(timeout=Config.CAMERA_TIMEOUT) as camera:
            while not _resource_pool._is_shutting_down:
                # Check if camera is paused
                if is_camera_paused():
                    logger.debug("Camera paused, skipping stream")
                    continue
                
                # Read frame from camera
                ret, frame = camera.read()
                if not ret:
                    error_count += 1
                    if error_count >= max_consecutive_errors:
                        logger.error("Too many consecutive frame read errors, stopping stream")
                        break
                    continue
                
                error_count = 0  # Reset error count on successful read
                frame_count += 1
                
                # Resize for performance
                frame = cv2.resize(frame, (640, 480))
                
                # Detect faces every 5 frames for performance
                if frame_count % 5 == 0:
                    try:
                        from deepface import DeepFace
                        
                        face_objs = DeepFace.extract_faces(
                            img_path=frame,
                            detector_backend=Config.DETECTOR_BACKEND,
                            enforce_detection=False,
                            align=True
                        )
                        
                        emotions_detected: List[Tuple[str, float]] = []
                        
                        # Try emotion detection
                        try:
                            fer = _resource_pool.get_fer_detector()
                            
                            if fer is not None:
                                for face_obj in face_objs:
                                    facial_area = face_obj.get('facial_area', {})
                                    x = facial_area.get('x', 0)
                                    y = facial_area.get('y', 0)
                                    w = facial_area.get('w', 0)
                                    h = facial_area.get('h', 0)
                                    
                                    # Extract face region with padding
                                    padding = 20
                                    y1 = max(0, y - padding)
                                    y2 = min(frame.shape[0], y + h + padding)
                                    x1 = max(0, x - padding)
                                    x2 = min(frame.shape[1], x + w + padding)
                                    
                                    face_region = frame[y1:y2, x1:x2]
                                    
                                    # Detect emotion
                                    try:
                                        emotion_result = fer.top_emotion(face_region)
                                        emotion = "Unknown"
                                        confidence_pct = 0.0
                                        
                                        if emotion_result and isinstance(emotion_result, tuple) and len(emotion_result) == 2:
                                            emotion_name, confidence_val = emotion_result
                                            if isinstance(emotion_name, str):
                                                emotion = emotion_name
                                            if isinstance(confidence_val, (int, float)):
                                                confidence_pct = float(confidence_val * 100)
                                        
                                        emotions_detected.append((emotion, confidence_pct))
                                    except:
                                        emotions_detected.append(("Unknown", 0.0))
                            else:
                                emotions_detected = [("Unknown", 0.0)] * len(face_objs)
                        
                        except Exception as e:
                            logger.debug(f"Emotion detection error: {e}")
                            emotions_detected = [("Unknown", 0)] * len(face_objs)
                        
                        # Draw boxes and emotions on frame
                        for idx, face_obj in enumerate(face_objs):
                            facial_area = face_obj.get('facial_area', {})
                            x = facial_area.get('x', 0)
                            y = facial_area.get('y', 0)
                            w = facial_area.get('w', 0)
                            h = facial_area.get('h', 0)
                            
                            emotion, confidence_pct = emotions_detected[idx] if idx < len(emotions_detected) else ("Unknown", 0)
                            color = (0, 255, 0) if emotion != "Unknown" else (0, 165, 255)  # Green or Orange
                            
                            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
                            
                            if emotion != "Unknown":
                                label = f"{emotion} ({confidence_pct:.0f}%)"
                                cv2.putText(frame, label, (x, y - 15), 
                                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                            else:
                                cv2.putText(frame, "Analyzing...", (x, y - 15),
                                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                        
                        # Update global data for real-time UI
                        latest_face_data['face_count'] = len(face_objs)
                        latest_face_data['emotions'] = [e[0] for e in emotions_detected]
                        latest_face_data['confidences'] = [e[1] for e in emotions_detected]
                        latest_face_data['last_update'] = datetime.now().isoformat()
                        
                    except Exception as e:
                        logger.debug(f"Stream detection error: {e}")
                        cv2.putText(frame, "Detection Error", (10, 30),
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                
                # Draw frame info
                face_count = latest_face_data.get('face_count', 0)
                cv2.putText(frame, f"Faces: {face_count} | Frame: {frame_count}", (10, 30),
                          cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                # Encode and yield
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if not ret:
                    continue
                
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Content-Length: ' + f"{len(frame_bytes)}".encode() + b'\r\n\r\n' +
                       frame_bytes + b'\r\n')
        
    except Exception as e:
        logger.error(f"Stream error: {e}")


@router.get("/stream")
async def stream_video():
    """
    MJPEG stream with face detection and emotion overlays
    From Vision-Nexus streaming endpoint
    """
    if _resource_pool is None:
        raise HTTPException(status_code=500, detail="Resource pool not initialized")
    
    try:
        return StreamingResponse(
            generate_frames(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    except Exception as e:
        logger.error(f"Stream endpoint error: {e}")
        raise HTTPException(status_code=500, detail=f"Streaming failed: {str(e)}")


@router.get("/live")
async def live_view():
    """
    HTML page for live video streaming
    From Vision-Nexus /live endpoint
    """
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title> NEXI Vision - Live Stream</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #1e1e1e 0%, #2d2d2d 100%);
                color: #fff;
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 900px;
                margin: 0 auto;
            }
            header {
                text-align: center;
                margin-bottom: 30px;
            }
            h1 {
                font-size: 32px;
                margin-bottom: 10px;
                color: #4CAF50;
            }
            .main-grid {
                display: grid;
                grid-template-columns: 1fr 300px;
                gap: 20px;
                margin-bottom: 20px;
            }
            .video-container {
                background: #000;
                border-radius: 10px;
                overflow: hidden;
                box-shadow: 0 8px 16px rgba(0,0,0,0.3);
                aspect-ratio: 16/9;
            }
            img {
                width: 100%;
                height: 100%;
                object-fit: cover;
                display: block;
            }
            .info-panel {
                display: flex;
                flex-direction: column;
                gap: 15px;
            }
            .info-card {
                background: #2d2d2d;
                padding: 15px;
                border-radius: 8px;
                border-left: 4px solid #4CAF50;
            }
            .label {
                font-size: 11px;
                color: #999;
                text-transform: uppercase;
                letter-spacing: 1px;
                margin-bottom: 5px;
            }
            .value {
                font-size: 24px;
                font-weight: bold;
                color: #4CAF50;
            }
            .controls {
                display: flex;
                gap: 10px;
                margin-bottom: 20px;
                flex-wrap: wrap;
            }
            button {
                flex: 1;
                padding: 14px;
                background: #4CAF50;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s;
            }
            button:hover {
                background: #45a049;
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(76, 175, 80, 0.3);
            }
            button:active {
                transform: translateY(0);
            }
            @media (max-width: 768px) {
                .main-grid {
                    grid-template-columns: 1fr;
                }
                h1 { font-size: 24px; }
                .value { font-size: 20px; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1> NEXI Vision Service - Live Stream</h1>
                <p>Real-time face detection and emotion analysis</p>
            </header>
            
            <div class="main-grid">
                <div class="video-container">
                    <img src="/stream" alt="Live Stream" />
                </div>
                
                <div class="info-panel">
                    <div class="info-card">
                        <div class="label">Service Status</div>
                        <div class="value" style="color: #4CAF50;"> Online</div>
                    </div>
                    <div class="info-card">
                        <div class="label">Stream</div>
                        <div class="value">Streaming</div>
                    </div>
                    <div class="info-card">
                        <div class="label">Detection</div>
                        <div class="value">Active</div>
                    </div>
                </div>
            </div>
            
            <div class="controls">
                <button onclick="pauseCamera()"> Pause</button>
                <button onclick="resumeCamera()"> Resume</button>
                <button onclick="location.reload()"> Refresh</button>
            </div>
        </div>
        
        <script>
            async function pauseCamera() {
                try {
                    await fetch('/camera/pause', { method: 'POST' });
                    alert('Camera paused');
                } catch (error) {
                    console.error('Error:', error);
                }
            }
            
            async function resumeCamera() {
                try {
                    await fetch('/camera/resume', { method: 'POST' });
                    alert('Camera resumed');
                } catch (error) {
                    console.error('Error:', error);
                }
            }
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html)

