"""
Hardware Resource Manager for NEXI System

Manages centralized access to hardware devices (camera, microphone)
to prevent resource conflicts, deadlocks, and ensure proper allocation.

Features:
- Request/Grant/Release cycle
- Priority-based queue (CRITICAL > HIGH > MEDIUM > LOW)
- Timeout auto-release (30 seconds default)
- Preemption for higher priority tasks
- Deadlock prevention
- Resource monitoring and logging
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Set
from enum import Enum
import time
import uuid
import logging
from datetime import datetime
import threading

logger = logging.getLogger(__name__)


class ResourceType(Enum):
    """Types of hardware resources"""
    CAMERA = "camera"
    MICROPHONE = "microphone"


class PriorityLevel(Enum):
    """Priority levels for resource requests (higher = more urgent)"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class ResourceLease:
    """A lease granted for resource usage"""
    lease_id: str
    resource_type: ResourceType
    service_name: str
    priority: PriorityLevel
    requested_at: float
    granted_at: Optional[float] = None
    timeout_seconds: int = 30
    is_active: bool = False
    
    def is_expired(self) -> bool:
        """Check if lease has exceeded timeout"""
        if not self.is_active or self.granted_at is None:
            return False
        return (time.time() - self.granted_at) > self.timeout_seconds
    
    def time_remaining(self) -> float:
        """Get remaining time before expiration (in seconds)"""
        if not self.is_active or self.granted_at is None:
            return self.timeout_seconds
        elapsed = time.time() - self.granted_at
        return max(0, self.timeout_seconds - elapsed)


@dataclass
class ResourceRequest:
    """A request for resource access"""
    request_id: str
    resource_type: ResourceType
    service_name: str
    priority: PriorityLevel
    requested_at: float
    lease: Optional[ResourceLease] = None
    
    def __lt__(self, other: ResourceRequest) -> bool:
        """Support sorting by priority (higher priority first)"""
        if self.priority.value != other.priority.value:
            return self.priority.value > other.priority.value
        return self.requested_at < other.requested_at


class ResourceState:
    """State of a single resource"""
    
    def __init__(self, resource_type: ResourceType):
        self.resource_type = resource_type
        self.is_available = True
        self.current_lease: Optional[ResourceLease] = None
        self.request_queue: List[ResourceRequest] = []
        self.history: List[Dict] = []
    
    def get_status(self) -> Dict:
        """Get current status of resource"""
        return {
            "resource_type": self.resource_type.value,
            "available": self.is_available,
            "held_by": self.current_lease.service_name if self.current_lease else None,
            "held_since": self.current_lease.granted_at if self.current_lease else None,
            "time_remaining": self.current_lease.time_remaining() if self.current_lease else None,
            "queue_length": len(self.request_queue),
            "queue": [
                {
                    "service": req.service_name,
                    "priority": req.priority.name,
                    "requested_at": datetime.fromtimestamp(req.requested_at).isoformat()
                }
                for req in sorted(self.request_queue)
            ]
        }


