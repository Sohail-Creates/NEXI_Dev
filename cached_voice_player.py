"""
Cached Voice Player - Load and play pre-generated voice files

This module loads WAV files from the voice_cache folder and plays them
with proper audio parameters (sampling rate, channels, etc.).

No TTS call needed for predefined responses - instant playback!
"""

import logging
from pathlib import Path
from typing import Optional, Tuple
import soundfile as sf
import sounddevice as sd
import io

logger = logging.getLogger(__name__)

class CachedVoicePlayer:
    """
    Load and play pre-generated voice files from voice_cache folder.
    
    Predefined voices:
    - listening.wav:           "I am listening" (wake word response)
    - teachme_mode.wav:       "Teachme mode activated"
    - learning.wav:           "Learning object started"
    - learned.wav:            "Object learned successfully"
    - ask_label.wav:          "What is the label of this object?"
    - verify_failed.wav:      "Speaker verification failed"
    - transcribe_failed.wav:  "Speech transcription failed"
    - error_generic.wav:      "An error occurred, please try again"
    """
    
    def __init__(self, cache_dir: Optional[str] = None):
        """Initialize voice cache player."""
        if cache_dir is None:
            cache_dir = Path(__file__).parent / "voice_cache"
        
        self.cache_dir = Path(cache_dir)
        self.logger = logging.getLogger(__name__)
        
        # Verify cache directory exists
        if not self.cache_dir.exists():
            self.logger.warning(f"Voice cache directory not found: {self.cache_dir}")
        
        # Available voices
        self.voices = {
            "listening": "listening.wav",
            "teachme_mode": "teachme_mode.wav",
            "learning": "learning.wav",
            "learned": "learned.wav",
            "ask_label": "ask_label.wav",
            "verify_failed": "verify_failed.wav",
            "transcribe_failed": "transcribe_failed.wav",
            "error_generic": "error_generic.wav",
        }
        
        # Cache loaded audio in memory for faster playback
        self._loaded_audio = {}
    
    def has_voice(self, voice_name: str) -> bool:
        """Check if voice file exists in cache."""
        if voice_name not in self.voices:
            return False
        
        voice_file = self.cache_dir / self.voices[voice_name]
        return voice_file.exists()
    
    def load_voice(self, voice_name: str) -> Optional[Tuple[object, int]]:
        """
        Load voice audio from cache.
        
        Args:
            voice_name: Key name (e.g., 'listening', 'teachme_mode')
        
        Returns:
            Tuple of (audio_data, sample_rate) or None if not found
        """
        # Check cache first
        if voice_name in self._loaded_audio:
            return self._loaded_audio[voice_name]
        
        # Check if voice exists
        if voice_name not in self.voices:
            self.logger.warning(f"Unknown voice: {voice_name}")
            return None
        
        voice_file = self.cache_dir / self.voices[voice_name]
        if not voice_file.exists():
            self.logger.warning(f"Voice file not found: {voice_file}")
            return None
        
        try:
            # Load WAV file
            audio_data, sample_rate = sf.read(str(voice_file), dtype='float32')
            
            # Cache it for future use
            self._loaded_audio[voice_name] = (audio_data, sample_rate)
            
            self.logger.debug(f"Loaded voice: {voice_name} ({sample_rate}Hz)")
            return (audio_data, sample_rate)
            
        except Exception as e:
            self.logger.error(f"Failed to load {voice_name}: {e}")
            return None
    
    def play_voice(self, voice_name: str, latency: str = 'low') -> bool:
        """
        Play voice from cache.
        
        Args:
            voice_name: Key name (e.g., 'listening', 'teachme_mode')
            latency: Audio latency mode ('low' for real-time, 'high' for processing)
        
        Returns:
            True if playback successful, False otherwise
        """
        try:
            # Load voice
            result = self.load_voice(voice_name)
            if result is None:
                self.logger.warning(f"Cannot play voice: {voice_name} (not found or error loading)")
                return False
            
            audio_data, sample_rate = result
            
            # Play audio
            self.logger.debug(f"Playing: {voice_name} at {sample_rate}Hz")
            sd.play(audio_data, samplerate=sample_rate, latency=latency)
            sd.wait()  # Wait for playback to complete
            
            return True
            
        except Exception as e:
            self.logger.error(f"Playback error for {voice_name}: {e}")
            return False
    
    def get_available_voices(self) -> list:
        """Get list of available voice names."""
        return [name for name in self.voices.keys() if self.has_voice(name)]
    
    def list_voices(self):
        """Print available voices."""
        print("\nAvailable Cached Voices:")
        print("-" * 50)
        
        for voice_name, filename in self.voices.items():
            voice_file = self.cache_dir / filename
            available = "✓" if voice_file.exists() else "✗"
            print(f"  {available} {voice_name:20s} ({filename})")
        
        print("-" * 50)


# Global instance
_player_instance = None

def get_voice_player(cache_dir: Optional[str] = None) -> CachedVoicePlayer:
    """Get or create global voice player instance."""
    global _player_instance
    if _player_instance is None:
        _player_instance = CachedVoicePlayer(cache_dir)
    return _player_instance


if __name__ == "__main__":
    # Test voice player
    print("\n" + "=" * 70)
    print("CACHED VOICE PLAYER TEST")
    print("=" * 70)
    
    player = get_voice_player()
    player.list_voices()
    
    # Test loading each voice
    print("\nTesting voice playback:")
    for voice_name in player.get_available_voices():
        print(f"\nPlaying: {voice_name}")
        success = player.play_voice(voice_name)
        if success:
            print(f"   Played successfully")
        else:
            print(f"   Failed to play")
