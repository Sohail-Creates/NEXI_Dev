"""Compatibility camera routes backed by the single resource authority."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from resource_authority import get_resource_authority, ResourceType, PriorityLevel

router = APIRouter(prefix="/camera", tags=["camera"])

class CameraRequest(BaseModel):
    service_name: str
    timeout: int = 30
    lease_id: str | None = None

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
