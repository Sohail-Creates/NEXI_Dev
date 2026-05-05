"""Model loader service for LLM - handles model initialization and loading."""

import os
import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)


def detect_device() -> str:
    """
    Detect available device (GPU or CPU) with graceful fallback.
    
    Returns:
        'cuda' if GPU available, 'cpu' otherwise
    """
    try:
        import torch
        if torch.cuda.is_available():
            device = 'cuda'
            gpu_count = torch.cuda.device_count()
            gpu_name = torch.cuda.get_device_name(0)
            logger.info(f"✅ GPU Detected: {gpu_name} (Count: {gpu_count})")
            logger.info(f"CUDA Version: {torch.version.cuda}")
            logger.info(f"Device capability: {torch.cuda.get_device_capability(0)}")
            return device
        else:
            logger.info("⚠️  No GPU available - using CPU (inference will be slower)")
            return 'cpu'
    except Exception as e:
        logger.warning(f"GPU detection error: {str(e)[:100]} - falling back to CPU")
        return 'cpu'


class ModelLoader:
    """Loads and manages the SmolLM2-1.7B-Instruct model."""
    
    _instance = None
    _model = None
    _tokenizer = None
    _device = None
    
    def __new__(cls):
        """Singleton pattern - ensure only one model instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize model loader (singleton)."""
        self.logger = logging.getLogger(__name__)
    
    @staticmethod
    def is_model_available(model_path: str) -> bool:
        """Check if model files are available at the specified path."""
        path = Path(model_path)
        
        # Check for essential model files
        required_files = [
            "config.json",
            "model.safetensors",  # or pytorch_model.bin
            "tokenizer.json",
            "tokenizer_config.json",
        ]
        
        if not path.exists():
            return False
        
        # Check if config.json exists
        if not (path / "config.json").exists():
            return False
        
        # Check for model file (either safetensors or pytorch)
        has_model = (
            (path / "model.safetensors").exists() or
            (path / "pytorch_model.bin").exists()
        )
        
        # Check for tokenizer files
        has_tokenizer = (
            (path / "tokenizer.json").exists() or
            (path / "tokenizer_config.json").exists()
        )
        
        return has_model and has_tokenizer
    
    def load_model(
        self,
        model_name: str,
        model_path: str,
        device: str = "auto",
        low_memory: bool = True,
    ):
        """
        Load the model from local path or download from HuggingFace.
        
        Args:
            model_name: HuggingFace model identifier
            model_path: Local path where model should be stored
            device: "auto" (detect), "cpu", or "cuda"
            low_memory: Whether to use memory-efficient settings
        """
        try:
            # DEVICE DETECTION: Auto-detect GPU/CPU if not explicitly provided
            if device == "auto":
                device = detect_device()
                logger.info(f"Device auto-detected: {device}")
            elif device not in ["cpu", "cuda"]:
                logger.warning(f"Invalid device '{device}', auto-detecting...")
                device = detect_device()
            
            # Store device for later reference
            self._device = device
            
            # Import transformers here to allow optional dependency
            from transformers import AutoTokenizer, AutoModelForCausalLM
            import os
            
            self.logger.info(f"Loading model: {model_name}")
            self.logger.info(f"Model path: {model_path}")
            self.logger.info(f"Device: {device}")
            
            # Convert relative path to absolute path
            model_path = os.path.abspath(model_path)
            self.logger.info(f"Absolute model path: {model_path}")
            
            # Diagnose path issues BEFORE attempting to load
            if not os.path.exists(model_path):
                self.logger.error(f"Model path DOES NOT EXIST: {model_path}")
                self.logger.error(f"Current working directory: {os.getcwd()}")
                self.logger.error(f"Please ensure model files are at: {model_path}")
                return False
            
            # Check for essential model files
            config_path = os.path.join(model_path, "config.json")
            tokenizer_path = os.path.join(model_path, "tokenizer.json")
            model_file = None
            for model_filename in ["model.safetensors", "pytorch_model.bin"]:
                candidate = os.path.join(model_path, model_filename)
                if os.path.exists(candidate):
                    model_file = candidate
                    break
            
            if not os.path.exists(config_path):
                self.logger.error(f"Missing config.json at: {config_path}")
                self.logger.error(f"Directory contents: {os.listdir(model_path)}")
                return False
            
            if model_file is None:
                self.logger.error(f"Missing model file (model.safetensors or pytorch_model.bin)")
                self.logger.error(f"Directory contents: {os.listdir(model_path)}")
                return False
            
            if not os.path.exists(tokenizer_path):
                self.logger.warning(f"Tokenizer not found at {tokenizer_path}, will try to download")
            
            self.logger.info(f"Model files validated:")
            self.logger.info(f"  - config.json: OK")
            self.logger.info(f"  - {os.path.basename(model_file)}: OK")
            
            # Create model directory if needed
            os.makedirs(model_path, exist_ok=True)
            
            # Load tokenizer
            self.logger.info("Loading tokenizer...")
            self._tokenizer = AutoTokenizer.from_pretrained(
                model_path,  # Always use local path if available, fall back is handled by exists check
                trust_remote_code=True,
            )
            
            # Set padding token if not set
            if self._tokenizer.pad_token is None:
                self._tokenizer.pad_token = self._tokenizer.eos_token
            
            # Load model with memory optimization
            self.logger.info("Loading model weights...")
            
            kwargs = {
                "trust_remote_code": True,
                "device_map": "auto" if device == "cuda" else None,
            }
            
            # Add memory optimizations
            if low_memory and device == "cpu":
                kwargs["low_cpu_mem_usage"] = True
            
            try:
                self._model = AutoModelForCausalLM.from_pretrained(
                    model_path,  # Use absolute path
                    **kwargs
                )
            except RuntimeError as cuda_error:
                # Handle CUDA-specific errors
                error_str = str(cuda_error).lower()
                if "cuda" in error_str or "gpu" in error_str or "out of memory" in error_str:
                    self.logger.error(f"CUDA/GPU Error: {str(cuda_error)[:100]}")
                    self.logger.warning("Falling back to CPU")
                    device = "cpu"
                    self._device = "cpu"
                    kwargs["device_map"] = None
                    if low_memory:
                        kwargs["low_cpu_mem_usage"] = True
                    self._model = AutoModelForCausalLM.from_pretrained(
                        model_path,
                        **kwargs
                    )
                else:
                    raise
            
            self._device = device
            
            # Move to device if not using device_map
            if device == "cpu":
                try:
                    self._model = self._model.to(device)
                except RuntimeError as e:
                    self.logger.error(f"Error moving model to CPU: {str(e)[:100]}")
                    # Model might already be on CPU
                    pass
            
            # Set to evaluation mode
            self._model.eval()
            
            self.logger.info(f"✅ Model loaded successfully on device: {device}")
            return True
            
        except ImportError:
            self.logger.error(
                "transformers library not found. Install with: pip install transformers torch"
            )
            return False
        except RuntimeError as e:
            # CUDA or memory errors
            if "cuda" in str(e).lower():
                self.logger.error(f"CUDA error loading model: {e}")
                self.logger.info("Try using CPU mode instead: device='cpu'")
            elif "memory" in str(e).lower() or "oom" in str(e).lower():
                self.logger.error(f"Out of memory loading model: {e}")
                self.logger.info("Try enabling low_memory=True or reduce model size")
            else:
                self.logger.error(f"Runtime error loading model: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to load model: {type(e).__name__}: {str(e)}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    def get_model(self):
        """Get loaded model instance."""
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        return self._model
    
    def get_tokenizer(self):
        """Get loaded tokenizer instance."""
        if self._tokenizer is None:
            raise RuntimeError("Tokenizer not loaded. Call load_model() first.")
        return self._tokenizer
    
    def get_device(self) -> str:
        """Get current device (cpu or cuda)."""
        return self._device or "cpu"
    
    def get_device_info(self) -> dict:
        """Get detailed device information."""
        info = {
            "device": self.get_device(),
            "model_loaded": self.is_loaded(),
        }
        
        try:
            import torch
            info["pytorch_version"] = torch.__version__
            info["cuda_available"] = torch.cuda.is_available()
            if torch.cuda.is_available():
                info["cuda_version"] = torch.version.cuda
                info["gpu_count"] = torch.cuda.device_count()
                info["gpu_name"] = torch.cuda.get_device_name(0)
                info["gpu_memory_gb"] = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        except Exception as e:
            info["error"] = f"Failed to get PyTorch info: {str(e)[:50]}"
        
        return info
    
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model is not None and self._tokenizer is not None
    
    def unload_model(self):
        """Release model from memory."""
        import gc
        
        self._model = None
        self._tokenizer = None
        gc.collect()
        
        try:
            import torch
            torch.cuda.empty_cache()
        except ImportError:
            pass
        
        self.logger.info("Model unloaded")
