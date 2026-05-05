"""
Vision Service Object Detection Module
YOLOv8 Object Detection Integration
Production implementation from Vision-Nexus
"""

import numpy as np
import logging
from typing import Optional, Dict, List, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class ObjectDetector:
    """YOLOv8 Object Detection Wrapper"""
    
    # COCO dataset classes (80 classes detected by YOLO)
    COCO_CLASSES = [
        'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck',
        'boat', 'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench',
        'cat', 'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe',
        'backpack', 'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee', 'skis',
        'snowboard', 'sports ball', 'kite', 'baseball bat', 'baseball glove',
        'skateboard', 'surfboard', 'tennis racket', 'bottle', 'wine glass', 'cup',
        'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple', 'sandwich', 'orange',
        'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch',
        'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse',
        'remote', 'keyboard', 'microwave', 'oven', 'toaster', 'sink', 'refrigerator',
        'book', 'clock', 'vase', 'scissors', 'teddy bear', 'hair drier', 'toothbrush'
    ]
    
    def __init__(self, model_name: str = "yolov8n", model_path: Optional[str] = None):
        """
        Initialize object detector with YOLO model
        
        Args:
            model_name: YOLO model name (yolov8n, yolov8s, etc)
            model_path: Optional path to model file (if not using ultralytics auto-download)
        """
        self.model_name = model_name
        self.model = None
        self.available = False
        self.model_path = model_path
        
    def load_model(self) -> bool:
        """
        Load YOLO model
        
        Returns:
            True if model loaded successfully, False otherwise
        """
        try:
            from ultralytics import YOLO
            
            if self.model_path and Path(self.model_path).exists():
                # Load from specific path (e.g., models/yolov8n.pt)
                logger.info(f"Loading YOLO from {self.model_path}...")
                self.model = YOLO(self.model_path)
            else:
                # Load from ultralytics auto-download
                logger.info(f"Loading YOLO model: {self.model_name}...")
                self.model = YOLO(f"{self.model_name}.pt")
            
            self.available = True
            logger.info(f"YOLO {self.model_name} loaded successfully")
            return True
            
        except ImportError:
            logger.error("ultralytics package not installed. Install with: pip install ultralytics")
            return False
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            self.available = False
            return False
    
    def detect(self, image: np.ndarray, confidence_threshold: float = 0.5) -> Optional[Dict]:
        """
        Detect objects in image
        
        Args:
            image: Image as numpy array (BGR format from OpenCV)
            confidence_threshold: Minimum confidence score (0.0-1.0)
        
        Returns:
            Dictionary with detected objects or None if detection failed
        """
        if not self.available or self.model is None:
            logger.debug("YOLO model not available")
            return None
        
        try:
            # Run inference
            results = self.model(image, verbose=False)
            
            if not results or len(results) == 0:
                logger.debug("No detections found")
                return {
                    "objects_detected": 0,
                    "detections": []
                }
            
            # Process first result
            result = results[0]
            detections = []
            
            # Handle case where no objects detected
            if result.boxes is None or len(result.boxes) == 0:
                return {
                    "objects_detected": 0,
                    "detections": []
                }
            
            # Extract detections
            for box in result.boxes:
                try:
                    # Get box coordinates
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                    
                    # Get confidence
                    confidence = float(box.conf[0].cpu().numpy())
                    
                    # Apply confidence threshold
                    if confidence < confidence_threshold:
                        continue
                    
                    # Get class
                    class_id = int(box.cls[0].cpu().numpy())
                    class_name = self.COCO_CLASSES[class_id] if class_id < len(self.COCO_CLASSES) else f"class_{class_id}"
                    
                    # Calculate width and height
                    width = x2 - x1
                    height = y2 - y1
                    
                    detection = {
                        "class_id": class_id,
                        "class_name": class_name,
                        "confidence": confidence,
                        "bounding_box": {
                            "x": x1,
                            "y": y1,
                            "width": width,
                            "height": height
                        }
                    }
                    detections.append(detection)
                    
                except Exception as e:
                    logger.warning(f"Error processing detection: {e}")
                    continue
            
            return {
                "objects_detected": len(detections),
                "detections": detections
            }
            
        except Exception as e:
            logger.error(f"Error in object detection: {e}")
            return None
    
    def detect_batch(self, images: List[np.ndarray]) -> List[Optional[Dict]]:
        """
        Detect objects in multiple images
        
        Args:
            images: List of images as numpy arrays
        
        Returns:
            List of detection results
        """
        results = []
        for image in images:
            result = self.detect(image)
            results.append(result)
        return results