class HardwareResourceManager:
    """
    Centralized manager for hardware resource allocation.
    
    Handles all camera and microphone access requests from services.
    Prevents conflicts, deadlocks, and ensures fair/priority-based allocation.
    """
    
    def __init__(self):
        self.resources: Dict[ResourceType, ResourceState] = {
            ResourceType.CAMERA: ResourceState(ResourceType.CAMERA),
            ResourceType.MICROPHONE: ResourceState(ResourceType.MICROPHONE),
        }
        self.active_leases: Dict[str, ResourceLease] = {}
        self.lock = threading.RLock()
        self.timeout_check_interval = 5  # Check every 5 seconds
        self._start_timeout_monitor()
        logger.info("Hardware Resource Manager initialized")
    
    def request_resource(
        self,
        resource_type: ResourceType,
        service_name: str,
        priority: PriorityLevel = PriorityLevel.MEDIUM,
        timeout_seconds: int = 30
    ) -> ResourceLease:
        """
        Request access to a hardware resource.
        
        Args:
            resource_type: Type of resource (camera, microphone)
            service_name: Name of service requesting resource
            priority: Priority level of request
            timeout_seconds: Maximum time to hold resource (default 30s)
        
        Returns:
            ResourceLease with lease_id and status
        """
        with self.lock:
            resource_state = self.resources[resource_type]
            
            # Create lease and request
            lease_id = str(uuid.uuid4())[:8]
            lease = ResourceLease(
                lease_id=lease_id,
                resource_type=resource_type,
                service_name=service_name,
                priority=priority,
                requested_at=time.time(),
                timeout_seconds=timeout_seconds
            )
            
            request = ResourceRequest(
                request_id=str(uuid.uuid4())[:8],
                resource_type=resource_type,
                service_name=service_name,
                priority=priority,
                requested_at=time.time()
            )
            request.lease = lease
            
            # Try to grant immediately if available
            if resource_state.is_available:
                self._grant_lease(lease, resource_state)
                logger.info(
                    f"GRANTED: {service_name} -> {resource_type.value} "
                    f"(priority={priority.name}, lease_id={lease_id})"
                )
                return lease
            
            # Resource busy - check if we should preempt lower priority
            if (resource_state.current_lease and 
                resource_state.current_lease.priority.value < priority.value):
                
                preempted_service = resource_state.current_lease.service_name
                logger.warning(
                    f"PREEMPTING: {preempted_service} (priority={resource_state.current_lease.priority.name}) "
                    f"for {service_name} (priority={priority.name})"
                )
                
                old_lease = resource_state.current_lease
                self._revoke_lease(old_lease, "preempted_by_higher_priority")
                
                self._grant_lease(lease, resource_state)
                logger.info(f"GRANTED (after preemption): {service_name} -> {resource_type.value}")
                return lease
            
            # Add to queue
            resource_state.request_queue.append(request)
            resource_state.request_queue.sort()
            
            logger.info(
                f"QUEUED: {service_name} -> {resource_type.value} "
                f"(priority={priority.name}, queue_position={len(resource_state.request_queue)})"
            )
            
            self.active_leases[lease_id] = lease
            return lease
    
    def release_resource(self, lease_id: str) -> bool:
        """
        Release a resource lease.
        
        Args:
            lease_id: The lease ID to release
        
        Returns:
            True if successful, False if lease not found
        """
        with self.lock:
            if lease_id not in self.active_leases:
                logger.warning(f"RELEASE FAILED: Lease {lease_id} not found")
                return False
            
            lease = self.active_leases[lease_id]
            resource_state = self.resources[lease.resource_type]
            
            if resource_state.current_lease and resource_state.current_lease.lease_id == lease_id:
                service_name = lease.service_name
                resource_type = lease.resource_type.value
                
                self._revoke_lease(lease, "released_by_service")
                logger.info(f"RELEASED: {service_name} -> {resource_type}")
                
                # Grant to next in queue
                if resource_state.request_queue:
                    next_request = resource_state.request_queue.pop(0)
                    next_lease = next_request.lease
                    
                    self._grant_lease(next_lease, resource_state)
                    logger.info(
                        f"GRANTED (from queue): {next_lease.service_name} -> {resource_type} "
                        f"(was #{len(resource_state.request_queue) + 1} in queue)"
                    )
                    return True
                
                return True
            else:
                logger.warning(f"RELEASE FAILED: Lease {lease_id} is not currently active")
                return False
    
    def check_lease_status(self, lease_id: str) -> Optional[Dict]:
        """
        Check the status of a lease.
        
        Args:
            lease_id: The lease ID to check
        
        Returns:
            Dictionary with lease status or None if not found
        """
        with self.lock:
            if lease_id not in self.active_leases:
                return None
            
            lease = self.active_leases[lease_id]
            return {
                "lease_id": lease_id,
                "service": lease.service_name,
                "resource": lease.resource_type.value,
                "priority": lease.priority.name,
                "is_active": lease.is_active,
                "time_remaining": lease.time_remaining(),
                "is_expired": lease.is_expired()
            }
    
    def get_all_resources_status(self) -> Dict:
        """Get status of all resources and queues"""
        with self.lock:
            return {
                resource_type.value: resource_state.get_status()
                for resource_type, resource_state in self.resources.items()
            }
    
    def _grant_lease(self, lease: ResourceLease, resource_state: ResourceState):
        """Grant a lease (internal use)"""
        lease.is_active = True
        lease.granted_at = time.time()
        resource_state.is_available = False
        resource_state.current_lease = lease
        self.active_leases[lease.lease_id] = lease
        
        resource_state.history.append({
            "action": "granted",
            "service": lease.service_name,
            "timestamp": datetime.fromtimestamp(lease.granted_at).isoformat(),
            "priority": lease.priority.name
        })
    
    def _revoke_lease(self, lease: ResourceLease, reason: str):
        """Revoke a lease (internal use)"""
        resource_state = self.resources[lease.resource_type]
        
        lease.is_active = False
        resource_state.is_available = True
        resource_state.current_lease = None
        
        if lease.lease_id in self.active_leases:
            del self.active_leases[lease.lease_id]
        
        resource_state.history.append({
            "action": "revoked",
            "service": lease.service_name,
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        })
    
    def _start_timeout_monitor(self):
        """Start background thread to monitor and auto-release timed-out leases"""
        def monitor():
            while True:
                try:
                    time.sleep(self.timeout_check_interval)
                    self._check_timeouts()
                except Exception as e:
                    logger.error(f"Error in timeout monitor: {e}")
        
        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()
    
    def _check_timeouts(self):
        """Check for expired leases and auto-release them"""
        with self.lock:
            for resource_type, resource_state in self.resources.items():
                if resource_state.current_lease and resource_state.current_lease.is_expired():
                    expired_lease = resource_state.current_lease
                    logger.warning(
                        f"TIMEOUT: {expired_lease.service_name} exceeded "
                        f"{expired_lease.timeout_seconds}s holding {resource_type.value}. "
                        f"Force-releasing..."
                    )
                    self._revoke_lease(expired_lease, "timeout_exceeded")
                    
                    # Grant to next in queue
                    if resource_state.request_queue:
                        next_request = resource_state.request_queue.pop(0)
                        self._grant_lease(next_request.lease, resource_state)


# Global instance
_resource_manager: Optional[HardwareResourceManager] = None


def get_hardware_resource_manager() -> HardwareResourceManager:
    """Get or create the global resource manager instance"""
    global _resource_manager
    if _resource_manager is None:
        _resource_manager = HardwareResourceManager()
    return _resource_manager
