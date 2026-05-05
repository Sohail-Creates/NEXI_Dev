"""
LLM Service - Conversational AI Brain for NEXI Robot.

This service provides local language model inference with context awareness
from other NEXI services (Vision, Audio, TeachMe, etc).

Port: 8006
Model: SmolLM2-1.7B-Instruct
"""

import logging
import asyncio
import sys
import os
from contextlib import asynccontextmanager
from typing import Optional
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Load environment variables from .env file (root directory)
# This searches from current directory upward until it finds .env
load_dotenv()

# Import Phase 1 security: Rate limiting
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.rate_limiter import create_rate_limit_middleware

# Import service components
from llm_service.config import (
    HOST,
    PORT,
    DEBUG,
    ModelLoadConfig,
    InferenceConfig,
)
from llm_service.services.model_loader import ModelLoader
from llm_service.services.inference_engine import InferenceEngine
from llm_service.services.prompt_builder import PromptBuilder
from llm_service.services.openrouter_client import OpenRouterClient
from llm_service.services.hybrid_inference import HybridInferenceManager
from llm_service.routes.generation import create_generation_routes

# Configure logging
logging.basicConfig(
    level=logging.INFO if not DEBUG else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Global service instances
model_loader: Optional[ModelLoader] = None
inference_engine: Optional[InferenceEngine] = None
prompt_builder: Optional[PromptBuilder] = None
openrouter_client: Optional[OpenRouterClient] = None
hybrid_manager: Optional[HybridInferenceManager] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI application.
    
    Handles startup (model loading) and shutdown (cleanup).
    """
    global model_loader, inference_engine, prompt_builder, openrouter_client, hybrid_manager
    
    # Startup
    logger.info("=" * 80)
    logger.info("Starting LLM Service (Port 8006)")
    logger.info("=" * 80)
    
    try:
        # Initialize OpenRouter client (for hybrid inference)
        logger.info("Initializing OpenRouter client...")
        openrouter_client = OpenRouterClient()
        if openrouter_client.is_available:
            logger.info(" OpenRouter API configured - will use as primary with local LLM fallback")
        else:
            logger.info(" OpenRouter API key not found - will use local LLM only")
        
        # Initialize model loader
        logger.info("Initializing model loader...")
        model_loader = ModelLoader()
        
        # Load model
        model_config = ModelLoadConfig()
        logger.info(f"Loading model: {model_config.model_name}")
        logger.info(f"Model path: {model_config.model_path}")
        logger.info(f"Device: {model_config.device}")
        
        success = model_loader.load_model(
            model_name=model_config.model_name,
            model_path=model_config.model_path,
            device=model_config.device,
            low_memory=model_config.low_memory,
        )
        
        if success:
            logger.info(" Model loaded successfully")
            
            # Initialize inference engine
            inference_config = InferenceConfig()
            inference_engine = InferenceEngine(model_loader, inference_config)
            logger.info(" Inference engine initialized")
            
            # Initialize prompt builder
            import llm_service.config as config_module
            prompt_builder = PromptBuilder(config_module)
            logger.info(" Prompt builder initialized")
            
            # Initialize hybrid inference manager
            hybrid_manager = HybridInferenceManager(openrouter_client, inference_engine)
            logger.info(" Hybrid inference manager initialized")
            
            # Register routes AFTER initialization
            logger.info("Registering generation routes...")
            generation_router = create_generation_routes(
                inference_engine,
                prompt_builder,
                model_loader,
                hybrid_manager=hybrid_manager,
            )
            app.include_router(generation_router)
            logger.info(" Routes registered")
            
            logger.info("=" * 80)
            logger.info("LLM Service ready to accept requests on http://{}:{}".format(HOST, PORT))
            logger.info("=" * 80)
        else:
            logger.error("Failed to load model during startup")
            raise RuntimeError("Model initialization failed")
        
    except Exception as e:
        logger.error(f"Startup failed: {str(e)}", exc_info=True)
        raise
    
    # Yield to FastAPI application
    yield
    
    # Shutdown
    logger.info("=" * 80)
    logger.info("Shutting down LLM Service...")
    logger.info("=" * 80)
    
    try:
        if model_loader:
            model_loader.unload_model()
            logger.info(" Model unloaded")
        
        logger.info("LLM Service shutdown complete")
    except Exception as e:
        logger.error(f"Error during shutdown: {str(e)}", exc_info=True)


# Create FastAPI application
app = FastAPI(
    title="NEXI LLM Service",
    description="Local language model inference service with context awareness",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add Phase 1 security: Rate limiting middleware
# LLM endpoints are expensive, so we use stricter limits
rate_limit_middleware = create_rate_limit_middleware()
app.middleware("http")(rate_limit_middleware)


# Error handlers
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An internal server error occurred",
            }
        }
    )


# Request hook for logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests."""
    logger.debug(f"Incoming request: {request.method} {request.url.path}")
    
    response = await call_next(request)
    
    logger.debug(f"Response: {response.status_code}")
    return response


# Root endpoint
@app.get("/", tags=["info"])
async def root():
    """Root endpoint with service information."""
    return {
        "service": "NEXI LLM Service",
        "version": "1.0.0",
        "status": "running",
        "model": "SmolLM2-1.7B-Instruct",
        "endpoints": {
            "health": "/api/v1/health",
            "model_info": "/api/v1/model-info",
            "generate": "/api/v1/generate",
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting LLM Service on {HOST}:{PORT}")
    
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        reload=DEBUG,
        workers=1,  # Single worker to avoid multiple model instances
        log_level="info" if not DEBUG else "debug",
    )
