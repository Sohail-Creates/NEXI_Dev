"""
TTS Voice Pre-Generator

Script to pre-generate and cache common phrases from the TTS service.
Run this once to generate all common voices, then they are served from cache.

Usage:
    python tts_voice_cache/voice_generator.py

Optional:
    python tts_voice_cache/voice_generator.py --clear        # Clear cache first
    python tts_voice_cache/voice_generator.py --stats        # Show cache stats
    python tts_voice_cache/voice_generator.py --list         # List cached items
"""

import sys
import argparse
import requests
import time
import logging
from pathlib import Path
from typing import List, Tuple
from tqdm import tqdm

# Add workspace root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tts_voice_cache.cache_manager import get_cache_manager
from tts_voice_cache.common_phrases import (
    COMMON_PHRASES, get_phrases_for_generation, print_phrases_summary
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration
TTS_SERVICE_URL = "http://localhost:8003"
SYNTHESIS_ENDPOINT = f"{TTS_SERVICE_URL}/api/v1/synthesize"
HEALTH_ENDPOINT = f"{TTS_SERVICE_URL}/health"

class VoicePreGenerator:
    """Pre-generates and caches voice samples."""
    
    def __init__(self, tts_url: str = TTS_SERVICE_URL):
        """Initialize generator."""
        self.tts_url = tts_url
        self.health_url = f"{tts_url}/health"
        self.synthesis_url = f"{tts_url}/api/v1/synthesize"
        self.cache = get_cache_manager()
        self.generated_count = 0
        self.skipped_count = 0
        self.failed_count = 0
    
    def check_tts_service(self) -> bool:
        """Check if TTS service is healthy."""
        try:
            response = requests.get(self.health_url, timeout=5)
            if response.status_code == 200:
                logger.info("✓ TTS Service is healthy")
                return True
            else:
                logger.error(f"✗ TTS Service unhealthy: HTTP {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            logger.error("✗ Cannot connect to TTS Service")
            logger.error(f"   Make sure TTS Service is running at {self.tts_url}")
            return False
        except Exception as e:
            logger.error(f"✗ TTS Service check failed: {e}")
            return False
    
    def generate_voice(self, text: str, language: str) -> bytes:
        """Generate voice for text using TTS service."""
        try:
            payload = {
                "text": text,
                "language": language,
                "voice_id": "en-US-ryan-high" if language == "en" else "shahid"
            }
            
            response = requests.post(
                self.synthesis_url,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.content
            else:
                logger.warning(f"TTS failed for '{text[:20]}...': HTTP {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            logger.warning(f"TTS timeout for '{text[:20]}...'")
            return None
        except Exception as e:
            logger.warning(f"TTS error for '{text[:20]}...': {e}")
            return None
    
    def generate_all(self, skip_existing: bool = True) -> dict:
        """
        Generate all common phrases.
        
        Args:
            skip_existing: Skip phrases already in cache
        
        Returns:
            Summary dict with counts
        """
        phrases = get_phrases_for_generation()
        
        logger.info(f"Starting to generate {len(phrases)} phrases")
        
        with tqdm(total=len(phrases), desc="Generating voices") as pbar:
            for text, language, category in phrases:
                pbar.set_description(f"Generating: {text[:30]}...")
                
                # Check if already cached
                if skip_existing and self.cache.has_voice(text, language):
                    logger.debug(f"Skipping (cached): {text[:30]}... ({language})")
                    self.skipped_count += 1
                    pbar.update(1)
                    continue
                
                # Generate voice
                audio_bytes = self.generate_voice(text, language)
                
                if audio_bytes:
                    # Store in cache
                    success = self.cache.store_voice(
                        text=text,
                        language=language,
                        audio_bytes=audio_bytes,
                        metadata={"category": category}
                    )
                    
                    if success:
                        self.generated_count += 1
                        logger.debug(f"Generated: {text[:30]}... ({language})")
                    else:
                        self.failed_count += 1
                        logger.warning(f"Failed to cache: {text[:30]}...")
                else:
                    self.failed_count += 1
                
                # Small delay to avoid overwhelming TTS service
                time.sleep(0.1)
                
                pbar.update(1)
        
        return {
            "generated": self.generated_count,
            "skipped": self.skipped_count,
            "failed": self.failed_count,
            "total": len(phrases)
        }
    
    def show_stats(self):
        """Display cache statistics."""
        stats = self.cache.get_cache_stats()
        
        print("\n" + "=" * 70)
        print("VOICE CACHE STATISTICS")
        print("=" * 70)
        print(f"Cached Voices:    {stats['total_cached_voices']}")
        print(f"Total Size:       {stats['total_size_mb']} MB")
        print(f"Cache Directory:  {stats['cache_directory']}")
        print(f"Index Entries:    {stats['index_entries']}")
        print("=" * 70 + "\n")
    
    def show_list(self):
        """Display list of cached voices."""
        voices = self.cache.list_cached_voices()
        
        print("\n" + "=" * 70)
        print("CACHED VOICES")
        print("=" * 70)
        
        for language in ["en", "ur"]:
            if voices[language]:
                print(f"\n{language.upper()} ({len(voices[language])} voices):")
                for text in sorted(set(voices[language])):
                    print(f"  • {text}")
        
        print("\n" + "=" * 70 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Pre-generate and cache TTS voices"
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Generate all voices (default if no other option specified)"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear cache before generating"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show cache statistics"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all cached voices"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip voices already in cache (default: True)"
    )
    parser.add_argument(
        "--tts-url",
        default=TTS_SERVICE_URL,
        help=f"TTS service URL (default: {TTS_SERVICE_URL})"
    )
    
    args = parser.parse_args()
    
    # Default to generate if no other option
    if not (args.stats or args.list):
        args.generate = True
    
    # Create generator
    gen = VoicePreGenerator(tts_url=args.tts_url)
    
    # Handle different commands
    if args.clear:
        print("Clearing voice cache...")
        gen.cache.clear_cache()
        print("Cache cleared!\n")
    
    if args.generate:
        print_phrases_summary()
        
        if not gen.check_tts_service():
            logger.error("TTS service is not available. Please start it and try again.")
            return 1
        
        print("\nGenerating voices...\n")
        result = gen.generate_all(skip_existing=args.skip_existing)
        
        print("\n" + "=" * 70)
        print("Generation Complete")
        print("=" * 70)
        print(f"Generated: {result['generated']} new voices")
        print(f"Skipped:   {result['skipped']} voices (already cached)")
        print(f"Failed:    {result['failed']} voices")
        print(f"Total:     {result['total']} phrases in common_phrases.py")
        print("=" * 70 + "\n")
    
    if args.stats:
        gen.show_stats()
    
    if args.list:
        gen.show_list()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
