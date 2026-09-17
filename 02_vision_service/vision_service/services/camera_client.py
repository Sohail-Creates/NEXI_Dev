"""Fail-closed client of Central's acknowledged resource leases."""
import logging
import requests
import os
import psutil
from typing import Optional
from shared.security import internal_service_headers
from config.ssl_config import client_verify

logger = logging.getLogger(__name__)

class CameraResourceClient:
    def __init__(self, central_server_url="https://localhost:8000", service_name="vision_service"):
        self.central_server_url = central_server_url.rstrip("/")
        self.service_name = service_name
        self.camera_granted = False
        self.lease_id = None

    def request_camera(self, timeout=5, max_retries=3):
        if self.lease_id is not None:
            # A failed previous release must be acknowledged before a new request.
            if not self.release_camera(timeout):
                return False
        try:
            response = requests.post(self.central_server_url + "/resources/request",
                params={"resource_type": "camera", "service_name": self.service_name,
                        "priority": "BACKGROUND", "timeout_seconds": timeout,
                        "holder_pid": os.getpid(), "holder_started": psutil.Process().create_time(),
                        "holder_port": int(os.getenv("VISION_PORT", "8001"))},
                headers=internal_service_headers(), timeout=timeout, verify=client_verify(self.central_server_url))
            response.raise_for_status()
            data = response.json()
            self.lease_id = data.get("lease_id")
            if data.get("state") != "reserved" or not self.lease_id:
                self.release_camera(timeout)
                return False
            response = requests.post(self.central_server_url + "/resources/acknowledge/" + self.lease_id,
                                     headers=internal_service_headers(), timeout=timeout, verify=client_verify(self.central_server_url))
            response.raise_for_status()
            data = response.json()
            self.camera_granted = data.get("granted") is True and data.get("lease_id") == self.lease_id
            if not self.camera_granted:
                self.release_camera(timeout)
            return self.camera_granted
        except (requests.RequestException, ValueError, TypeError) as exc:
            logger.warning("Camera authority unavailable or denied grant: %s", exc)
            self.camera_granted = False
            if self.lease_id is not None and not self.release_camera(timeout):
                logger.error(
                    "Failed to release provisional camera lease %s after grant failure",
                    self.lease_id,
                )
            return False

    def release_camera(self, timeout=5, lease_id=None, forced=False):
        lease_id = lease_id or self.lease_id
        if lease_id == self.lease_id:
            self.camera_granted = False
        if lease_id is None:
            return True
        try:
            response = requests.post(self.central_server_url + "/resources/release/" + lease_id,
                                     params={"forced": forced}, headers=internal_service_headers(), timeout=timeout, verify=client_verify(self.central_server_url))
            if response.status_code == 404 or (response.status_code == 200 and response.json().get("success") is True):
                if self.lease_id == lease_id:
                    self.lease_id = None
                return True
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Camera release acknowledgement failed: %s", exc)
        return False

    def lease_active(self, lease_id, timeout=1):
        try:
            response = requests.get(self.central_server_url + "/resources/status/" + lease_id,
                                    headers=internal_service_headers(), timeout=timeout, verify=client_verify(self.central_server_url))
            return response.status_code == 200 and response.json().get("lease", {}).get("state") == "active"
        except (requests.RequestException, ValueError):
            return False

    def validate_delegated_video_lease(self, lease_id, timeout=2):
        """Validate, without adopting, Central's active VIDEO_CALL camera lease."""
        try:
            response = requests.get(
                self.central_server_url + "/resources/status/" + lease_id,
                headers=internal_service_headers(),
                timeout=timeout, verify=client_verify(self.central_server_url),
            )
            if response.status_code != 200:
                return False
            lease = response.json().get("lease", {})
            return (
                lease.get("lease_id") == lease_id
                and lease.get("resource_type") == "camera"
                and lease.get("priority") == "VIDEO_CALL"
                and lease.get("state") == "active"
                and str(lease.get("service_name", "")).startswith("video_call:")
            )
        except (requests.RequestException, ValueError, TypeError):
            return False


# Global instance
_camera_client: Optional[CameraResourceClient] = None


def initialize_camera_client(central_server_url: str = "https://localhost:8000",
                              service_name: str = "vision_service") -> CameraResourceClient:
    """Initialize the global camera client instance"""
    global _camera_client
    _camera_client = CameraResourceClient(central_server_url, service_name)
    return _camera_client


def get_camera_client(central_server_url: str = "https://localhost:8000",
                      service_name: str = "vision_service") -> CameraResourceClient:
    """Get or create global camera client instance"""
    global _camera_client
    if _camera_client is None:
        _camera_client = CameraResourceClient(central_server_url, service_name)
    return _camera_client

