"""
NEXI Enterprise Service Layer v3.1 - Distributed Architecture

Professional-grade services for RAG, query processing, and knowledge management.

ARCHITECTURE (Intended Distribution):
=====================================

Phase 1: Core RAG & Query Processing (SHARED - /service/)
- query_processor: Entity extraction, label extraction, intent classification
- rag_orchestrator: Orchestrates Phase 1 + Phase 2

Phase 2: Service Layer Abstraction (DISTRIBUTED - TeachMe service)
- SearchService, ObjectService, SearchResult, SearchMetadata
  Location: 05_teachme_service/teachme_service/client.py

Phase 3: Object Distinction System (DISTRIBUTED - Vision service)  
- VisualFeatureExtractor, VisualFeatures, ColorFeature, SizeFeature, ShapeFeature
  Location: 02_vision_service/vision_service/services/feature_extractor.py
- InstanceTracker, InstanceRecord, MatchingStrategy
  Location: 02_vision_service/vision_service/services/instance_tracker.py

IMPORT DESIGN:
================

Single source of truth - files only in their proper service locations
No duplication - deleted copies from /service/ to maintain clean architecture
"""

import sys
from pathlib import Path

# Add service directories to Python path for imports
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir / "05_teachme_service"))
sys.path.insert(0, str(root_dir / "02_vision_service"))

# Direct imports from /service/ (core shared components)
from .query_processor import QueryProcessorService
from .rag_orchestrator import RAGOrchestrator, RAGPipeline
from .config import ServiceConfig

# Imports from proper service locations (distributed architecture)
try:
    from teachme_service.client import SearchService, SearchResult, SearchMetadata, SearchStrategy, ObjectService
except ImportError as e:
    # Fallback if teachme_service is not available
    SearchService = None
    SearchResult = None
    SearchMetadata = None
    SearchStrategy = None
    ObjectService = None

try:
    from vision_service.services.feature_extractor import VisualFeatureExtractor, VisualFeatures, ColorFeature, SizeFeature, ShapeFeature
except ImportError as e:
    # Fallback if vision_service is not available
    VisualFeatureExtractor = None
    VisualFeatures = None
    ColorFeature = None
    SizeFeature = None
    ShapeFeature = None

try:
    from vision_service.services.instance_tracker import InstanceTracker, InstanceRecord, MatchingStrategy
except ImportError as e:
    # Fallback if vision_service is not available
    InstanceTracker = None
    InstanceRecord = None
    MatchingStrategy = None

__version__ = "3.1"
__all__ = [
    "QueryProcessorService",
    "SearchService",
    "SearchResult",
    "SearchMetadata",
    "SearchStrategy",
    "ObjectService",
    "RAGOrchestrator",
    "RAGPipeline",
    "VisualFeatureExtractor",
    "VisualFeatures",
    "ColorFeature",
    "SizeFeature",
    "ShapeFeature",
    "InstanceTracker",
    "InstanceRecord",
    "MatchingStrategy",
    "ServiceConfig"
]
