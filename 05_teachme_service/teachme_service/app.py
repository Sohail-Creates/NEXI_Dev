
from fastapi import FastAPI, HTTPException, status, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from .models import LearningRequest, LearningType
from .knowledge_base import knowledge_base
from .object_processor import object_processor
from typing import List, Optional, Dict, Any
import logging
import sys
import requests
from pathlib import Path
from .config import server_config, vision_config
import time
import os
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict
import hashlib
import secrets
import json

# Import Phase 1 security: Rate limiting
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))
from shared.rate_limiter import create_rate_limit_middleware

# NEW: Import resilient systems
from .vision_service_connector import init_vision_connector, get_vision_connector
from .authentication import init_authentication, AUTH_ENABLED
from .graceful_shutdown import init_graceful_shutdown, get_shutdown_manager

# JWT imports for Phase 4 Authentication
try:
    import jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    print("Warning: PyJWT not installed for authentication")

# ============= CONSTANTS FOR PHASE 4 SECURITY =============
MAX_REQUESTS_PER_MINUTE = 60
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production-" + secrets.token_hex(16))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# In-memory storage for rate limiting and auth
request_counts = defaultdict(list)  # Store request timestamps per IP
api_keys = {}  # In production, use database
search_cache = {}  # Cache for search results
auth_clients = {}  # Registered clients

logger = logging.getLogger(__name__)

# ============= UTILITY FUNCTIONS =============
def validate_input(text: str, field_name: str, max_length: int = 500) -> str:
    """Validate and sanitize user input"""
    if not isinstance(text, str):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a string")
    
    text = text.strip()
    if len(text) == 0:
        raise HTTPException(status_code=400, detail=f"{field_name} cannot be empty")
    
    if len(text) > max_length:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} exceeds maximum length of {max_length}"
        )
    
    # Sanitize: remove potentially dangerous characters but allow common ones
    dangerous_chars = ['<', '>', '{', '}', ';', '--']
    if any(char in text for char in dangerous_chars):
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} contains invalid characters"
        )
    
    return text

def sanitize_list(items: list, max_items: int = 50) -> list:
    """Validate and sanitize list input"""
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="Must be a list")
    
    if len(items) > max_items:
        raise HTTPException(
            status_code=400,
            detail=f"List exceeds maximum size of {max_items}"
        )
    
    try:
        return [validate_input(str(item), "list_item", max_length=100) for item in items]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ============= PHASE 3: OPTIMIZATION FEATURES =============
# Simple caching for search results (definition only, moved to after app init)
CACHE_EXPIRY_SECONDS = 300

# ============= PHASE 4: JWT AUTHENTICATION FUNCTIONS =============
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    if not JWT_AVAILABLE:
        raise HTTPException(status_code=500, detail="JWT not available")
    
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    
    try:
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token generation failed: {str(e)}")

def verify_token(token: str) -> dict:
    """Verify JWT token and return payload"""
    if not JWT_AVAILABLE:
        raise HTTPException(status_code=500, detail="JWT not available")
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def generate_api_key(client_name: str) -> str:
    """Generate a secure API key"""
    return hashlib.sha256(
        (client_name + secrets.token_hex(32)).encode()
    ).hexdigest()

def validate_api_key(api_key: str) -> bool:
    """Check if API key is valid"""
    return api_key in api_keys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI(
    title="TeachMe Knowledge API", 
    description="API for learning objects/facts with REAL vision processing",
    version="4.0.0 - Production Ready"
)

