"""
Instance Tracker - Track and distinguish multiple object instances

Enables fine-grained object distinction:
- Track multiple instances of same class (Buddy vs Max vs Cooper - all dogs)
- Visual feature-based matching
- Instance history and temporal consistency
- Multi-factor similarity scoring

Located in vision_service for co-location with vision processing

Example:
    tracker = InstanceTracker()
    
    # Track first dog (Buddy)
    buddy_features = extract_features(buddy_image)
    tracker.register_instance("dog", "Buddy", buddy_features)
    
    # Track second dog (Max)
    max_features = extract_features(max_image)
    tracker.register_instance("dog", "Max", max_features)
    
    # Later, identify which dog in new frame
    new_features = extract_features(new_frame)
    match, confidence = tracker.find_best_match("dog", new_features)
    # Result: match="Buddy", confidence=0.92
"""

from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum
import numpy as np
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class MatchingStrategy(Enum):
    """Object matching strategies"""
    COLOR_DOMINANT = "color_dominant"  # Use dominant color
    COLOR_HISTOGRAM = "color_histogram"  # Use color histogram
    SIZE_BASED = "size_based"  # Use size features
    SHAPE_BASED = "shape_based"  # Use shape features
    MULTI_FACTOR = "multi_factor"  # Weighted combination of all features
    TEMPORAL = "temporal"  # Consider temporal consistency


@dataclass
class InstanceRecord:
    """Record of a tracked instance"""
    instance_id: str  # e.g., "Buddy", "Max", "Cooper"
    class_name: str  # e.g., "dog", "cat", "phone"
    visual_features: Dict[str, Any]  # Complete visual feature set
    first_seen: datetime  # When first tracked
    last_seen: datetime  # Last observation time
    observation_count: int  # Number of frames seen
    confidence_score: float  # 0-1, confidence in matching
    metadata: Dict[str, Any]  # Additional tracking data


