# Vision Service - Heavy ML service with TensorFlow, DeepFace, YOLO
FROM nexi-base:latest

# Vision-specific: TensorFlow, DeepFace, YOLO, OpenCV
RUN pip install --no-cache-dir \
    tensorflow==2.13.1 \
    keras==2.13.1 \
    torch==2.0.1 torchvision==0.15.2 \
    ultralytics==8.0.196 \
    deepface==0.0.79 \
    opencv-python-headless==4.8.0.76 \
    scikit-image==0.21.0 \
    pillow==10.0.1 \
    numpy==1.24.3 scipy==1.11.2 \
    fastapi==0.104.1 \
    uvicorn[standard]==0.24.0 \
    pydantic==2.5.0 \
    python-dotenv==1.0.0 \
    httpx==0.25.0

COPY 02_vision_service/ /app/
WORKDIR /app/vision_service

EXPOSE 8001
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["python", "main.py"]