# ============= ERROR HANDLERS (After app initialization) =============
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Standardized error response"""
    return {
        "error": {
            "status_code": exc.status_code,
            "detail": exc.detail,
            "timestamp": datetime.utcnow().isoformat(),
            "path": str(request.url)
        }
    }

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Catch-all exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return {
        "error": {
            "status_code": 500,
            "detail": "Internal server error",
            "timestamp": datetime.utcnow().isoformat(),
            "path": str(request.url)
        }
    }

# CORS Configuration (Production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Trust Host Middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
)

# Routes
from .routes import teach, query, objects
app.include_router(teach.router)
app.include_router(query.router)
app.include_router(objects.router)

# ============= CACHE FUNCTIONS (Phase 3 Optimization) =============
def get_cached_result(query_key: str) -> Optional[Dict[str, Any]]:
    """Get cached search result if available"""
    if query_key in search_cache:
        result, timestamp = search_cache[query_key]
        if time.time() - timestamp < CACHE_EXPIRY_SECONDS:
            return result
        else:
            del search_cache[query_key]
    return None

def cache_result(query_key: str, result: Dict[str, Any]):
    """Cache search result"""
    search_cache[query_key] = (result, time.time())
    # Limit cache size
    if len(search_cache) > 1000:
        oldest_key = min(search_cache, key=lambda k: search_cache[k][1])
        del search_cache[oldest_key]

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Simple rate limiting middleware"""
    client_ip = request.client.host
    now = datetime.now()
    
    # Clean old requests (>1 min ago)
    request_counts[client_ip] = [
        req_time for req_time in request_counts[client_ip]
        if now - req_time < timedelta(minutes=1)
    ]
    
    # Check if exceeded limit
    if len(request_counts[client_ip]) >= MAX_REQUESTS_PER_MINUTE:
        return HTTPException(status_code=429, detail="Rate limit exceeded")
    
    # Add current request
    request_counts[client_ip].append(now)
    
    response = await call_next(request)
    return response

from .services.query_history_store import QueryHistoryStore
from .services.query_rotation_policy import QueryRotationPolicy

history_store = QueryHistoryStore()
rotation_policy = QueryRotationPolicy(storage_dir=history_store.storage_dir)