class InstanceTracker:
    """
    Professional instance tracking and distinction system
    
    Enables fine-grained object distinction:
    - Multiple instances of same class (Buddy vs Max)
    - Visual feature comparison
    - Temporal consistency
    - Confidence-based matching
    
    Features:
    - Multi-factor similarity (color, size, shape)
    - Temporal filtering (reject unlikely matches based on time)
    - Confidence tracking (improve confidence with more observations)
    - Instance history (full tracking history per instance)
    """
    
    def __init__(
        self,
        similarity_threshold: float = 0.7,
        temporal_weight: float = 0.1,
        max_tracked_instances: int = 100
    ):
        """
        Initialize instance tracker
        
        Args:
            similarity_threshold: Minimum similarity to match (0.0-1.0)
            temporal_weight: Weight of temporal consistency in matching
            max_tracked_instances: Maximum instances to track simultaneously
        """
        self.similarity_threshold = similarity_threshold
        self.temporal_weight = temporal_weight
        self.max_tracked_instances = max_tracked_instances
        
        # Instance storage: {class_name: {instance_id: InstanceRecord}}
        self.instances: Dict[str, Dict[str, InstanceRecord]] = {}
        self.observation_history: Dict[str, List[Dict]] = {}
    
    def register_instance(
        self,
        class_name: str,
        instance_id: str,
        visual_features: Dict[str, Any],
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Register a new instance
        
        Args:
            class_name: Object class (e.g., "dog", "cat")
            instance_id: Instance identifier (e.g., "Buddy", "Max")
            visual_features: Dictionary of visual features
            metadata: Optional tracking metadata
        
        Returns:
            True if registered successfully
        """
        try:
            if class_name not in self.instances:
                self.instances[class_name] = {}
            
            # Check if already registered
            if instance_id in self.instances[class_name]:
                logger.warning(f"Instance {class_name}/{instance_id} already registered")
                return False
            
            # Create record
            record = InstanceRecord(
                instance_id=instance_id,
                class_name=class_name,
                visual_features=visual_features,
                first_seen=datetime.now(),
                last_seen=datetime.now(),
                observation_count=1,
                confidence_score=0.8,  # Start with moderate confidence
                metadata=metadata or {}
            )
            
            # Store record
            self.instances[class_name][instance_id] = record
            
            # Initialize history
            history_key = f"{class_name}/{instance_id}"
            if history_key not in self.observation_history:
                self.observation_history[history_key] = []
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to register instance: {e}")
            return False
    
    def find_best_match(
        self,
        class_name: str,
        visual_features: Dict[str, Any],
        strategy: MatchingStrategy = MatchingStrategy.MULTI_FACTOR
    ) -> Tuple[Optional[str], float]:
        """
        Find best matching instance for given features
        
        Args:
            class_name: Object class to search in
            visual_features: Features to match against
            strategy: Matching algorithm to use
        
        Returns:
            (instance_id, confidence_score) or (None, 0.0)
        """
        if class_name not in self.instances or not self.instances[class_name]:
            return None, 0.0
        
        best_match = None
        best_score = 0.0
        
        for instance_id, record in self.instances[class_name].items():
            # Compute similarity
            if strategy == MatchingStrategy.MULTI_FACTOR:
                similarity = self._compute_multi_factor_similarity(
                    record.visual_features,
                    visual_features
                )
            elif strategy == MatchingStrategy.COLOR_HISTOGRAM:
                similarity = self._compute_color_histogram_similarity(
                    record.visual_features,
                    visual_features
                )
            elif strategy == MatchingStrategy.SIZE_BASED:
                similarity = self._compute_size_similarity(
                    record.visual_features,
                    visual_features
                )
            elif strategy == MatchingStrategy.SHAPE_BASED:
                similarity = self._compute_shape_similarity(
                    record.visual_features,
                    visual_features
                )
            else:
                similarity = self._compute_color_dominant_similarity(
                    record.visual_features,
                    visual_features
                )
            
            # Apply temporal weighting
            temporal_factor = self._compute_temporal_factor(record.last_seen)
            final_score = (similarity * (1 - self.temporal_weight) + 
                          temporal_factor * self.temporal_weight)
            
            if final_score > best_score and final_score >= self.similarity_threshold:
                best_score = final_score
                best_match = instance_id
        
        return best_match, best_score
    
    def update_instance(
        self,
        class_name: str,
        instance_id: str,
        visual_features: Dict[str, Any],
        confidence: float
    ) -> bool:
        """
        Update instance record with new observation
        
        Args:
            class_name: Object class
            instance_id: Instance identifier
            visual_features: Updated visual features
            confidence: Confidence of this observation
        
        Returns:
            True if updated successfully
        """
        try:
            if class_name not in self.instances:
                return False
            
            if instance_id not in self.instances[class_name]:
                return False
            
            record = self.instances[class_name][instance_id]
            
            # Update record
            record.last_seen = datetime.now()
            record.observation_count += 1
            # Exponential moving average for confidence
            record.confidence_score = (0.7 * record.confidence_score + 
                                       0.3 * confidence)
            # Update features (weighted average with new observation)
            record.visual_features = self._merge_features(
                record.visual_features,
                visual_features,
                weight=0.3
            )
            
            # Record in history
            history_key = f"{class_name}/{instance_id}"
            self.observation_history[history_key].append({
                "timestamp": record.last_seen,
                "confidence": confidence,
                "features": visual_features
            })
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to update instance: {e}")
            return False
    
    def get_instance_info(
        self,
        class_name: str,
        instance_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get information about tracked instance
        
        Args:
            class_name: Object class
            instance_id: Instance identifier
        
        Returns:
            Instance information dictionary or None
        """
        try:
            if class_name not in self.instances:
                return None
            
            if instance_id not in self.instances[class_name]:
                return None
            
            record = self.instances[class_name][instance_id]
            
            return {
                "instance_id": record.instance_id,
                "class_name": record.class_name,
                "first_seen": record.first_seen.isoformat(),
                "last_seen": record.last_seen.isoformat(),
                "observation_count": record.observation_count,
                "confidence_score": float(record.confidence_score),
                "visual_features": record.visual_features,
                "metadata": record.metadata
            }
        
        except Exception as e:
            logger.error(f"Failed to get instance info: {e}")
            return None
    
    def get_all_instances(self, class_name: str) -> List[Dict[str, Any]]:
        """
        Get all tracked instances of a class
        
        Returns:
            List of instance info dictionaries
        """
        if class_name not in self.instances:
            return []
        
        return [
            self.get_instance_info(class_name, instance_id)
            for instance_id in self.instances[class_name].keys()
        ]
    
    # ===== Similarity Computation Methods =====
    
    def _compute_multi_factor_similarity(
        self,
        features1: Dict,
        features2: Dict
    ) -> float:
        """Weighted combination of color, size, and shape similarities"""
        try:
            color_sim = self._compute_color_histogram_similarity(features1, features2) * 0.5
            size_sim = self._compute_size_similarity(features1, features2) * 0.3
            shape_sim = self._compute_shape_similarity(features1, features2) * 0.2
            
            return min(max(color_sim + size_sim + shape_sim, 0.0), 1.0)
        except:
            return 0.0
    
    def _compute_color_dominant_similarity(
        self,
        features1: Dict,
        features2: Dict
    ) -> float:
        """Compare dominant colors"""
        try:
            color1 = np.array(features1.get('color', {}).get('dominant_color', [128, 128, 128]))
            color2 = np.array(features2.get('color', {}).get('dominant_color', [128, 128, 128]))
            
            distance = np.linalg.norm(color1 - color2)
            similarity = 1.0 - (distance / 255.0)
            
            return max(0.0, similarity)
        except:
            return 0.0
    
    def _compute_color_histogram_similarity(
        self,
        features1: Dict,
        features2: Dict
    ) -> float:
        """Compare color histograms using chi-square distance"""
        try:
            hist1 = np.array(features1.get('color', {}).get('color_histogram', []))
            hist2 = np.array(features2.get('color', {}).get('color_histogram', []))
            
            if len(hist1) == 0 or len(hist2) == 0:
                return 0.5
            
            # Chi-square distance
            chi_square = 0.0
            for h1, h2 in zip(hist1, hist2):
                if (h1 + h2) > 0:
                    chi_square += ((h1 - h2) ** 2) / (h1 + h2)
            
            similarity = 1.0 / (1.0 + chi_square)
            
            return float(similarity)
        except:
            return 0.0
    
    def _compute_size_similarity(
        self,
        features1: Dict,
        features2: Dict
    ) -> float:
        """Compare size features"""
        try:
            size1 = features1.get('size', {})
            size2 = features2.get('size', {})
            
            aspect1 = size1.get('aspect_ratio', 1.0)
            aspect2 = size2.get('aspect_ratio', 1.0)
            
            # Compare aspect ratios
            aspect_diff = abs(aspect1 - aspect2) / max(aspect1, aspect2, 0.1)
            similarity = 1.0 - min(aspect_diff, 1.0)
            
            return float(similarity)
        except:
            return 0.0
    
    def _compute_shape_similarity(
        self,
        features1: Dict,
        features2: Dict
    ) -> float:
        """Compare shape features"""
        try:
            shape1 = features1.get('shape', {})
            shape2 = features2.get('shape', {})
            
            circ1 = shape1.get('circularity', 0.5)
            circ2 = shape2.get('circularity', 0.5)
            
            # Compare circularities
            circ_diff = abs(circ1 - circ2)
            similarity = 1.0 - min(circ_diff, 1.0)
            
            return float(similarity)
        except:
            return 0.0
    
    def _compute_temporal_factor(self, last_seen: datetime) -> float:
        """Compute temporal consistency factor"""
        try:
            time_diff = (datetime.now() - last_seen).total_seconds()
            # Higher score for recent observations
            factor = 1.0 / (1.0 + time_diff / 3600.0)  # Decay over hours
            return float(factor)
        except:
            return 0.5
    
    def _merge_features(
        self,
        features1: Dict,
        features2: Dict,
        weight: float = 0.3
    ) -> Dict:
        """Merge two feature sets (weighted average)"""
        try:
            # Simple merging - in production, would be smarter
            merged = {}
            
            for key in features1:
                if key in features2:
                    if isinstance(features1[key], dict):
                        merged[key] = self._merge_features(
                            features1[key],
                            features2[key],
                            weight
                        )
                    elif isinstance(features1[key], (int, float)):
                        merged[key] = (features1[key] * (1 - weight) + 
                                      features2[key] * weight)
                    else:
                        merged[key] = features1[key]
                else:
                    merged[key] = features1[key]
            
            return merged
        except:
            return features1
