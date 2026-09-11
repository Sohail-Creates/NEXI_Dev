from __future__ import annotations

import sys
from pathlib import Path

# Make the repository-level shared package available for direct ``python main.py`` startup.
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from shared.security import allowed_origins, InternalRouteAuthMiddleware
from shared.api_errors import error_response, install_error_handlers
import asyncio

from sqlite_store import DATABASE, read_records, connect
from starlette.responses import JSONResponse
from routes import user_router
from routes.conversations_routes import router as conversations_router
from camera_routes import router as camera_router, call_router
from teachme_routes import router as teachme_router
from restricted_rag import router as restricted_rag_router
from resource_routes import router as resource_router
from teachme_connector import init_teachme_connector
from service_config import get_config
from services.cloud_sync_service import CloudSyncService, router as sync_router
from migrate_cloud_sync_outbox import migrate_outbox

# Import Phase 1 security modules (from shared/)
from shared.rate_limiter import create_rate_limit_middleware


def create_app() -> FastAPI:
    migrate_outbox(DATABASE)
    app = FastAPI(title="NEXI Central Server", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        InternalRouteAuthMiddleware,
        protected_prefixes=("/resources", "/camera", "/calls", "/sync", "/users/data/add_user"),
    )
    
    # Add Phase 1 security: Rate limiting middleware
    # Exempt: /health, /docs, /openapi.json (health checks should always work)
    rate_limit_middleware = create_rate_limit_middleware()
    app.middleware("http")(rate_limit_middleware)

    app.state.db = {"users": read_records("users")}
    app.state.user_store_lock = asyncio.Lock()
    app.state.cloud_sync_service = CloudSyncService.from_env(DATABASE)

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
                    return error_response(request, 500, "Failed to persist users")
                if response.status_code >= 400:
                    connection.rollback()
                else:
                    connection.commit()
                return response
            except Exception:
                connection.rollback()
                return error_response(request, 500, "User transaction failed")
            finally:
                connection.close()
    app.include_router(user_router)
    app.include_router(conversations_router)
    app.include_router(camera_router)
    app.include_router(call_router)
    app.include_router(teachme_router)
    app.include_router(restricted_rag_router)
    app.include_router(resource_router)
    app.include_router(sync_router)
    install_error_handlers(app, "central")
    
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
        app.state.cloud_sync_service.start()

    @app.on_event("shutdown")
    async def shutdown_event():
        await app.state.cloud_sync_service.stop()


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
