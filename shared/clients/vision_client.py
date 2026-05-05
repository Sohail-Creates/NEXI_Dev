"""
Vision Service Client

All communication with Vision Service (port 8001) goes through this class.
Never call Vision Service directly from a route handler.
Every method wraps the HTTP call in the circuit breaker.
"""

import httpx
import logging
from ..utils.circuit_breaker import CircuitBreaker, CircuitBreakerException
from .models import ServiceCallResult
from ..config import ServiceConfig

logger = logging.getLogger(__name__)

# Service configuration (dynamically loaded from env vars or localhost)
VISION_SERVICE_URL = ServiceConfig.get_service_url("vision")
CIRCUIT_BREAKER_MAX_FAILURES = 3
CIRCUIT_BREAKER_RESET_TIMEOUT = 30


class VisionServiceClient:
    """
    Dedicated client for Vision Service communication.
    Handles face detection, emotion recognition, and face embeddings.
    """

    def __init__(self, base_url: str = VISION_SERVICE_URL):
        self.base_url = base_url
        self.timeout = httpx.Timeout(
            connect=5.0,
            read=15.0,  # Vision processing
            write=10.0,
            pool=5.0
        )
        self.circuit_breaker = CircuitBreaker(
            name="vision_service",
            failure_threshold=CIRCUIT_BREAKER_MAX_FAILURES,
            recovery_timeout=CIRCUIT_BREAKER_RESET_TIMEOUT
        )

    async def process_face(
        self,
        image_file_bytes: bytes,
        filename: str
    ) -> ServiceCallResult:
        """
        Send image to Vision Service for face detection and embedding extraction.
        Returns face embeddings, bounding boxes, and detected attributes (age, gender, mood).
        
        Args:
            image_file_bytes: Raw image bytes
            filename: Original filename
            
        Returns:
            ServiceCallResult with face embeddings and attributes on success
        """
        try:
            if self.circuit_breaker.state.value == "OPEN":
                return ServiceCallResult(
                    success=False,
                    error_code="VISION_SERVICE_CIRCUIT_OPEN",
                    error_message="Vision Service is temporarily unavailable"
                )

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                files = {"file": (filename, image_file_bytes, "image/jpeg")}
                response = await client.post(
                    f"{self.base_url}/process-face",
                    files=files
                )

                if response.status_code == 200:
                    self.circuit_breaker.record_success()
                    return ServiceCallResult(
                        success=True,
                        data=response.json()
                    )
                else:
                    self.circuit_breaker.record_failure()
                    return ServiceCallResult(
                        success=False,
                        error_code="FACE_PROCESSING_FAILED",
                        error_message=f"Vision Service returned {response.status_code}: {response.text[:200]}"
                    )

        except httpx.TimeoutException:
            self.circuit_breaker.record_failure()
            return ServiceCallResult(
                success=False,
                error_code="VISION_SERVICE_TIMEOUT",
                error_message="Vision Service did not respond in time"
            )
        except (httpx.ConnectError, httpx.RequestError):
            self.circuit_breaker.record_failure()
            return ServiceCallResult(
                success=False,
                error_code="VISION_SERVICE_UNREACHABLE",
                error_message="Could not connect to Vision Service"
            )
        except Exception as e:
            self.circuit_breaker.record_failure()
            return ServiceCallResult(
                success=False,
                error_code="VISION_SERVICE_ERROR",
                error_message=f"Unexpected error: {str(e)}"
            )

    async def health_check(self) -> ServiceCallResult:
        """
        Health check without circuit breaker.
        Used to determine if service is up.
        """
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as client:
                response = await client.get(f"{self.base_url}/health")
                if response.status_code == 200:
                    return ServiceCallResult(
                        success=True,
                        data=response.json()
                    )
                else:
                    return ServiceCallResult(
                        success=False,
                        error_code="VISION_UNHEALTHY",
                        error_message=f"Health check returned {response.status_code}"
                    )
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
            return ServiceCallResult(
                success=False,
                error_code="VISION_UNREACHABLE",
                error_message="Vision Service is not responding"
            )
        except Exception as e:
            return ServiceCallResult(
                success=False,
                error_code="VISION_HEALTH_ERROR",
                error_message=str(e)
            )
