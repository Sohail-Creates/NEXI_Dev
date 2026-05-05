"""
Language Detection Module
Detects whether text is Urdu or English based on Unicode character ranges.
Lightweight and efficient for real-time TTS processing.
"""

import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class LanguageDetector:
    """
    Simple, efficient language detector for Urdu vs English.
    Uses Unicode character ranges to classify text.
    """
    
    # Unicode ranges for different scripts
    URDU_SCRIPT_RANGE = (0x0600, 0x06FF)  # Arabic script (used for Urdu)
    URDU_EXTENDED_RANGE = (0x0750, 0x077F)  # Arabic Supplement
    COMMON_URDU_DIACRITICS = {0x064B, 0x064C, 0x064D, 0x064E, 0x064F, 0x0650}
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.cache = {}
    
    def detect_language(self, text: str) -> Tuple[str, float]:
        """
        Detect language of text.
        
        Args:
            text: Input text to analyze
            
        Returns:
            Tuple of (language_code, confidence)
            language_code: 'ur' for Urdu, 'en' for English
            confidence: 0.0 to 1.0 confidence score
        """
        if not text or len(text.strip()) < 1:
            return "en", 1.0
        
        # Simple cache for repeated texts
        if text in self.cache:
            return self.cache[text]
        
        urdu_char_count = 0
        total_chars = 0
        
        for char in text:
            char_code = ord(char)
            
            # Count alphabetic characters only (skip spaces, punctuation score)
            if char_code >= 32:  # Skip control characters
                total_chars += 1
                
                # Check if character is in Urdu/Arabic range
                if (self.URDU_SCRIPT_RANGE[0] <= char_code <= self.URDU_SCRIPT_RANGE[1] or
                    self.URDU_EXTENDED_RANGE[0] <= char_code <= self.URDU_EXTENDED_RANGE[1] or
                    char_code in self.COMMON_URDU_DIACRITICS):
                    urdu_char_count += 1
        
        # Calculate confidence
        if total_chars == 0:
            return "en", 1.0
        
        urdu_ratio = urdu_char_count / total_chars
        
        # Decision logic: if >20% Urdu characters, treat as Urdu
        if urdu_ratio > 0.20:
            result = ("ur", min(1.0, urdu_ratio * 1.2))  # Boost confidence slightly
        else:
            result = ("en", 1.0 - urdu_ratio)  # English confidence
        
        # Cache result
        if len(self.cache) < 500:  # Limit cache size
            self.cache[text] = result
        
        return result
    
    def is_urdu(self, text: str, threshold: float = 0.20) -> bool:
        """Quick check if text is primarily Urdu."""
        language, _ = self.detect_language(text)
        return language == "ur"
    
    def is_english(self, text: str) -> bool:
        """Quick check if text is primarily English."""
        language, _ = self.detect_language(text)
        return language == "en"
    
    def clear_cache(self):
        """Clear the detection cache to free memory."""
        self.cache.clear()


# Global instance
_detector = None


def get_language_detector() -> LanguageDetector:
    """Get the global language detector instance."""
    global _detector
    if _detector is None:
        _detector = LanguageDetector()
    return _detector


def detect_language(text: str) -> str:
    """
    Convenience function to detect language.
    
    Args:
        text: Input text
        
    Returns:
        'ur' for Urdu, 'en' for English
    """
    detector = get_language_detector()
    language, _ = detector.detect_language(text)
    return language
