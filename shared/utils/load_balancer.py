"""
Load Balancer - Support for multiple service instances.

FEATURE #9: LOAD BALANCING

Problem:
- Single service instance = single point of failure
- Can't scale horizontally

Solution:
- Multiple instances per service
- Health-based routing
- Round-robin load distribution
- Automatic failover

Architecture:
- Service registry: Which instances are healthy?
- Health checker: Periodic status checks
- Load balancer: Choose healthiest instance
- Fallback: Auto-failover to backup instances

Usage:
    lb = LoadBalancer(service_name="vision")
    lb.add_instance("http://vision-1:8001")
    lb.add_instance("http://vision-2:8001")
    
    # Get a healthy instance
    url = lb.get_healthy_instance()
    # Make request to url...
    
    # Mark as failed
    lb.mark_instance_failed(url)
"""

import asyncio
import aiohttp
import time
from enum import Enum
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import logging
import random


logger = logging.getLogger("LoadBalancer")


class InstanceHealth(Enum):
    """Health status of a service instance."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ServiceInstance:
    """Represents a single service instance."""
    url: str
    health_status: InstanceHealth = InstanceHealth.UNKNOWN
    last_check_time: float = field(default_factory=time.time)
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    response_time_ms: float = 0.0
    
    def mark_success(self, response_time_ms: float = 0.0):
        """Record successful request."""
        self.consecutive_failures = 0
        self.consecutive_successes += 1
        self.response_time_ms = response_time_ms
        self.last_check_time = time.time()
        
        # Healthy after 2 consecutive successes
        if self.consecutive_successes >= 2:
            self.health_status = InstanceHealth.HEALTHY
    
    def mark_failure(self, response_time_ms: float = 0.0):
        """Record failed request."""
        self.consecutive_successes = 0
        self.consecutive_failures += 1
        self.response_time_ms = response_time_ms
        self.last_check_time = time.time()
        
        # Unhealthy after 3 consecutive failures
        if self.consecutive_failures >= 3:
            self.health_status = InstanceHealth.UNHEALTHY
        elif self.consecutive_failures >= 1:
            self.health_status = InstanceHealth.DEGRADED
    
    def get_score(self) -> float:
        """
        Calculate score for selection (lower is better).
        Considers health, response time, and failure count.
        """
        if self.health_status == InstanceHealth.UNHEALTHY:
            return float('inf')
        
        if self.health_status == InstanceHealth.HEALTHY:
            return self.response_time_ms
        
        if self.health_status == InstanceHealth.DEGRADED:
            return self.response_time_ms + 100
        
        return self.response_time_ms + 200  # Unknown status


class LoadBalancer:
    """
    Load balancer for service instances.
    """
    
    def __init__(
        self,
        service_name: str,
        health_check_interval: float = 10.0,
        health_check_timeout: float = 2.0
    ):
        """
        Initialize load balancer.
        
        Args:
            service_name: Name of service (e.g., "vision", "audio")
            health_check_interval: How often to check health (seconds)
            health_check_timeout: Timeout for health check (seconds)
        """
        self.service_name = service_name
        self.health_check_interval = health_check_interval
        self.health_check_timeout = health_check_timeout
        self.instances: Dict[str, ServiceInstance] = {}
        self.last_health_check: float = 0.0
        self.health_check_running: bool = False
        
        logger.info(f"LoadBalancer created for '{service_name}'")
    
    def add_instance(self, url: str) -> bool:
        """
        Add service instance to balancer.
        
        Args:
            url: Instance URL (e.g., "http://localhost:8001")
        
        Returns:
            True if added successfully
        """
        if url in self.instances:
            logger.warning(f"Instance already registered: {url}")
            return False
        
        self.instances[url] = ServiceInstance(url=url)
        logger.info(f"Added instance to '{self.service_name}': {url}")
        return True
    
    def remove_instance(self, url: str) -> bool:
        """
        Remove service instance from balancer.
        
        Args:
            url: Instance URL
        
        Returns:
            True if removed successfully
        """
        if url not in self.instances:
            logger.warning(f"Instance not found: {url}")
            return False
        
        del self.instances[url]
        logger.info(f"Removed instance from '{self.service_name}': {url}")
        return True
    
    def get_healthy_instance(self) -> Optional[str]:
        """
        Get URL of healthiest available instance.
        Uses lowest-score instance (best health + lowest latency).
        
        Returns:
            Instance URL or None if no healthy instances
        """
        if not self.instances:
            logger.error(f"No instances registered for '{self.service_name}'")
            return None
        
        # Get healthy instances first
        healthy = [
            (url, inst) for url, inst in self.instances.items()
            if inst.health_status in [InstanceHealth.HEALTHY, InstanceHealth.DEGRADED]
        ]
        
        # If no healthy instances, try any
        if not healthy:
            healthy = list(self.instances.items())
        
        if not healthy:
            return None
        
        # Select instance with lowest score (best health + latency)
        best_url, best_inst = min(healthy, key=lambda x: x[1].get_score())
        
        logger.debug(f"Selected instance: {best_url} (health={best_inst.health_status})")
        return best_url
    
    def get_random_instance(self) -> Optional[str]:
        """
        Get random healthy instance (for round-robin style).
        
        Returns:
            Instance URL or None
        """
        if not self.instances:
            return None
        
        # Prefer healthy instances
        healthy = [
            url for url, inst in self.instances.items()
            if inst.health_status in [InstanceHealth.HEALTHY, InstanceHealth.DEGRADED]
        ]
        
        if healthy:
            return random.choice(healthy)
        
        # Fall back to any
        return random.choice(list(self.instances.keys()))
    
    def mark_instance_success(self, url: str, response_time_ms: float = 0.0):
        """Mark instance as having successful request."""
        if url in self.instances:
            self.instances[url].mark_success(response_time_ms)
            logger.debug(f"Instance success: {url}")
    
    def mark_instance_failure(self, url: str, response_time_ms: float = 0.0):
        """Mark instance as having failed request."""
        if url in self.instances:
            self.instances[url].mark_failure(response_time_ms)
            logger.warning(f"Instance failure: {url}")
    
    async def perform_health_check(self, session: aiohttp.ClientSession) -> Dict[str, InstanceHealth]:
        """
        Perform health check on all instances.
        
        Args:
            session: aiohttp ClientSession for HTTP requests
        
        Returns:
            Dictionary of health status per instance
        """
        results = {}
        
        for url, instance in self.instances.items():
            try:
                health_url = f"{url}/health"
                
                async with session.get(
                    health_url,
                    timeout=aiohttp.ClientTimeout(total=self.health_check_timeout)
                ) as resp:
                    if resp.status == 200:
                        instance.mark_success()
                        results[url] = InstanceHealth.HEALTHY
                        logger.debug(f"Health check OK: {url}")
                    else:
                        instance.mark_failure()
                        results[url] = InstanceHealth.UNHEALTHY
                        logger.warning(f"Health check failed {url}: {resp.status}")
            
            except asyncio.TimeoutError:
                instance.mark_failure()
                results[url] = InstanceHealth.UNHEALTHY
                logger.warning(f"Health check timeout: {url}")
            
            except Exception as e:
                instance.mark_failure()
                results[url] = InstanceHealth.UNHEALTHY
                logger.warning(f"Health check error {url}: {e}")
        
        self.last_health_check = time.time()
        logger.info(f"Health check completed for '{self.service_name}': {results}")
        return results
    
    def get_status(self) -> Dict[str, any]:
        """Get load balancer status."""
        return {
            'service_name': self.service_name,
            'total_instances': len(self.instances),
            'healthy_instances': sum(
                1 for inst in self.instances.values()
                if inst.health_status == InstanceHealth.HEALTHY
            ),
            'degraded_instances': sum(
                1 for inst in self.instances.values()
                if inst.health_status == InstanceHealth.DEGRADED
            ),
            'unhealthy_instances': sum(
                1 for inst in self.instances.values()
                if inst.health_status == InstanceHealth.UNHEALTHY
            ),
            'instances': [
                {
                    'url': inst.url,
                    'health_status': inst.health_status.value,
                    'response_time_ms': inst.response_time_ms,
                    'consecutive_failures': inst.consecutive_failures,
                    'consecutive_successes': inst.consecutive_successes
                }
                for inst in self.instances.values()
            ]
        }


class LoadBalancerManager:
    """Manager for multiple load balancers (one per service)."""
    
    def __init__(self):
        """Initialize load balancer manager."""
        self.balancers: Dict[str, LoadBalancer] = {}
        logger.info("LoadBalancerManager initialized")
    
    def get_or_create_balancer(
        self,
        service_name: str,
        health_check_interval: float = 10.0
    ) -> LoadBalancer:
        """Get or create load balancer for service."""
        if service_name not in self.balancers:
            self.balancers[service_name] = LoadBalancer(
                service_name,
                health_check_interval=health_check_interval
            )
        return self.balancers[service_name]
    
    def get_balancer(self, service_name: str) -> Optional[LoadBalancer]:
        """Get load balancer for service."""
        return self.balancers.get(service_name)
    
    def get_all_status(self) -> Dict[str, any]:
        """Get status of all load balancers."""
        return {
            name: balancer.get_status()
            for name, balancer in self.balancers.items()
        }


# Global load balancer manager instance
_lb_manager: Optional[LoadBalancerManager] = None


def get_load_balancer_manager() -> LoadBalancerManager:
    """Get global load balancer manager (lazy singleton)."""
    global _lb_manager
    if _lb_manager is None:
        _lb_manager = LoadBalancerManager()
    return _lb_manager


# Version info
__version__ = "1.0.0"
__load_balancer_feature__ = "FEATURE #9: Load Balancing"
