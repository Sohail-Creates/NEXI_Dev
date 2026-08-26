# LLM Service - OpenRouter integration with /format endpoint
FROM nexi-base:latest

# LLM: OpenRouter client, outlines (for constrained decoding)
RUN pip install --no-cache-dir \
    fastapi==0.129.0 \
    uvicorn==0.41.0 \
    pydantic==2.12.5 \
    python-dotenv==1.2.1 \
    httpx==0.28.1 \
    requests==2.32.5 \
    outlines==0.0.45 \
    outlines-core==0.0.45

COPY 07_llm_service/ /app/
WORKDIR /app/llm_service

EXPOSE 8006
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["python", "main.py"]