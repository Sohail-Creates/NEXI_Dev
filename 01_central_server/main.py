from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import sys
from pathlib import Path

# Make shared modules available before Phase 4 route modules are imported.
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlite_store import read_records, connect
from starlette.responses import JSONResponse
from routes import user_router
from routes.conversations_routes import router as conversations_router
from camera_routes import router as camera_router
from teachme_routes import router as teachme_router
from restricted_rag import router as restricted_rag_router
from resource_routes import router as resource_router
from teachme_connector import init_teachme_connector
from service_config import get_config
from services.cloud_sync_service import CloudSyncService
import os

sync_service = CloudSyncService(
    history_dir="D:\\TRUSTNEXUS\\NEXI_Refactor\\TN-NEXI\\05_teachme_service\\teachme_service\\data\\history",
    cloud_url=os.getenv("CLOUD_SYNC_URL", "https://api.yourcloud.com")
)

async def daily_sync_task():
    while True:
        await sync_service.sync_history()
        await asyncio.sleep(86400) # 24 hours

# Import Phase 1 security modules (from shared/)
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

    app.state.db = {"users": read_records("users")}
    app.state.user_store_lock = asyncio.Lock()

    @app.middleware("http")
    async def transactional_users(request, call_next):
        if not request.url.path.startswith("/users/") or request.url.path.endswith("/conversations"):
            return await call_next(request)
        async with app.state.user_store_lock:
            connection = connect()
            try:
                await asyncio.to_thread(connection.execute, "BEGIN IMMEDIATE")
                app.state.db["users"] = read_records("users", connection)
                request.state.user_connection = connection
                request.state.persistence_failed = False
                response = await call_next(request)
                if request.state.persistence_failed:
                    connection.rollback()
                    return JSONResponse(status_code=500, content={"detail": "Failed to persist users"})
                if response.status_code >= 400:
                    connection.rollback()
                else:
                    connection.commit()
                return response
            except Exception:
                connection.rollback()
                return JSONResponse(status_code=500, content={"detail": "User transaction failed"})
            finally:
                connection.close()
    app.include_router(user_router)
    app.include_router(conversations_router)
    app.include_router(camera_router)
    app.include_router(teachme_router)
    app.include_router(restricted_rag_router)
    app.include_router(resource_router)
    
    # Startup event for TeachMe connector initialization
    @app.on_event("startup")
    async def startup_event():
        """Initialize services on startup"""
        try:
            import json
            config = get_config()
            teachme_config = config.services.get_service_configs().get("teachme", {})
            await init_teachme_connector(config=teachme_config)
            print(" TeachMe connector initialized")
            asyncio.create_task(daily_sync_task())
        except Exception as e:
            import json
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
