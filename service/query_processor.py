"""
NEXI Service Layer - Query Processing

Handles:
- Entity extraction from natural language queries
- Query validation
- Label extraction from voice input
- Intent classification

Professional enterprise-grade implementation with zero dependencies on test code.
"""

from typing import List, Dict, Tuple, Optional, Any
import re
from enum import Enum


class QueryIntent(Enum):
    IDENTIFICATION = "identify"  # "What is this?"
    PROPERTY = "property"  # "What color is it?"
    LOCATION = "location"  # "Where is it?"
    ACTION = "action"  # "Do something"
    UNKNOWN = "unknown"


class QueryProcessorService:
    """Professional-grade query processing service for NEXI RAG."""
    
    # Object/Entity stopwords to remove from labels
    OBJECT_STOPWORDS = {
        'the', 'a', 'an', 'my', 'his', 'her', 'its', 'our', 'their',
        'is', 'are', 'was', 'were', 'this', 'that', 'these', 'those',
        'one', 'say', 'says', 'said', 'have', 'has', 'had',
        'do', 'does', 'did', 'will', 'would', 'could', 'should',
        'can', 'could', 'may', 'might', 'must', 'shall',
        'and', 'or', 'but', 'if', 'because', 'when', 'where', 'why', 'how',
        'what', 'which', 'who', 'whom', 'whose', 'i', 'you', 'he', 'she', 'we', 'they',
        'am', 'be', 'being', 'been', 'me', 'him', 'them', 'us',
        'my', 'mine', 'your', 'yours', 'his', 'hers', 'its', 'ours', 'theirs',
        # Additional stopwords for better filtering
        'tell', 'show', 'give', 'make', 'find', 'get', 'think', 'know', 'see',
        'like', 'want', 'need', 'help', 'use', 'try', 'ask', 'take', 'come',
        'go', 'put', 'say', 'come', 'think', 'know', 'take', 'see', 'come',
        'please', 'thanks', 'hello', 'bye', 'yes', 'no', 'ok', 'okay', 'sure',
        'about', 'about', 'with', 'from', 'to', 'at', 'in', 'on', 'of', 'for',
        'also', 'very', 'just', 'only', 'then', 'now', 'here', 'there', 'up', 'down',
        'more', 'less', 'all', 'each', 'every', 'both', 'either', 'neither'
    }
    
    # Common object synonyms for fuzzy matching
    OBJECT_SYNONYMS = {
        'phone': ['mobile', 'cellular', 'smartphone', 'device', 'handset'],
        'dog': ['puppy', 'canine', 'pup', 'doggo', 'pooch'],
        'cat': ['kitten', 'feline', 'kitty', 'kittycat'],
        'cup': ['mug', 'glass', 'drinking glass', 'tumbler'],
        'chair': ['seat', 'stool', 'bench', 'seating'],
        'table': ['desk', 'counter', 'surface'],
        'book': ['novel', 'text', 'publication'],
        'bottle': ['container', 'flask', 'jar'],
        'car': ['vehicle', 'automobile', 'motor', 'sedan', 'truck'],
        'bicycle': ['bike', 'cycle', 'two-wheeler'],
        'person': ['human', 'people', 'man', 'woman', 'child', 'kid', 'boy', 'girl'],
        'plant': ['flower', 'vegetation', 'foliage', 'pot plant'],
        'keyboard': ['input device', 'keboard'],  # Note: common misspelling
        'mouse': ['pointing device', 'rodent', 'trackpad'],
        'monitor': ['screen', 'display', 'tv'],
        'laptop': ['computer', 'notebook', 'pc', 'notebook computer'],
    }
    
    # Intent keywords for query classification
    INTENT_KEYWORDS = {
        QueryIntent.IDENTIFICATION: ['what', 'which', 'who', 'identify', 'recognize', 'name'],
        QueryIntent.PROPERTY: ['color', 'size', 'shape', 'material', 'weight', 'describe'],
        QueryIntent.LOCATION: ['where', 'location', 'position', 'place', 'find'],
        QueryIntent.ACTION: ['do', 'help', 'get', 'fetch', 'bring', 'move'],
    }
    
    @staticmethod
    def extract_entities(transcription: str) -> List[str]:
        """
        Extract object entities from user transcription.
        
        CRITICAL: Only extract RELEVANT entities for KB search.
        Removes stopwords, filler words, and action verbs.
        
        Examples:
          "What is the apple?" -> ["apple"]
          "Tell me about gardening" -> ["gardening"]  (NOT "tell")
          "I am Sohail, this is my mobile phone" -> ["mobile", "phone"]
          "Show me the red car" -> ["red", "car"]
        
        Args:
            transcription: Raw user transcription/voice input
            
        Returns:
            List of extracted object terms (empty if none meaningful)
        """
        if not transcription or not isinstance(transcription, str):
            return []
        
        # Convert to lowercase for processing
        text = transcription.lower().strip()
        
        # Remove punctuation except hyphens (for compound words)
        text = re.sub(r'[^\w\s\-]', ' ', text)
        
        # Split into words
        words = text.split()
        
        # Remove stopwords and very short words
        # CRITICAL: Only keep meaningful nouns/adjectives/objects
        extracted = [
            word.strip('-')  # Remove trailing hyphens
            for word in words
            if word and 
               word not in QueryProcessorService.OBJECT_STOPWORDS and
               len(word) > 2  # Keep only meaningful words (3+ chars)
        ]
        
        # Remove duplicates while preserving order
        seen = set()
        unique_extracted = []
        for word in extracted:
            if word not in seen:
                unique_extracted.append(word)
                seen.add(word)
        
        # QUALITY CHECK: If too many entities, likely parsed incorrectly
        # More than 5 entities from single query is suspicious
        if len(unique_extracted) > 5:
            # Return only the last few entities (most likely objects)
            unique_extracted = unique_extracted[-3:]
        
        return unique_extracted
    
    @staticmethod
    def validate_query(entities: List[str], min_length: int = 1) -> Tuple[bool, str]:
        """
        Validate extracted query entities.
        
        Args:
            entities: List of extracted terms
            min_length: Minimum number of entities required
            
        Returns:
            (is_valid, reason)
        """
        if not entities:
            return False, "No valid entities extracted from query"
        
        if len(entities) < min_length:
            return False, f"Too few entities (need at least {min_length})"
        
        # Check for invalid characters in entities
        for entity in entities:
            if not re.match(r'^[\w\s\-]+$', entity, re.UNICODE):
                return False, f"Invalid characters in entity: {entity}"
        
        return True, "Query valid"
    
    @staticmethod
    def extract_label_from_voice(transcription: str) -> str:
        """
        Extract object label from conversational voice input.
        
        Purpose: Convert "I am Sohail, this is my mobile phone" to "mobile phone"
        
        Strategy:
          1. Remove personal information (names, pronouns)
          2. Extract object-related terms
          3. Join into coherent label
          4. Clean and standardize
        
        Args:
            transcription: Raw voice transcription
            
        Returns:
            Extracted and cleaned object label
        """
        if not transcription:
            return ""
        
        text = transcription.lower().strip()
        
        # Remove common personal patterns
        # Patterns like: "I am [name]", "my name is [name]", "this is [name]'s"
        personal_patterns = [
            r'\bmy name is \w+',
            r'\bi am \w+',
            r'\b(i\'m|im) \w+',
            r'\b(this is|that\'s|that is) \w+ (saying|speaking)',
        ]
        
        for pattern in personal_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # Extract main object phrase
        # Common patterns: "this is [object]", "it's [object]", "my [object]", "the [object]"
        object_patterns = [
            r'(?:this is|that is|its|it\'s|my|the|a|an)\s+(?:my\s+)?([\w\s\-]+?)(?:\.|,|$)',
            r'([\w\s\-]+)\s+(?:phone|object|thing|device)',
        ]
        
        label = ""
        for pattern in object_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                label = match.group(1).strip()
                break
        
        # If no pattern matched, use all entities except stopwords
        if not label:
            entities = QueryProcessorService.extract_entities(text)
            label = ' '.join(entities) if entities else ""
        
        # Clean label: remove extra whitespace, standardize
        label = ' '.join(label.split())  # Normalize spaces
        label = label.strip('-').strip()  # Remove leading/trailing hyphens
        
        # If label is empty or too short, use original extraction
        if len(label) < 3:
            entities = QueryProcessorService.extract_entities(transcription)
            label = ' '.join(entities) if entities else "unknown"
        
        return label
    
    @staticmethod
    def classify_intent(transcription: str) -> QueryIntent:
        """
        Classify user query intent.
        
        Args:
            transcription: User query
            
        Returns:
            QueryIntent enum
        """
        text = transcription.lower()
        
        for intent, keywords in QueryProcessorService.INTENT_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    return intent
        
        return QueryIntent.UNKNOWN
    
    @staticmethod
    def normalize_object_name(name: str) -> str:
        """
        Normalize object name for consistent KB matching.
        
        Examples:
          "Mobile Phone" -> "mobile phone"
          "DOG" -> "dog"
          "red  car" -> "red car"
        
        Args:
            name: Raw object name
            
        Returns:
            Normalized name
        """
        if not name:
            return ""
        
        # Convert to lowercase
        name = name.lower().strip()
        
        # Normalize spaces (remove extra whitespace)
        name = ' '.join(name.split())
        
        # Remove trailing punctuation
        name = name.rstrip('.,!?;:')
        
        # Remove articles (a, an, the) at the beginning
        name = re.sub(r'^(a|an|the)\s+', '', name)
        
        # Remove possessive indicators
        name = re.sub(r"'s\s+", ' ', name)
        
        return name
    
    @staticmethod
    def enrich_query_with_synonyms(entity: str) -> List[str]:
        """
        Expand query entity with known synonyms for better matching.
        
        Example:
          "phone" -> ["phone", "mobile", "cellular", "smartphone", ...]
        
        Args:
            entity: Single entity term
            
        Returns:
            List including original and synonyms
        """
        entity_lower = entity.lower()
        
        # Check if we have synonyms for this entity
        if entity_lower in QueryProcessorService.OBJECT_SYNONYMS:
            return [entity_lower] + QueryProcessorService.OBJECT_SYNONYMS[entity_lower]
        
        # Check if this entity is a synonym for something
        for main_term, synonyms in QueryProcessorService.OBJECT_SYNONYMS.items():
            if entity_lower in synonyms:
                return [entity_lower] + [main_term] + [s for s in synonyms if s != entity_lower]
        
        # No synonyms found, return original
        return [entity_lower]


