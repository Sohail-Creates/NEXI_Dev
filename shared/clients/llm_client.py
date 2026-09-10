"""LLM Service Client - Interface for Central Server to call LLM service."""

import logging
import asyncio
import random
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import httpx

from shared.utils.circuit_breaker import CircuitBreaker
from shared.models.api_response import APIResponse, ErrorCode
from shared.config import ServiceConfig
from shared.focus_mode import FocusModeClient

logger = logging.getLogger(__name__)


class LLMServiceClient:
    """
    Client for LLM Service (Port 8006).
    
    Handles communication with the local language model inference service.
    Includes circuit breaker protection and automatic retry logic.
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 150.0,  # CPU inference takes time, allow 150s
        max_retries: int = 1,
        focus_mode_client=None,
    ):
        """
        Initialize LLM service client.
        
        Args:
            base_url: LLM service base URL (defaults to env var or localhost:8006)
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries
        """
        if base_url is None:
            base_url = ServiceConfig.get_service_url("llm")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.logger = logging.getLogger(__name__)
        self.focus_mode_client = focus_mode_client or FocusModeClient()
        
        # Circuit breaker configuration
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=15,
            name="llm_service",
        )
        
        # Fallback response templates (when LLM is unavailable)
        self.fallback_responses = {
            "en": [
                "That's an interesting question! Let me think about that.",
                "I'm not sure about that right now, but that's a great question!",
                "That's something worth learning more about.",
                "I'd like to know more about that too!",
                "That's useful information to remember.",
            ],
            "ur": [
                "یہ ایک دلچسپ سوال ہے!",
                "مجھے اس کے بارے میں مزید جاننا پسند ہے۔",
                "یہ سیکھنے کے لیے اہم ہے۔",
                "آپ نے بہتری سے سوال کیا۔",
                "یہ معلومات یاد رکھنے کے قابل ہے۔",
            ]
        }
    
    def _get_fallback_response(self, language: str = "en") -> str:
        """Get a random fallback response when LLM is unavailable."""
        responses = self.fallback_responses.get(language, self.fallback_responses["en"])
        return random.choice(responses)

    async def cooperate_with_focus(self, request_context="conversation"):
        """Queue one non-TeachMe call briefly while TeachMe owns focus."""
        return await self.focus_mode_client.async_defer_if_needed(request_context)
    
    async def generate_response(
        self,
        query: str,
        language: str = "en",
        user_context: Optional[Dict[str, Any]] = None,
        vision_context: Optional[Dict[str, Any]] = None,
        knowledge_items: Optional[List[Dict[str, Any]]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        max_response_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        request_context: str = "conversation",
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Generate AI response with context.
        
        Args:
            query: User's prompt/question
            language: 'en' for English, 'ur' for Urdu
            user_context: User profile information
            vision_context: Current visual/sensor information
            knowledge_items: Relevant knowledge from TeachMe
            conversation_history: Previous conversation turns
            max_response_tokens: Maximum tokens for response
            temperature: Sampling temperature
            top_p: Top-p sampling parameter
        
        Returns:
            Tuple of (success, response_dict)
        """
        await self.cooperate_with_focus(request_context)

        # Check circuit breaker
        if not self.circuit_breaker.is_closed():
            self.logger.warning("LLM service circuit breaker is open")
            return False, {
                "error": "LLM service unavailable (circuit breaker open)",
                "error_code": ErrorCode.SERVICE_UNAVAILABLE,
            }
        
        try:
            # Build request payload
            payload = {
                "query": query,
                "language": language,
                "user_context": user_context,
                "vision_context": vision_context,
                "knowledge_items": knowledge_items or [],
                "conversation_history": conversation_history or [],
            }
            
            # Add optional parameters
            if max_response_tokens is not None:
                payload["max_response_tokens"] = max_response_tokens
            if temperature is not None:
                payload["temperature"] = temperature
            if top_p is not None:
                payload["top_p"] = top_p
            
            # Make request with proper timeout for LLM inference
            async with httpx.AsyncClient() as client:
                # CPU inference takes 20-30s for SmolLM2-1.7B, allow 90s buffer
                response = await asyncio.wait_for(
                    client.post(
                        f"{self.base_url}/api/v1/generate",
                        json=payload,
                        timeout=self.timeout,
                    ),
                    timeout=90.0  # Allow 90s for CPU inference
                )
            
            # Handle response
            if response.status_code == 200:
                result = response.json()
                
                if result.get("success"):
                    self.circuit_breaker.record_success()
                    
                    return True, {
                        "response": result["data"].get("response", ""),
                        "language": result["data"].get("language", language),
                        "metadata": result["data"].get("metadata", {}),
                    }
                else:
                    # Model returned error in response - use fallback
                    self.circuit_breaker.record_failure()
                    self.logger.warning("LLM generation failed, returning fallback response")
                    
                    return True, {  # Still return success=True with fallback
                        "response": self._get_fallback_response(language),
                        "language": language,
                        "metadata": {"fallback": True, "reason": "LLM error"},
                    }
            else:
                # HTTP error - use fallback
                self.circuit_breaker.record_failure()
                self.logger.error(f"LLM service error: {response.status_code}")
                
                return True, {  # Still return success=True with fallback
                    "response": self._get_fallback_response(language),
                    "language": language,
                    "metadata": {"fallback": True, "reason": f"HTTP {response.status_code}"},
                }
        
        except (asyncio.TimeoutError, httpx.TimeoutException):
            self.circuit_breaker.record_failure()
            self.logger.warning("LLM service timeout, returning fallback response")
            
            return True, {  # Still return success=True with fallback
                "response": self._get_fallback_response(language),
                "language": language,
                "metadata": {"fallback": True, "reason": "timeout"},
            }
        
        except (httpx.ConnectError, httpx.RequestError):
            self.circuit_breaker.record_failure()
            self.logger.warning("LLM service unreachable, returning fallback response")
            
            return True, {  # Still return success=True with fallback
                "response": self._get_fallback_response(language),
                "language": language,
                "metadata": {"fallback": True, "reason": "service unavailable"},
            }
        
        except Exception as e:
            self.circuit_breaker.record_failure()
            self.logger.error(f"LLM service error: {str(e)}", exc_info=True)
            
            return True, {  # Still return success=True with fallback
                "response": self._get_fallback_response(language),
                "language": language,
                "metadata": {"fallback": True, "reason": str(e)},
            }
    
    async def health_check(self) -> bool:
        """
        Check if LLM service is healthy.
        
        Returns:
            True if service is healthy, False otherwise
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/health",
                    timeout=5.0,
                )
            
            if response.status_code == 200:
                data = response.json()
                is_healthy = data.get("model_loaded", False)
                
                if is_healthy:
                    self.circuit_breaker.record_success()
                else:
                    self.logger.warning("LLM model not loaded")
                
                return is_healthy
            
            return False
        
        except Exception as e:
            self.logger.warning(f"Health check failed: {str(e)}")
            return False
    
    async def get_model_info(self) -> Optional[Dict[str, Any]]:
        """
        Get information about the loaded model.
        
        Returns:
            Model information dict, or None if unavailable
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/model-info",
                    timeout=5.0,
                )
            
            if response.status_code == 200:
                return response.json()
            
            return None
        
        except Exception as e:
            self.logger.warning(f"Failed to get model info: {str(e)}")
            return None
    
    def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """
        Get circuit breaker status.
        
        Returns:
            Circuit breaker state information
        """
        return {
            "is_closed": self.circuit_breaker.is_closed(),
            "failure_count": self.circuit_breaker.failure_count,
            "success_count": self.circuit_breaker.success_count,
            "state": "closed" if self.circuit_breaker.is_closed() else "open",
        }
