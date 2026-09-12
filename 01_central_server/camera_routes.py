"""Camera and video-call routes backed by the single resource authority."""
import asyncio
import os
import time

import httpx
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from resource_authority import get_resource_authority, ResourceType, PriorityLevel
from shared.security import internal_service_headers
from config.ssl_config import client_verify

router = APIRouter(prefix="/camera", tags=["camera"])

class CameraRequest(BaseModel):
    service_name: str
    timeout: int = 30
    lease_id: str | None = None


class CallRequest(BaseModel):
    call_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")


CALL_PREEMPTION_TIMEOUT_SECONDS = float(os.getenv("CALL_PREEMPTION_TIMEOUT_SECONDS", "5"))
CALL_LEASE_TIMEOUT_SECONDS = float(os.getenv("CALL_LEASE_TIMEOUT_SECONDS", "3600"))
VISION_SERVICE_URL = os.getenv("VISION_SERVICE_URL", "https://localhost:8001").rstrip("/")

@router.post("/request")
def request_camera(request: CameraRequest):
    lease = get_resource_authority().request_resource(
        ResourceType.CAMERA, request.service_name, PriorityLevel.BACKGROUND, request.timeout)
    if lease.state != "reserved":
        get_resource_authority().release_resource(lease.lease_id)
        return {"status": "denied", "message": "Camera is held by another lease"}
    return {"status": "reserved", "lease_id": lease.lease_id,
            "message": "Acknowledge the lease before opening the camera"}

@router.post("/release")
def release_camera(request: CameraRequest):
    authority = get_resource_authority()
    lease = authority.check_lease_status(request.lease_id)
    if not lease or lease["service_name"] != request.service_name:
        raise HTTPException(status_code=409, detail="Matching lease_id is required")
    authority.release_resource(request.lease_id)
    return {"status": "released", "message": "Physical release acknowledged"}

@router.get("/status")
def get_camera_status():
    state = get_resource_authority().get_all_resources_status()["camera"]
    return {"status": "available" if state["is_available"] else "in_use", **state}

@router.post("/force-release")
def force_release_camera():
    raise HTTPException(status_code=409, detail="Physical closure must be acknowledged before release")


call_router = APIRouter(prefix="/calls", tags=["video-call"])


@call_router.post("/start")
async def start_call(request: CallRequest):
    authority = get_resource_authority()
    current = authority.get_call_status()
    if current["state"] == "CALL_ACTIVE":
        raise HTTPException(status_code=409, detail="A video call is already active")

    lease = authority.request_resource(
        ResourceType.CAMERA,
        f"video_call:{request.call_id}",
        PriorityLevel.VIDEO_CALL,
        CALL_LEASE_TIMEOUT_SECONDS,
    )
    deadline = time.monotonic() + CALL_PREEMPTION_TIMEOUT_SECONDS
    while lease.state == "queued" and time.monotonic() < deadline:
        await asyncio.sleep(0.05)

    if lease.state != "reserved":
        authority.release_resource(lease.lease_id)
        raise HTTPException(
            status_code=409,
            detail={"code": "RESOURCE_PREEMPTION_TIMEOUT", "message": "Camera holder did not acknowledge release"},
        )
    if not authority.acknowledge_grant(lease.lease_id):
        authority.release_resource(lease.lease_id)
        raise HTTPException(status_code=409, detail="Video-call camera grant was not acknowledged")
    if not authority.activate_call(request.call_id, lease.lease_id):
        authority.release_resource(lease.lease_id)
        raise HTTPException(status_code=409, detail="Unable to enter CALL_ACTIVE state")
    return {"state": "CALL_ACTIVE", "call_id": request.call_id, "lease_id": lease.lease_id}


@call_router.post("/end")
async def end_call(request: CallRequest):
    authority = get_resource_authority()
    current = authority.get_call_status()
    if current["state"] != "CALL_ACTIVE" or current["call_id"] != request.call_id:
        raise HTTPException(status_code=404, detail="Matching active call not found")
    lease_id = current["lease_id"]
    if not authority.release_resource(lease_id):
        raise HTTPException(status_code=409, detail="Active call lease could not be released")
    return {"state": "IDLE", "call_id": request.call_id, "released_lease_id": lease_id}


@call_router.get("/status")
async def get_call_status():
    return get_resource_authority().get_call_status()


async def _fetch_vision_frame(lease_id: str) -> tuple[bytes, str]:
    async with httpx.AsyncClient(timeout=10.0, headers=internal_service_headers(), verify=client_verify(VISION_SERVICE_URL)) as client:
        response = await client.get(f"{VISION_SERVICE_URL}/api/v1/frame", params={"lease_id": lease_id})
    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail={"code": "VISION_FRAME_FAILED", "message": "Vision could not capture a call frame"},
        )
    return response.content, response.headers.get("content-type", "image/jpeg")


@call_router.get("/screenshot", responses={200: {"content": {"image/jpeg": {}}}})
async def capture_call_screenshot():
    authority = get_resource_authority()
    current = authority.get_call_status()
    if current["state"] != "CALL_ACTIVE" or not current["lease_id"]:
        raise HTTPException(status_code=409, detail="Screenshot requires an active video call")
    frame, content_type = await _fetch_vision_frame(current["lease_id"])
    return Response(
        content=frame,
        media_type=content_type,
        headers={"X-NEXI-Call-ID": current["call_id"]},
    )
