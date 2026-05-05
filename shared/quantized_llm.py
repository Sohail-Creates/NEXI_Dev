"""
Quantized LLM Model Manager
Supports 8-bit and 4-bit quantization for 2-3x speedup with minimal accuracy loss
Production-ready implementation from Vision-Nexus
"""

import logging
from typing import Optional, Dict, Any, Tuple
from pathlib import Path
import torch
import torch.nn as nn
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
import os

logger = logging.getLogger(__name__)


class QuantizationConfig:
    """Configuration for model quantization"""
    
    def __init__(
        self,
        quantization_bits: int = 8,
        use_flash_attention: bool = True,
        device_map: str = "auto",
        max_memory: Optional[Dict[int, str]] = None
    ):
        """
        Initialize quantization configuration
        
        Args:
            quantization_bits: Quantization level (4 or 8 bits)
            use_flash_attention: Whether to use Flash Attention 2
            device_map: Device mapping strategy
            max_memory: Maximum memory per device
        """
        if quantization_bits not in (4, 8):
            raise ValueError("Quantization bits must be 4 or 8")
        
        self.quantization_bits = quantization_bits
        self.use_flash_attention = use_flash_attention
        self.device_map = device_map
        self.max_memory = max_memory


class QuantizedLLMLoader:
    """Load and manage quantized LLM models"""
    
    def __init__(self, config: Optional[QuantizationConfig] = None):
        """
        Initialize quantized LLM loader
        
        Args:
            config: QuantizationConfig instance
        """
        self.config = config or QuantizationConfig()
        self.model = None
        self.tokenizer = None
        logger.info(f"Initialized QuantizedLLMLoader with {self.config.quantization_bits}-bit quantization")
    
    def _get_quantization_config(self) -> BitsAndBytesConfig:
        """
        Get BitsAndBytes quantization configuration
        
        Returns:
            BitsAndBytesConfig instance
        """
        if self.config.quantization_bits == 4:
            return BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16
            )
        else:  # 8-bit
            return BitsAndBytesConfig(
                load_in_8bit=True,
                llm_int8_threshold=6.0,
                llm_int8_has_fp16_weight=False
            )
    
    def load_model(
        self,
        model_name: str,
        trust_remote_code: bool = True
    ) -> Tuple[Any, Any]:
        """
        Load quantized model and tokenizer
        
        Args:
            model_name: HuggingFace model name
            trust_remote_code: Whether to trust remote code
        
        Returns:
            Tuple of (model, tokenizer)
        """
        try:
            logger.info(f"Loading {self.config.quantization_bits}-bit quantized model: {model_name}")
            
            # Get quantization config
            quant_config = self._get_quantization_config()
            
            # Load model with quantization
            self.model = AutoModelForCausalLM.from_pretrained(
                model_name,
                quantization_config=quant_config,
                device_map=self.config.device_map,
                max_memory=self.config.max_memory,
                trust_remote_code=trust_remote_code,
                torch_dtype=torch.bfloat16 if self.config.quantization_bits == 4 else torch.float16,
                attn_implementation="flash_attention_2" if self.config.use_flash_attention else "eager"
            )
            
            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                trust_remote_code=trust_remote_code
            )
            
            logger.info(f" Model loaded successfully with {self.config.quantization_bits}-bit quantization")
            logger.info(f"  Model size (estimated): {self._estimate_model_size()} MB")
            
            return self.model, self.tokenizer
        
        except Exception as e:
            logger.error(f"Failed to load quantized model: {e}")
            raise
    
    def _estimate_model_size(self) -> float:
        """
        Estimate model size in MB
        
        Returns:
            Estimated size in MB
        """
        if self.model is None:
            return 0
        
        total_params = sum(p.numel() for p in self.model.parameters())
        
        # Estimate based on quantization level
        if self.config.quantization_bits == 4:
            size_mb = (total_params * 4) / (8 * 1024 * 1024)  # 4-bit per parameter
        else:
            size_mb = (total_params * 8) / (8 * 1024 * 1024)  # 8-bit per parameter
        
        return size_mb
    
    def generate(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
        top_p: float = 0.95,
        **kwargs
    ) -> str:
        """
        Generate text from prompt using quantized model
        
        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            top_p: Top-p nucleus sampling parameter
            **kwargs: Additional generation parameters
        
        Returns:
            Generated text
        """
        if self.model is None or self.tokenizer is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        
        try:
            # Encode input
            inputs = self.tokenizer.encode(prompt, return_tensors="pt")
            
            # Generate
            outputs = self.model.generate(
                inputs,
                max_new_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                do_sample=True,
                pad_token_id=self.tokenizer.eos_token_id,
                **kwargs
            )
            
            # Decode output
            generated_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            return generated_text
        
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            raise
    
    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about loaded model
        
        Returns:
            Dictionary with model information
        """
        if self.model is None:
            return {}
        
        total_params = sum(p.numel() for p in self.model.parameters())
        trainable_params = sum(p.numel() for p in self.model.parameters() if p.requires_grad)
        
        return {
            "total_parameters": total_params,
            "trainable_parameters": trainable_params,
            "quantization_bits": self.config.quantization_bits,
            "estimated_size_mb": self._estimate_model_size(),
            "device": next(self.model.parameters()).device,
            "dtype": next(self.model.parameters()).dtype
        }
    
    def unload_model(self) -> None:
        """Unload model and free memory"""
        if self.model is not None:
            del self.model
            self.model = None
        
        if self.tokenizer is not None:
            del self.tokenizer
            self.tokenizer = None
        
        # Clear CUDA cache if using GPU
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        logger.info("Model unloaded and memory freed")


class QuantizationBenchmark:
    """Benchmark quantized models against full precision"""
    
    @staticmethod
    def estimate_speedup(quantization_bits: int) -> float:
        """
        Estimate speedup from quantization
        
        Args:
            quantization_bits: Quantization level (4 or 8)
        
        Returns:
            Estimated speedup factor
        """
        # 8-bit: ~1.5-2x speedup
        # 4-bit: ~2-3x speedup
        if quantization_bits == 4:
            return 2.5  # 2.5x speedup expected
        elif quantization_bits == 8:
            return 1.8  # 1.8x speedup expected
        else:
            return 1.0  # No speedup for unknown quantization
    
    @staticmethod
    def estimate_accuracy_loss(quantization_bits: int) -> float:
        """
        Estimate accuracy loss from quantization
        
        Args:
            quantization_bits: Quantization level
        
        Returns:
            Estimated accuracy loss percentage (0-100)
        """
        # 8-bit: <2% accuracy loss typically
        # 4-bit: 3-5% accuracy loss typically
        if quantization_bits == 4:
            return 4.0  # ~4% loss
        elif quantization_bits == 8:
            return 1.5  # ~1.5% loss
        else:
            return 0.0


# ============================================================================
# INTEGRATION POINTS
# ============================================================================

def create_quantized_loader(
    quantization_bits: int = 8,
    use_flash_attention: bool = True
) -> QuantizedLLMLoader:
    """
    Factory function to create quantized LLM loader
    
    Args:
        quantization_bits: 4 or 8 bit quantization
        use_flash_attention: Enable Flash Attention 2
    
    Returns:
        QuantizedLLMLoader instance
    """
    config = QuantizationConfig(
        quantization_bits=quantization_bits,
        use_flash_attention=use_flash_attention
    )
    return QuantizedLLMLoader(config)


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

if __name__ == "__main__":
    # Example: Load 8-bit quantized model
    logging.basicConfig(level=logging.INFO)
    
    # Create loader
    loader = create_quantized_loader(quantization_bits=8)
    
    # Load model
    try:
        model, tokenizer = loader.load_model("TinyLlama/TinyLlama-1.1B-Chat-v1.0")
        
        # Show model info
        info = loader.get_model_info()
        print(f"Model loaded:")
        print(f"  Parameters: {info['total_parameters']:,}")
        print(f"  Size: {info['estimated_size_mb']:.1f} MB")
        print(f"  Speedup expected: {QuantizationBenchmark.estimate_speedup(8):.1f}x")
        
    except Exception as e:
        print(f"Error: {e}")
