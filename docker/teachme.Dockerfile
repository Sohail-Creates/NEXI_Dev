# TeachMe Service - RAG with SigLIP2 + FAISS
FROM nexi-base:latest

# TeachMe: FAISS, Transformers (SigLIP2), FastAPI
RUN pip install --no-cache-dir \
    fastapi==0.126.0 \
    uvicorn==0.40.0 \
    pydantic==2.12.5 \
    numpy>=1.21.0 \
    faiss-cpu>=1.7.0 \
    python-dotenv>=0.19.0 \
    aiofiles>=23.0.0 \
    aiohttp>=3.9.0 \
    PyJWT>=2.8.0 \
    requests>=2.31.0 \
    httpx==0.28.1 \
    python-multipart==0.0.22 \
    annotated-types==0.7.0 \
    anyio==4.12.0 \
    certifi==2025.11.12 \
    colorama==0.4.6 \
    click==8.3.1 \
    h11==0.16.0 \
    httpcore==1.0.9 \
    idna==3.11 \
    pydantic_core==2.41.5 \
    starlette==0.50.0 \
    typing-inspection==0.4.2 \
    typing_extensions==4.15.0 \
    torch==2.10.0 torchvision==0.25.0 \
    transformers==5.2.0 \
    pillow==12.1.1

COPY 05_teachme_service/ /app/
WORKDIR /app/teachme_service

EXPOSE 8004
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["python", "main.py"]