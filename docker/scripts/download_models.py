#!/usr/bin/env python3
"""Pre-download all ML models at build/startup time."""

import os
import sys
from pathlib import Path

# The script lives at ``docker/scripts`` in source and ``/app/scripts`` in
# deployment.  Locate the application root explicitly so the embedding model
# identifier remains sourced from the same shared module as Central/TeachMe.
for candidate_root in (
    Path(__file__).resolve().parents[1],
    Path(__file__).resolve().parents[2],
):
    if (candidate_root / "shared").is_dir():
        sys.path.insert(0, str(candidate_root))
        break

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

def download_text_embeddings():
    """Provision the shared Phase 4 semantic model for offline runtime use."""
    try:
        from sentence_transformers import SentenceTransformer
        from shared.semantic_embeddings import SEMANTIC_EMBEDDING_MODEL

        SentenceTransformer(SEMANTIC_EMBEDDING_MODEL)
        print("TeachMe semantic embedding model downloaded")
    except Exception as e:
        print(f"TeachMe semantic embedding download failed: {e}")

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
    download_text_embeddings()
    download_yolo()
    download_deepface()
    print("Model download complete.")
