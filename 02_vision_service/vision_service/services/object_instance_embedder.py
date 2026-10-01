"""One versioned, local visual-instance encoder; no labels or persistence."""

import hashlib
import logging
import math
import threading
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

INSTANCE_MODEL_ID = "torchvision-resnet18-imagenet1k-v1"
INSTANCE_MODEL_VERSION = 1
INSTANCE_DIMENSION = 512
_WEIGHTS_SHA256 = "f37072fd47e89c5e827621c5baffa7500819f7896bbacec160b1a16c560e07ec"


class InstanceEmbeddingError(RuntimeError):
    """The selected ROI cannot be represented reliably."""


class ObjectInstanceEmbedder:
    def __init__(self, weights_path: Path):
        self.weights_path = Path(weights_path).resolve()
        self.model = None
        self.transform = None
        self._lock = threading.Lock()

    def load(self) -> None:
        """Load one pinned local artifact; never download at request/startup time."""
        import torch
        from torchvision.models import ResNet18_Weights, resnet18

        if not self.weights_path.is_file():
            raise FileNotFoundError(f"Instance model missing: {self.weights_path}")
        with self.weights_path.open("rb") as weights_file:
            digest = hashlib.file_digest(weights_file, "sha256").hexdigest()
        if digest != _WEIGHTS_SHA256:
            raise ValueError("Instance model checksum mismatch")
        model = resnet18(weights=None)
        model.load_state_dict(torch.load(self.weights_path, map_location="cpu", weights_only=True))
        model.fc = torch.nn.Identity()
        model.eval()
        self.transform = ResNet18_Weights.IMAGENET1K_V1.transforms()
        self.model = model

    def encode(self, frame: np.ndarray, bbox: tuple[int, int, int, int]) -> list[float]:
        """Apply the same crop and preprocessing for teaching and recognition."""
        import torch

        if self.model is None or self.transform is None:
            raise InstanceEmbeddingError("Instance model is not ready")
        x1, y1, x2, y2 = bbox
        height, width = frame.shape[:2]
        if x1 < 0 or y1 < 0 or x2 > width or y2 > height or x2 - x1 < 16 or y2 - y1 < 16:
            raise InstanceEmbeddingError("Selected object ROI is too small or out of bounds")
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            raise InstanceEmbeddingError("Selected object ROI is empty")
        started = time.perf_counter()
        tensor = self.transform(Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))).unsqueeze(0)
        with self._lock, torch.inference_mode():
            vector = self.model(tensor)[0].float()
        norm = torch.linalg.vector_norm(vector)
        if vector.numel() != INSTANCE_DIMENSION or not torch.isfinite(vector).all() or not math.isfinite(norm.item()) or norm.item() <= 0:
            raise InstanceEmbeddingError("Instance model produced an invalid vector")
        result = (vector / norm).cpu().tolist()
        logger.info("Instance embedding preprocess_inference_ms=%.1f", (time.perf_counter() - started) * 1000)
        return result
