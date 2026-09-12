"""
LLM Service - Conversational AI Brain for NEXI Robot.
This service provides online LLM inference via OpenRouter.
Port: 8006
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from shared.security import allowed_origins, InternalRouteAuthMiddleware
from shared.api_errors import install_error_handlers
from shared.request_middleware import install_request_observability
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import service components
from llm_service.config import HOST, PORT
from llm_service.services.openrouter_client import OpenRouterClient
from llm_service.routes.generation import create_generation_routes
from llm_service.routes.format import create_format_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Construct the configured provider without performing network I/O so routes are
# present in OpenAPI before lifespan startup and at runtime alike.
openrouter_client = OpenRouterClient()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager.
    Initializes OpenRouter client.
    """
    logger.info("=" * 80)
    logger.info("Starting LLM Service (Port 8006) - Online Mode + /format endpoint")
    logger.info("=" * 80)
    
    yield
    
    logger.info("LLM Service shutdown complete")

# Create FastAPI application
app = FastAPI(
    title="NEXI LLM Service",
    description="Online language model inference service via OpenRouter",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Route registration is application construction, not a startup side effect.
app.include_router(create_generation_routes(openrouter_client))
app.include_router(create_format_router(None))  # model_loader removed
app.add_middleware(InternalRouteAuthMiddleware, protected_prefixes=("/api/v1/generate",))
install_error_handlers(app, "llm")
install_request_observability(app, "llm")

@app.get("/", tags=["info"])
async def root():
    return {
        "service": "NEXI LLM Service",
        "version": "1.0.0",
        "status": "running (online mode)",
    }

if __name__ == "__main__":
    import uvicorn
    from config.ssl_config import get_tls_config
    uvicorn.run(app, host=HOST, port=PORT, **get_tls_config().uvicorn_kwargs())
