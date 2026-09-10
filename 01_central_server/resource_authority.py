"""Single-process camera/microphone lease authority.

A reservation excludes competitors before the holder acknowledges its grant.
Release acknowledges physical closure; an expired lease is never silently freed.
"""

from dataclasses import dataclass, field
from enum import Enum, IntEnum
import threading
import time
import uuid
import logging
import psutil
import socket
import ipaddress

try:
    from shared.focus_mode import FocusModeBroadcast
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from shared.focus_mode import FocusModeBroadcast


class ResourceType(Enum):
    CAMERA = "camera"
    MICROPHONE = "microphone"


class PriorityLevel(IntEnum):
    BACKGROUND = 0
    ACTIVE_CONVERSATION = 1
    ENROLLMENT = 2
    ACTIVE_TEACHME = 3
    VIDEO_CALL = 4
    LOW = BACKGROUND
    MEDIUM = ACTIVE_CONVERSATION
    HIGH = ACTIVE_TEACHME
    CRITICAL = VIDEO_CALL


@dataclass
class ResourceLease:
    resource_type: ResourceType
    service_name: str
    priority: PriorityLevel
    timeout_seconds: float
    lease_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    requested_at: float = field(default_factory=time.time)
    state: str = "queued"
    granted_at: float = 0.0
    holder_pid: int | None = None
    holder_started: float | None = None
    holder_host: str | None = None
    holder_port: int | None = None
    liveness: str = "unknown"
    liveness_checks: int = 0

    @property
    def is_active(self):
        return self.state == "active"


@dataclass
class ResourceState:
    holder: str = None
    request_queue: list = field(default_factory=list)

    @property
    def is_available(self):
        return self.holder is None


