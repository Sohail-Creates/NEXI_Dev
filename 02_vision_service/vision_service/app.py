"""
Vision Service FastAPI Application
Main application setup and initialization
Production implementation from Vision-Nexus
"""

import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import configuration and services
from .config import Config
from .services.resource_pool import ResourcePool
from .services.face_detector import load_model_with_retry

# Import route handlers
from .routes import health, detection, streaming, camera

# Import Phase 1 security: Rate limiting
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))
from shared.rate_limiter import create_rate_limit_middleware

# Global resource pool
_resource_pool: ResourcePool = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI startup and shutdown events
    Production implementation from Vision-Nexus
    """
    global _resource_pool
    app.state.face_model_loaded = False
    
    # Startup
    logger.info("=" * 60)
    logger.info("NEXI Vision Service v4.0.0 Starting")
    logger.info("=" * 60)
    
    try:
        # Initialize configuration
        logger.info(f"Configuration loaded:")
        logger.info(f"   Embedding model: {Config.EMBEDDING_MODEL}")
        logger.info(f"   Detector backend: {Config.DETECTOR_BACKEND}")
        logger.info(f"   Log level: {Config.LOG_LEVEL}")
        logger.info(f"   Camera timeout: {Config.CAMERA_TIMEOUT}s")
        
        # Validate configuration
        Config.validate()
        
        # Create and initialize resource pool
        _resource_pool = ResourcePool(
            camera_timeout=Config.CAMERA_TIMEOUT,
            central_server_url=Config.CENTRAL_SERVER_URL,
            enable_object_detection=Config.ENABLE_OBJECT_DETECTION,
            object_model_name=Config.OBJECT_DETECTION_MODEL
        )
        logger.info(" Resource pool initialized with Central Server camera management")
        
        # Load embedding model with retry logic
        try:
            success = load_model_with_retry(
                model_name=Config.EMBEDDING_MODEL,
                max_retries=Config.MODEL_LOAD_MAX_RETRIES,
                backoff_seconds=Config.MODEL_LOAD_BACKOFF_SECONDS
            )
            app.state.face_model_loaded = bool(success)
            if not success:
                logger.error("Failed to load embedding model - service may have limited functionality")
        except Exception as e:
            logger.error(f"Critical error loading embedding model: {e}")
            logger.warning("Service continuing but may have limited functionality")
        
        # Set resource pool references in route handlers
        health.set_resource_pool(_resource_pool)
        detection.set_resource_pool(_resource_pool)
        streaming.set_resource_pool(_resource_pool)
        camera.set_resource_pool(_resource_pool)
        logger.info(" Route handlers initialized")
        
        # Test YOLO availability if enabled
        if Config.ENABLE_OBJECT_DETECTION:
            if _resource_pool.is_object_detector_available():
                logger.info(f" Object detection is available ({Config.OBJECT_DETECTION_MODEL})")
            else:
                logger.warning(" Object detection is not available")
        
        logger.info("=" * 60)
        logger.info(" Vision Service Ready for Requests")
        logger.info(f" Running on {Config.HOST}:{Config.PORT}")
        logger.info(f" Documentation: http://localhost:{Config.PORT}/docs")
        logger.info("=" * 60)
        
        yield
        
    except Exception as e:
        logger.error(f"[CRITICAL] Startup error: {e}", exc_info=True)
        raise
    
    finally:
        # Shutdown
        logger.info("=" * 60)
        logger.info("Vision Service Shutting Down")
        logger.info("=" * 60)
        
        if _resource_pool is not None:
            try:
                _resource_pool.shutdown()
                logger.info(" Resource pool shutdown complete")
            except Exception as e:
                logger.error(f"Error during shutdown: {e}", exc_info=True)
        
        logger.info("=" * 60)
        logger.info("Vision Service Stopped")
        logger.info("=" * 60)


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application
    """
    
    app = FastAPI(
        title="NEXI Vision Service",
        description="Production-grade vision service for face detection, recognition",
        version="4.0.0",
        lifespan=lifespan
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
    rate_limit_middleware = create_rate_limit_middleware()
    app.middleware("http")(rate_limit_middleware)
    
    # Include routers
    app.include_router(health.router, tags=["Health"])
    app.include_router(detection.router, prefix="/api/v1", tags=["Face Detection"])
    app.include_router(streaming.router, tags=["Video Streaming"])
    app.include_router(camera.router, tags=["Camera Control"])
    
    logger.info("FastAPI application created with all routes registered")
    
    return app


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting Vision Service on {Config.HOST}:{Config.PORT}")
    
    uvicorn.run(
        app,
        host=Config.HOST,
        port=Config.PORT,
        log_level=Config.LOG_LEVEL.lower()
    )
