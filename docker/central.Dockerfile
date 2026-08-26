# Central Server - Lightweight FastAPI service
FROM nexi-base:latest

# Central Server deps
RUN pip install --no-cache-dir \
    fastapi==0.111.0 \
    uvicorn[standard]==0.29.0 \
    pydantic==2.7.1 \
    aiohttp==3.9.1 \
    httpx==0.28.1 \
    requests==2.32.3 \
    python-dotenv==1.0.0 \
    anyio==4.1.1

COPY 01_central_server/ /app/
WORKDIR /app

EXPOSE 8000
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["python", "main.py"]