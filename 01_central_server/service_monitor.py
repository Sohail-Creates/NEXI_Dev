from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from resource_manager import ResourceSnapshot, collect_snapshot
from service_connector import ServiceConnector, ServiceStatus, build_connector


@dataclass(frozen=True)
class SystemStatus:
    resources: ResourceSnapshot
    services: Dict[str, ServiceStatus]


class ServiceMonitor:
    def __init__(self, connector: Optional[ServiceConnector] = None) -> None:
        self._connector = connector if connector is not None else build_connector()

    def check_services(self, timeout: float = 2.0) -> Dict[str, ServiceStatus]:
        return self._connector.check_all(timeout=timeout)

    def snapshot(self, path: str = ".", timeout: float = 2.0) -> SystemStatus:
        resources = collect_snapshot(path)
        services = self.check_services(timeout=timeout)
        return SystemStatus(resources=resources, services=services)