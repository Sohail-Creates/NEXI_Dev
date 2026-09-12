import sys
import os
import asyncio
from pathlib import Path

# Add parent directory to path to allow imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from shared.security import allowed_origins, UploadGuardMiddleware
from shared.api_errors import install_error_handlers
from shared.request_middleware import install_request_observability
from app.routes import enrollment
from app.models import HealthCheckResponse
from dotenv import load_dotenv

# Import Phase 1 security: Rate limiting
from shared.rate_limiter import create_rate_limit_middleware

load_dotenv()

app = FastAPI(
    title="NEXI Enrollment Service",
    description="""
    ## Enrollment Service for Project NEXI - Week 3 Enhanced
    
    This service handles the complete user enrollment workflow with:
    -  Photo capture and validation
    -  Voice sample capture and validation
    -  AI-powered face embedding extraction (via Vision Service)
    -  AI-powered voice embedding extraction (via Audio Service)
    -  User registration with Central Server
    -  **Secure encrypted storage for enrollment data** (NEW)
    -  **Storage management and statistics** (NEW)
    -  **Data retrieval and deletion capabilities** (NEW)
    
    ### Service Architecture
    - **Port:** 8005
    - **Dependencies:** 
      - Vision Service (8001)
      - Audio Service (8002)
      - Central Server (8000)
    
    ### Week 3 Features
    [OK] Secure encrypted storage  
    [OK] Integration with Central Server user profiles  
    [OK] Storage statistics and management  
    [OK] Data retrieval and deletion APIs  
    [OK] Enhanced progress tracking  
    
    ### Security
    - All enrollment data is encrypted at rest
    - Encryption keys are securely generated and stored
    - Audit logging for all operations
    """,
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    UploadGuardMiddleware,
    rules={
        "/enrollment/enroll": (76 * 1024 * 1024, ("multipart/form-data",)),
        "/enrollment/improve-training": (76 * 1024 * 1024, ("multipart/form-data",)),
        "/enrollment/update-model": (76 * 1024 * 1024, ("multipart/form-data",)),
    },
)

# Add Phase 1 security: Rate limiting middleware
# Exempt: /health endpoints (should always be available)
rate_limit_middleware = create_rate_limit_middleware()
app.middleware("http")(rate_limit_middleware)
install_request_observability(app, "enrollment")

# Include routers
app.include_router(enrollment.router)
install_error_handlers(app, "enrollment")

@app.get("/", response_model=HealthCheckResponse)
async def health_check():
    """Basic health check endpoint"""
    return HealthCheckResponse(
        service=os.getenv("SERVICE_NAME", "Enrollment Service"),
        status="running",
        port=int(os.getenv("SERVICE_PORT", 8005))
    )

@app.get("/health")
async def health():
    """Simple health check"""
    return {"status": "healthy", "version": "3.0.0"}

@app.on_event("startup")
async def startup_event():
    """Service startup"""
    print("=" * 60)
    print("[NEXI] Enrollment Service (Week 3) Starting...")
    print(f"[PORT] {os.getenv('SERVICE_PORT', 8005)}")
    print(f"[DOCS] http://localhost:{os.getenv('SERVICE_PORT', 8005)}/docs")
    print(f"[ENCRYPT] {os.getenv('ENABLE_ENCRYPTION', 'true')}")
    print(f"[STORAGE] {os.getenv('ENROLLMENT_DATA_DIR', './enrollment_data')}")
    print("=" * 60)

    # Auto-sync existing enrollments into Central Server without blocking startup.
    try:
        from app.routes.enrollment import enrollment_service

        async def _run_sync():
            result = await enrollment_service.sync_local_enrollments_to_central()
            print(f"[SYNC] Central Server sync: {result}")

        asyncio.create_task(_run_sync())
    except Exception as exc:
        print(f"[SYNC] Central Server sync skipped: {exc}")

if __name__ == "__main__":
    import uvicorn
    from config.ssl_config import get_tls_config
    port = int(os.getenv("SERVICE_PORT", 8005))
    uvicorn.run(app, host="0.0.0.0", port=port, **get_tls_config().uvicorn_kwargs())
