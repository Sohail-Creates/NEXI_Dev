"""
Bulkhead Isolation - Separate thread pools for resilience.

FEATURE #6: BULKHEAD ISOLATION

Prevents one failing service from exhausting resources and impacting others.
Implements thread pool isolation:
- Vision Service: Separate thread pool  
- Audio Service: Separate thread pool
- Enrollment Service: Separate thread pool

Architecture:
- Each service gets dedicated thread pool
- Max workers per pool: configurable
- Prevents thundering herd

Example:
    bulkhead = BulkheadManager(max_workers_per_service=3)
    bulkhead.register_service("vision", max_workers=3)
    
    # Queue work to Vision Service pool
    future = bulkhead.submit_to_service("vision", some_function, arg1, arg2)
    result = future.result(timeout=30)
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError, Future
from typing import Dict, Optional, Any, Callable
from contextlib import contextmanager
import logging


logger = logging.getLogger("Bulkhead")


class BulkheadService:
    """
    Represents an isolated service with its own thread pool.
    """
    
    def __init__(self, name: str, max_workers: int = 3):
        """
        Initialize bulkhead for a service.
        
        Args:
            name: Service name (e.g., "vision", "audio")
            max_workers: Maximum concurrent workers for this service
        """
        self.name = name
        self.max_workers = max_workers
        self.executor: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=f"bulkhead-{name}"
        )
        self.active_tasks: Dict[str, Dict[str, Any]] = {}
        self.completed_tasks: int = 0
        self.failed_tasks: int = 0
        self.lock = threading.Lock()
        
        logger.info(f"Bulkhead '{name}' initialized with {max_workers} workers")
    
    def submit(self, func: Callable, *args, **kwargs) -> tuple[str, Future]:
        """
        Submit work to this service's thread pool.
        
        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
        
        Returns:
            (task_id, future) tuple for tracking
        """
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        
        def tracked_task():
            """Wrapper to track task execution."""
            try:
                with self.lock:
                    self.active_tasks[task_id] = {
                        'status': 'running',
                        'function': func.__name__
                    }
                
                result = func(*args, **kwargs)
                
                with self.lock:
                    self.completed_tasks += 1
                    self.active_tasks.pop(task_id, None)
                
                return result
            
            except Exception as e:
                with self.lock:
                    self.failed_tasks += 1
                    self.active_tasks.pop(task_id, None)
                raise
        
        future = self.executor.submit(tracked_task)
        
        logger.debug(f"Bulkhead '{self.name}' submitted task {task_id}")
        return task_id, future
    
    def get_status(self) -> Dict[str, Any]:
        """Get bulkhead statistics."""
        with self.lock:
            return {
                'name': self.name,
                'max_workers': self.max_workers,
                'active_tasks': len(self.active_tasks),
                'completed_tasks': self.completed_tasks,
                'failed_tasks': self.failed_tasks,
                'active_task_names': [
                    task['function'] for task in self.active_tasks.values()
                ]
            }
    
    def shutdown(self, wait: bool = True):
        """Shutdown the thread pool."""
        logger.info(f"Shutting down bulkhead '{self.name}'")
        self.executor.shutdown(wait=wait)


class BulkheadManager:
    """
    Manager for multiple bulkheads (one per service).
    
    Provides:
    - Service registration
    - Work submission to service-specific pools
    - Pool health/status monitoring
    - Graceful shutdown
    """
    
    def __init__(self):
        """Initialize bulkhead manager."""
        self.bulkheads: Dict[str, BulkheadService] = {}
        self.lock = threading.Lock()
        logger.info("BulkheadManager initialized")
    
    def register_service(self, name: str, max_workers: int = 3) -> BulkheadService:
        """
        Register a service with a dedicated thread pool.
        
        Args:
            name: Service name (e.g., "vision", "audio", "enrollment")
            max_workers: Max concurrent workers (default 3)
        
        Returns:
            BulkheadService instance
        """
        with self.lock:
            if name in self.bulkheads:
                logger.warning(f"Bulkhead '{name}' already registered")
                return self.bulkheads[name]
            
            bulkhead = BulkheadService(name, max_workers)
            self.bulkheads[name] = bulkhead
            return bulkhead
    
    def submit_to_service(
        self,
        service_name: str,
        func: Callable,
        *args,
        **kwargs
    ) -> Optional[Future]:
        """
        Submit work to a specific service's thread pool.
        
        Args:
            service_name: Name of service (must be registered)
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
        
        Returns:
            Future object or None if service not found
        """
        with self.lock:
            bulkhead = self.bulkheads.get(service_name)
        
        if not bulkhead:
            logger.error(f"Service '{service_name}' not registered in bulkhead")
            return None
        
        _, future = bulkhead.submit(func, *args, **kwargs)
        return future
    
    def get_service(self, name: str) -> Optional[BulkheadService]:
        """Get bulkhead for a service."""
        with self.lock:
            return self.bulkheads.get(name)
    
    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all bulkheads."""
        with self.lock:
            return {
                name: bulkhead.get_status()
                for name, bulkhead in self.bulkheads.items()
            }
    
    def shutdown(self, wait: bool = True):
        """Shutdown all bulkheads."""
        logger.info("Shutting down all bulkheads")
        with self.lock:
            for bulkhead in self.bulkheads.values():
                bulkhead.shutdown(wait=wait)
            self.bulkheads.clear()


# Global bulkhead manager instance
_bulkhead_manager: Optional[BulkheadManager] = None


def get_bulkhead_manager() -> BulkheadManager:
    """Get global bulkhead manager (lazy singleton)."""
    global _bulkhead_manager
    if _bulkhead_manager is None:
        _bulkhead_manager = BulkheadManager()
    return _bulkhead_manager


@contextmanager
def bulkhead_context():
    """
    Context manager for bulkhead operations.
    
    Usage:
        with bulkhead_context() as manager:
            manager.register_service("vision", max_workers=3)
            future = manager.submit_to_service("vision", some_func)
    """
    manager = get_bulkhead_manager()
    try:
        yield manager
    finally:
        pass  # Don't shutdown on context exit - might be reused


# Version info
__version__ = "1.0.0"
__bulkhead_feature__ = "FEATURE #6: Bulkhead Isolation"
