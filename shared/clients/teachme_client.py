"""
TeachMe Service Client

All communication with TeachMe Service (port 8003) goes through this class.
Handles object learning, fact storage, and knowledge retrieval.
"""

import httpx
import logging
from typing import Optional, List
from ..utils.circuit_breaker import CircuitBreaker
from .models import ServiceCallResult
from ..config import ServiceConfig

logger = logging.getLogger(__name__)

# Service configuration (dynamically loaded from env vars or localhost)
TEACHME_SERVICE_URL = ServiceConfig.get_service_url("teachme")
CIRCUIT_BREAKER_MAX_FAILURES = 3
CIRCUIT_BREAKER_RESET_TIMEOUT = 30


class TeachMeServiceClient:
    """
    Dedicated client for TeachMe Service communication.
    Manages object and fact learning, knowledge retrieval and forgetting.
    """

    def __init__(self, base_url: str = TEACHME_SERVICE_URL):
        self.base_url = base_url
        self.timeout = httpx.Timeout(
            connect=5.0,
            read=10.0,
            write=10.0,
            pool=5.0
        )
        self.circuit_breaker = CircuitBreaker(
            name="teachme_service",
            failure_threshold=CIRCUIT_BREAKER_MAX_FAILURES,
            recovery_timeout=CIRCUIT_BREAKER_RESET_TIMEOUT
        )

    async def learn_object(
        self,
        object_name: str,
        description: str,
        image_embedding: Optional[List[float]] = None
    ) -> ServiceCallResult:
        """
        Teach TeachMe Service a new object with its name, description, and optionally its visual embedding.
        The image_embedding comes from Vision Service and lets the system recognize the object later.
        
        Args:
            object_name: Name of the object
            description: Text description
            image_embedding: Optional visual embedding from Vision Service
            
        Returns:
            ServiceCallResult with learning confirmation on success
        """
        try:
            if self.circuit_breaker.state.value == "OPEN":
                return ServiceCallResult(
                    success=False,
                    error_code="TEACHME_SERVICE_CIRCUIT_OPEN",
                    error_message="TeachMe Service is temporarily unavailable"
                )

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                payload = {
                    "object_name": object_name,
                    "description": description
                }
                if image_embedding:
                    payload["image_embedding"] = image_embedding

                response = await client.post(
                    f"{self.base_url}/learn/object",
                    json=payload
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
                        error_code="LEARN_OBJECT_FAILED",
                        error_message=f"TeachMe Service returned {response.status_code}"
                    )

        except httpx.TimeoutException:
            self.circuit_breaker.record_failure()
            return ServiceCallResult(
                success=False,
                error_code="TEACHME_SERVICE_TIMEOUT",
                error_message="TeachMe Service did not respond in time"
            )
        except (httpx.ConnectError, httpx.RequestError):
            self.circuit_breaker.record_failure()
            return ServiceCallResult(
                success=False,
                error_code="TEACHME_SERVICE_UNREACHABLE",
                error_message="Could not connect to TeachMe Service"
            )
        except Exception as e:
            self.circuit_breaker.record_failure()
            return ServiceCallResult(
                success=False,
                error_code="TEACHME_SERVICE_ERROR",
                error_message=str(e)
            )

    async def learn_fact(
        self,
        fact_topic: str,
        fact_content: str,
        user_id: Optional[str] = None
    ) -> ServiceCallResult:
        """
        Teach TeachMe Service a new fact.
        user_id is optional - if provided, the fact is associated with that user's session.
        
        Args:
            fact_topic: Topic of the fact
            fact_content: Actual fact content
            user_id: Optional user association
            
        Returns:
            ServiceCallResult with confirmation on success
        """
        try:
            if self.circuit_breaker.state.value == "OPEN":
                return ServiceCallResult(
                    success=False,
                    error_code="TEACHME_SERVICE_CIRCUIT_OPEN",
                    error_message="TeachMe Service is temporarily unavailable"
                )

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                payload = {
                    "topic": fact_topic,
                    "content": fact_content
                }
                if user_id:
                    payload["user_id"] = user_id

                response = await client.post(
                    f"{self.base_url}/learn/fact",
                    json=payload
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
                        error_code="LEARN_FACT_FAILED",
                        error_message=f"TeachMe Service returned {response.status_code}"
                    )

        except httpx.TimeoutException:
            self.circuit_breaker.record_failure()
            return ServiceCallResult(
                success=False,
                error_code="TEACHME_SERVICE_TIMEOUT",
                error_message="TeachMe Service did not respond in time"
            )
        except (httpx.ConnectError, httpx.RequestError):
            self.circuit_breaker.record_failure()
            return ServiceCallResult(
                success=False,
                error_code="TEACHME_SERVICE_UNREACHABLE",
                error_message="Could not connect to TeachMe Service"
            )
        except Exception as e:
            self.circuit_breaker.record_failure()
            return ServiceCallResult(
                success=False,
                error_code="TEACHME_SERVICE_ERROR",
                error_message=str(e)
            )

    async def retrieve_knowledge(
        self,
        query: str,
        user_id: Optional[str] = None
    ) -> ServiceCallResult:
        """
        Query the knowledge base. Returns relevant facts/objects that match the query.
        
        Args:
            query: Search query
            user_id: Optional user filtering
            
        Returns:
            ServiceCallResult with matching knowledge on success
        """
        try:
            if self.circuit_breaker.state.value == "OPEN":
                return ServiceCallResult(
                    success=False,
                    error_code="TEACHME_SERVICE_CIRCUIT_OPEN",
                    error_message="TeachMe Service is temporarily unavailable"
                )

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                params = {"query": query}
                if user_id:
                    params["user_id"] = user_id

                response = await client.get(
                    f"{self.base_url}/knowledge",
                    params=params
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
                        error_code="KNOWLEDGE_RETRIEVAL_FAILED",
                        error_message=f"TeachMe Service returned {response.status_code}"
                    )

        except httpx.TimeoutException:
            self.circuit_breaker.record_failure()
            return ServiceCallResult(
                success=False,
                error_code="TEACHME_SERVICE_TIMEOUT",
                error_message="TeachMe Service did not respond in time"
            )
        except (httpx.ConnectError, httpx.RequestError):
            self.circuit_breaker.record_failure()
            return ServiceCallResult(
                success=False,
                error_code="TEACHME_SERVICE_UNREACHABLE",
                error_message="Could not connect to TeachMe Service"
            )
        except Exception as e:
            self.circuit_breaker.record_failure()
            return ServiceCallResult(
                success=False,
                error_code="TEACHME_SERVICE_ERROR",
                error_message=str(e)
            )

    async def forget(
        self,
        item_type: str,
        item_id: str
    ) -> ServiceCallResult:
        """
        Remove a learned item. item_type is 'object' or 'fact'. item_id identifies the specific item.
        
        Args:
            item_type: Type of item ('object' or 'fact')
            item_id: ID of the item to forget
            
        Returns:
            ServiceCallResult with confirmation on success
        """
        try:
            if self.circuit_breaker.state.value == "OPEN":
                return ServiceCallResult(
                    success=False,
                    error_code="TEACHME_SERVICE_CIRCUIT_OPEN",
                    error_message="TeachMe Service is temporarily unavailable"
                )

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.delete(
                    f"{self.base_url}/forget/{item_type}/{item_id}"
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
                        error_code="FORGET_FAILED",
                        error_message=f"TeachMe Service returned {response.status_code}"
                    )

        except httpx.TimeoutException:
            self.circuit_breaker.record_failure()
            return ServiceCallResult(
                success=False,
                error_code="TEACHME_SERVICE_TIMEOUT",
                error_message="TeachMe Service did not respond in time"
            )
        except (httpx.ConnectError, httpx.RequestError):
            self.circuit_breaker.record_failure()
            return ServiceCallResult(
                success=False,
                error_code="TEACHME_SERVICE_UNREACHABLE",
                error_message="Could not connect to TeachMe Service"
            )
        except Exception as e:
            self.circuit_breaker.record_failure()
            return ServiceCallResult(
                success=False,
                error_code="TEACHME_SERVICE_ERROR",
                error_message=str(e)
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
                        error_code="TEACHME_UNHEALTHY",
                        error_message=f"Health check returned {response.status_code}"
                    )
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
            return ServiceCallResult(
                success=False,
                error_code="TEACHME_UNREACHABLE",
                error_message="TeachMe Service is not responding"
            )
        except Exception as e:
            return ServiceCallResult(
                success=False,
                error_code="TEACHME_HEALTH_ERROR",
                error_message=str(e)
            )
