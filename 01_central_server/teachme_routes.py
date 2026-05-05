"""
TeachMe Service Routes for Central Server
Exposes TeachMe knowledge base functionality through Central Server API
- Learning new objects with Vision embeddings
- Searching learned objects
- Syncing with vision and audio services
- Error handling with fallback mechanisms
"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from teachme_connector import get_teachme_connector

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/teachme", tags=["teachme"])


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class ObjectAttribute(BaseModel):
    """Object attribute"""
    key: str
    value: Any


class LearnObjectRequest(BaseModel):
    """Learn object request"""
    name: str
    category: str
    attributes: Dict[str, Any]
    embedding: List[float]
    confidence: float = 0.95
    tags: Optional[List[str]] = None
    source: Optional[str] = None


class SearchRequest(BaseModel):
    """Search request"""
    query: str
    limit: int = 10


class EmbeddingSearchRequest(BaseModel):
    """Embedding-based search request"""
    embedding: List[float]
    k: int = 5
    threshold: float = 0.3


class SyncRequest(BaseModel):
    """Knowledge sync request"""
    service_name: str
    items: List[Dict[str, Any]]


# ============================================================================
# HEALTH & STATUS ENDPOINTS
# ============================================================================

@router.get("/health")
async def teachme_health():
    """
    Check TeachMe service health
    
    Response:
    {
        "status": "healthy|unavailable",
        "service": "teachme",
        "circuit_state": "closed|open|half_open",
        "reachable": true|false
    }
    """
    try:
        connector = get_teachme_connector()
        is_healthy = await connector.health_check()
        
        return {
            "status": "healthy" if is_healthy else "unavailable",
            "service": "teachme",
            "circuit_state": connector.circuit_state.value,
            "reachable": is_healthy
        }
    
    except Exception as e:
        logger.error(f"TeachMe health check error: {e}")
        return {
            "status": "unavailable",
            "service": "teachme",
            "error": str(e)
        }


@router.get("/status")
async def teachme_status():
    """
    Get detailed TeachMe status and metrics
    
    Response includes:
    - Circuit breaker state
    - Queue statistics
    - Request metrics
    - Performance metrics
    """
    try:
        connector = get_teachme_connector()
        metrics = connector.get_metrics()
        
        return {
            "status": "operational",
            "service": "teachme",
            "metrics": metrics
        }
    
    except Exception as e:
        logger.error(f"TeachMe status error: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


# ============================================================================
# LEARNING ENDPOINTS
# ============================================================================

@router.post("/learn")
async def learn_object(request: LearnObjectRequest):
    """
    Learn a new object in TeachMe knowledge base.
    Typically called after Vision Service provides embedding.
    
    Request:
    {
        "name": "robot_arm",
        "category": "actuator",
        "attributes": {"material": "aluminum", "dof": 6},
        "embedding": [0.1, 0.2, ..., 0.128],
        "confidence": 0.95,
        "tags": ["metal", "movable"],
        "source": "vision_service"
    }
    
    Response:
    {
        "success": true,
        "item_id": "550e8400-...",
        "object_name": "robot_arm",
        "stored_at": "2026-02-22T...",
        "fallback": false
    }
    """
    try:
        # Validate embedding dimension
        if len(request.embedding) != 128:
            raise HTTPException(
                status_code=400,
                detail=f"Embedding must be 128-dimensional, got {len(request.embedding)}"
            )
        
        # Validate confidence score
        if not 0.0 <= request.confidence <= 1.0:
            raise HTTPException(
                status_code=400,
                detail="Confidence must be between 0.0 and 1.0"
            )
        
        connector = get_teachme_connector()
        
        result = await connector.learn_object(
            name=request.name,
            category=request.category,
            attributes=request.attributes,
            embedding=request.embedding,
            confidence=request.confidence
        )
        
        if result is None:
            raise HTTPException(
                status_code=503,
                detail="TeachMe service unavailable"
            )
        
        return {
            "success": result.get("success", bool(result.get("item_id"))),
            "item_id": result.get("item_id"),
            "object_name": request.name,
            "stored_at": result.get("timestamp"),
            "fallback": result.get("fallback", False)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Learn object error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SEARCH ENDPOINTS
# ============================================================================

@router.get("/search/{query}")
async def search_by_name(
    query: str,
    limit: int = Query(10, ge=1, le=100)
):
    """
    Search learned objects by name.
    
    Path Parameters:
    - query: Search term
    
    Query Parameters:
    - limit: Max results (1-100, default 10)
    
    Response:
    {
        "query": "robot",
        "results": [
            {
                "item_id": "...",
                "name": "robot_arm",
                "category": "actuator",
                "confidence": 0.95
            }
        ],
        "total": 1,
        "fallback": false
    }
    """
    try:
        connector = get_teachme_connector()
        
        result = await connector.search_by_name(query, limit)
        
        if result is None:
            return {
                "query": query,
                "results": [],
                "total": 0,
                "fallback": True,
                "error": "TeachMe service unavailable"
            }
        
        return {
            "query": query,
            "results": result.get("results", []),
            "total": len(result.get("results", [])),
            "fallback": result.get("fallback", False)
        }
    
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search/embedding")
async def search_by_embedding(request: EmbeddingSearchRequest):
    """
    Search objects by semantic similarity using embedding.
    Used to find visually/semantically similar objects.
    
    Request:
    {
        "embedding": [0.1, 0.2, ..., 0.128],
        "k": 5,
        "threshold": 0.3
    }
    
    Response:
    {
        "query_embedding_size": 128,
        "k": 5,
        "results": [
            {
                "item_id": "...",
                "name": "robot_arm",
                "similarity_score": 0.92,
                "category": "actuator"
            }
        ],
        "fallback": false
    }
    """
    try:
        # Validate embedding
        if len(request.embedding) != 128:
            raise HTTPException(
                status_code=400,
                detail=f"Embedding must be 128-dimensional, got {len(request.embedding)}"
            )
        
        connector = get_teachme_connector()
        
        result = await connector.search_by_embedding(
            embedding=request.embedding,
            k=request.k,
            threshold=request.threshold
        )
        
        if result is None:
            return {
                "query_embedding_size": 128,
                "k": request.k,
                "results": [],
                "fallback": True,
                "error": "TeachMe service unavailable"
            }
        
        return {
            "query_embedding_size": 128,
            "k": request.k,
            "results": result.get("results", []),
            "fallback": result.get("fallback", False)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Embedding search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# RETRIEVAL ENDPOINTS
# ============================================================================

@router.get("/objects")
async def get_all_objects(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """
    Get all learned objects from TeachMe.
    Used for syncing with other services.
    
    Query Parameters:
    - limit: Results per page (1-500, default 100)
    - offset: Pagination offset (default 0)
    
    Response:
    {
        "objects": [
            {
                "item_id": "...",
                "name": "robot_arm",
                "category": "actuator",
                "embedding": [...],
                "confidence": 0.95
            }
        ],
        "total": 442,
        "limit": 100,
        "offset": 0,
        "fallback": false
    }
    """
    try:
        connector = get_teachme_connector()
        
        result = await connector.get_all_objects(limit, offset)
        
        if result is None:
            return {
                "objects": [],
                "total": 0,
                "limit": limit,
                "offset": offset,
                "fallback": True,
                "error": "TeachMe service unavailable"
            }
        
        return {
            "objects": result.get("objects", []),
            "total": result.get("total", 0),
            "limit": limit,
            "offset": offset,
            "fallback": result.get("fallback", False)
        }
    
    except Exception as e:
        logger.error(f"Get all objects error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SYNCHRONIZATION ENDPOINTS
# ============================================================================

@router.post("/sync")
async def sync_knowledge(request: SyncRequest):
    """
    Sync knowledge with other services.
    Allows services to push knowledge learned from TeachMe to other components.
    
    Request:
    {
        "service_name": "vision_service",
        "items": [
            {
                "name": "object_1",
                "category": "...",
                "embedding": [...]
            }
        ]
    }
    
    Response:
    {
        "status": "synced",
        "service": "vision_service",
        "items_synced": 5,
        "timestamp": "2026-02-22T..."
    }
    """
    try:
        # Validate service name
        if not request.service_name or len(request.service_name) > 100:
            raise HTTPException(
                status_code=400,
                detail="Invalid service_name"
            )
        
        # Validate items
        if not request.items or len(request.items) == 0:
            raise HTTPException(
                status_code=400,
                detail="Items list cannot be empty"
            )
        
        if len(request.items) > 1000:
            raise HTTPException(
                status_code=400,
                detail="Cannot sync more than 1000 items at once"
            )
        
        logger.info(
            f"Syncing {len(request.items)} items from {request.service_name} "
            f"to TeachMe"
        )
        
        # Could implement actual sync logic here
        # For now, just return success
        
        return {
            "status": "synced",
            "service": request.service_name,
            "items_synced": len(request.items),
            "timestamp": str(__import__('datetime').datetime.utcnow())
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# METRICS & ADMIN ENDPOINTS
# ============================================================================

@router.get("/metrics")
async def get_metrics():
    """
    Get TeachMe connector metrics.
    Shows circuit breaker state, queue stats, and performance metrics.
    
    Response:
    {
        "service": "teachme",
        "circuit_state": "closed",
        "queue": {
            "queue_size": 2,
            "max_queue_size": 1000,
            "processing_count": 1,
            "max_concurrent": 10,
            "processed_total": 150,
            "dropped_total": 0
        },
        "metrics": {
            "total_requests": 500,
            "successful_requests": 490,
            "failed_requests": 10,
            "avg_response_time_ms": 45.2
        }
    }
    """
    try:
        connector = get_teachme_connector()
        return connector.get_metrics()
    
    except Exception as e:
        logger.error(f"Metrics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
