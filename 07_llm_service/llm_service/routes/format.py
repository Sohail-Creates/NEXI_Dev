"""Import-compatible formatting route; formatting behavior is not implemented."""

from fastapi import APIRouter, HTTPException


def create_format_router(model_loader):
    """Preserve the existing factory contract without restoring local inference."""
    router = APIRouter(prefix="/api/v1")

    @router.post("/format")
    async def format_response():
        raise HTTPException(status_code=501, detail="Formatting is not implemented")

    return router