# UNIT TESTS (for validation)
def test_query_processor():
    """Quick validation of QueryProcessorService"""
    
    # Test entity extraction
    assert QueryProcessorService.extract_entities("What is the apple?") == ["apple"]
    assert "mobile" in QueryProcessorService.extract_entities("I am Sohail, this is my mobile phone")
    assert "phone" in QueryProcessorService.extract_entities("I am Sohail, this is my mobile phone")
    
    # Test label extraction
    label = QueryProcessorService.extract_label_from_voice("I am Sohail, this is my mobile phone")
    assert len(label) > 0 and "mobile" in label.lower()
    
    # Test normalization
    assert QueryProcessorService.normalize_object_name("The Mobile Phone") == "mobile phone"
    assert QueryProcessorService.normalize_object_name("RED  CAR") == "red car"
    
    # Test intent classification
    assert QueryProcessorService.classify_intent("What is this?") == QueryIntent.IDENTIFICATION
    assert QueryProcessorService.classify_intent("What color?") == QueryIntent.PROPERTY
    
    # Test synonyms
    synonyms = QueryProcessorService.enrich_query_with_synonyms("phone")
    assert "mobile" in synonyms
    assert "smartphone" in synonyms
    
    print("All QueryProcessor tests passed!")


if __name__ == "__main__":
    test_query_processor()
