"""
Hardware Resource Management API Routes

REST endpoints for services to request, release, and monitor hardware resources.
All hardware access (camera, microphone) goes through these endpoints.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import logging

from hardware_resource_manager import (
    get_hardware_resource_manager,
    ResourceType,
    PriorityLevel,
    ResourceLease
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/resources", tags=["Hardware Resources"])

resource_manager = get_hardware_resource_manager()


@router.post("/request")
async def request_resource(
    resource_type: str = Query(..., description="Type of resource: camera, microphone"),
    service_name: str = Query(..., description="Name of requesting service"),
    priority: str = Query("MEDIUM", description="Priority: CRITICAL, HIGH, MEDIUM, LOW"),
    timeout_seconds: int = Query(30, description="Maximum time to hold resource")
) -> dict:
    """
    Request access to a hardware resource.
    
    Returns immediately with lease_id if available, or queued status if busy.
    Higher priorities may preempt lower priority tasks.
    """
    try:
        # Validate inputs
        try:
            res_type = ResourceType[resource_type.upper()]
        except KeyError:
            raise ValueError(f"Invalid resource type: {resource_type}. Must be: camera, microphone")
        
        try:
            priority_level = PriorityLevel[priority.upper()]
        except KeyError:
            raise ValueError(f"Invalid priority: {priority}. Must be: CRITICAL, HIGH, MEDIUM, LOW")
        
        # Request resource
        lease = resource_manager.request_resource(
            resource_type=res_type,
            service_name=service_name,
            priority=priority_level,
            timeout_seconds=timeout_seconds
        )
        
        return {
            "success": True,
            "lease_id": lease.lease_id,
            "resource_type": lease.resource_type.value,
            "service_name": lease.service_name,
            "granted": lease.is_active,
            "timestamp": lease.requested_at,
            "message": (
                "Resource granted" if lease.is_active
                else f"Request queued (position {len(resource_manager.resources[res_type].request_queue)})"
            )
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error requesting resource: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/release/{lease_id}")
async def release_resource(lease_id: str) -> dict:
    """
    Release a hardware resource lease.
    
    After release, the next queued request (if any) is automatically granted.
    """
    try:
        success = resource_manager.release_resource(lease_id)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Lease not found: {lease_id}")
        
        return {
            "success": True,
            "lease_id": lease_id,
            "message": "Resource released successfully"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error releasing resource: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{lease_id}")
async def get_lease_status(lease_id: str) -> dict:
    """
    Check the status of a resource lease.
    
    Returns current status (active, expired, queued, etc.)
    """
    try:
        status = resource_manager.check_lease_status(lease_id)
        
        if status is None:
            raise HTTPException(status_code=404, detail=f"Lease not found: {lease_id}")
        
        return {
            "success": True,
            "lease": status
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking lease status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_all_resources_status() -> dict:
    """
    Get comprehensive status of all hardware resources.
    
    Shows:
    - Current holder of each resource
    - Queue of waiting requests
    - Availability status
    - Time remaining for active leases
    """
    try:
        status = resource_manager.get_all_resources_status()
        
        return {
            "success": True,
            "timestamp": __import__("time").time(),
            "resources": status
        }
    
    except Exception as e:
        logger.error(f"Error getting resource status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def resource_manager_health() -> dict:
    """
    Health check for resource manager.
    
    Returns True if resource manager is operational.
    """
    try:
        # Try to get status - if it works, manager is healthy
        status = resource_manager.get_all_resources_status()
        
        return {
            "success": True,
            "status": "healthy",
            "active_leases": len(resource_manager.active_leases),
            "resources_available": {
                resource_type.value: resource_state.is_available
                for resource_type, resource_state in resource_manager.resources.items()
            }
        }
    
    except Exception as e:
        logger.error(f"Resource manager health check failed: {e}")
        return {
            "success": False,
            "status": "unhealthy",
            "error": str(e)
        }
