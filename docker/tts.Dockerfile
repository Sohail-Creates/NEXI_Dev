# TTS Service - Piper TTS with ONNX Runtime
FROM nexi-base:latest

# TTS: Piper, ONNX, Transformers
RUN pip install --no-cache-dir \
    piper-tts==1.4.1 \
    onnxruntime==1.20.1 \
    transformers==4.30.0 \
    torch==2.0.0 torchaudio==2.0.0 \
    safetensors==0.3.1 \
    huggingface-hub==0.21.4 \
    fastapi==0.112.0 \
    uvicorn[standard]==0.28.0 \
    pydantic==2.7.1 \
    pydantic-settings==2.2.1 \
    python-dotenv==1.0.0 \
    httpx==0.25.0 \
    prometheus-client==0.19.0

# Pre-download Jenny voice model at build time (optional)
ARG DOWNLOAD_MODELS=true
RUN if [ "$DOWNLOAD_MODELS" = "true" ]; then \
    python -c "from piper import download; download('en_GB-jenny_dioco-medium', '/app/models')"; \
    fi

COPY 04_tts_service/ /app/
WORKDIR /app/tts_service

EXPOSE 8003
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["python", "main.py"]