class ResourceAuthority:
    def __init__(self, release_ack_timeout=2.0, liveness_interval=1.0):
        self._lock = threading.RLock()
        self.resources = {kind: ResourceState() for kind in ResourceType}
        self.active_leases = {}
        self.release_ack_timeout = release_ack_timeout
        self.liveness_interval = liveness_interval
        self.focus_mode = FocusModeBroadcast()

    def request_resource(self, resource_type, service_name, priority, timeout_seconds=30,
                         holder_pid=None, holder_started=None, holder_host=None, holder_port=None,
                         peer_port=None, authority_port=None):
        if not service_name or timeout_seconds <= 0:
            raise ValueError("Service name and positive timeout are required")
        with self._lock:
            lease = ResourceLease(resource_type, service_name, priority, timeout_seconds)
            # Bind a local PID only when it owns the actual incoming TCP connection.
            # A caller-provided PID alone is not evidence that its camera process died.
            if holder_pid is not None and holder_host and peer_port:
                try:
                    process = psutil.Process(holder_pid)
                    if (ipaddress.ip_address(holder_host).is_loopback
                            and process.create_time() == holder_started
                            and any(connection.laddr.port == peer_port and connection.raddr
                                    and connection.raddr.port == authority_port
                                    for connection in process.net_connections(kind="tcp"))):
                        lease.holder_pid = holder_pid
                        lease.holder_started = holder_started
                except (psutil.Error, ValueError):
                    pass  # Unknown identity never permits death-based reassignment.
            lease.holder_host = holder_host
            lease.holder_port = holder_port
            self.active_leases[lease.lease_id] = lease
            state = self.resources[resource_type]
            state.request_queue.append(lease.lease_id)
            self._grant_next(resource_type)
            holder = self.active_leases.get(state.holder)
            if holder is not lease and holder is not None and priority > holder.priority:
                self.request_revoke(holder.lease_id)
            return lease

    def request_revoke(self, lease_id):
        with self._lock:
            lease = self.active_leases.get(lease_id)
            if lease is None or lease.state not in ("active", "reserved"):
                return False
            lease.state = "revoking"
            timer = threading.Timer(self.release_ack_timeout, self._release_timed_out, args=(lease_id,))
            timer.daemon = True
            timer.start()
            return True

    def _release_timed_out(self, lease_id):
        with self._lock:
            lease = self.active_leases.get(lease_id)
            if lease is None or lease.state not in ("revoking", "suspect"):
                return
        liveness = self._probe_holder(lease)
        with self._lock:
            if self.active_leases.get(lease_id) is not lease:
                return
            lease.liveness = liveness
            lease.liveness_checks += 1
            if liveness == "dead":
                logging.getLogger(__name__).warning("Confirmed holder process exit for lease %s; expiring lease", lease_id)
                self.release_resource(lease_id)
                return
            lease.state = "suspect"
            logging.getLogger(__name__).warning("Lease %s suspect: holder=%s; denying new grants", lease_id, liveness)
            timer = threading.Timer(self.liveness_interval, self._release_timed_out, args=(lease_id,))
            timer.daemon = True
            timer.start()

    @staticmethod
    def _probe_holder(lease):
        if lease.holder_pid is not None:
            try:
                process = psutil.Process(lease.holder_pid)
                if process.create_time() != lease.holder_started or process.status() == psutil.STATUS_ZOMBIE:
                    return "dead"
                if process.is_running():
                    return "alive"
            except psutil.NoSuchProcess:
                return "dead"
            except psutil.Error:
                pass
        if lease.holder_host and lease.holder_port:
            try:
                with socket.create_connection((lease.holder_host, lease.holder_port), timeout=0.25):
                    return "alive"
            except OSError:
                # Refusal can mean the listener closed while a live process retains
                # its camera. Without process-exit proof, it is not safe to regrant.
                return "unreachable"
        return "unknown"

    def _grant_next(self, resource_type):
        state = self.resources[resource_type]
        if state.holder is not None or not state.request_queue:
            return
        state.request_queue.sort(key=lambda key: (-self.active_leases[key].priority,
                                                  self.active_leases[key].requested_at))
        state.holder = state.request_queue.pop(0)
        lease = self.active_leases[state.holder]
        lease.state = "reserved"
        lease.granted_at = time.monotonic()
        timer = threading.Timer(lease.timeout_seconds, self.request_revoke, args=(lease.lease_id,))
        timer.daemon = True
        timer.start()

    def acknowledge_grant(self, lease_id):
        with self._lock:
            lease = self.active_leases.get(lease_id)
            if lease is None or lease.state not in ("reserved", "active"):
                return False
            lease.state = "active"
            if lease.priority == PriorityLevel.ACTIVE_TEACHME:
                self.focus_mode.publish_teachme(lease.lease_id)
            return True

    def release_resource(self, lease_id):
        """Holder calls only after closing the device; queued calls cancel."""
        with self._lock:
            lease = self.active_leases.pop(lease_id, None)
            if lease is None:
                return False
            if lease.priority == PriorityLevel.ACTIVE_TEACHME:
                self.focus_mode.clear_teachme(lease.lease_id)
            state = self.resources[lease.resource_type]
            if lease_id in state.request_queue:
                state.request_queue.remove(lease_id)
            if state.holder == lease_id:
                state.holder = None
            self._grant_next(lease.resource_type)
            return True

    def check_lease_status(self, lease_id):
        with self._lock:
            lease = self.active_leases.get(lease_id)
            if lease is None:
                return None
            return {"lease_id": lease_id, "service_name": lease.service_name,
                    "resource_type": lease.resource_type.value, "state": lease.state,
                    "is_active": lease.is_active, "priority": lease.priority.name,
                    "process_identity_verified": lease.holder_pid is not None,
                    "liveness": lease.liveness, "liveness_checks": lease.liveness_checks}

    def get_all_resources_status(self):
        with self._lock:
            return {kind.value: {"is_available": state.is_available,
                                "holder": state.holder,
                                "queue": list(state.request_queue)}
                    for kind, state in self.resources.items()}

    def get_focus_mode_status(self):
        return self.focus_mode.snapshot()

    def subscribe_focus_mode(self, callback):
        self.focus_mode.subscribe(callback)


_authority = ResourceAuthority()


def get_resource_authority():
    return _authority
