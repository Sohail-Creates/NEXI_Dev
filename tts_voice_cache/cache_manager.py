"""
TTS Voice Cache Manager

Manages loading, storing, and serving pre-generated voice audio files.
Improves performance by serving common phrases from cache instead of generating them each time.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import os

logger = logging.getLogger(__name__)

class VoiceCacheManager:
    """
    Manages pre-generated voice cache.
    
    Structure:
    cache/
        en/
            i_am_listening_en_ryan.wav
            i_am_listening_en_ryan.json  # metadata
        ur/
            mein_sun_raha_hun_ur_shahid.wav
    """
    
    def __init__(self, cache_dir: Optional[str] = None):
        """
        Initialize voice cache manager.
        
        Args:
            cache_dir: Path to cache directory (defaults to ./tts_voice_cache/cache)
        """
        if cache_dir is None:
            cache_dir = Path(__file__).parent / "cache"
        
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Create language subdirectories
        for lang in ["en", "ur"]:
            (self.cache_dir / lang).mkdir(exist_ok=True)
        
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Voice cache manager initialized at {self.cache_dir}")
        
        # Load cache index
        self.index = self._load_index()
    
    def _get_cache_key(self, text: str, language: str, voice_id: str = "default") -> str:
        """Generate cache key for a phrase."""
        # Normalize text for filename
        normalized = text.lower().replace(" ", "_").replace("'", "")[:50]
        # Create hash for exact matching
        text_hash = hashlib.md5(f"{text}|{language}|{voice_id}".encode()).hexdigest()[:8]
        return f"{normalized}_{language}_{voice_id}_{text_hash}"
    
    def _load_index(self) -> Dict:
        """Load cache index from disk."""
        index_file = self.cache_dir / "index.json"
        if index_file.exists():
            try:
                with open(index_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.warning(f"Failed to load cache index: {e}")
        return {}
    
    def _save_index(self):
        """Save cache index to disk."""
        index_file = self.cache_dir / "index.json"
        try:
            with open(index_file, 'w') as f:
                json.dump(self.index, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save cache index: {e}")
    
    def store_voice(self, text: str, language: str, audio_bytes: bytes, 
                   voice_id: str = "default", metadata: dict = None) -> bool:
        """
        Store generated voice in cache.
        
        Args:
            text: Original text
            language: Language code ('en' or 'ur')
            audio_bytes: WAV audio data
            voice_id: Voice identifier
            metadata: Additional metadata to store
        
        Returns:
            True if successful, False otherwise
        """
        try:
            cache_key = self._get_cache_key(text, language, voice_id)
            lang_dir = self.cache_dir / language
            
            # Store audio file
            audio_file = lang_dir / f"{cache_key}.wav"
            with open(audio_file, 'wb') as f:
                f.write(audio_bytes)
            
            # Store metadata
            meta = {
                "text": text,
                "language": language,
                "voice_id": voice_id,
                "size_bytes": len(audio_bytes),
                "cache_key": cache_key,
            }
            if metadata:
                meta.update(metadata)
            
            meta_file = lang_dir / f"{cache_key}.json"
            with open(meta_file, 'w') as f:
                json.dump(meta, f, indent=2)
            
            # Update index
            index_key = f"{language}|{text.lower()}|{voice_id}"
            self.index[index_key] = {
                "cache_key": cache_key,
                "file": str(audio_file),
                "size": len(audio_bytes)
            }
            self._save_index()
            
            self.logger.info(f"Cached voice: {text[:30]}... ({language})")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to store voice: {e}")
            return False
    
    def get_voice(self, text: str, language: str = "en", 
                 voice_id: str = "default") -> Optional[bytes]:
        """
        Get cached voice audio.
        
        Args:
            text: Text to look up
            language: Language code
            voice_id: Voice identifier
        
        Returns:
            Audio bytes if found, None otherwise
        """
        try:
            # Check index first
            index_key = f"{language}|{text.lower()}|{voice_id}"
            if index_key not in self.index:
                return None
            
            cache_entry = self.index[index_key]
            audio_file = Path(cache_entry["file"])
            
            if not audio_file.exists():
                # Index is stale, remove it
                del self.index[index_key]
                self._save_index()
                return None
            
            with open(audio_file, 'rb') as f:
                audio_bytes = f.read()
            
            self.logger.debug(f"Using cached voice: {text[:30]}... ({language})")
            return audio_bytes
            
        except Exception as e:
            self.logger.warning(f"Failed to get cached voice: {e}")
            return None
    
    def has_voice(self, text: str, language: str = "en", 
                 voice_id: str = "default") -> bool:
        """Check if voice is cached."""
        try:
            index_key = f"{language}|{text.lower()}|{voice_id}"
            if index_key not in self.index:
                return False
            
            cache_entry = self.index[index_key]
            audio_file = Path(cache_entry["file"])
            return audio_file.exists()
            
        except Exception:
            return False
    
    def clear_cache(self):
        """Clear all cached voices."""
        try:
            for lang_dir in self.cache_dir.glob("*/"):
                if lang_dir.is_dir() and lang_dir.name in ["en", "ur"]:
                    for file in lang_dir.glob("*.wav"):
                        file.unlink()
                    for file in lang_dir.glob("*.json"):
                        if file.name != "index.json":
                            file.unlink()
            
            self.index.clear()
            self._save_index()
            self.logger.info("Voice cache cleared")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to clear cache: {e}")
            return False
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics."""
        total_size = 0
        total_files = 0
        
        for lang_dir in self.cache_dir.glob("*/"):
            if lang_dir.is_dir() and lang_dir.name in ["en", "ur"]:
                for file in lang_dir.glob("*.wav"):
                    total_size += file.stat().st_size
                    total_files += 1
        
        return {
            "total_cached_voices": total_files,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "cache_directory": str(self.cache_dir),
            "index_entries": len(self.index),
        }
    
    def list_cached_voices(self) -> Dict[str, List[str]]:
        """List all cached voices organized by language."""
        voices = {"en": [], "ur": []}
        
        for index_key in self.index.keys():
            parts = index_key.split("|")
            if len(parts) >= 3:
                language = parts[0]
                text = parts[1]
                if language in ["en", "ur"]:
                    voices[language].append(text)
        
        return voices


# Global cache instance
_cache_instance = None

def get_cache_manager(cache_dir: Optional[str] = None) -> VoiceCacheManager:
    """Get or create global cache manager instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = VoiceCacheManager(cache_dir)
    return _cache_instance

if __name__ == "__main__":
    # Test cache manager
    cache = get_cache_manager()
    stats = cache.get_cache_stats()
    print(f"\nCache Statistics:")
    print(f"  Total Cached: {stats['total_cached_voices']} voices")
    print(f"  Total Size: {stats['total_size_mb']} MB")
    print(f"  Cache Directory: {stats['cache_directory']}")
