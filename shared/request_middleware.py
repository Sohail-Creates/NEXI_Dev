"""
Request ID Middleware
=====================

Adds request ID to every request for correlation and logging.
Makes it possible to trace a request through all services.

PHASE 1: System Truth & Observability
"""

from fastapi import Request
from typing import Callable
import uuid
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from error_handler import set_request_id, clear_request_id, logger


async def request_id_middleware(request: Request, call_next: Callable):
    """
    Middleware that:
    1. Generates or extracts request ID
    2. Sets it in context
    3. Logs request start
    4. Logs request end
    5. Clears context
    """
    
    # Get or generate request ID
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    set_request_id(request_id)
    
    # Log request start
    logger.info(
        f"REQUEST START: {request.method} {request.url.path}",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        query=dict(request.query_params) if request.query_params else {}
    )
    
    try:
        # Process request
        response = await call_next(request)
        
        # Log request success
        logger.info(
            f"REQUEST END: {request.method} {request.url.path} - {response.status_code}",
            request_id=request_id,
            status_code=response.status_code
        )
        
        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id
        
        return response
    
    except Exception as e:
        # Log request failure
        logger.error(
            f"REQUEST FAILED: {request.method} {request.url.path} - {type(e).__name__}: {str(e)}",
            request_id=request_id,
            exception=type(e).__name__
        )
        raise
    
    finally:
        # Clear context
        clear_request_id()
