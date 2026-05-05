"""
Visual Feature Extractor - Advanced object visual feature analysis

Provides comprehensive visual feature extraction:
- Color detection and analysis (dominant color, color histogram)
- Size calculation (bounding box dimensions)
- Shape analysis (aspect ratio, contour complexity)
- Texture features (entropy, edge density)
- Position tracking (center coordinates)

These features enable fine-grained object distinction even when
multiple instances of the same object class exist (Buddy vs Max - both dogs)

Located in vision_service to enable co-location with vision processing
"""

from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class ColorFeature:
    """Color-based features"""
    dominant_color: Tuple[int, int, int]  # RGB tuple
    color_histogram: List[float]  # Normalized histogram [0-1]
    hsv_mean: Tuple[float, float, float]  # HSV mean values
    color_variance: float  # Color variation in image
    
    def to_dict(self) -> Dict:
        return {
            "dominant_color": self.dominant_color,
            "color_histogram": self.color_histogram,
            "hsv_mean": self.hsv_mean,
            "color_variance": float(self.color_variance)
        }


@dataclass
class SizeFeature:
    """Size-based features"""
    width: int  # Pixels
    height: int  # Pixels
    area: int  # Pixels squared
    aspect_ratio: float  # Width / Height
    
    def to_dict(self) -> Dict:
        return {
            "width": self.width,
            "height": self.height,
            "area": self.area,
            "aspect_ratio": float(self.aspect_ratio)
        }


@dataclass
class ShapeFeature:
    """Shape-based features"""
    contour_complexity: float  # Perimeter / Area (normalized)
    circularity: float  # 4π*Area / Perimeter²
    eccentricity: float  # 0=circle, 1=line
    symmetry_score: float  # 0-1, higher = more symmetric
    edge_density: float  # Edges per pixel area
    
    def to_dict(self) -> Dict:
        return {
            "contour_complexity": float(self.contour_complexity),
            "circularity": float(self.circularity),
            "eccentricity": float(self.eccentricity),
            "symmetry_score": float(self.symmetry_score),
            "edge_density": float(self.edge_density)
        }


@dataclass
class VisualFeatures:
    """Complete visual feature set"""
    color: ColorFeature
    size: SizeFeature
    shape: ShapeFeature
    position: Tuple[int, int]  # Center coordinates
    texture_entropy: float  # Image entropy (0=uniform, higher=complex)
    brightness: float  # Mean brightness [0-255]
    
    def to_dict(self) -> Dict:
        return {
            "color": self.color.to_dict(),
            "size": self.size.to_dict(),
            "shape": self.shape.to_dict(),
            "position": self.position,
            "texture_entropy": float(self.texture_entropy),
            "brightness": float(self.brightness)
        }


