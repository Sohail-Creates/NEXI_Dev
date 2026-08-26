# NEXI CLI Runner - Interactive terminal interface
FROM nexi-base:latest

# CLI deps: OpenCV for camera, PyAudio for audio, requests for API
RUN pip install --no-cache-dir \
    opencv-python-headless==4.8.0.76 \
    pyaudio==0.2.14 \
    requests==2.32.5 \
    pillow==12.1.1 \
    numpy==1.26.4

COPY nexctl.py /app/nexctl.py
COPY docker/scripts/wait-for-services.sh /app/scripts/
WORKDIR /app

# Override entrypoint to run nexctl directly
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["python", "nexctl.py"]