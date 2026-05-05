"""
Common Phrases for Voice Pre-Caching

Define all repetitive phrases that are frequently used in the NEXI system.
These phrases will be pre-generated once and reused multiple times to save CPU resources.

Categories:
1. Wake-Word Responses: Responses to wake word detection
2. Verification Responses: Speaker verification messages
3. System Messages: TeachMe, settings, etc.
4. Error Messages: Common error responses
"""

from typing import Dict, List

# ============================================================================
# COMMON PHRASES TO PRE-GENERATE
# ============================================================================

COMMON_PHRASES = {
    # Wake Word Detection Responses
    "wake_word": {
        "en": [
            "I am listening",  # Wake word detected - ready to receive query
            "Yes, I am here",
            "Ready to help",
        ],
        "ur": [
            "میں سن رہا ہوں",
            "ہاں، میں یہاں ہوں",
            "مدد کے لیے تیار ہوں",
        ]
    },
    
    # Speaker Verification
    "verification": {
        "en": [
            "Verifying your voice",
            "Please speak clearly",
            "Try again",
            "Voice verified",
            "Welcome back",
        ],
        "ur": [
            "آپ کی آواز کی تصدیق ہو رہی ہے",
            "براہ کرم واضح طریقے سے بات کریں",
            "دوبارہ کوشش کریں",
            "آواز تصدیق شدہ",
            "خوش آمدید",
        ]
    },
    
    # Enrollment
    "enrollment": {
        "en": [
            "Let's get you enrolled",
            "Enrollment in progress",
            "Please provide your face samples",
            "Recording complete",
            "Enrollment successful",
        ],
        "ur": [
            "آئیے آپ کو رجسٹر کریں",
            "رجسٹریشن جاری ہے",
            "براہ کرم اپنے چہرے کے نمونے فراہم کریں",
            "ریکارڈنگ مکمل",
            "رجسٹریشن کامیاب",
        ]
    },
    
    # Teach Objects Mode
    "teach_objects": {
        "en": [
            "Let's learn the object",
            "Teachme mode activated",
            "What is this object about",
            "Tell me",
            "Learning object",
            "Object saved",
        ],
        "ur": [
            "آئیے چیز سیکھیں",
            "ٹیچ می موڈ فعال ہے",
            "یہ چیز کس بارے میں ہے",
            "مجھے بتائیں",
            "چیز سیکھ رہے ہیں",
            "چیز محفوظ ہے",
        ]
    },
    
    # Error Messages
    "errors": {
        "en": [
            "Error occurred",
            "Please try again",
            "Service unavailable",
            "Network error",
        ],
        "ur": [
            "خرابی واقع ہوئی",
            "براہ کرم دوبارہ کوشش کریں",
            "سروس دستیاب نہیں",
            "نیٹ ورک میں خرابی",
        ]
    },
    
    # Settings
    "settings": {
        "en": [
            "Opening settings",
            "Settings updated",
            "Configuration saved",
        ],
        "ur": [
            "ترتیبات کھول رہے ہیں",
            "ترتیبات اپڈیٹ ہو گئیں",
            "تشکیل محفوظ ہو گئی",
        ]
    },
}

# Flatten to list of (text, language) tuples for batch generation
def get_phrases_for_generation() -> List[tuple]:
    """Get all phrases to pre-generate."""
    phrases = []
    for category, lang_dict in COMMON_PHRASES.items():
        for language, texts in lang_dict.items():
            for text in texts:
                phrases.append((text, language, category))
    return phrases

def print_phrases_summary():
    """Print summary of all phrases to be pre-generated."""
    print("\n" + "=" * 70)
    print("COMMON PHRASES FOR PRE-GENERATION")
    print("=" * 70)
    
    total = 0
    for category, lang_dict in COMMON_PHRASES.items():
        print(f"\n{category.upper()}")
        print("-" * 70)
        for language, texts in lang_dict.items():
            print(f"  [{language}] ({len(texts)} phrases)")
            for text in texts:
                print(f"    • {text}")
            total += len(texts)
    
    print("\n" + "=" * 70)
    print(f"TOTAL PHRASES: {total}")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    print_phrases_summary()
