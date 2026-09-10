"""OpenRouter API client for high-speed inference with chat completions."""

import logging
import os
from typing import Dict, List, Any, Optional, Tuple
import requests
import time
from llm_service.config import OPENROUTER_MODEL, OPENROUTER_BASE_URL, OPENROUTER_API_KEY_ENV

logger = logging.getLogger(__name__)


class OpenRouterClient:
    """
    Client for the configured OpenRouter model.
    
    Provides online chat completions.
    """
    
    def __init__(self, api_key: Optional[str] = None, timeout: float = 30.0):
        """
        Initialize OpenRouter client.
        
        Args:
            api_key: OpenRouter API key (defaults to env var)
            timeout: Request timeout in seconds
        """
        self.api_key = api_key or os.getenv(OPENROUTER_API_KEY_ENV)
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)
        self.base_url = OPENROUTER_BASE_URL.rstrip("/")
        self.model = OPENROUTER_MODEL
        if not self.model:
            raise ValueError("OPENROUTER_MODEL must be configured")
        self.is_available = bool(self.api_key)
        
        if not self.api_key:
            self.logger.warning("OpenRouter API key not found - generation unavailable")
    
    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 128,
        temperature: float = 0.6,
        timeout: Optional[float] = None,
    ) -> Tuple[str, Dict[str, Any], bool]:
        """
        Generate response using OpenRouter API.
        
        Args:
            prompt: User query/prompt
            system_prompt: System instructions
            max_tokens: Max response tokens
            temperature: Sampling temperature
            timeout: Request timeout
        
        Returns:
            Tuple of (response_text, metadata, success)
            - response_text: Generated text or empty on failure
            - metadata: Time taken, model info, etc.
            - success: Whether generation succeeded
        """
        if not self.is_available:
            return "", {"error": "API key not configured"}, False
        
        timeout = timeout or self.timeout
        start_time = time.time()
        
        try:
            url = f"{self.base_url}/chat/completions"
            
            # Build messages for chat/completions format
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            payload = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": 0.9,
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            self.logger.debug(f"Calling OpenRouter API: {url}")
            
            # Make request
            response = requests.post(url, json=payload, headers=headers, timeout=timeout)
            elapsed = time.time() - start_time
            
            # Check for success
            if response.status_code == 200:
                data = response.json()
                
                # Extract response text from chat/completions format
                if "choices" in data and len(data["choices"]) > 0:
                    choice = data["choices"][0]
                    if "message" in choice and "content" in choice["message"]:
                        text = choice["message"]["content"]
                        
                        if text:
                            metadata = {
                                "elapsed_seconds": elapsed,
                                "model": self.model,
                                "source": "openrouter",
                                "tokens_generated": len(text.split()),
                            }
                            self.logger.info(f"OpenRouter response in {elapsed:.2f}s")
                            return text, metadata, True
                
                # No valid response
                self.logger.warning("OpenRouter returned no text content")
                return "", {"error": "No text in response", "elapsed": elapsed}, False
            
            # Handle API errors
            elif response.status_code == 429:
                self.logger.warning("OpenRouter rate limit hit")
                return "", {"error": "rate_limited", "elapsed": elapsed}, False
            
            elif response.status_code == 400:
                error_data = response.json() if response.text else {}
                error_msg = "Bad request"
                if isinstance(error_data.get("error"), dict):
                    error_msg = error_data.get("error", {}).get("message", error_msg)
                else:
                    error_msg = str(error_data.get("error", error_msg))
                self.logger.warning(f"OpenRouter bad request: {error_msg}")
                return "", {"error": f"bad_request: {error_msg}", "elapsed": elapsed}, False
            
            elif response.status_code >= 500:
                self.logger.warning(f"OpenRouter server error {response.status_code}")
                return "", {"error": "server_error", "elapsed": elapsed}, False
            
            else:
                self.logger.warning(f"OpenRouter error {response.status_code}")
                error_detail = response.text[:200] if response.text else "No details"
                self.logger.debug(f"OpenRouter error response: {error_detail}")
                return "", {"error": f"http_{response.status_code}", "elapsed": elapsed}, False
        
        except requests.exceptions.Timeout:
            elapsed = time.time() - start_time
            self.logger.warning(f"OpenRouter request timed out after {elapsed:.1f}s")
            return "", {"error": "timeout", "elapsed": elapsed}, False
        
        except requests.exceptions.ConnectionError:
            elapsed = time.time() - start_time
            self.logger.warning("OpenRouter connection error")
            return "", {"error": "offline", "elapsed": elapsed}, False
        
        except Exception as e:
            elapsed = time.time() - start_time
            self.logger.error(f"OpenRouter error: {str(e)}")
            return "", {"error": str(e), "elapsed": elapsed}, False
    
    def is_healthy(self) -> bool:
        """Check if OpenRouter API is accessible."""
        if not self.is_available:
            return False
        
        try:
            # Quick health check
            response = requests.get(
                f"{self.base_url}/models",
                timeout=5,
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            return 200 <= response.status_code < 300
        except Exception as e:
            self.logger.debug(f"OpenRouter health check failed: {str(e)}")
            return False
