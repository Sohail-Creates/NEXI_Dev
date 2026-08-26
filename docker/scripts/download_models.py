#!/usr/bin/env python3
"""Pre-download all ML models at build/startup time."""

import os
import sys
from pathlib import Path

MODELS_DIR = Path("/app/models")
MODELS_DIR.mkdir(parents=True, exist_ok=True)

def download_piper_jenny():
    """Download Piper TTS Jenny voice."""
    try:
        from piper import download
        download("en_GB-jenny_dioco-medium", MODELS_DIR)
        print("✓ Piper Jenny model downloaded")
    except Exception as e:
        print(f"⚠ Piper download failed: {e}")

def download_siglip2():
    """Download SigLIP2 model for TeachMe."""
    try:
        from transformers import AutoProcessor, AutoModel
        model_id = "google/siglip2-base-patch16-224"
        AutoProcessor.from_pretrained(model_id, cache_dir="/app/models/hf")
        AutoModel.from_pretrained(model_id, cache_dir="/app/models/hf")
        print("✓ SigLIP2 model downloaded")
    except Exception as e:
        print(f"⚠ SigLIP2 download failed: {e}")

def download_yolo():
    """Download YOLOv8n."""
    try:
        from ultralytics import YOLO
        YOLO("yolov8n.pt")  # Auto-downloads
        print("✓ YOLOv8n downloaded")
    except Exception as e:
        print(f"⚠ YOLO download failed: {e}")

def download_deepface():
    """Pre-load DeepFace models."""
    try:
        from deepface import DeepFace
        DeepFace.build_model("Facenet")
        print("✓ DeepFace Facenet downloaded")
    except Exception as e:
        print(f"⚠ DeepFace download failed: {e}")

if __name__ == "__main__":
    print("Downloading NEXI models...")
    download_piper_jenny()
    download_siglip2()
    download_yolo()
    download_deepface()
    print("Model download complete.")