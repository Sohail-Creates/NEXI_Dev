"""
Object Detection Test - YOLOv8 Real-Time Visualization
=======================================================
Real-time object detection with bounding boxes on cv2 window
Same pattern as emotion detection test but for YOLO objects
"""

import cv2
import requests
import numpy as np
import time
import logging
from ultralytics import YOLO

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# CONFIG
API_URL = "http://localhost:8001/api/v1/detect/objects/upload"
DISPLAY_SIZE = (800, 600)
CONFIDENCE_THRESHOLD = 0.45
USE_LOCAL_INFERENCE = True  # Use local YOLO for speed, or API for server integration

# YOLO Model Selection
# Options: 'yolov8n' (15-25 FPS, 37% accurate), 
#          'yolov8s' (8-12 FPS, 46% accurate) ⭐ RECOMMENDED,
#          'yolov8m' (3-5 FPS, 50% accurate)
YOLO_MODEL = 'yolov8s'  # CHANGE THIS TO SWITCH MODELS

# YOLO Class colors (BGR format) - ALL 80 COCO classes
# Generate visually distinct colors using HSV color space
def generate_coco_colors():
    """Generate 80 distinct colors for all COCO classes using HSV color space"""
    colors = {}
    
    # All 80 COCO class names (YOLOv8 standard order)
    coco_classes = [
        'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck',
        'boat', 'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench',
        'cat', 'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe',
        'backpack', 'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee', 'skis',
        'snowboard', 'sports ball', 'kite', 'baseball bat', 'baseball glove', 'skateboard',
        'surfboard', 'tennis racket', 'bottle', 'wine glass', 'cup', 'fork', 'knife',
        'spoon', 'bowl', 'banana', 'apple', 'sandwich', 'orange', 'broccoli', 'carrot',
        'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch', 'potted plant', 'bed',
        'dining table', 'toilet', 'tv', 'laptop', 'mouse', 'remote', 'keyboard', 'microwave',
        'oven', 'toaster', 'sink', 'refrigerator', 'book', 'clock', 'vase', 'scissors',
        'teddy bear', 'hair drier', 'toothbrush'
    ]
    
    # Generate colors with good visual distinction (HSV → BGR)
    for idx, class_name in enumerate(coco_classes):
        # Use HSV color space for better visual distinction
        hue = int((idx / len(coco_classes)) * 180)  # OpenCV HSV: hue 0-180
        saturation = 200 + (idx % 2) * 55  # Vary between 200-255
        value = 200 + ((idx // 2) % 2) * 55  # Vary between 200-255
        
        # Convert HSV to BGR
        hsv = np.uint8([[[hue, saturation, value]]])
        bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0][0]
        colors[class_name] = tuple(int(x) for x in bgr)
    
    # Override with manually tuned nice colors for important classes
    nice_colors = {
        'person': (0, 255, 0),        # Green
        'car': (0, 0, 255),           # Red
        'dog': (0, 255, 255),         # Yellow
        'cat': (255, 0, 255),         # Magenta
        'bicycle': (255, 0, 0),       # Blue
        'phone': (128, 128, 0),       # Dark cyan
        'laptop': (0, 128, 128),      # Cyan
        'cup': (255, 165, 0),         # Orange
        'bottle': (100, 200, 200),    # Light cyan
        'chair': (128, 0, 128),       # Purple
        'backpack': (200, 100, 50),   # Brown
        'handbag': (150, 100, 255),   # Light purple
        'book': (100, 150, 200),      # Light blue
        'knife': (255, 200, 0),       # Sky blue
        'fork': (0, 200, 200),        # Cyan-green
        'spoon': (200, 100, 150),     # Pink
        'bowl': (100, 200, 100),      # Light green
        'food': (180, 150, 255),      # Light magenta
        'TV': (0, 100, 200),          # Dark red-orange
        'remote': (150, 150, 255),    # Light pink
        'keyboard': (200, 200, 0),    # Cyan
        'mouse': (100, 100, 255),     # Red-ish
        'umbrella': (0, 150, 150),    # Teal
        'tie': (255, 100, 100),       # Light red
        'suitcase': (150, 200, 100),  # Yellow-green
    }
    
    # Merge manual colors with generated ones
    colors.update(nice_colors)
    
    return colors

# Generate all colors at startup
CLASS_COLORS = generate_coco_colors()

class ObjectDetectionTest:
    def __init__(self):
        logger.info("Initializing Object Detection Test...")
        
        # Initialize camera
        self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        self.frame_count = 0
        self.running = True
        self.current_fps = 0
        
        # Initialize YOLO model for LOCAL inference (faster!)
        logger.info(f"Loading {YOLO_MODEL.upper()} model for local inference...")
        try:
            self.model = YOLO(f'{YOLO_MODEL}.pt')  # Load specified model
            logger.info(f"✓ {YOLO_MODEL.upper()} loaded successfully")
            self.use_local = True
        except Exception as e:
            logger.warning(f"Could not load {YOLO_MODEL.upper()}: {e}")
            logger.info("✓ Falling back to API inference")
            self.use_local = False
            
            # Check Vision Service as fallback
            try:
                r = requests.get("http://localhost:8001/health", timeout=2)
                if r.status_code == 200:
                    logger.info("✓ Vision Service is READY (fallback mode)")
            except:
                logger.error("✗ Vision Service not running!")
                raise
    
    def run(self):
        """Main loop - LOCAL camera + LOCAL YOLO inference (fastest)"""
        logger.info("Starting OBJECT DETECTION test...")
        if self.use_local:
            logger.info(f"Mode: LOCAL {YOLO_MODEL.upper()} inference")
        else:
            logger.info("Mode: API inference (fallback)")
        logger.info(f"Confidence threshold: {CONFIDENCE_THRESHOLD}")
        logger.info("Press 'Q' to quit, 'S' to save screenshot, 'M' to toggle mode")
        logger.info("")
        
        cv2.namedWindow("Object Detection", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Object Detection", DISPLAY_SIZE[0], DISPLAY_SIZE[1])
        
        fps_time = time.time()
        fps_count = 0
        frame_stats_time = time.time()
        
        try:
            while self.running:
                ret, frame = self.cap.read()
                if not ret:
                    continue
                
                self.frame_count += 1
                objects_detected = 0
                detections = []
                inference_time = 0
                
                # ==== RUN INFERENCE (LOCAL or API) ====
                if self.use_local:
                    # LOCAL YOLO inference (FAST!)
                    infer_start = time.time()
                    results = self.model(frame, conf=CONFIDENCE_THRESHOLD, verbose=False)
                    inference_time = (time.time() - infer_start) * 1000
                    
                    # Parse YOLOv8 results
                    if results and len(results) > 0:
                        r = results[0]
                        objects_detected = len(r.boxes)
                        
                        for box in r.boxes:
                            class_id = int(box.cls[0].item())
                            class_name = r.names[class_id]
                            confidence = float(box.conf[0].item())
                            
                            # Get box coordinates
                            x1, y1, x2, y2 = box.xyxy[0].numpy()
                            x, y = int(x1), int(y1)
                            w, h = int(x2 - x1), int(y2 - y1)
                            
                            detections.append({
                                'class_name': class_name,
                                'confidence': confidence,
                                'bounding_box': {
                                    'x': x,
                                    'y': y,
                                    'width': w,
                                    'height': h
                                }
                            })
                else:
                    # API inference (fallback)
                    infer_start = time.time()
                    small_frame = cv2.resize(frame, (640, 480))
                    _, buffer = cv2.imencode('.jpg', small_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    
                    try:
                        files = {'file': ('frame.jpg', buffer.tobytes(), 'image/jpeg')}
                        params = {'confidence_threshold': CONFIDENCE_THRESHOLD}
                        r = requests.post(API_URL, files=files, params=params, timeout=10)
                        inference_time = (time.time() - infer_start) * 1000
                        
                        if r.status_code == 200:
                            data = r.json()
                            objects_detected = data.get('objects_detected', 0)
                            detections = data.get('detections', [])
                            
                            # Scale coordinates back
                            scale_x = frame.shape[1] / 640
                            scale_y = frame.shape[0] / 480
                            for detection in detections:
                                bbox = detection.get('bounding_box', {})
                                if bbox:
                                    bbox['x'] = int(bbox['x'] * scale_x)
                                    bbox['y'] = int(bbox['y'] * scale_y)
                                    bbox['width'] = int(bbox['width'] * scale_x)
                                    bbox['height'] = int(bbox['height'] * scale_y)
                    except Exception as e:
                        logger.debug(f"API error: {e}")
                
                # ==== DRAW DETECTIONS ====
                display_frame = cv2.resize(frame, DISPLAY_SIZE)
                
                for detection in detections:
                    bbox = detection.get('bounding_box', {})
                    class_name = detection.get('class_name', 'unknown')
                    confidence = detection.get('confidence', 0)
                    
                    if bbox:
                        # Scale coordinates to display frame
                        scale_x = DISPLAY_SIZE[0] / frame.shape[1]
                        scale_y = DISPLAY_SIZE[1] / frame.shape[0]
                        
                        x = int(bbox['x'] * scale_x)
                        y = int(bbox['y'] * scale_y)
                        w = int(bbox['width'] * scale_x)
                        h = int(bbox['height'] * scale_y)
                        
                        # Get color for class
                        color = CLASS_COLORS.get(class_name, (200, 200, 200))  # Gray fallback
                        
                        # Draw bounding box
                        cv2.rectangle(display_frame, (x, y), (x + w, y + h), color, 2)
                        
                        # Draw label with confidence
                        label = f"{class_name} ({confidence:.2f})"
                        text_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                        
                        # Label background
                        cv2.rectangle(display_frame,
                                     (x, max(0, y - 25)),
                                     (x + text_size[0] + 10, y),
                                     color, -1)
                        
                        # Label text
                        cv2.putText(display_frame, label, (x + 5, y - 5),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
                # ==== DRAW STATS ====
                h_disp, w_disp = display_frame.shape[:2]
                cv2.rectangle(display_frame, (0, 0), (w_disp, 110), (0, 0, 0), -1)
                cv2.rectangle(display_frame, (0, 0), (w_disp, 110), (0, 255, 0), 2)
                
                fps_count += 1
                elapsed = time.time() - fps_time
                if elapsed >= 1:
                    self.current_fps = fps_count / elapsed
                    fps_time = time.time()
                    fps_count = 0
                
                # Display stats
                mode_str = "LOCAL" if self.use_local else "API"
                info1 = f"FPS: {self.current_fps:.1f} | Objects: {objects_detected} | Mode: {mode_str} | Inference: {inference_time:.0f}ms"
                info2 = f"Model: {YOLO_MODEL.upper()} | Confidence: {CONFIDENCE_THRESHOLD} | Q=Quit | S=Save | M=Mode"
                cv2.putText(display_frame, info1, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                cv2.putText(display_frame, info2, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1)
                
                # Show frame
                cv2.imshow("Object Detection", display_frame)
                
                # Log stats every 5 seconds
                if time.time() - frame_stats_time > 5:
                    logger.info(f"Status: FPS={self.current_fps:.1f} | Objects={objects_detected} | Frame#{self.frame_count} | Inference={inference_time:.0f}ms")
                    frame_stats_time = time.time()
                
                # Handle keyboard
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == 27:
                    self.running = False
                elif key == ord('s'):
                    filename = f"object_detection_{int(time.time())}.jpg"
                    cv2.imwrite(filename, display_frame)
                    logger.info(f"Saved: {filename}")
                elif key == ord('m'):
                    if self.model and self.use_local:
                        self.use_local = False
                        logger.info("Switched to API mode")
                    else:
                        self.use_local = True
                        logger.info("Switched to LOCAL mode")
        
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
    test = ObjectDetectionTest()
    test.run()
