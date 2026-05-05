"""
TeachMe Service Routes
======================

Orchestration routes for TeachMe Service microservice integration.
Handles object learning, knowledge storage, and retrieval.
"""

import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Query

# Import TeachMe service client (shared module)
try:
    from shared.clients.teachme_client import TeachMeServiceClient
    from shared.models.api_response import APIResponse, success_response, error_response, ErrorCode
    from shared.utils.circuit_breaker import CircuitBreaker
    from config.settings import get_settings
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
    from shared.clients.teachme_client import TeachMeServiceClient
    from shared.models.api_response import APIResponse, success_response, error_response, ErrorCode
    from shared.utils.circuit_breaker import CircuitBreaker
    from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Create router with prefix
router = APIRouter(prefix="/teachme", tags=["TeachMe Service"])

# Circuit breaker for TeachMe service
teachme_circuit_breaker = CircuitBreaker(
    name="teachme_service",
    failure_threshold=settings.circuit_breaker_failure_threshold,
    recovery_timeout=settings.circuit_breaker_recovery_timeout
)

# Initialize TeachMe service client
teachme_client = TeachMeServiceClient()


@router.get("/health")
async def teachme_health():
    """TeachMe service health check"""
    try:
        if not teachme_circuit_breaker.is_healthy():
            raise HTTPException(status_code=503, detail="TeachMe service unavailable")
        
        logger.info("[TeachMeRoutes] Health check requested")
        result = await teachme_client.health_check()
        teachme_circuit_breaker.mark_success()
        
        if result.success:
            return success_response({"status": "healthy", "service": "teachme"})
        else:
            teachme_circuit_breaker.mark_failure()
            raise HTTPException(status_code=503, detail=result.error_message)
    except Exception as e:
        teachme_circuit_breaker.mark_failure()
        logger.error(f"TeachMe health check failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/learn-object")
async def learn_object(
    object_name: str,
    description: str = None,
    image_file: UploadFile = File(None)
):
    """
    Teach the system a new object.
    
    Args:
        object_name: Name of the object to learn
        description: Optional description of the object
        image_file: Optional image file for visual learning
        
    Returns:
        Object ID and confirmation
    """
    try:
        if not teachme_circuit_breaker.is_healthy():
            raise HTTPException(status_code=503, detail="TeachMe service unavailable")
        
        logger.info(f"[TeachMeRoutes] POST /learn-object: {object_name}")
        
        image_bytes = None
        if image_file:
            image_bytes = await image_file.read()
        
        result = await teachme_client.learn_object(
            object_name=object_name,
            description=description,
            image_bytes=image_bytes
        )
        
        teachme_circuit_breaker.mark_success()
        
        if result.success:
            logger.info("[TeachMeRoutes] learn_object SUCCESS")
            return {
                "status": "success",
                "data": result.data
            }
        else:
            logger.error(f"[TeachMeRoutes] learn_object FAILED: {result.error_message}")
            raise HTTPException(status_code=400, detail=result.error_message)
    
    except Exception as e:
        teachme_circuit_breaker.mark_failure()
        logger.error(f"[TeachMeRoutes] learn_object ERROR: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/recognize-object")
async def recognize_object(image_file: UploadFile = File(...)):
    """
    Recognize objects in an image based on learned knowledge.
    
    Args:
        image_file: Image file for recognition
        
    Returns:
        Recognized objects with confidence scores
    """
    try:
        logger.info(f"[TeachMeRoutes] POST /recognize-object: {image_file.filename}")
        
        image_bytes = await image_file.read()
        
        result = await teachme_client.recognize_object(
            image_bytes=image_bytes
        )
        
        if result.success:
            logger.info("[TeachMeRoutes] recognize_object SUCCESS")
            return {
                "status": "success",
                "data": result.data
            }
        else:
            logger.error(f"[TeachMeRoutes] recognize_object FAILED: {result.error_message}")
            raise HTTPException(status_code=400, detail=result.error_message)
    
    except Exception as e:
        logger.error(f"[TeachMeRoutes] recognize_object ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/retrieve-knowledge")
async def retrieve_knowledge(query: str = Query(...)):
    """
    Retrieve knowledge from the knowledge base.
    
    Args:
        query: Query string to search knowledge base
        
    Returns:
        Matching facts and objects
    """
    try:
        logger.info(f"[TeachMeRoutes] GET /retrieve-knowledge: query='{query}'")
        
        result = await teachme_client.retrieve_knowledge(query=query)
        
        if result.success:
            logger.info("[TeachMeRoutes] retrieve_knowledge SUCCESS")
            return {
                "status": "success",
                "data": result.data
            }
        else:
            logger.error(f"[TeachMeRoutes] retrieve_knowledge FAILED: {result.error_message}")
            raise HTTPException(status_code=400, detail=result.error_message)
    
    except Exception as e:
        logger.error(f"[TeachMeRoutes] retrieve_knowledge ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge-base/list")
async def list_knowledge():
    """
    Get list of all learned objects and facts.
    
    Returns:
        Complete knowledge base inventory
    """
    try:
        logger.info("[TeachMeRoutes] GET /knowledge-base/list")
        
        result = await teachme_client.list_knowledge_base()
        
        if result.success:
            logger.info("[TeachMeRoutes] list_knowledge_base SUCCESS")
            return {
                "status": "success",
                "data": result.data
            }
        else:
            logger.error(f"[TeachMeRoutes] list_knowledge_base FAILED: {result.error_message}")
            raise HTTPException(status_code=400, detail=result.error_message)
    
    except Exception as e:
        logger.error(f"[TeachMeRoutes] list_knowledge_base ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
