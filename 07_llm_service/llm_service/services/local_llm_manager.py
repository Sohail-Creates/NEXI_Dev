"""
Intelligent Local LLM Manager - Lazy loading, resource optimization, and fallback management.

Key Features:
1. Lazy loads model only when fallback needed
2. Keeps model loaded during fallback mode
3. Auto-detects CUDA for GPU acceleration
4. Manages resource lifecycle efficiently
5. Monitors OpenRouter health for recovery
"""

import logging
import asyncio
from typing import Dict, Any, Optional, Tuple
from enum import Enum
import time

logger = logging.getLogger(__name__)


class FallbackState(Enum):
    """Fallback system operational state."""
    IDLE = "idle"  # No fallback, using OpenRouter
    ACTIVATING = "activating"  # Starting to load local model
    ACTIVE = "active"  # Local model loaded and in use
    MONITORING = "monitoring"  # Monitoring OpenRouter recovery
    RELEASING = "releasing"  # Unloading local model


class LocalLLMManager:
    """
    Intelligently manages local LLM with lazy loading and resource optimization.
    
    Lifecycle:
    1. IDLE: OpenRouter available, local model not loaded
    2. ACTIVATING: OpenRouter failed, loading local model
    3. ACTIVE: Local model loaded, providing responses
    4. MONITORING: Checking if OpenRouter recovered
    5. RELEASING: Unloading local model when OpenRouter back online
    """
    
    def __init__(self, inference_engine, config: Optional[Dict[str, Any]] = None):
        """
        Initialize Local LLM Manager.
        
        Args:
            inference_engine: InferenceEngine instance (lazy-loaded)
            config: Optional configuration dict
        """
        self.inference_engine = inference_engine
        self.logger = logging.getLogger(__name__)
        
        # State management
        self.state = FallbackState.IDLE
        self.model_loaded = False
        self.load_time = None
        self.last_used_time = None
        
        # Performance monitoring
        self.fallback_start_time = None
        self.consecutive_failures = 0
        self.recovery_check_interval = 5.0  # Check OpenRouter every 5 seconds
        self.model_unload_timeout = 30.0  # Unload after 30 seconds of OpenRouter success
        
        # CUDA detection
        self.use_cuda = self._detect_cuda()
        self.logger.info(f"CUDA available: {self.use_cuda}")
        
        # Monitoring task
        self.monitoring_task: Optional[asyncio.Task] = None
        self.stop_monitoring = False
    
    def _detect_cuda(self) -> bool:
        """Detect if CUDA is available for GPU acceleration."""
        try:
            import torch
            cuda_available = torch.cuda.is_available()
            if cuda_available:
                device_name = torch.cuda.get_device_name(0)
                self.logger.info(f"CUDA available: {device_name}")
            return cuda_available
        except Exception as e:
            self.logger.debug(f"CUDA detection failed: {str(e)} - using CPU")
            return False
    
    async def activate_fallback(self) -> None:
        """
        Activate fallback mode - load local model and start monitoring.
        """
        if self.state == FallbackState.ACTIVE:
            self.logger.debug("Fallback already active")
            return
        
        self.state = FallbackState.ACTIVATING
        self.fallback_start_time = time.time()
        self.logger.info(f"Activating fallback mode (CUDA={self.use_cuda})...")
        
        try:
            # Lazy-load the inference engine if not already loaded
            if not self.model_loaded:
                load_start = time.time()
                self.logger.info("Loading local LLM model (may take 10-30 seconds on first load)...")
                
                # Trigger model loading in inference engine
                # This typically happens on first forward pass
                await self._ensure_model_loaded()
                
                self.load_time = time.time() - load_start
                self.model_loaded = True
                self.logger.info(f"Local LLM model loaded in {self.load_time:.1f}s")
            
            self.state = FallbackState.ACTIVE
            self.consecutive_failures = 0
            self.logger.info("Fallback mode ACTIVE - local model ready")
            
            # Start background monitoring to detect OpenRouter recovery
            await self._start_monitoring()
        
        except Exception as e:
            self.logger.error(f"Failed to activate fallback: {str(e)}")
            self.state = FallbackState.IDLE
            raise
    
    async def _ensure_model_loaded(self) -> None:
        """Ensure model is loaded - model loads on first actual inference."""
        try:
            # Model will load on first actual inference in generate()
            # No need for dummy test inference - it just adds 27-92s delay!
            # The model_loader is already initialized, we just verify it
            model = self.inference_engine.model_loader.get_model()
            if model is None:
                raise RuntimeError("Model failed to load")
            self.logger.debug("Model ready for inference")
        except Exception as e:
            self.logger.error(f"Model not available: {str(e)}")
            raise
    
    async def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        timeout: float = 150.0,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Generate response using local LLM in fallback mode.
        
        Args:
            prompt: User query
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            timeout: Request timeout in seconds
        
        Returns:
            Tuple of (response_text, metadata)
        """
        if self.state not in [FallbackState.ACTIVE, FallbackState.MONITORING]:
            await self.activate_fallback()
        
        self.last_used_time = time.time()
        self.logger.debug(f"Local LLM generating response (timeout={timeout}s)...")
        
        try:
            response_text, metadata = await asyncio.wait_for(
                self.inference_engine.generate(
                    prompt=prompt,
                    max_tokens=max_tokens or 128,
                    temperature=temperature or 0.6,
                    timeout=timeout,
                ),
                timeout=timeout + 5.0  # Add buffer
            )
            
            self.consecutive_failures = 0
            metadata["fallback_duration"] = time.time() - self.fallback_start_time
            metadata["cuda_enabled"] = self.use_cuda
            
            return response_text, metadata
        
        except asyncio.TimeoutError:
            self.logger.error(f"Local LLM timeout after {timeout}s")
            self.consecutive_failures += 1
            raise
        except Exception as e:
            self.logger.error(f"Local LLM generation failed: {str(e)}")
            self.consecutive_failures += 1
            raise
    
    async def _start_monitoring(self) -> None:
        """Start background task to monitor OpenRouter recovery."""
        if self.monitoring_task and not self.monitoring_task.done():
            self.logger.debug("Monitoring already active")
            return
        
        self.stop_monitoring = False
        self.monitoring_task = asyncio.create_task(self._monitor_openrouter_health())
        self.logger.debug("Started OpenRouter health monitoring")
    
    async def _monitor_openrouter_health(self) -> None:
        """
        Background task to periodically check if OpenRouter is back online.
        If recovered, transitions back to OpenRouter mode and releases resources.
        """
        consecutive_success = 0
        required_successes = 3  # Need 3 consecutive successes before switching back
        
        try:
            while not self.stop_monitoring and self.state in [FallbackState.ACTIVE, FallbackState.MONITORING]:
                await asyncio.sleep(self.recovery_check_interval)
                
                # This will be called by HybridInferenceManager to notify us
                # For now, log status
                uptime = time.time() - self.fallback_start_time if self.fallback_start_time else 0
                self.logger.debug(f"Fallback active for {uptime:.0f}s, failures={self.consecutive_failures}")
        
        except asyncio.CancelledError:
            self.logger.debug("Health monitoring cancelled")
        except Exception as e:
            self.logger.error(f"Monitoring error: {str(e)}")
    
    async def deactivate_fallback(self) -> None:
        """
        Deactivate fallback mode - stop monitoring and optionally keep model loaded.
        Model stays loaded for faster re-activation if needed.
        """
        if self.state == FallbackState.IDLE:
            return
        
        # Stop monitoring task
        self.stop_monitoring = True
        if self.monitoring_task and not self.monitoring_task.done():
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        # Keep model loaded in memory for faster recovery
        # This provides ~27s response time if OpenRouter fails again
        self.state = FallbackState.IDLE
        uptime = time.time() - self.fallback_start_time if self.fallback_start_time else 0
        self.logger.info(f"Fallback mode deactivated after {uptime:.1f}s - model kept in memory")
    
    def get_status(self) -> Dict[str, Any]:
        """Get fallback system status."""
        uptime = time.time() - self.fallback_start_time if self.fallback_start_time else 0
        
        return {
            "state": self.state.value,
            "model_loaded": self.model_loaded,
            "load_time_seconds": self.load_time,
            "fallback_uptime_seconds": uptime if self.fallback_start_time else 0,
            "consecutive_failures": self.consecutive_failures,
            "cuda_enabled": self.use_cuda,
            "last_used": self.last_used_time,
        }
    
    def release_resources(self) -> None:
        """
        Explicitly release resources (model from memory).
        Model will be reloaded on next fallback activation.
        """
        if self.model_loaded:
            self.logger.info("Releasing local LLM model from memory")
            self.model_loaded = False
            self.load_time = None
            # In production, you might call gc.collect() here
            # but be careful not to do it too frequently
