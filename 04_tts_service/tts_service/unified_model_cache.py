"""
Unified Model Cache
Single cache managing all TTS models (English + Urdu).
Replaces separate model_cache.py and urdu_engine.py logic.
Thread-safe, timeout-based unloading, LRU eviction.
"""

import os
import io
import logging
import threading
import time
import wave
from typing import Optional, Dict, Any, Tuple
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class UnifiedModelCache:
    """
    Single cache for all TTS models (English Piper + Urdu Rehnuma).
    
    Features:
    - One cache for all languages/voices
    - LRU eviction when max models reached
    - Timeout-based automatic unload
    - Thread-safe operations with RLock
    - Metrics collection (hit rate, loads)
    - Support for both Piper and Rehnuma ONNX models
    
    Voice Mapping:
    - English: ryan, jenny (Piper models)
    - Urdu: shahid (Rehnuma model, Piper-compatible)
    """
    
    # PHASE 1.2: Standardized to SHORT voice IDs + ONNX filenames mapping
    VOICE_MODEL_MAP = {
        "ryan": {
            "language": "english",
            "model_file": "en_US-ryan-high.onnx",
            "config_file": "en_US-ryan-high.onnx.json",
            "gender": "male",
        },
        "jenny": {
            "language": "english",
            "model_file": "en_GB-jenny_dioco-medium.onnx",
            "config_file": "en_GB-jenny_dioco-medium.onnx.json",
            "gender": "female",
        },
        "shahid": {
            "language": "urdu",
            "model_file": "ur_ma-rehnuma_shahid-low.onnx",
            "config_file": "ur_ma-rehnuma_shahid-low.onnx.json",
            "gender": "male",
        },
    }
    
    def __init__(
        self,
        models_dir: str = "models",
        model_timeout: int = 3600,
        max_cached_models: int = 2,
    ):
        """
        Initialize Unified Model Cache.
        
        Args:
            models_dir: Root directory containing model files
            model_timeout: Seconds to keep unused model (0 = never unload)
            max_cached_models: Maximum models to keep in memory simultaneously
        """
        self.models_dir = Path(models_dir)
        self.model_timeout = model_timeout
        self.max_cached_models = max_cached_models
        
        # Cached models
        self._models: Dict[str, Any] = {}  # voice_id -> PiperVoice
        self._load_times: Dict[str, datetime] = {}
        self._access_times: Dict[str, datetime] = {}
        
        # Thread safety
        self.lock = threading.RLock()
        
        # Metrics
        self.cache_hits = 0
        self.cache_misses = 0
        self.loads_total = 0
        self.evictions_total = 0
        
        logger.info(
            f"UnifiedModelCache initialized "
            f"(dir: {self.models_dir}, timeout: {model_timeout}s, "
            f"max_cached: {max_cached_models})"
        )
    
    def get_model(self, voice_id: str):
        """
        Get model from cache or load if not present.
        
        Thread-safe. Returns cached model if available, otherwise loads from disk.
        
        Args:
            voice_id: Voice identifier (ryan, jenny, shahid)
            
        Returns:
            Loaded Piper voice object
            
        Raises:
            ValueError: If voice_id unknown
            RuntimeError: If model load fails
        """
        if voice_id not in self.VOICE_MODEL_MAP:
            raise ValueError(f"Unknown voice: {voice_id}")
        
        with self.lock:
            # Cache hit - return existing model
            if voice_id in self._models:
                self.cache_hits += 1
                self._access_times[voice_id] = datetime.now()
                logger.debug(f"Cache HIT: {voice_id}")
                return self._models[voice_id]
            
            # Cache miss - need to load
            self.cache_misses += 1
            self.loads_total += 1
            
            logger.debug(
                f"Cache MISS: {voice_id} "
                f"(cached: {len(self._models)}/{self.max_cached_models})"
            )
            
            # Enforce max models in memory
            while len(self._models) >= self.max_cached_models:
                self._evict_lru()
            
            # Load model from disk
            model = self._load_model_file(voice_id)
            
            self._models[voice_id] = model
            self._load_times[voice_id] = datetime.now()
            self._access_times[voice_id] = datetime.now()
            
            return model
    
    def unload_model(self, voice_id: str) -> bool:
        """
        Explicitly unload a model from cache.
        Called by speaker manager when switching speakers.
        
        Args:
            voice_id: Voice identifier to unload
            
        Returns:
            True if model was unloaded, False if not cached
        """
        with self.lock:
            if voice_id in self._models:
                logger.info(f"Unloading model: {voice_id}")
                del self._models[voice_id]
                if voice_id in self._load_times:
                    del self._load_times[voice_id]
                if voice_id in self._access_times:
                    del self._access_times[voice_id]
                logger.info(f"Model unloaded: {voice_id}")
                return True
            else:
                logger.debug(f"Model not in cache: {voice_id}")
                return False
    
    def _load_model_file(self, voice_id: str):
        """
        Load model file from disk using Piper.
        
        Args:
            voice_id: Voice identifier
            
        Returns:
            Loaded Piper voice object
            
        Raises:
            RuntimeError: If load fails
        """
        try:
            from piper import PiperVoice
        except ImportError:
            raise RuntimeError("Piper not installed. Install: pip install piper-tts")
        
        voice_config = self.VOICE_MODEL_MAP[voice_id]
        model_filename = voice_config["model_file"]
        
        # Model path depends on language
        language = voice_config["language"]
        if language == "urdu":
            model_path = self.models_dir / "urdu" / model_filename
        else:
            model_path = self.models_dir / model_filename
        
        if not model_path.exists():
            raise RuntimeError(f"Model file not found: {model_path}")
        
        try:
            logger.info(f"Loading model: {voice_id} from {model_path}")
            voice = PiperVoice.load(str(model_path))
            logger.info(f"Successfully loaded: {voice_id}")
            return voice
        except Exception as e:
            logger.error(f"Failed to load model {voice_id}: {e}")
            raise RuntimeError(f"Model load failed for {voice_id}: {str(e)}")
    
    def _evict_lru(self) -> Optional[str]:
        """
        Evict Least Recently Used model from cache.
        
        Returns:
            Voice ID of evicted model, or None if nothing to evict
        """
        if not self._models:
            return None
        
        # Find least recently used
        lru_voice = min(self._access_times, key=self._access_times.get)
        
        logger.info(f"LRU Eviction: {lru_voice}")
        
        del self._models[lru_voice]
        del self._load_times[lru_voice]
        del self._access_times[lru_voice]
        
        self.evictions_total += 1
        
        return lru_voice
    
    def preload(self, voice_id: str) -> bool:
        """
        Preload model at startup (for default voices).
        
        Args:
            voice_id: Voice to preload
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Preloading: {voice_id}")
            self.get_model(voice_id)
            logger.info(f"Preload complete: {voice_id}")
            return True
        except Exception as e:
            logger.error(f"Preload failed for {voice_id}: {e}")
            return False
    
    def synthesize(self, voice_id: str, text: str, **kwargs) -> Optional[bytes]:
        """
        Synthesize text using specified voice.
        
        Args:
            voice_id: Voice to use
            text: Text to synthesize
            **kwargs: Additional args for Piper synthesis
            
        Returns:
            WAV audio bytes (complete with RIFF header), or None if failed
        """
        try:
            voice = self.get_model(voice_id)
            
            # Synthesize with Piper - collect raw audio bytes
            audio_bytes = bytearray()
            for audio_chunk in voice.synthesize(text, None):
                audio_bytes.extend(audio_chunk.audio_int16_bytes)
            
            if not audio_bytes:
                return None
            
            # Wrap raw audio bytes in proper WAV format
            # Piper returns 16-bit PCM audio at 22050 Hz, mono
            wav_buffer = io.BytesIO()
            try:
                with wave.open(wav_buffer, 'wb') as wav_file:
                    # Mono, 16-bit, 22050 Hz (standard Piper output)
                    wav_file.setnchannels(1)  # Mono
                    wav_file.setsampwidth(2)  # 16-bit
                    wav_file.setframerate(22050)
                    wav_file.writeframes(bytes(audio_bytes))
                
                return wav_buffer.getvalue()
            except Exception as wav_err:
                logger.error(f"Failed to create WAV container: {wav_err}")
                return None
            
        except Exception as e:
            logger.error(f"Synthesis failed for {voice_id}: {e}")
            return None
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with hit rate, sizes, etc.
        """
        with self.lock:
            total_requests = self.cache_hits + self.cache_misses
            hit_rate = (
                self.cache_hits / total_requests * 100 if total_requests > 0 else 0
            )
            
            return {
                "cached_models": len(self._models),
                "cached_voices": list(self._models.keys()),
                "max_cached": self.max_cached_models,
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
                "hit_rate_percent": round(hit_rate, 2),
                "total_loads": self.loads_total,
                "total_evictions": self.evictions_total,
            }
    
    def get_available_voices(self) -> Dict[str, list]:
        """Get available voices grouped by language."""
        voices_by_lang = {
            "english": [],
            "urdu": [],
        }
        
        for voice_id, config in self.VOICE_MODEL_MAP.items():
            lang = config["language"]
            voices_by_lang[lang].append(voice_id)
        
        return voices_by_lang
    
    def clear_cache(self):
        """Clear all cached models."""
        with self.lock:
            self._models.clear()
            self._load_times.clear()
            self._access_times.clear()
            logger.info("Cache cleared")


# Global singleton instance
_unified_cache = None


def get_unified_model_cache(
    models_dir: str = None,
    model_timeout: int = None,
    max_cached: int = None,
) -> UnifiedModelCache:
    """
    Get or create global unified model cache instance.
    
    Args:
        models_dir: Models directory (only used on first call)
        model_timeout: Timeout in seconds (only used on first call)
        max_cached: Max models to cache (only used on first call)
        
    Returns:
        Singleton UnifiedModelCache instance
    """
    global _unified_cache
    
    if _unified_cache is None:
        # First call - create instance
        if models_dir is None:
            from .config import Config
            models_dir = str(Config.PIPER_MODELS_DIR)
        
        if model_timeout is None:
            model_timeout = 3600
        
        if max_cached is None:
            max_cached = 2
        
        _unified_cache = UnifiedModelCache(
            models_dir=models_dir,
            model_timeout=model_timeout,
            max_cached_models=max_cached,
        )
    
    return _unified_cache