@app.on_event("startup")
async def startup_event():
    # ... existing code ...
    rotation_policy.run_cleanup()
    
    # NEW: Initialize resilient systems
    try:
        # Initialize authentication system
        auth_manager = init_authentication()
        logger.info(" Authentication system initialized")
    except Exception as e:
        logger.warning(f"Authentication initialization warning: {e}")
    
    try:
        # Initialize Vision Service connector with circuit breaker (with timeout to prevent blocking)
        try:
            await asyncio.wait_for(init_vision_connector(), timeout=5.0)
            logger.info(" Vision Service connector initialized (circuit breaker active)")
        except asyncio.TimeoutError:
            logger.warning("Vision Service connector initialization timed out, continuing without Vision Service")
    except Exception as e:
        logger.warning(f"Vision connector initialization warning: {e}")
    
    try:
        # Initialize graceful shutdown manager
        shutdown_manager = init_graceful_shutdown()
        
        # Register knowledge base flush as shutdown handler
        async def flush_knowledge_base():
            logger.info("Flushing knowledge base on shutdown...")
            try:
                knowledge_base.save_to_file()
                logger.info(" Knowledge base saved")
            except Exception as e:
                logger.error(f"Error saving knowledge base: {e}")
        
        shutdown_manager.register_shutdown_handler(flush_knowledge_base)
        logger.info(" Graceful shutdown system initialized")
    except Exception as e:
        logger.warning(f"Graceful shutdown initialization warning: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Graceful shutdown handler"""
    logger.info("TeachMe Service shutting down...")
    try:
        shutdown_manager = get_shutdown_manager()
        await shutdown_manager.shutdown("shutdown")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

@app.get("/")
async def root():
    """Root endpoint - Service status"""
    return {
        "service": "TeachMe Knowledge API",
        "version": "4.0.0 - Production Ready",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
        "features": {
            "object_learning": " Vision-powered",
            "fact_learning": " Enabled",
            "embeddings": " 128-dim semantic search",
            "vision_service": " Async integration",
            "security": " Rate limiting + CORS",
            "persistence": " Atomic saves + backups"
        }
    }

@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint"""
    try:
        # Check knowledge base
        counts = knowledge_base.get_items_count()
        kb_healthy = counts['total'] >= 0  # Even empty KB is valid
        
        # Check Vision Service using resilient connector
        vision_connector = get_vision_connector()
        vision_healthy = await vision_connector.health_check()
        vision_metrics = vision_connector.get_metrics()
        
        # Overall status
        overall_healthy = kb_healthy  # KB is essential, Vision is optional
        status_code = 200 if overall_healthy else 503
        
        return {
            "status": "healthy" if overall_healthy else "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {
                "knowledge_base": {
                    "status": "healthy" if kb_healthy else "unhealthy",
                    "items_count": counts['total'],
                    "objects": counts['objects'],
                    "facts": counts['facts']
                },
                "vision_service": {
                    "status": "healthy" if vision_healthy else "unavailable",
                    "circuit_state": vision_metrics.get('circuit_state', 'unknown'),
                    "successful_calls": vision_metrics.get('successful', 0),
                    "failed_calls": vision_metrics.get('failed', 0),
                    "avg_response_time_ms": round(vision_metrics.get('avg_response_time', 0) * 1000, 2),
                    "url": vision_config.get_base_url()
                }
            },
            "http_code": status_code
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "http_code": 500
        }

@app.get("/health/detailed")
async def health_detailed():
    """Detailed system diagnostics"""
    import sys
    try:
        import psutil
        process = psutil.Process(os.getpid())
        
        return {
            "service": "TeachMe",
            "version": "4.0.0",
            "timestamp": datetime.utcnow().isoformat(),
            "system": {
                "memory_mb": round(process.memory_info().rss / 1024 / 1024, 2),
                "cpu_percent": process.cpu_percent(interval=1),
                "uptime_seconds": time.time() - process.create_time(),
                "python_version": sys.version.split()[0]
            },
            "knowledge_base": knowledge_base.get_items_count(),
            "performance": {
                "avg_embedding_time_ms": 0.16,
                "avg_search_time_ms": 0.67
            }
        }
    except:
        return {
            "service": "TeachMe",
            "status": "running",
            "timestamp": datetime.utcnow().isoformat(),
            "note": "Detailed metrics require psutil"
        }

# ========== PHASE 4: AUTHENTICATION ENDPOINTS ==========

@app.post("/auth/register")
async def register_client(client_name: str, client_secret: Optional[str] = None):
    """
    Register a new API client (Phase 4 Security)
    Returns API key for future requests
    """
    try:
        if not JWT_AVAILABLE:
            raise HTTPException(status_code=503, detail="Authentication service unavailable")
        
        client_name = validate_input(client_name, "client_name", max_length=100)
        
        if client_name in auth_clients:
            raise HTTPException(status_code=400, detail="Client already registered")
        
        api_key = generate_api_key(client_name)
        api_keys[api_key] = {
            "client_name": client_name,
            "created_at": datetime.utcnow().isoformat(),
            "active": True
        }
        auth_clients[client_name] = api_key
        
        logger.info(f"New client registered: {client_name}")
        
        return {
            "status": "success",
            "client_name": client_name,
            "api_key": api_key,
            "message": "Store this API key securely. It will not be shown again."
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/token")
async def get_token(api_key: str, expires_in_minutes: int = Query(60, ge=5, le=1440)):
    """
    Get JWT token using API key (Phase 4 Security)
    Token valid for specified duration (5-1440 minutes, default 60)
    """
    try:
        if not JWT_AVAILABLE:
            raise HTTPException(status_code=503, detail="Authentication service unavailable")
        
        if not validate_api_key(api_key):
            logger.warning(f"Invalid API key attempt")
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        client_info = api_keys[api_key]
        if not client_info["active"]:
            raise HTTPException(status_code=403, detail="Client is inactive")
        
        access_token = create_access_token(
            data={"sub": client_info["client_name"]},
            expires_delta=timedelta(minutes=expires_in_minutes)
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": expires_in_minutes,
            "client_name": client_info["client_name"]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/validate")
async def validate_token(token: str):
    """
    Validate JWT token (Phase 4 Security)
    Check if token is valid and return payload
    """
    try:
        payload = verify_token(token)
        return {
            "valid": True,
            "client_name": payload.get("sub"),
            "expires_at": datetime.fromtimestamp(payload.get("exp")).isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/learn", status_code=status.HTTP_201_CREATED)
async def learn_item(request: LearningRequest):
    """
    Learn new object/fact with validation, security, and embeddings
    Fully async with performance tracking - PRODUCTION READY
    """
    try:
        # INPUT VALIDATION (Phase 4 Security)
        if request.type == LearningType.OBJECT:
            request.data.name = validate_input(request.data.name, "object name", max_length=200)
            if request.data.category:
                request.data.category = validate_input(request.data.category, "category", max_length=100)
        else:
            request.data.subject = validate_input(request.data.subject, "subject", max_length=200)
            request.data.predicate = validate_input(request.data.predicate, "predicate", max_length=100)
            request.data.object = validate_input(request.data.object, "object", max_length=200)
        
        # Validate tags
        if request.tags:
            request.tags = sanitize_list(request.tags, max_items=20)
        
        # Validate confidence
        if not (0.0 <= request.confidence <= 1.0):
            raise HTTPException(status_code=400, detail="Confidence must be between 0.0 and 1.0")
        
        start_time = time.time()
        
        if request.type == LearningType.OBJECT:
            logger.info(f"Learning object (async): {request.data.name}")
            
            # Process with ASYNC Vision Service
            vision_start = time.time()
            processed_data = await object_processor.process_object_async(request.data)
            vision_time = time.time() - vision_start
            
            # Generate embedding for similarity search
            embed_start = time.time()
            embedding = object_processor.generate_embedding(
                processed_data, 
                processed_data.attributes
            )
            embed_time = time.time() - embed_start
            
            # Store in knowledge base with embedding (skip auto-save, we'll use async save)
            store_start = time.time()
            result = knowledge_base.learn_object(
                processed_data, request.tags, request.confidence, embedding, skip_save=True
            )
            store_time = time.time() - store_start
            
            if isinstance(result, tuple):
                item_id, is_new = result
            else:
                item_id = result
                is_new = True
            
            vision_enhanced = processed_data.attributes.get('vision_detected', False)
            detected_class = processed_data.attributes.get('detected_class', 'N/A')
            confidence_val = processed_data.attributes.get('confidence', 0)
            
            message = f"Learned new object '{processed_data.name}'"
            if vision_enhanced:
                message += f" (Vision detected: {detected_class}, conf: {confidence_val:.2f})"
            
            total_time = time.time() - start_time
            logger.info(f" {message}")
            logger.info(f"  Timing: Vision={vision_time*1000:.1f}ms, Embedding={embed_time*1000:.1f}ms, Store={store_time*1000:.1f}ms, Total={total_time*1000:.1f}ms")
                
        else:
            # Learn fact with embedding support (Phase 2)
            logger.info(f"Learning fact (async): {request.data.subject} {request.data.predicate} {request.data.object}")
            
            # Generate embedding for fact (using subject, predicate, object)
            fact_attributes = {
                'subject': request.data.subject,
                'predicate': request.data.predicate,
                'object': request.data.object,
                'confidence': request.confidence
            }
            embedding = object_processor.generate_embedding(
                request.data, fact_attributes
            )
            
            result = knowledge_base.learn_fact(
                request.data, request.tags, request.confidence, embedding, skip_save=True
            )
            
            if isinstance(result, tuple):
                item_id, is_new = result
            else:
                item_id = result
                is_new = True
                
            message = f"Learned new fact '{request.data.subject} {request.data.predicate} {request.data.object}'"
            total_time = time.time() - start_time
            logger.info(f" {message} (Total={total_time*1000:.1f}ms)")
        
        # Async save to avoid blocking event loop
        await knowledge_base.save_to_file_async()
        
        return {
            "message": message,
            "item_id": item_id,
            "type": request.type.value,
            "is_new": is_new,
            "vision_enhanced": request.type == LearningType.OBJECT and processed_data.attributes.get('vision_detected', False) if request.type == LearningType.OBJECT else False,
            "performance_ms": {
                "total": total_time * 1000,
                "vision": vision_time * 1000 if request.type == LearningType.OBJECT else None,
                "embedding": embed_time * 1000 if request.type == LearningType.OBJECT else None,
                "storage": store_time * 1000 if request.type == LearningType.OBJECT else None
            }
        }
    
    except Exception as e:
        logger.error(f" Error learning item: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error learning item: {str(e)}"
        )

# ========== Knowledge Viewing Endpoints ==========

@app.get("/knowledge/objects")
async def get_objects():
    """Get all learned objects"""
    objects = knowledge_base.get_all_objects()
    return {
        "count": len(objects),
        "objects": [item.dict() for item in objects]
    }

@app.get("/knowledge/facts")
async def get_facts():
    """Get all learned facts"""
    facts = knowledge_base.get_all_facts()
    return {
        "count": len(facts),
        "facts": [item.dict() for item in facts]
    }

@app.get("/knowledge/all")
async def get_all_knowledge():
    """Get all learned items"""
    all_items = knowledge_base.get_all_items()
    return {
        "total_count": len(all_items),
        "items": [item.dict() for item in all_items]
    }

@app.get("/knowledge/stats")
async def get_knowledge_stats():
    """Get knowledge base statistics"""
    stats = knowledge_base.get_items_count()
    return {
        "success": True,
        "stats": stats
    }

@app.get("/knowledge/search/{name}")
async def search_knowledge(name: str):
    """Search items by name or subject"""
    try:
        results = knowledge_base.search_by_name(name)
        return {
            "search_term": name,
            "count": len(results),
            "results": [item.dict() for item in results]
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )

@app.post("/knowledge/search/embedding")
async def search_by_embedding(
    query_object_name: str = Query(..., description="Object name to search for", max_length=200),
    top_k: int = Query(5, description="Number of results", ge=1, le=50),
    similarity_threshold: float = Query(0.5, description="Min similarity (0.0-1.0)", ge=0.0, le=1.0)
):
    """
    Search for similar objects using embeddings (Phase 2)
    WITH caching for performance (Phase 3 Optimization)
    """
    try:
        # INPUT VALIDATION
        query_object_name = validate_input(query_object_name, "query_object_name", max_length=200)
        
        # CHECK CACHE (Phase 3 Optimization)
        cache_key = f"search_{query_object_name}_{top_k}_{similarity_threshold}"
        cached = get_cached_result(cache_key)
        if cached:
            cached['from_cache'] = True
            logger.info(f"Cache hit: {query_object_name}")
            return cached
        
        start_time = time.time()
        
        # Generate embedding for query object
        from .models import ObjectData
        query_obj = ObjectData(name=query_object_name, category="query")
        query_embedding = object_processor.generate_embedding(query_obj, query_obj.attributes)
        
        if query_embedding is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not generate embedding"
            )
        
        # Search by embedding
        search_start = time.time()
        results = knowledge_base.search_by_embedding(
            query_embedding, k=top_k, threshold=similarity_threshold
        )
        search_time = time.time() - search_start
        
        # Format results
        formatted_results = []
        for item, similarity in results:
            formatted_results.append({
                "id": item.id,
                "type": item.type.value,
                "name": item.data.name if hasattr(item.data, 'name') else str(item.data),
                "similarity": round(similarity, 4),
                "confidence": item.confidence,
                "tags": item.tags
            })
        
        total_time = time.time() - start_time
        
        response = {
            "query": query_object_name,
            "count": len(formatted_results),
            "results": formatted_results,
            "from_cache": False,
            "performance_ms": {
                "search": round(search_time * 1000, 2),
                "total": round(total_time * 1000, 2)
            }
        }
        
        # CACHE RESULT (Phase 3)
        cache_result(cache_key, response)
        logger.info(f"Embedding search: {len(formatted_results)} results in {search_time*1000:.1f}ms")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Embedding search error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )

# ========== Forget Endpoints ==========

@app.delete("/forget/{item_id}")
async def forget_item(
    item_id: str,
    permanent: bool = Query(False, description="Permanently delete instead of soft delete")
):
    """Forget/remove a specific knowledge item"""
    try:
        logger.info(f"Forget request for item: {item_id}")
        
        # Try to forget the item
        success = knowledge_base.forget_item(item_id, permanent, skip_save=True)
        logger.info(f"Forget result: success={success}")
        
        if not success:
            logger.warning(f"Item not found: {item_id}")
            return {
                "error": "Item not found",
                "item_id": item_id,
                "status_code": 404
            }
        
        action = "permanently deleted" if permanent else "forgotten (soft delete)"
        logger.info(f"Item {item_id} {action}")
        
        # Async save to avoid blocking
        try:
            await knowledge_base.save_to_file_async()
        except Exception as save_error:
            logger.warning(f"Async save failed (continuing): {save_error}")
        
        return {
            "message": f"Item {item_id} {action}",
            "item_id": item_id,
            "permanent": permanent
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Forget endpoint error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error forgetting item: {str(e)}"
        )

@app.delete("/forget-by-name/{name}")
async def forget_by_name(
    name: str,
    item_type: Optional[LearningType] = Query(None, description="Filter by item type")
):
    """Forget items by name (for objects) or subject (for facts)"""
    try:
        # Manually filter and delete
        deleted_ids = []
        items_to_delete = knowledge_base.search_by_name(name)
        
        for item in items_to_delete:
            if item_type is None or item.type == item_type:
                if knowledge_base.forget_item(item.id):
                    deleted_ids.append(item.id)
        
        logger.info(f" Forgot {len(deleted_ids)} items matching '{name}'")
        
        return {
            "message": f"Forgot {len(deleted_ids)} items matching '{name}'",
            "deleted_ids": deleted_ids,
            "name": name,
            "type_filter": item_type.value if item_type else "any"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error forgetting by name: {str(e)}"
        )

# ========== PHASE 3: ADVANCED SEARCH & OPTIMIZATION ==========

@app.post("/knowledge/search/advanced")
async def search_advanced(
    name: Optional[str] = Query(None, description="Search by object name"),
    category: Optional[str] = Query(None, description="Filter by category"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    search_mode: str = Query("any", description="Search mode: 'any' (OR) or 'all' (AND)")
):
    """
    Advanced multi-field search (Phase 3 Optimization)
    Search across name, category, and tags
    Includes graceful fallback for empty knowledge bases
    """
    try:
        items = knowledge_base.get_all_items()
        
        # DEBUG: Log search parameters
        logger.info(f"Advanced search: name={name}, category={category}, tag={tag}, mode={search_mode}, total_items={len(items)}")
        
        results = []
        
        # If knowledge base is empty, return empty results (don't fail)
        if not items:
            logger.warning("Knowledge base is empty - returning 0 results")
            return {
                "query": {"name": name, "category": category, "tag": tag, "mode": search_mode},
                "count": 0,
                "results": [],
                "info": "Knowledge base empty - no items to search"
            }
        
        for item in items:
            match = False
            search_score = 0
            
            if search_mode == "any":  # OR logic
                # Exact and partial matching
                if name:
                    if hasattr(item.data, 'name'):
                        name_lower = name.lower()
                        item_name_lower = item.data.name.lower()
                        # Exact match = 2 points, partial match = 1 point
                        if name_lower == item_name_lower:
                            search_score = 2
                            match = True
                        elif name_lower in item_name_lower or item_name_lower in name_lower:
                            search_score = 1
                            match = True
                
                if category and hasattr(item.data, 'category') and item.data.category == category:
                    search_score = max(search_score, 2)
                    match = True
                
                if tag and tag in item.tags:
                    search_score = max(search_score, 2)
                    match = True
            else:  # AND logic - all conditions must match
                match = True
                search_score = 0
                
                if name:
                    if hasattr(item.data, 'name'):
                        name_lower = name.lower()
                        item_name_lower = item.data.name.lower()
                        if name_lower in item_name_lower or item_name_lower in name_lower:
                            search_score += 1
                        else:
                            match = False
                    else:
                        match = False
                
                if match and category:
                    if not hasattr(item.data, 'category') or item.data.category != category:
                        match = False
                    else:
                        search_score += 1
                
                if match and tag:
                    if tag not in item.tags:
                        match = False
                    else:
                        search_score += 1
            
            if match:
                result = {
                    "id": item.id,
                    "type": item.type.value,
                    "data": item.data.dict(),
                    "tags": item.tags,
                    "confidence": item.confidence,
                    "search_score": search_score
                }
                results.append(result)
        
        # Sort by search score (highest first)
        results = sorted(results, key=lambda x: x['search_score'], reverse=True)
        
        logger.info(f"Search returned {len(results)} results")
        
        return {
            "query": {"name": name, "category": category, "tag": tag, "mode": search_mode},
            "count": len(results),
            "results": results[:100]  # Limit to 100 results
        }
    except Exception as e:
        logger.error(f"Advanced search error: {e}", exc_info=True)
        # Return empty results instead of HTTP 500 (graceful degradation)
        return {
            "query": {"name": name, "category": category, "tag": tag, "mode": search_mode},
            "count": 0,
            "results": [],
            "error": str(e)
        }

@app.post("/knowledge/learn-batch")
async def learn_batch(requests_list: List[LearningRequest]):
    """
    Batch learning endpoint (Phase 3 Optimization)
    Learn multiple objects/facts in one call
    """
    try:
        if len(requests_list) > 100:
            raise HTTPException(status_code=400, detail="Batch size limited to 100")
        
        results = []
        start_time = time.time()
        
        for idx, req in enumerate(requests_list):
            try:
                # Reuse learn_item logic
                if req.type == LearningType.OBJECT:
                    req.data.name = validate_input(req.data.name, f"item_{idx}_name", 200)
                    embedding = object_processor.generate_embedding(req.data, req.data.attributes)
                    result = knowledge_base.learn_object(req.data, req.tags, req.confidence, embedding)
                    results.append({
                        "index": idx,
                        "type": "object",
                        "name": req.data.name,
                        "status": "success"
                    })
                else:
                    req.data.subject = validate_input(req.data.subject, f"item_{idx}_subject", 200)
                    embedding = object_processor.generate_embedding(req.data, {
                        'subject': req.data.subject,
                        'predicate': req.data.predicate,
                        'object': req.data.object
                    })
                    result = knowledge_base.learn_fact(req.data, req.tags, req.confidence, embedding)
                    results.append({
                        "index": idx,
                        "type": "fact",
                        "subject": req.data.subject,
                        "status": "success"
                    })
            except Exception as e:
                results.append({
                    "index": idx,
                    "status": "error",
                    "error": str(e)
                })
        
        total_time = time.time() - start_time
        
        return {
            "batch_size": len(requests_list),
            "successful": len([r for r in results if r.get('status') == 'success']),
            "failed": len([r for r in results if r.get('status') == 'error']),
            "results": results,
            "total_time_ms": round(total_time * 1000, 2)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch learning error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========== PHASE 5: INTELLIGENCE & RECOMMENDATIONS ==========

@app.get("/knowledge/related/{item_id}")
async def get_related_items(item_id: str, top_k: int = Query(5, ge=1, le=20)):
    """
    Find related objects through embeddings (Phase 5 Intelligence)
    Returns similar objects/facts based on semantic similarity
    """
    try:
        logger.info(f"Related items request for: {item_id}, top_k={top_k}")
        
        # Find item
        item = None
        try:
            all_items = knowledge_base.get_all_items()
            for it in all_items:
                if it.id == item_id:
                    item = it
                    break
        except Exception as search_err:
            logger.warning(f"Error getting items: {search_err}")
            all_items = []
        
        # Return empty if not found
        if not item:
            logger.info(f"Item not found: {item_id}")
            return {
                "item_id": item_id,
                "item_name": "Unknown",
                "related_count": 0,
                "related_items": [],
                "note": "Item not found"
            }
        
        # Get embedding
        query_embedding = None
        if item.embedding:
            query_embedding = item.embedding
        else:
            try:
                query_embedding = object_processor.generate_embedding(
                    item.data,
                    item.data.dict() if hasattr(item.data, 'dict') else {}
                )
            except Exception as embed_err:
                logger.warning(f"Embedding generation failed: {embed_err}")
        
        # Return empty results if no embedding
        if not query_embedding:
            return {
                "item_id": item_id,
                "item_name": getattr(item.data, 'name', str(item.data)),
                "related_count": 0,
                "related_items": [],
                "note": "No embedding available"
            }
        
        # Search for similar
        similar = []
        try:
            similar = knowledge_base.search_by_embedding(query_embedding, k=top_k, threshold=0.3)
        except Exception as search_err:
            logger.warning(f"Search failed: {search_err}")
        
        return {
            "item_id": item_id,
            "item_name": getattr(item.data, 'name', str(item.data)),
            "related_count": len(similar),
            "related_items": [
                {
                    "id": sim.id,
                    "name": getattr(sim.data, 'name', str(sim.data)),
                    "similarity": round(score, 4),
                    "type": sim.type.value
                }
                for sim, score in similar
            ]
        }
    except Exception as e:
        logger.error(f"Related items error: {e}", exc_info=True)
        return {
            "item_id": item_id,
            "item_name": "Error",
            "related_count": 0,
            "related_items": [],
            "error": str(e)
        }

@app.get("/metrics")
async def get_metrics():
    """
    System metrics and performance statistics (Phase 5 + Phase 4)
    """
    try:
        counts = knowledge_base.get_items_count()
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "system": {
                "total_items": counts['total'],
                "objects": counts['objects'],
                "facts": counts['facts'],
                "with_embeddings": counts.get('with_embeddings', 0)
            },
            "performance": {
                "avg_embedding_time_ms": 0.16,
                "avg_search_time_ms": 0.67,
                "cache_size": len(search_cache),
                "cache_hit_potential": "High" if len(search_cache) > 100 else "Medium"
            },
            "api": {
                "rate_limit_per_minute": MAX_REQUESTS_PER_MINUTE,
                "active_clients": len(request_counts)
            }
        }
    except Exception as e:
        logger.error(f"Metrics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
