"""
Vision Service Object Detection Module
YOLOv8 Object Detection Integration
Production implementation from Vision-Nexus
"""

import numpy as np
import logging
import math
import threading
from typing import Optional, Dict, List, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)
_SERVICE_ROOT = Path(__file__).resolve().parents[2]
OBJECT_EMBEDDING_MODEL = "yolov8n-p3-roi-avg-v1"


class ObjectEmbeddingError(RuntimeError):
    """Raised when a detected object's visual feature cannot be encoded."""


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
        self._inference_lock = threading.RLock()
        
    def load_model(self) -> bool:
        """
        Load YOLO model
        
        Returns:
            True if model loaded successfully, False otherwise
        """
        try:
            from ultralytics import YOLO
            
            checkpoint = (
                Path(self.model_path).expanduser().resolve()
                if self.model_path
                else (_SERVICE_ROOT / f"{self.model_name}.pt").resolve()
            )
            if not checkpoint.is_file():
                raise FileNotFoundError(f"YOLO checkpoint not found: {checkpoint}")
            logger.info("Loading YOLO from absolute checkpoint path %s", checkpoint)
            self.model = YOLO(str(checkpoint))
            
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
            import torch

            # Capture the P3 feature map from the same forward pass as detection.
            # The pinned YOLOv8n Detect head consumes layers [15, 18, 21]; its
            # first input is the stride-8 feature map used for object-level ROIs.
            with self._inference_lock:
                capture: dict[str, object] = {}
                detection_model = self.model.model
                layers = detection_model.model
                detect_head = layers[-1]
                p3_layer_index = detect_head.f[0]
                p3_layer = layers[p3_layer_index]

                def capture_input(_module, args):
                    capture["input_hw"] = tuple(args[0].shape[-2:])

                def capture_p3(_module, _args, output):
                    capture["p3"] = output

                input_hook = layers[0].register_forward_pre_hook(capture_input)
                p3_hook = p3_layer.register_forward_hook(capture_p3)
                try:
                    results = self.model(image, verbose=False)
                finally:
                    input_hook.remove()
                    p3_hook.remove()

                feature_map = capture.get("p3")
                input_hw = capture.get("input_hw")
                if feature_map is None or input_hw is None:
                    raise ObjectEmbeddingError("YOLO object feature map was not produced")
                if not isinstance(feature_map, torch.Tensor):
                    raise ObjectEmbeddingError("YOLO object feature map has an invalid type")
                stride = float(detect_head.stride[0].item())
            
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

                    embedding = self._roi_embedding(
                        image=image,
                        feature_map=feature_map,
                        input_hw=input_hw,
                        stride=stride,
                        bbox=(x1, y1, x2, y2),
                    )

                    detection = {
                        "class_id": class_id,
                        "class_name": class_name,
                        "confidence": confidence,
                        "bounding_box": {
                            "x": x1,
                            "y": y1,
                            "width": width,
                            "height": height
                        },
                        "embedding": embedding,
                        "embedding_model": OBJECT_EMBEDDING_MODEL,
                        "embedding_dimension": len(embedding),
                    }
                    detections.append(detection)
                    
                except ObjectEmbeddingError:
                    raise
                except Exception as e:
                    raise RuntimeError("Failed to decode YOLO detection output") from e
            
            return {
                "objects_detected": len(detections),
                "detections": detections
            }
            
        except ObjectEmbeddingError:
            raise
        except Exception as e:
            logger.error(f"Error in object detection: {e}")
            return None

    @staticmethod
    def _roi_embedding(
        *,
        image: np.ndarray,
        feature_map,
        input_hw: tuple[int, int],
        stride: float,
        bbox: tuple[int, int, int, int],
    ) -> list[float]:
        """Pool and L2-normalize P3 activations within one detected box."""
        import torch
        import torch.nn.functional as torch_functional

        image_height, image_width = image.shape[:2]
        input_height, input_width = input_hw
        scale = min(input_width / image_width, input_height / image_height)
        resized_width = round(image_width * scale)
        resized_height = round(image_height * scale)
        pad_x = round((input_width - resized_width) / 2 - 0.1)
        pad_y = round((input_height - resized_height) / 2 - 0.1)
        _, _, feature_height, feature_width = feature_map.shape
        x1, y1, x2, y2 = bbox
        left = max(0, min(feature_width, math.floor((x1 * scale + pad_x) / stride)))
        top = max(0, min(feature_height, math.floor((y1 * scale + pad_y) / stride)))
        right = max(0, min(feature_width, math.ceil((x2 * scale + pad_x) / stride)))
        bottom = max(0, min(feature_height, math.ceil((y2 * scale + pad_y) / stride)))
        if right <= left or bottom <= top:
            raise ObjectEmbeddingError("Detected object has an empty feature-map crop")

        pooled = feature_map[0, :, top:bottom, left:right].detach().float().mean(dim=(1, 2))
        if not torch.isfinite(pooled).all() or torch.linalg.vector_norm(pooled).item() <= 1e-12:
            raise ObjectEmbeddingError("Detected object produced an invalid visual feature")
        normalized = torch_functional.normalize(pooled, p=2, dim=0)
        vector = normalized.cpu().tolist()
        if not vector or not all(math.isfinite(value) for value in vector):
            raise ObjectEmbeddingError("Detected object produced a non-finite visual feature")
        return vector
    
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
