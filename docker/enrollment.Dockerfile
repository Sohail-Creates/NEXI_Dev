# Enrollment Service - User enrollment with photos and voice
FROM nexi-base:latest

# Enrollment: FastAPI, Streamlit, audio/image processing
RUN pip install --no-cache-dir \
    fastapi==0.104.1 \
    uvicorn[standard]==0.24.0 \
    python-multipart==0.0.6 \
    pydantic==2.5.0 \
    python-dotenv==1.0.0 \
    httpx==0.25.0 \
    aiofiles==23.2.1 \
    pillow==10.1.0 \
    sounddevice==0.4.6 \
    soundfile==0.12.1 \
    numpy==1.24.3 \
    streamlit==1.28.0 \
    streamlit-webrtc==0.47.1 \
    av==14.0.0 \
    requests==2.31.0 \
    httpx==0.25.0

COPY 06_enrollment_service/ /app/
WORKDIR /app/enrollment_service/app

EXPOSE 8005
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["python", "main.py"]