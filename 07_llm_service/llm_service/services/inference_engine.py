"""Inference engine for LLM service - handles model inference with timeouts."""

import logging
import asyncio
import threading
import time
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

logger = logging.getLogger(__name__)


class InferenceEngine:
    """Handles model inference with timeout and error handling."""
    
    def __init__(self, model_loader, config):
        """
        Initialize inference engine.
        
        Args:
            model_loader: ModelLoader instance
            config: InferenceConfig instance
        """
        self.model_loader = model_loader
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._executor = ThreadPoolExecutor(max_workers=1)  # Single worker to prevent concurrent inference issues
    
    async def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        timeout: Optional[float] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Generate text using the model with async timeout support.
        
        Args:
            prompt: Input prompt
            max_tokens: Max tokens to generate (uses config default if None)
            temperature: Sampling temperature (uses config default if None)
            top_p: Top-p sampling (uses config default if None)
            timeout: Timeout in seconds (uses config default if None)
        
        Returns:
            Tuple of (generated_text, metadata)
        """
        if not self.model_loader.is_loaded():
            raise RuntimeError("Model not loaded")
        
        # Use config defaults if not specified
        max_tokens = max_tokens or self.config.max_response_tokens
        temperature = temperature or self.config.temperature
        top_p = top_p or self.config.top_p
        timeout = timeout or self.config.timeout
        
        try:
            start_time = datetime.now()
            
            # Run in thread pool with timeout
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    self._executor,
                    self._generate_sync,
                    prompt,
                    max_tokens,
                ),
                timeout=timeout,
            )
            
            elapsed = (datetime.now() - start_time).total_seconds()
            
            metadata = {
                "elapsed_seconds": elapsed,
                "model": "SmolLM2-1.7B-Instruct",
                "tokens_generated": len(result.split()),
                "timeout_seconds": timeout,
            }
            
            self.logger.info(f"Generated response in {elapsed:.1f}s")
            return result, metadata
            
        except asyncio.TimeoutError:
            self.logger.error(f"Inference timeout after {timeout}s")
            raise TimeoutError(f"Model inference exceeded {timeout}s timeout")
        except Exception as e:
            self.logger.error(f"Inference failed: {str(e)}")
            raise
    
    def _generate_sync(
        self,
        prompt: str,
        max_tokens: int,
    ) -> str:
        """
        Synchronous generation - runs in thread pool.
        Optimized for speed with minimal overhead.
        """
        try:
            import torch
            
            model = self.model_loader.get_model()
            tokenizer = self.model_loader.get_tokenizer()
            device = self.model_loader._device or "cpu"
            
            # Tokenize prompt
            inputs = tokenizer(
                prompt,
                return_tensors="pt",
                truncation=True,
                max_length=self.config.max_context_tokens,
            )
            
            # Move to device
            for key in inputs:
                if hasattr(inputs[key], "to"):
                    inputs[key] = inputs[key].to(device)
            
            # Generate with optimization flags
            with torch.no_grad():
                outputs = model.generate(
                    inputs["input_ids"],
                    attention_mask=inputs.get("attention_mask"),
                    max_new_tokens=max_tokens,
                    do_sample=False,
                    pad_token_id=tokenizer.pad_token_id,
                    eos_token_id=tokenizer.eos_token_id,
                    use_cache=True,  # ← Faster generation
                )
            
            # Decode and clean
            generated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
            if generated_text.startswith(prompt):
                generated_text = generated_text[len(prompt):].strip()
            
            return generated_text
            
        except Exception as e:
            self.logger.error(f"Inference error: {str(e)}")
            raise
    
    def validate_prompt(self, prompt: str, max_length: int = 16384) -> Tuple[bool, Optional[str]]:
        """
        Validate prompt before inference.
        
        Args:
            prompt: Prompt to validate
            max_length: Maximum prompt length (increased from 8000 to 16384 for better context support)
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not prompt or not isinstance(prompt, str):
            return False, "Prompt must be a non-empty string"
        
        if len(prompt) > max_length:
            return False, f"Prompt exceeds maximum length of {max_length} characters"
        
        # Check for potentially harmful content patterns (basic validation)
        harmful_patterns = [
            "execute code",
            "system prompt",
            "ignore instructions",
        ]
        
        prompt_lower = prompt.lower()
        for pattern in harmful_patterns:
            if pattern in prompt_lower:
                return False, f"Prompt contains restricted content: '{pattern}'"
        
        return True, None
    
    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.
        
        Args:
            text: Text to estimate tokens for
        
        Returns:
            Approximate token count
        """
        try:
            tokenizer = self.model_loader.get_tokenizer()
            tokens = tokenizer.encode(text, add_special_tokens=True)
            return len(tokens)
        except Exception as e:
            self.logger.warning(f"Token estimation failed: {str(e)}")
            # Fallback: rough estimate (1 token ≈ 4 characters)
            return len(text) // 4
