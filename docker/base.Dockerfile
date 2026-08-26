# NEXI Base Image - Shared dependencies for all services
FROM python:3.11-slim-bookworm

# System dependencies for ALL services
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Vision: OpenCV, DeepFace, TensorFlow
    libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1 \
    # Audio: PortAudio, PulseAudio, ALSA
    portaudio19-dev pulseaudio-utils alsa-utils libasound2-dev \
    # ML: ONNX Runtime, PyTorch
    libgomp1 \
    # Utilities
    curl wget git ffmpeg libsndfile1 \
    # Build tools for wheels
    build-essential cmake pkg-config \
 && rm -rf /var/lib/apt/lists/*

# Python base deps
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

WORKDIR /app

# Create non-root user for security
RUN useradd -m -u 1000 nexi && chown -R nexi:nexi /app
USER nexi