from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import sys
from pathlib import Path

from persistence import load_users
from routes import user_router
from routes.conversations_routes import router as conversations_router
from camera_routes import router as camera_router
from teachme_routes import router as teachme_router
from resource_routes import router as resource_router
from teachme_connector import init_teachme_connector
from service_config import get_config

# Import Phase 1 security modules (from shared/)
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.rate_limiter import create_rate_limit_middleware


def create_app() -> FastAPI:
    app = FastAPI(title="NEXI Central Server", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add Phase 1 security: Rate limiting middleware
    # Exempt: /health, /docs, /openapi.json (health checks should always work)
    rate_limit_middleware = create_rate_limit_middleware()
    app.middleware("http")(rate_limit_middleware)

    app.state.db = {"users": load_users()}
    app.include_router(user_router)
    app.include_router(conversations_router)
    app.include_router(camera_router)
    app.include_router(teachme_router)
    app.include_router(resource_router)
    
    # Startup event for TeachMe connector initialization
    @app.on_event("startup")
    async def startup_event():
        """Initialize services on startup"""
        try:
            config = get_config()
            teachme_config = config.services.get_service_configs().get("teachme", {})
            await init_teachme_connector(config=teachme_config)
            print(" TeachMe connector initialized")
        except Exception as e:
            print(f"Warning: TeachMe connector failed to initialize: {e}")

    return app


app = create_app()


@app.get("/")
def root() -> dict:
    return {"status": "running", "service": "central_server"}


@app.get("/health")
def health() -> dict:
    return {"status": "healthy", "service": "central_server"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)