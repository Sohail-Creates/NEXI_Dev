"""
TTS Service Wrapper - Cache-Aware Voice Synthesis

Wrapper around TTS service that:
1. Checks cache first for common phrases
2. Falls back to TTS service if not cached
3. Automatically stores new synthesis results for future use

This reduces CPU usage and improves response time significantly.
"""

import requests
import logging
import io
import soundfile as sf
import sounddevice as sd
from typing import Optional, Tuple
from pathlib import Path

# Add workspace root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from tts_voice_cache.cache_manager import get_cache_manager

logger = logging.getLogger(__name__)

class CacheAwareTTSClient:
    """
    TTS client with voice cache support.
    
    Usage:
        client = CacheAwareTTSClient()
        
        # Synthesize voice (uses cache if available)
        audio_bytes = client.synthesize("I am listening", language="en")
        
        # Play audio
        client.play_audio(audio_bytes)
        
        # Get cache stats
        stats = client.get_cache_stats()
    """
    
    def __init__(self, tts_service_url: str = "http://localhost:8003", 
                 use_cache: bool = True, cache_dir: Optional[str] = None):
        """
        Initialize TTS client.
        
        Args:
            tts_service_url: Base URL of TTS service
            use_cache: Whether to use caching (default: True)
            cache_dir: Path to cache directory (optional)
        """
        self.tts_url = tts_service_url.rstrip("/")
        self.synthesis_url = f"{self.tts_url}/api/v1/synthesize"
        self.use_cache = use_cache
        self.cache = get_cache_manager(cache_dir) if use_cache else None
        self.cache_hits = 0
        self.cache_misses = 0
        self.logger = logging.getLogger(__name__)
    
    def synthesize(self, text: str, language: str = "en", 
                  voice_id: str = "en-US-ryan-high",
                  return_wav_object: bool = False) -> Optional[bytes]:
        """
        Synthesize text to speech with caching.
        
        Args:
            text: Text to synthesize
            language: Language code ('en' or 'ur')
            voice_id: Voice identifier
            return_wav_object: If True, return (sample_rate, audio_data) instead of bytes
        
        Returns:
            Audio bytes (WAV format) or (sample_rate, audio_data) if return_wav_object=True
            None if synthesis failed
        """
        try:
            # Try cache first
            if self.use_cache:
                cached_audio = self.cache.get_voice(text, language, voice_id)
                if cached_audio:
                    self.cache_hits += 1
                    self.logger.debug(f"[CACHE HIT] {text[:30]}...")
                    
                    if return_wav_object:
                        return self._wav_bytes_to_object(cached_audio)
                    return cached_audio
            
            # Not in cache, synthesize from TTS
            self.cache_misses += 1
            self.logger.debug(f"[CACHE MISS] Synthesizing: {text[:30]}...")
            
            audio_bytes = self._synthesize_from_tts(text, language, voice_id)
            
            if audio_bytes:
                # Store in cache for next time
                if self.use_cache:
                    self.cache.store_voice(text, language, audio_bytes, voice_id)
                
                if return_wav_object:
                    return self._wav_bytes_to_object(audio_bytes)
                return audio_bytes
            
            return None
            
        except Exception as e:
            self.logger.error(f"Synthesis error: {e}")
            return None
    
    def _synthesize_from_tts(self, text: str, language: str, 
                            voice_id: str) -> Optional[bytes]:
        """Call TTS service to synthesize speech."""
        try:
            payload = {
                "text": text,
                "language": language,
                "voice_id": voice_id
            }
            
            response = requests.post(
                self.synthesis_url,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.content
            else:
                self.logger.warning(f"TTS HTTP {response.status_code}: {text[:20]}...")
                return None
                
        except requests.exceptions.Timeout:
            self.logger.warning(f"TTS timeout: {text[:20]}...")
            return None
        except Exception as e:
            self.logger.warning(f"TTS error: {e}")
            return None
    
    def _wav_bytes_to_object(self, wav_bytes: bytes) -> Tuple[int, object]:
        """Convert WAV bytes to (sample_rate, audio_data) tuple."""
        try:
            # Read WAV from bytes
            with io.BytesIO(wav_bytes) as f:
                audio_data, sample_rate = sf.read(f, dtype='float32')
            return (sample_rate, audio_data)
        except Exception as e:
            self.logger.error(f"Failed to convert WAV: {e}")
            return None
    
    def play_audio(self, audio_bytes: bytes, latency: str = 'low') -> bool:
        """
        Play synthesized audio to speaker.
        
        Args:
            audio_bytes: WAV audio data
            latency: Audio latency mode ('low' recommended for real-time)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            with io.BytesIO(audio_bytes) as f:
                audio_data, sample_rate = sf.read(f, dtype='float32')
            
            # Play audio
            sd.play(audio_data, samplerate=sample_rate, latency=latency)
            sd.wait()  # Wait for playback to complete
            
            return True
            
        except Exception as e:
            self.logger.error(f"Playback error: {e}")
            return False
    
    def synthesize_and_play(self, text: str, language: str = "en",
                           voice_id: str = "en-US-ryan-high") -> bool:
        """
        Synthesize text and play it immediately.
        
        Args:
            text: Text to synthesize
            language: Language code
            voice_id: Voice identifier
        
        Returns:
            True if successful, False otherwise
        """
        try:
            audio_bytes = self.synthesize(text, language, voice_id)
            
            if audio_bytes:
                return self.play_audio(audio_bytes)
            
            return False
            
        except Exception as e:
            self.logger.error(f"Synthesis and playback error: {e}")
            return False
    
    def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        if not self.use_cache:
            return {"cache_enabled": False}
        
        stats = self.cache.get_cache_stats()
        stats.update({
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate": round(
                self.cache_hits / (self.cache_hits + self.cache_misses) * 100, 1
            ) if (self.cache_hits + self.cache_misses) > 0 else 0
        })
        return stats
    
    def clear_cache(self) -> bool:
        """Clear all cached voices."""
        if not self.use_cache:
            return False
        
        self.cache.clear_cache()
        self.cache_hits = 0
        self.cache_misses = 0
        return True


# Global client instance
_client_instance = None

def get_tts_client(cache_enabled: bool = True) -> CacheAwareTTSClient:
    """Get or create global TTS client instance."""
    global _client_instance
    if _client_instance is None:
        _client_instance = CacheAwareTTSClient(use_cache=cache_enabled)
    return _client_instance


if __name__ == "__main__":
    # Test TTS client
    print("Initializing TTS client...")
    client = get_tts_client(cache_enabled=True)
    
    print(f"Cache stats: {client.get_cache_stats()}")
    
    # Example: Synthesize a common phrase
    print("\nSynthesizing 'I am listening'...")
    audio = client.synthesize("I am listening", language="en")
    
    if audio:
        print(f"Success! Audio size: {len(audio)} bytes")
    else:
        print("Failed to synthesize")