class VisualFeatureExtractor:
    """
    Extracts comprehensive visual features from object images/frames
    
    Used for:
    - Instance-level object distinction (Buddy vs Max vs Cooper)
    - Object matching across frames
    - Feature-based object verification
    
    Requires ndimage and scipy for advanced analysis
    """
    
    def __init__(self):
        """Initialize feature extractor"""
        try:
            from scipy import ndimage
            import cv2
            self.ndimage = ndimage
            self.cv2 = cv2
            self.available = True
        except ImportError:
            logger.warning("scipy/cv2 not available - limited feature extraction")
            self.available = False
    
    def extract_features(
        self,
        image: np.ndarray,
        mask: Optional[np.ndarray] = None
    ) -> Optional[VisualFeatures]:
        """
        Extract all visual features from image
        
        Args:
            image: Input image (RGB or BGR)
            mask: Optional segmentation mask (foreground=255, background=0)
        
        Returns:
            VisualFeatures if successful, None if extraction fails
        """
        if not self.available:
            logger.warning("Cannot extract features - cv2 not available")
            return None
        
        try:
            # Convert to RGB if needed
            if len(image.shape) == 3 and image.shape[2] == 3:
                rgb_image = image if image.shape[2] == 3 else self.cv2.cvtColor(image, self.cv2.COLOR_BGR2RGB)
            else:
                logger.warning("Invalid image format")
                return None
            
            # Use mask if provided, otherwise use whole image
            if mask is not None:
                working_image = rgb_image.copy()
                working_image[mask == 0] = [255, 255, 255]  # White background
            else:
                working_image = rgb_image
            
            # Extract color features
            color_feature = self._extract_color(working_image, mask)
            
            # Extract size features
            size_feature = self._extract_size(image, mask)
            
            # Extract shape features
            shape_feature = self._extract_shape(image, mask)
            
            # Get position (center)
            position = self._get_position(mask if mask is not None else image)
            
            # Get texture features
            texture_entropy = self._compute_entropy(working_image)
            brightness = np.mean(rgb_image)
            
            return VisualFeatures(
                color=color_feature,
                size=size_feature,
                shape=shape_feature,
                position=position,
                texture_entropy=texture_entropy,
                brightness=brightness
            )
        
        except Exception as e:
            logger.error(f"Feature extraction failed: {str(e)}")
            return None
    
    def _extract_color(
        self,
        image: np.ndarray,
        mask: Optional[np.ndarray] = None
    ) -> ColorFeature:
        """Extract color-based features"""
        try:
            # Get region of interest
            if mask is not None:
                roi = image[mask > 0]
            else:
                roi = image.reshape(-1, 3)
            
            # Dominant color (centroid of color distribution)
            dominant_color = np.mean(roi, axis=0).astype(int)
            dominant_color = tuple(dominant_color.tolist())
            
            # Color histogram (3 channels, 8 bins each)
            histogram = []
            for channel in range(3):
                hist, _ = np.histogram(roi[:, channel], bins=8, range=(0, 256))
                histogram.extend((hist / hist.sum()).tolist())
            
            # HSV analysis
            hsv_image = self.cv2.cvtColor(image.astype(np.uint8), self.cv2.COLOR_RGB2HSV)
            if mask is not None:
                hsv_roi = hsv_image[mask > 0]
            else:
                hsv_roi = hsv_image.reshape(-1, 3)
            
            hsv_mean = tuple(np.mean(hsv_roi, axis=0).tolist())
            
            # Color variance
            color_variance = np.var(roi)
            
            return ColorFeature(
                dominant_color=dominant_color,
                color_histogram=histogram,
                hsv_mean=hsv_mean,
                color_variance=float(color_variance)
            )
        
        except Exception as e:
            logger.warning(f"Color extraction failed: {e}")
            return ColorFeature(
                dominant_color=(128, 128, 128),
                color_histogram=[0.125] * 24,
                hsv_mean=(0, 0, 128),
                color_variance=0.0
            )
    
    def _extract_size(
        self,
        image: np.ndarray,
        mask: Optional[np.ndarray] = None
    ) -> SizeFeature:
        """Extract size-based features"""
        try:
            if mask is not None:
                height, width = mask.shape
                area = np.sum(mask > 0)
            else:
                height, width = image.shape[:2]
                area = height * width
            
            aspect_ratio = width / height if height > 0 else 1.0
            
            return SizeFeature(
                width=width,
                height=height,
                area=int(area),
                aspect_ratio=float(aspect_ratio)
            )
        
        except Exception as e:
            logger.warning(f"Size extraction failed: {e}")
            return SizeFeature(width=0, height=0, area=0, aspect_ratio=1.0)
    
    def _extract_shape(
        self,
        image: np.ndarray,
        mask: Optional[np.ndarray] = None
    ) -> ShapeFeature:
        """Extract shape-based features"""
        try:
            if mask is None:
                # Simple thresholding
                gray = self.cv2.cvtColor(image.astype(np.uint8), self.cv2.COLOR_RGB2GRAY)
                _, mask = self.cv2.threshold(gray, 127, 255, self.cv2.THRESH_BINARY)
            
            # Find contours
            contours, _ = self.cv2.findContours(
                mask.astype(np.uint8),
                self.cv2.RETR_TREE,
                self.cv2.CHAIN_APPROX_SIMPLE
            )
            
            if not contours:
                return ShapeFeature(
                    contour_complexity=0.0,
                    circularity=0.0,
                    eccentricity=0.0,
                    symmetry_score=0.0,
                    edge_density=0.0
                )
            
            # Use largest contour
            contour = max(contours, key=self.cv2.contourArea)
            perimeter = self.cv2.arcLength(contour, True)
            area = self.cv2.contourArea(contour)
            
            # Circularity
            if perimeter > 0:
                circularity = 4 * np.pi * area / (perimeter ** 2)
            else:
                circularity = 0.0
            
            # Contour complexity
            contour_complexity = perimeter / (area + 1e-6)
            
            # Fit ellipse for eccentricity
            if len(contour) >= 5:
                ellipse = self.cv2.fitEllipse(contour)
                axes = sorted([ellipse[1][0], ellipse[1][1]])
                if axes[1] > 0:
                    eccentricity = np.sqrt(1 - (axes[0] / axes[1]) ** 2)
                else:
                    eccentricity = 0.0
            else:
                eccentricity = 0.0
            
            # Edge density
            edges = self.cv2.Canny(mask.astype(np.uint8), 100, 200)
            edge_density = np.sum(edges > 0) / (area + 1e-6)
            
            # Symmetry (simplified)
            symmetry_score = 1.0 - min(abs(circularity - 1.0), 1.0)
            
            return ShapeFeature(
                contour_complexity=float(contour_complexity),
                circularity=float(circularity),
                eccentricity=float(eccentricity),
                symmetry_score=float(symmetry_score),
                edge_density=float(edge_density)
            )
        
        except Exception as e:
            logger.warning(f"Shape extraction failed: {e}")
            return ShapeFeature(
                contour_complexity=0.0,
                circularity=0.0,
                eccentricity=0.0,
                symmetry_score=0.0,
                edge_density=0.0
            )
    
    def _get_position(self, mask_or_image: np.ndarray) -> Tuple[int, int]:
        """Get center position of object"""
        try:
            if len(mask_or_image.shape) == 2:
                # It's a mask
                y_indices, x_indices = np.where(mask_or_image > 0)
            else:
                # It's an image
                y_indices, x_indices = np.where(mask_or_image[:, :, 0] > 0)
            
            if len(y_indices) > 0:
                center_y = int(np.mean(y_indices))
                center_x = int(np.mean(x_indices))
                return (center_x, center_y)
            else:
                height, width = mask_or_image.shape[:2]
                return (width // 2, height // 2)
        
        except Exception as e:
            logger.warning(f"Position extraction failed: {e}")
            height, width = mask_or_image.shape[:2]
            return (width // 2, height // 2)
    
    def _compute_entropy(self, image: np.ndarray) -> float:
        """Compute image entropy (texture complexity)"""
        try:
            # Convert to grayscale for entropy
            gray = self.cv2.cvtColor(image.astype(np.uint8), self.cv2.COLOR_RGB2GRAY)
            
            # Compute histogram
            hist, _ = np.histogram(gray, bins=256, range=(0, 256))
            hist = hist / hist.sum()
            
            # Compute entropy (Shannon entropy)
            entropy = -np.sum(hist[hist > 0] * np.log2(hist[hist > 0]))
            
            return float(entropy)
        
        except Exception as e:
            logger.warning(f"Entropy computation failed: {e}")
            return 0.0
