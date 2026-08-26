# Audio Service - Audio processing with PortAudio, pvporcupine, Groq STT
FROM nexi-base:latest

# Audio: PyAudio, pvporcupine, webrtcvad, Groq, Resemblyzer
RUN pip install --no-cache-dir \
    pyaudio==0.2.14 \
    pvporcupine==4.0.2 \
    webrtcvad-wheels==2.0.14 \
    sounddevice==0.5.5 \
    soundfile==0.13.1 \
    librosa==0.11.0 \
    Resemblyzer==0.1.4 \
    groq==1.0.0 \
    fastapi==0.129.0 \
    uvicorn==0.41.0 \
    pydantic==2.12.5 \
    pydantic-settings==2.13.0 \
    python-dotenv==1.2.1 \
    httpx==0.28.1 \
    aiofiles==25.1.0 \
    aiohttp==3.13.3 \
    numpy==1.26.4 \
    scipy==1.11.4 \
    scikit-learn==1.8.0 \
    prometheus-client==0.19.0 \
    cryptography==46.0.5 \
    keyboard==0.13.5 \
    pyyaml==6.0.3

COPY 03_audio_service/ /app/
WORKDIR /app/audio_service

EXPOSE 8002
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["python", "main.py"]