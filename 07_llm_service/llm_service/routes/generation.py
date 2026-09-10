"""Generation routes for LLM Service - OpenRouter only."""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)

class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1)
    max_tokens: int = 128
    temperature: float = 0.2
    language: str = "en"

    @field_validator("max_tokens", mode="before")
    @classmethod
    def clamp_max_tokens(cls, value):
        return max(1, min(512, int(value)))

    @field_validator("temperature", mode="before")
    @classmethod
    def clamp_temperature(cls, value):
        return max(0.0, min(1.5, float(value)))

def create_generation_routes(openrouter_client):
    router = APIRouter(prefix="/api/v1")

    @router.get("/model-info")
    async def model_info():
        return {"provider": "openrouter", "model": openrouter_client.model}
    
    @router.post("/generate")
    async def generate(req: GenerationRequest):
        try:
            text, metadata, success = await openrouter_client.generate(
                prompt=req.query,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
            )
            
            if not success:
                logger.error(f"Generation failed: {metadata.get('error')}")
                raise HTTPException(status_code=500, detail=f"Generation failed: {metadata.get('error')}")
            
            return {
                "success": True,
                "text": text,
                "metadata": metadata
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get("/health")
    async def health():
        healthy = openrouter_client.is_healthy()
        return {"status": "healthy" if healthy else "degraded", "openrouter": healthy}
    
    return router
