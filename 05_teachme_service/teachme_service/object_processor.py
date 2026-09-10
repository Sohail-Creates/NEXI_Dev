from .models import ObjectData
from typing import Dict, Any, List, Optional
from datetime import datetime
import requests
import logging
import time
from .config import vision_config
import asyncio

# Vision Service Connector with Circuit Breaker
from .vision_service_connector import get_vision_connector

# Try to import aiohttp for async HTTP
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

# Setup logging
logger = logging.getLogger(__name__)


class ObjectProcessor:
    """
    Processes object data and links names to vision output
    Handles object recognition, attribute extraction, and data enhancement
    Uses resilient Vision Service connector with circuit breaker
    """
    
    def __init__(self, vision_service_url: str = None):
        """Initialize with Vision Service
        
        Uses circuit breaker-equipped connector to prevent cascading failures
        when Vision Service is slow or unavailable.
        """
        if vision_service_url:
            self.vision_service_url = vision_service_url
        else:
            self.vision_service_url = vision_config.get_base_url()
        self.timeout = vision_config.TIMEOUT
        self.confidence_threshold = vision_config.OBJECT_CONFIDENCE_THRESHOLD
        self.vision_cache: Dict[str, Dict[str, Any]] = {}
        self.object_categories = self._initialize_categories()
        
        # Get resilient Vision Service connector
        self.vision_connector = get_vision_connector()
        
        logger.info(f"ObjectProcessor initialized with resilient Vision Service connector")
        logger.info(f"Vision Service URL: {self.vision_service_url}")
    
    def process_object(self, object_data: ObjectData) -> ObjectData:
        """
        Enhanced processing linking names to vision data
        Integrates computer vision output with object attributes
        """
        # Get vision-based attributes
        vision_attributes = self._get_vision_attributes(object_data.name)
        
        # Extract and enhance object features
        enhanced_attributes = self._enhance_object_features(object_data, vision_attributes)
        
        # Auto-detect category if not provided
        detected_category = self._detect_category(object_data.name, enhanced_attributes)
        
        return ObjectData(
            name=object_data.name,
            attributes=enhanced_attributes,
            category=object_data.category or detected_category,
            description=object_data.description or self._generate_description(object_data.name, enhanced_attributes)
        )
    
    async def process_object_async(self, object_data: ObjectData) -> ObjectData:
        """
        Async version: Non-blocking Vision Service integration (Phase 2)
        Processes object with async HTTP calls for better performance
        """
        # Get vision-based attributes asynchronously
        vision_attributes = await self._get_vision_attributes_async(object_data.name)
        
        # Extract and enhance object features
        enhanced_attributes = self._enhance_object_features(object_data, vision_attributes)
        
        # Auto-detect category if not provided
        detected_category = self._detect_category(object_data.name, enhanced_attributes)
        
        return ObjectData(
            name=object_data.name,
            attributes=enhanced_attributes,
            category=object_data.category or detected_category,
            description=object_data.description or self._generate_description(object_data.name, enhanced_attributes)
        )
    
    def _get_vision_attributes(self, object_name: str) -> Dict[str, Any]:
        """
        Get vision attributes using resilient connector with circuit breaker.
        
        If Vision Service is unavailable, returns gracefully with fallback data.
        Circuit breaker prevents cascading failures to other services.
        """
        # Check cache first
        cache_key = object_name.lower()
        if cache_key in self.vision_cache:
            logger.debug(f"Using cached Vision data for '{object_name}'")
            return self.vision_cache[cache_key]
        
        # Note: Must run synchronously from sync context
        # Use blocking connector call (not async)
        try:
            # For sync context, we need to create a new event loop or use blocking call
            # Since this is called from sync context, we'll use a fallback approach
            # that doesn't require async
            
            import threading
            result = [None]
            exception = [None]
            
            def get_async():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    vision_data = loop.run_until_complete(
                        self.vision_connector.get_vision_attributes(object_name, timeout_override=5)
                    )
                    result[0] = vision_data
                except Exception as e:
                    exception[0] = e
            
            # Run async connector in thread to avoid blocking
            thread = threading.Thread(target=get_async, daemon=True)
            thread.start()
            thread.join(timeout=7)  # Wait up to 7 seconds
            
            if exception[0]:
                logger.warning(f"Vision connector error: {exception[0]}")
                return self._get_mock_vision_attributes(object_name)
            
            if result[0] is None:
                logger.warning(f"Vision Service unavailable for '{object_name}', using fallback")
                return self._get_mock_vision_attributes(object_name)
            
            # Process vision data
            vision_result = result[0]
            if isinstance(vision_result, dict) and vision_result.get('objects'):
                objects_detected = vision_result.get('objects', [])
                logger.info(f"Vision Service detected {len(objects_detected)} objects")
                
                object_name_lower = object_name.lower().strip()
                matched_object = self._find_matching_object(object_name_lower, objects_detected)
                
                if matched_object:
                    bbox = matched_object.get('bounding_box', {})
                    result_data = {
                        'color': 'varies',
                        'shape': self._determine_shape(bbox),
                        'detected_class': matched_object.get('class_name', 'unknown'),
                        'confidence': matched_object.get('confidence', 0.0),
                        'bounding_box': bbox,
                        'vision_detected': True,
                    }
                    # Cache the result
                    self.vision_cache[cache_key] = result_data
                    logger.info(f" MATCHED: '{object_name}' found (conf: {result_data['confidence']:.2f})")
                    return result_data
                else:
                    logger.warning(f" Object '{object_name}' not detected, using fallback")
                    return self._get_mock_vision_attributes(object_name)
            
            logger.info(f"Using fallback data for '{object_name}'")
            return self._get_mock_vision_attributes(object_name)
            
        except Exception as e:
            logger.error(f"Unexpected error in _get_vision_attributes: {e}")
            return self._get_mock_vision_attributes(object_name)
    
    async def _get_vision_attributes_async(self, object_name: str) -> Dict[str, Any]:
        """
        Async version using resilient Vision Service connector.
        
        Non-blocking HTTP requests with circuit breaker for better performance
        and failure handling.
        """
        # Check cache first
        cache_key = object_name.lower()
        if cache_key in self.vision_cache:
            logger.debug(f"Using cached Vision data for '{object_name}' (async)")
            return self.vision_cache[cache_key]
        
        try:
            # Use resilient connector
            vision_data = await self.vision_connector.get_vision_attributes(object_name)
            
            if vision_data is None:
                logger.warning(f"Vision Service unavailable for '{object_name}' (async), using fallback")
                return self._get_mock_vision_attributes(object_name)
            
            # Process vision data
            if isinstance(vision_data, dict) and vision_data.get('objects'):
                objects_detected = vision_data.get('objects', [])
                logger.info(f"[Async] Vision Service detected {len(objects_detected)} objects")
                
                object_name_lower = object_name.lower().strip()
                matched_object = self._find_matching_object(object_name_lower, objects_detected)
                
                if matched_object:
                    bbox = matched_object.get('bounding_box', {})
                    result_data = {
                        'color': 'varies',
                        'shape': self._determine_shape(bbox),
                        'detected_class': matched_object.get('class_name', 'unknown'),
                        'confidence': matched_object.get('confidence', 0.0),
                        'bounding_box': bbox,
                        'vision_detected': True,
                    }
                    # Cache the result
                    self.vision_cache[cache_key] = result_data
                    logger.info(f"[Async]  MATCHED: '{object_name}' found (conf: {result_data['confidence']:.2f})")
                    return result_data
                else:
                    logger.warning(f"[Async]  Object '{object_name}' not detected, using fallback")
                    return self._get_mock_vision_attributes(object_name)
            
            logger.info(f"[Async] Using fallback data for '{object_name}'")
            return self._get_mock_vision_attributes(object_name)
            
        except Exception as e:
            logger.error(f"[Async] Unexpected error in _get_vision_attributes_async: {e}")
            return self._get_mock_vision_attributes(object_name)
    
    def _find_matching_object(self, object_name: str, detected_objects: List[Dict]) -> Dict[str, Any]:
        """
        CRITICAL: Find EXACT or SIMILAR match - reject if only detecting unrelated objects
        
        Returns the detected object ONLY if it matches what the user asked for
        """
        object_name = object_name.lower().strip()
        
        # Get synonyms and variations for the object
        variations = self._get_object_variations(object_name)
        
        logger.info(f"Looking for variations of '{object_name}': {variations}")
        
        # Try exact matches first
        for obj in detected_objects:
            detected_class = obj.get('class_name', '').lower()
            
            # Check if detected class matches any variation
            if detected_class in variations or object_name in detected_class:
                logger.info(f"   Exact match: {detected_class}")
                return obj
        
        # Try partial matches (e.g., "tv" in "laptop")
        for obj in detected_objects:
            detected_class = obj.get('class_name', '').lower()
            
            for variation in variations:
                if variation in detected_class or detected_class in variation:
                    # Only accept if confidence is decent
                    if obj.get('confidence', 0) > 0.3:
                        logger.info(f"  ~ Partial match: {detected_class} (conf: {obj['confidence']:.2f})")
                        return obj
        
        # No match found
        logger.warning(f"   No match for '{object_name}' in detected objects")
        return None
    
    def _get_object_variations(self, object_name: str) -> List[str]:
        """
        Get common variations/synonyms for an object name
        This helps match "remote" to "remote control", "tv" to "television", etc.
        """
        variations_map = {
            'remote': ['remote', 'remote control', 'controller'],
            'tv': ['tv', 'television', 'monitor'],
            'phone': ['phone', 'cell phone', 'mobile phone', 'smartphone'],
            'laptop': ['laptop', 'computer', 'notebook'],
            'mouse': ['mouse', 'computer mouse'],
            'keyboard': ['keyboard', 'computer keyboard'],
            'bottle': ['bottle', 'water bottle'],
            'cup': ['cup', 'mug', 'glass'],
            'scissors': ['scissors'],
            'book': ['book'],
            'pen': ['pen'],
            'chair': ['chair', 'seat'],
            'table': ['table', 'desk'],
            'couch': ['couch', 'sofa'],
            'car': ['car', 'automobile', 'vehicle'],
            'bike': ['bike', 'bicycle'],
            'cat': ['cat'],
            'dog': ['dog'],
            'person': ['person', 'human'],
        }
        
        base_name = object_name.lower().strip()
        
        # Return variations if we have them, otherwise just the name itself
        if base_name in variations_map:
            return variations_map[base_name]
        else:
            return [base_name]
    
    def _determine_shape(self, bbox: Dict[str, Any]) -> str:
        """Determine shape from bounding box"""
        width = bbox.get('width', 0)
        height = bbox.get('height', 0)
        
        if width and height:
            aspect_ratio = width / height
            if 0.9 <= aspect_ratio <= 1.1:
                return 'round'
            elif aspect_ratio > 1.5:
                return 'rectangular'
            else:
                return 'rectangular'
        return 'unknown'
    
    def _get_mock_vision_attributes(self, object_name: str) -> Dict[str, Any]:
        """
        FALLBACK DATA - used when Vision Service fails or object not detected
        """
        vision_library = {
            # Fruits
            "apple": {"color": "red", "shape": "round", "texture": "smooth", "size_cm": 7, "confidence": 0.95},
            "banana": {"color": "yellow", "shape": "curved", "texture": "smooth", "size_cm": 18, "confidence": 0.92},
            "orange": {"color": "orange", "shape": "spherical", "texture": "bumpy", "size_cm": 8, "confidence": 0.89},
            
            # Office items
            "book": {"color": "varies", "shape": "rectangular", "material": "paper", "pages": 300, "confidence": 0.94},
            "pen": {"color": "varies", "shape": "cylindrical", "material": "plastic", "length_cm": 14, "confidence": 0.91},
            "laptop": {"color": "silver", "shape": "rectangular", "material": "metal", "screen_size": 15, "confidence": 0.96},
            "scissors": {"color": "silver", "shape": "tool", "material": "metal", "confidence": 0.85},
            "remote": {"color": "black", "shape": "rectangular", "material": "plastic", "confidence": 0.88},
            
            # Animals
            "cat": {"color": "varies", "shape": "animal", "movement": "walking", "legs": 4, "confidence": 0.93},
            "dog": {"color": "varies", "shape": "animal", "movement": "running", "legs": 4, "confidence": 0.94},
            "bird": {"color": "varies", "shape": "animal", "movement": "flying", "wings": 2, "confidence": 0.90},
            
            # Common objects
            "bottle": {"color": "varies", "shape": "cylindrical", "material": "plastic", "confidence": 0.88},
            "cup": {"color": "varies", "shape": "cylindrical", "material": "ceramic", "confidence": 0.87},
            "phone": {"color": "varies", "shape": "rectangular", "material": "glass", "confidence": 0.92},
            
            # Default fallback
            "default": {"color": "unknown", "shape": "unknown", "confidence": 0.5}
        }
        
        object_key = object_name.lower().strip()
        result = vision_library.get(object_key, vision_library["default"])
        result['vision_detected'] = False
        result['fallback_mode'] = True
        result['reason'] = 'Object not detected in camera frame'
        return result
    
    def _enhance_object_features(self, object_data: ObjectData, vision_attributes: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge user-provided attributes with vision-detected attributes
        Vision data takes precedence ONLY if vision actually detected the object
        """
        enhanced = {}
        
        # Start with user-provided attributes
        if object_data.attributes:
            enhanced.update(object_data.attributes)
        
        # Only enhance with vision data if it's REAL vision detection
        if vision_attributes.get('vision_detected', False):
            # Overwrite with vision data
            for key, value in vision_attributes.items():
                if key not in enhanced or key in ['color', 'shape', 'size_cm']:
                    enhanced[key] = value
        else:
            # Use fallback data but mark it clearly
            for key, value in vision_attributes.items():
                if key not in enhanced:
                    enhanced[key] = value
        
        # Add metadata
        enhanced['processed_at'] = datetime.now().isoformat()
        enhanced['vision_confidence'] = vision_attributes.get('confidence', 0.5)
        enhanced['source'] = 'vision_enhanced' if vision_attributes.get('vision_detected') else 'fallback'
        
        # Add warning if using fallback
        if not vision_attributes.get('vision_detected'):
            enhanced['warning'] = vision_attributes.get('reason', 'Vision detection unavailable')
        
        return enhanced
    
    def _detect_category(self, object_name: str, attributes: Dict[str, Any]) -> str:
        """
        Auto-detect object category based on name and attributes
        """
        object_lower = object_name.lower()
        
        # Check detected class from Vision Service
        detected_class = attributes.get('detected_class', '').lower()
        
        category_mapping = {
            'fruits': ['apple', 'banana', 'orange', 'grape', 'strawberry'],
            'animals': ['cat', 'dog', 'bird', 'fish', 'horse'],
            'furniture': ['chair', 'table', 'desk', 'bed', 'sofa', 'couch'],
            'electronics': ['laptop', 'phone', 'tablet', 'camera', 'tv', 'mouse', 'keyboard', 'cell phone', 'remote', 'remote control'],
            'office': ['book', 'pen', 'pencil', 'paper', 'folder', 'scissors'],
            'vehicles': ['car', 'bike', 'bus', 'train', 'plane', 'bicycle', 'motorcycle'],
            'clothing': ['shirt', 'pants', 'shoes', 'hat', 'jacket'],
            'kitchenware': ['bottle', 'cup', 'fork', 'knife', 'spoon', 'bowl']
        }
        
        # Check detected class first
        for category, items in category_mapping.items():
            if detected_class in items:
                return category
        
        # Then check object name
        for category, items in category_mapping.items():
            if object_lower in items:
                return category
        
        # Fallback based on attributes
        if 'animal' in str(attributes.get('shape', '')):
            return 'animals'
        elif 'furniture' in str(attributes.get('shape', '')):
            return 'furniture'
        elif attributes.get('material') in ['metal', 'plastic', 'electronic']:
            return 'electronics'
        
        return 'unknown'
    
    def _generate_description(self, object_name: str, attributes: Dict[str, Any]) -> str:
        """
        Generate automatic description based on object attributes
        """
        color = attributes.get('color', 'unknown color')
        shape = attributes.get('shape', 'unknown shape')
        material = attributes.get('material', 'unknown material')
        
        # Check if vision-enhanced
        if attributes.get('vision_detected'):
            detected_class = attributes.get('detected_class', object_name)
            confidence = attributes.get('confidence', 0)
            return f"Vision-detected {detected_class} (confidence: {confidence:.2f}) with {shape} shape"
        else:
            # Fallback description with warning
            reason = attributes.get('reason', 'using default attributes')
            return f"A {color} {object_name} with {shape} shape ({reason})"
    
    def generate_embedding(self, object_data, attributes: Dict[str, Any]) -> Optional[List[float]]:
        """
        Generate a normalized semantic embedding for an object or fact.
        
        Args:
            object_data: Object or Fact data
            attributes: Enhanced attributes dict
            
        Returns:
            List of floats representing the embedding, or None if numpy not available
        """
        try:
            from .services.embedding_client import EmbeddingClient

            item_type = "object" if hasattr(object_data, "name") else "fact"
            return EmbeddingClient().embed(item_type, object_data)
            
        except Exception as e:
            logger.error(f"Failed to generate semantic embedding: {e}")
            raise
    
    def _initialize_categories(self) -> Dict[str, List[str]]:
        """Initialize object category mapping"""
        return {
            'fruits': ['apple', 'banana', 'orange', 'grape', 'strawberry', 'pear', 'peach'],
            'animals': ['cat', 'dog', 'bird', 'fish', 'horse', 'rabbit', 'hamster'],
            'furniture': ['chair', 'table', 'desk', 'bed', 'sofa', 'cabinet', 'shelf', 'couch'],
            'electronics': ['laptop', 'phone', 'tablet', 'camera', 'tv', 'monitor', 'keyboard', 'mouse', 'cell phone', 'remote'],
            'office': ['book', 'pen', 'pencil', 'paper', 'folder', 'stapler', 'clipboard', 'scissors'],
            'vehicles': ['car', 'bike', 'bus', 'train', 'plane', 'boat', 'truck', 'bicycle', 'motorcycle'],
            'clothing': ['shirt', 'pants', 'shoes', 'hat', 'jacket', 'dress', 'skirt'],
            'food': ['pizza', 'burger', 'sandwich', 'soup', 'salad', 'pasta', 'rice'],
            'kitchenware': ['bottle', 'cup', 'fork', 'knife', 'spoon', 'bowl']
        }


# Global processor instance
object_processor = ObjectProcessor()
