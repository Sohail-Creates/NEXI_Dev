"""Hybrid inference manager - OpenRouter with optimized local LLM fallback."""

import logging
import asyncio
from typing import Dict, Any, Optional, Tuple
from enum import Enum
import time

from llm_service.services.local_llm_manager import LocalLLMManager, FallbackState

logger = logging.getLogger(__name__)


class InferenceSource(Enum):
    """Source of inference response."""
    OPENROUTER = "openrouter"
    LOCAL_LLM = "local_llm"
    FALLBACK = "fallback"


class HybridInferenceManager:
    """
    Manages hybrid inference - tries OpenRouter first, falls back to locally-optimized LLM.
    
    Key Features:
    1. OpenRouter primary (1-5s response)
    2. Intelligent fallback with lazy loading (27-92s response)
    3. CUDA auto-detection for GPU acceleration
    4. Background health monitoring for OpenRouter recovery
    5. Automatic resource lifecycle management
    
    Fallback triggers:
    - No internet connection (offline)
    - OpenRouter rate limit hit (429)
    - OpenRouter server error (500+)
    - OpenRouter request timeout
    - OpenRouter API error
    """
    
    def __init__(self, openrouter_client, local_inference_engine):
        """
        Initialize hybrid manager with intelligent fallback.
        
        Args:
            openrouter_client: OpenRouterClient instance
            local_inference_engine: InferenceEngine instance (lazy-loaded)
        """
        self.openrouter = openrouter_client
        self.fallback_manager = LocalLLMManager(local_inference_engine)
        self.logger = logging.getLogger(__name__)
        
        # State tracking
        self.in_fallback_mode = False
        self.consecutive_openrouter_failures = 0
        self.consecutive_openrouter_successes = 0
        self.recovery_attempt_count = 0
        
        # Performance tracking
        self.last_openrouter_check_time = None
        self.recovery_check_interval = 15.0  # Re-test OpenRouter every 15s during fallback
        self.min_successes_for_recovery = 2  # Need 2 successful OpenRouter calls to exit fallback
    
    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        language: str = "en",
        try_openrouter_first: bool = True,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Generate response with intelligent fallback and recovery.
        
        Strategy:
        1. Normal Mode (OpenRouter available):
           - Try OpenRouter (1-5s)
           - If fails → Enter fallback mode
        
        2. Fallback Mode (OpenRouter down):
           - Use loaded local LLM (27-92s, but optimized)
           - Every 15s, test if OpenRouter recovered
           - If OpenRouter back online → Exit fallback, use OpenRouter
        
        3. Always returns a response (never timeouts due to fallback)
        
        Args:
            prompt: User query
            system_prompt: System instructions
            max_tokens: Max response tokens
            temperature: Sampling temperature
            language: "en" or "ur"
            try_openrouter_first: Whether to try OpenRouter (False = use local only)
        
        Returns:
            Tuple of (response_text, metadata) with detailed telemetry
        """
        metadata = {
            "language": language,
            "primary_source": None,
            "fallback_used": False,
            "fallback_mode": self.in_fallback_mode,
            "error_reason": None,
            "recovery_attempted": False,
        }
        
        # If we're in fallback mode, periodically check for OpenRouter recovery
        if self.in_fallback_mode:
            should_check_recovery = (
                self.last_openrouter_check_time is None or
                time.time() - self.last_openrouter_check_time > self.recovery_check_interval
            )
            
            if should_check_recovery:
                recovery_result = await self._check_openrouter_recovery()
                metadata["recovery_attempted"] = True
                metadata["recovery_check_time"] = time.time()
                
                if recovery_result:
                    # OpenRouter has recovered - exit fallback mode
                    self.logger.info("OpenRouter recovered - exiting fallback mode")
                    await self.fallback_manager.deactivate_fallback()
                    self.in_fallback_mode = False
                    self.consecutive_openrouter_successes = 0
                    self.recovery_attempt_count = 0
        
        # Try OpenRouter first if enabled and not skipping due to fallback
        if try_openrouter_first and self.openrouter.is_available and not self.in_fallback_mode:
            self.logger.debug("Attempting OpenRouter generation...")
            
            try:
                openrouter_text, openrouter_meta, openrouter_success = await asyncio.wait_for(
                    self.openrouter.generate(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        max_tokens=max_tokens or 128,
                        temperature=temperature or 0.6,
                        timeout=30.0,
                    ),
                    timeout=35.0
                )
                
                if openrouter_success:
                    # OpenRouter succeeded - use it
                    self.consecutive_openrouter_failures = 0
                    self.consecutive_openrouter_successes += 1
                    
                    metadata["primary_source"] = InferenceSource.OPENROUTER.value
                    metadata["openrouter_response_time"] = openrouter_meta.get("elapsed_seconds", 0)
                    self.logger.info(f"OpenRouter success ({openrouter_meta.get('elapsed_seconds', 0):.2f}s)")
                    return openrouter_text, metadata
                
                else:
                    # OpenRouter failed - enter fallback mode
                    self.consecutive_openrouter_failures += 1
                    error_reason = openrouter_meta.get("error", "unknown")
                    metadata["error_reason"] = error_reason
                    metadata["openrouter_attempt_time"] = openrouter_meta.get("elapsed_seconds", 0)
                    
                    self.logger.warning(f"OpenRouter failed ({error_reason}) - activating fallback")
                    self.in_fallback_mode = True
                    await self.fallback_manager.activate_fallback()
                    metadata["fallback_used"] = True
                    metadata["fallback_mode"] = True
            
            except asyncio.TimeoutError:
                self.consecutive_openrouter_failures += 1
                self.logger.warning("OpenRouter timeout - activating fallback")
                self.in_fallback_mode = True
                await self.fallback_manager.activate_fallback()
                metadata["fallback_used"] = True
                metadata["fallback_mode"] = True
                metadata["error_reason"] = "timeout"
            
            except Exception as e:
                self.consecutive_openrouter_failures += 1
                self.logger.error(f"OpenRouter error: {str(e)} - falling back")
                self.in_fallback_mode = True
                await self.fallback_manager.activate_fallback()
                metadata["fallback_used"] = True
                metadata["fallback_mode"] = True
                metadata["error_reason"] = str(e)
        
        # Use fallback local LLM with optimized performance
        self.logger.debug("Using local LLM for generation...")
        
        try:
            local_text, local_meta = await self.fallback_manager.generate(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=150.0 if self.in_fallback_mode else 30.0,  # Allow longer timeout in fallback mode
            )
            
            metadata["primary_source"] = InferenceSource.LOCAL_LLM.value
            metadata["local_response_time"] = local_meta.get("elapsed_seconds", 0)
            metadata["cuda_enabled"] = local_meta.get("cuda_enabled", False)
            
            if self.in_fallback_mode:
                metadata["primary_source"] = InferenceSource.FALLBACK.value
                metadata["fallback_mode"] = True
                self.logger.info(f"Fallback LLM response ({local_meta.get('elapsed_seconds', 0):.1f}s)")
            else:
                self.logger.info(f"Local LLM response ({local_meta.get('elapsed_seconds', 0):.1f}s)")
            
            # Merge metadata
            metadata.update(local_meta)
            metadata["fallback_manager_status"] = self.fallback_manager.get_status()
            
            return local_text, metadata
        
        except Exception as e:
            self.logger.error(f"Local LLM also failed: {str(e)}")
            
            # Both failed - this is a critical error
            metadata["error"] = "Both OpenRouter and local LLM failed"
            metadata["local_error"] = str(e)
            
            return f"[Error: Unable to generate response - {str(e)}]", metadata
    
    async def _check_openrouter_recovery(self) -> bool:
        """
        Check if OpenRouter has recovered while in fallback mode.
        
        Returns:
            True if OpenRouter is healthy, False otherwise
        """
        try:
            self.last_openrouter_check_time = time.time()
            
            # Quick health check using is_healthy()
            if self.openrouter.is_healthy():
                self.consecutive_openrouter_successes += 1
                self.logger.debug(f"OpenRouter recovery check passed ({self.consecutive_openrouter_successes}/{self.min_successes_for_recovery})")
                
                # Require minimum successes before trusting that OpenRouter is back
                return self.consecutive_openrouter_successes >= self.min_successes_for_recovery
            else:
                self.consecutive_openrouter_successes = 0
                self.logger.debug("OpenRouter still recovering...")
                return False
        
        except Exception as e:
            self.consecutive_openrouter_successes = 0
            self.logger.debug(f"Recovery check error: {str(e)}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive hybrid system status."""
        return {
            "openrouter_available": self.openrouter.is_available,
            "openrouter_healthy": self.openrouter.is_healthy() if self.openrouter.is_available else False,
            "in_fallback_mode": self.in_fallback_mode,
            "consecutive_failures": self.consecutive_openrouter_failures,
            "consecutive_successes": self.consecutive_openrouter_successes,
            "fallback_manager": self.fallback_manager.get_status(),
            "hybrid_mode_enabled": self.openrouter.is_available,
            "recovery_check_interval": self.recovery_check_interval,
        }
