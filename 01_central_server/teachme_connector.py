"""
TeachMe Service Connector
Integrates TeachMe (Knowledge & Learning Service) with Central Server
- Circuit breaker pattern with automatic recovery
- Resource queue management (prevent CPU/memory overload)
- Comprehensive error handling and fallback mechanisms
- Performance metrics and health monitoring
"""

import asyncio
import logging
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import aiohttp
from urllib.parse import urlencode
from enum import Enum
from collections import deque
from shared.semantic_embeddings import SEMANTIC_EMBEDDING_DIMENSION

logger = logging.getLogger(__name__)


class TeachMeCircuitState(Enum):
    """Circuit breaker states for TeachMe service"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Service failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class TeachMeQueueManager:
    """
    Queue management for TeachMe requests.
    Prevents overwhelming the service with requests.
    """
    
    def __init__(self, max_queue_size: int = 1000, max_concurrent: int = 10):
        self.max_queue_size = max_queue_size
        self.max_concurrent = max_concurrent
        self.queue: deque = deque(maxlen=max_queue_size)
        self.processing_count = 0
        self.processed_count = 0
        self.dropped_count = 0
        logger.info(f"TeachMeQueueManager initialized: max_queue={max_queue_size}, max_concurrent={max_concurrent}")
    
    async def enqueue(self, request_id: str, endpoint: str) -> bool:
        """
        Try to enqueue a request.
        Returns True if successful, False if queue is full.
        """
        if len(self.queue) < self.max_queue_size:
            self.queue.append({
                "id": request_id,
                "endpoint": endpoint,
                "enqueued_at": datetime.utcnow()
            })
            return True
        else:
            self.dropped_count += 1
            logger.warning(f"TeachMe queue full, dropped request {request_id}")
            return False
    
    async def can_process(self) -> bool:
        """Check if more requests can be processed"""
        return self.processing_count < self.max_concurrent
    
    def mark_processing(self) -> None:
        """Mark that a request is being processed"""
        self.processing_count += 1
    
    def mark_completed(self) -> None:
        """Mark that a request completed"""
        if self.processing_count > 0:
            self.processing_count -= 1
        self.processed_count += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        return {
            "queue_size": len(self.queue),
            "max_queue_size": self.max_queue_size,
            "processing_count": self.processing_count,
            "max_concurrent": self.max_concurrent,
            "processed_total": self.processed_count,
            "dropped_total": self.dropped_count,
        }


class TeachMeConnector:
    """
    TeachMe Service Connector with advanced resilience patterns.
    
    Features:
    - Circuit breaker (fail-fast on service failures)
    - Request queuing (prevent overwhelming service)
    - Exponential backoff retry (smooth recovery)
    - Health checks (detect service recovery)
    - Metrics collection (monitor service health)
    - Graceful degradation (continue when TeachMe unavailable)
    """
    
    def __init__(self, base_url: str = "http://localhost:8004", config: Optional[Dict] = None):
        self.base_url = base_url
        self.config = config or {}
        self.embedding_dimension = SEMANTIC_EMBEDDING_DIMENSION
        
        # Extract config
        self.max_retries = self.config.get("max_retries", 3)
        self.timeout = self.config.get("timeout", 15)
        self.circuit_threshold = self.config.get("circuit_breaker_threshold", 5)
        self.circuit_timeout = self.config.get("circuit_breaker_timeout", 60)
        
        # Circuit breaker state
        self.circuit_state = TeachMeCircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.last_success_time: Optional[datetime] = None
        
        # Queue manager
        self.queue_manager = TeachMeQueueManager(max_queue_size=1000, max_concurrent=10)
        
        # Metrics
        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "retried_requests": 0,
            "circuit_opens": 0,
            "queue_drops": 0,
            "avg_response_time_ms": 0.0,
            "request_times": deque(maxlen=100),  # Track last 100 requests
        }
        
        # HTTP session
        self.session: Optional[aiohttp.ClientSession] = None
        
        logger.info(f"TeachMeConnector initialized: {base_url}")
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close_session(self) -> None:
        """Close HTTP session gracefully"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
            logger.info("TeachMe HTTP session closed")
    
    # ============================================================================
    # PUBLIC API METHODS
    # ============================================================================
    
    async def learn_object(
        self,
        name: str,
        category: str,
        attributes: Dict[str, Any],
        confidence: float = 0.95,
        tags: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Learn an object in TeachMe knowledge base.
        
        Args:
            name: Object name
            category: Object category
            attributes: Object attributes dict
            confidence: Confidence score (0.0-1.0)
        
        Returns:
            Response with item_id or None if failed
        """
        request_id = f"learn_{name}_{datetime.utcnow().timestamp()}"
        
        # Try to enqueue
        if not await self.queue_manager.enqueue(request_id, "/learn"):
            logger.warning(f"TeachMe queue full, rejecting learn request for {name}")
            return {"success": False, "error": "Service queue full", "fallback": True}
        
        try:
            self.queue_manager.mark_processing()
            
            payload = {
                "type": "object",
                "data": {"name": name, "category": category, "attributes": attributes},
                "tags": tags or [],
                "confidence": confidence,
            }
            
            response = await self.request("POST", "/learn", payload)
            
            if response:
                logger.info(f"TeachMe: Learned object '{name}'")
                return response
            else:
                logger.error(f"TeachMe: Failed to learn object '{name}'")
                return {"success": False, "error": "Service request failed"}
        
        finally:
            self.queue_manager.mark_completed()

    async def learn_item(
        self,
        item_type: str,
        data: Dict[str, Any],
        tags: Optional[List[str]] = None,
        confidence: float = 1.0,
    ) -> Optional[Dict[str, Any]]:
        """Send TeachMe's typed object/fact contract without reshaping it."""
        request_id = f"learn_{item_type}_{datetime.utcnow().timestamp()}"
        if not await self.queue_manager.enqueue(request_id, "/learn"):
            return {"success": False, "error": "Service queue full", "fallback": True}
        try:
            self.queue_manager.mark_processing()
            return await self.request(
                "POST",
                "/learn",
                {"type": item_type, "data": data, "tags": tags or [], "confidence": confidence},
            )
        finally:
            self.queue_manager.mark_completed()
    
    async def search_by_name(
        self,
        query: str,
        limit: int = 10
    ) -> Optional[Dict[str, Any]]:
        """
        Search objects by name in TeachMe.
        
        Args:
            query: Search query string
            limit: Maximum results
        
        Returns:
            Search results or None if failed
        """
        request_id = f"search_{query}_{datetime.utcnow().timestamp()}"
        
        if not await self.queue_manager.enqueue(request_id, "/knowledge/search"):
            logger.warning(f"TeachMe queue full, returning empty results for '{query}'")
            return {"results": [], "fallback": True}
        
        try:
            self.queue_manager.mark_processing()
            
            endpoint = f"/knowledge/search/{query}?limit={limit}"
            response = await self.request("GET", endpoint)
            
            return response or {"results": []}
        
        finally:
            self.queue_manager.mark_completed()
    
    async def search_by_embedding(
        self,
        query: str,
        k: int = 5,
        threshold: float = 0.3
    ) -> Optional[Dict[str, Any]]:
        """
        Semantic similarity search by embedding.
        
        Args:
            query: Natural-language query to embed in TeachMe
            k: Number of results
            threshold: Similarity threshold
        
        Returns:
            Similar objects or None if failed
        """
        request_id = f"embed_search_{datetime.utcnow().timestamp()}"
        
        if not await self.queue_manager.enqueue(request_id, "/knowledge/search/embedding"):
            logger.warning("TeachMe queue full, returning empty embedding search results")
            return {"results": [], "fallback": True}
        
        try:
            self.queue_manager.mark_processing()
            
            params = urlencode({"query_object_name": query, "top_k": k, "similarity_threshold": threshold})
            endpoint = f"/knowledge/search/embedding?{params}"
            response = await self.request("POST", endpoint)
            return response or {"results": []}
        
        finally:
            self.queue_manager.mark_completed()
    
    async def get_all_objects(self, limit: int = 100, offset: int = 0) -> Optional[Dict[str, Any]]:
        """
        Get all learned objects from TeachMe.
        
        Args:
            limit: Result limit
            offset: Pagination offset
        
        Returns:
            Objects list or None if failed
        """
        request_id = f"get_all_{datetime.utcnow().timestamp()}"
        
        if not await self.queue_manager.enqueue(request_id, "/knowledge/objects"):
            logger.warning("TeachMe queue full, returning empty objects")
            return {"objects": [], "total": 0, "fallback": True}
        
        try:
            self.queue_manager.mark_processing()
            
            endpoint = f"/knowledge/objects?limit={limit}&offset={offset}"
            response = await self.request("GET", endpoint)
            return response or {"objects": [], "total": 0}
        
        finally:
            self.queue_manager.mark_completed()
    
    async def health_check(self) -> bool:
        """
        Check TeachMe service health.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            response = await self.request("GET", "/health", timeout=2.0)
            
            if response:
                self._record_success()
                logger.debug("TeachMe health check: OK")
                return True
            else:
                self._record_failure()
                logger.warning("TeachMe health check: FAILED")
                return False
        
        except Exception as e:
            logger.error(f"TeachMe health check exception: {e}")
            self._record_failure()
            return False
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get connector metrics"""
        return {
            "service": "teachme",
            "base_url": self.base_url,
            "circuit_state": self.circuit_state.value,
            "failure_count": self.failure_count,
            "last_failure": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "last_success": self.last_success_time.isoformat() if self.last_success_time else None,
            "queue": self.queue_manager.get_stats(),
            "metrics": {
                "total_requests": self.metrics["total_requests"],
                "successful_requests": self.metrics["successful_requests"],
                "failed_requests": self.metrics["failed_requests"],
                "retried_requests": self.metrics["retried_requests"],
                "circuit_opens": self.metrics["circuit_opens"],
                "avg_response_time_ms": self.metrics["avg_response_time_ms"],
            }
        }
    
    # ============================================================================
    # PRIVATE METHODS
    # ============================================================================
    
    async def request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Make HTTP request with circuit breaker and retry logic.
        
        Args:
            method: HTTP method
            endpoint: Service endpoint
            data: Request body
            timeout: Request timeout
        
        Returns:
            Response JSON or None if failed
        """
        if timeout is None:
            timeout = self.timeout
        
        self.metrics["total_requests"] += 1
        
        # Check circuit breaker
        if not self._check_circuit():
            logger.warning(f"TeachMe circuit breaker OPEN, rejecting {method} {endpoint}")
            return None
        
        # Retry logic with exponential backoff
        for attempt in range(self.max_retries):
            try:
                import time
                start_time = time.time()
                
                result = await self._make_request(method, endpoint, data, timeout)
                
                elapsed_ms = (time.time() - start_time) * 1000
                self.metrics["request_times"].append(elapsed_ms)
                self.metrics["avg_response_time_ms"] = sum(self.metrics["request_times"]) / len(self.metrics["request_times"])
                
                self._record_success()
                return result
            
            except Exception as e:
                is_last_attempt = attempt == self.max_retries - 1
                
                if is_last_attempt:
                    self._record_failure()
                    logger.error(
                        f"TeachMe request failed after {self.max_retries} attempts "
                        f"({method} {endpoint}): {e}"
                    )
                    return None
                
                # Exponential backoff
                backoff = 2 ** attempt
                logger.warning(
                    f"TeachMe request failed, retry {attempt + 1}/{self.max_retries} "
                    f"in {backoff:.1f}s: {e}"
                )
                self.metrics["retried_requests"] += 1
                await asyncio.sleep(backoff)
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]],
        timeout: float
    ) -> Optional[Dict[str, Any]]:
        """Make actual HTTP request"""
        session = await self.get_session()
        url = f"{self.base_url}{endpoint}"
        
        try:
            async with asyncio.timeout(timeout):
                async with session.request(
                    method,
                    url,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:
                    if response.status in (200, 201):
                        result = await response.json()
                        logger.debug(f"TeachMe {method} {endpoint}: {response.status}")
                        return result
                    else:
                        raise Exception(f"HTTP {response.status}: {await response.text()}")
        
        except asyncio.TimeoutError:
            raise Exception(f"Timeout ({timeout}s)")
        except Exception as e:
            raise
    
    def _check_circuit(self) -> bool:
        """Check if request should be allowed through circuit breaker"""
        if self.circuit_state == TeachMeCircuitState.CLOSED:
            return True
        
        if self.circuit_state == TeachMeCircuitState.OPEN:
            # Try transition to half-open
            if self.last_failure_time:
                elapsed = datetime.utcnow() - self.last_failure_time
                if elapsed >= timedelta(seconds=self.circuit_timeout):
                    logger.info("TeachMe circuit breaker transitioning to HALF_OPEN")
                    self.circuit_state = TeachMeCircuitState.HALF_OPEN
                    return True
            return False
        
        # HALF_OPEN: allow single request to test recovery
        return True
    
    def _record_failure(self) -> None:
        """Record failure and update circuit breaker"""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        self.metrics["failed_requests"] += 1
        
        # Open circuit if threshold exceeded
        if self.failure_count >= self.circuit_threshold:
            if self.circuit_state != TeachMeCircuitState.OPEN:
                logger.error(
                    f"TeachMe circuit breaker OPENING "
                    f"(failures: {self.failure_count}/{self.circuit_threshold})"
                )
                self.circuit_state = TeachMeCircuitState.OPEN
                self.metrics["circuit_opens"] += 1
    
    def _record_success(self) -> None:
        """Record success and potentially close circuit"""
        self.last_success_time = datetime.utcnow()
        self.metrics["successful_requests"] += 1
        
        # Close circuit if in half-open
        if self.circuit_state == TeachMeCircuitState.HALF_OPEN:
            logger.info("TeachMe circuit breaker CLOSING (recovery successful)")
            self.circuit_state = TeachMeCircuitState.CLOSED
            self.failure_count = 0


# Global connector instance
_teachme_connector: Optional[TeachMeConnector] = None


async def init_teachme_connector(config: Optional[Dict] = None) -> TeachMeConnector:
    """Initialize TeachMe connector"""
    global _teachme_connector
    _teachme_connector = TeachMeConnector(config=config)
    return _teachme_connector


def get_teachme_connector() -> TeachMeConnector:
    """Get TeachMe connector instance"""
    if _teachme_connector is None:
        raise RuntimeError("TeachMe connector not initialized")
    return _teachme_connector
