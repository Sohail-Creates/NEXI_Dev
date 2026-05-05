"""
TeachMe Service Client - Professional REST API wrapper

Unified client for TeachMe Knowledge Base operations:
- SearchService: Semantic and advanced search with fallback
- ObjectService: CRUD operations for objects

Pattern: Similar to vision_service_connector.py in the same service
All calls made via proper configuration - no hardcoded URLs
"""

import requests
import logging
from typing import List, Dict, Optional, Tuple, Any
from enum import Enum
from dataclasses import dataclass
import sys
import os

# Smart import: Try from root-level service config first, fallback if needed
try:
    from service.config import ServiceConfig
except ImportError:
    # Fallback: Add root to path and retry
    root_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    if root_path not in sys.path:
        sys.path.insert(0, root_path)
    try:
        from service.config import ServiceConfig
    except ImportError:
        # Last resort: Define ServiceConfig locally
        class ServiceConfig:
            TEACHME_SERVICE = "http://localhost:8004"
            TEACHME_API = "http://localhost:8004/api/v1"

logger = logging.getLogger(__name__)


# ============================================================================
# SEARCH SERVICE
# ============================================================================

class SearchStrategy(Enum):
    """Search strategy types"""
    EMBEDDING = "embedding"  # Semantic/vector similarity
    ADVANCED = "advanced"     # String matching fallback


@dataclass
class SearchResult:
    """Individual search result from TeachMe"""
    name: str
    similarity: float
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    object_id: Optional[str] = None
    description: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for LLM context"""
        return {
            "object_name": self.name,
            "confidence": self.similarity,
            "category": self.category,
            "tags": self.tags or [],
            "description": self.description
        }


@dataclass
class SearchMetadata:
    """Metadata about search operation"""
    strategy_used: SearchStrategy
    results_count: int
    kb_total: int
    error: Optional[str] = None
    fallback_used: bool = False
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "strategy": self.strategy_used.value,
            "results": self.results_count,
            "kb_total": self.kb_total,
            "fallback": self.fallback_used,
            "error": self.error
        }


class SearchService:
    """
    Professional search service for TeachMe knowledge base access.
    
    Features:
    - Semantic search via embeddings (preferred)
    - String matching fallback
    - Automatic strategy selection
    - Result validation and formatting
    - Error handling with diagnostics
    """
    
    def __init__(self, timeout: int = 30, similarity_threshold: float = 0.5):
        """
        Initialize search service
        
        Args:
            timeout: Request timeout in seconds
            similarity_threshold: Minimum similarity score (0.0-1.0)
        """
        self.timeout = timeout
        self.similarity_threshold = similarity_threshold
        self.teachme_url = ServiceConfig.TEACHME_SERVICE
    
    def validate_kb(self) -> Tuple[bool, int, Optional[str]]:
        """
        Validate knowledge base exists and has data
        
        Returns:
            (is_valid, total_items, error_message)
        """
        try:
            response = requests.get(
                f"{self.teachme_url}/knowledge/stats",
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                stats = response.json().get('stats', {})
                total = stats.get('total', 0)
                
                if total == 0:
                    return False, 0, "Knowledge base is empty. Teach objects first (Option 6)."
                return True, total, None
            else:
                return False, 0, f"KB stats failed: HTTP {response.status_code}"
        
        except Exception as e:
            return False, 0, f"KB validation error: {str(e)[:100]}"
    
    def search_by_embedding(
        self,
        query: str,
        top_k: int = 5
    ) -> Tuple[List[SearchResult], Optional[str]]:
        """
        Search using semantic embeddings (PREFERRED method)
        
        Args:
            query: Object name to search for
            top_k: Number of results to return
        
        Returns:
            (results, error)
        """
        try:
            response = requests.post(
                f"{self.teachme_url}/knowledge/search/embedding",
                params={
                    "query_object_name": query,
                    "top_k": top_k,
                    "similarity_threshold": self.similarity_threshold
                },
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                raw_results = response.json().get('results', [])
                results = [
                    SearchResult(
                        name=r.get('name'),
                        similarity=float(r.get('similarity', 0)),
                        category=r.get('category'),
                        tags=r.get('tags', []),
                        object_id=r.get('id'),
                        description=r.get('description')
                    )
                    for r in raw_results
                ]
                return results, None
            else:
                return [], f"Embedding search failed: HTTP {response.status_code}"
        
        except Exception as e:
            return [], f"Embedding search error: {str(e)[:100]}"
    
    def search_by_advanced(
        self,
        query: str
    ) -> Tuple[List[SearchResult], Optional[str]]:
        """
        Search using string matching (FALLBACK method)
        
        Args:
            query: Object name to search for
        
        Returns:
            (results, error)
        """
        try:
            response = requests.post(
                f"{self.teachme_url}/knowledge/search/advanced",
                params={
                    "name": query,
                    "search_mode": "any"
                },
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                raw_results = response.json().get('results', [])
                results = [
                    SearchResult(
                        name=r.get('name'),
                        similarity=0.5,  # Fallback search doesn't return scores
                        category=r.get('category'),
                        tags=r.get('tags', []),
                        object_id=r.get('id')
                    )
                    for r in raw_results
                ]
                return results, None
            else:
                return [], f"Advanced search failed: HTTP {response.status_code}"
        
        except Exception as e:
            return [], f"Advanced search error: {str(e)[:100]}"
    
    def search(
        self,
        query: str,
        top_k: int = 5,
        allow_fallback: bool = True
    ) -> Tuple[List[SearchResult], SearchMetadata]:
        """
        Search with automatic strategy selection and fallback
        
        Strategy:
        1. Try semantic search (embedding)
        2. If no results, try advanced search (string matching)
        3. Return best results
        
        Args:
            query: Object name to search for
            top_k: Number of results
            allow_fallback: Allow fallback to advanced search
        
        Returns:
            (results, metadata)
        """
        # Validate KB first
        is_valid, kb_total, kb_error = self.validate_kb()
        
        if not is_valid:
            return [], SearchMetadata(
                strategy_used=SearchStrategy.EMBEDDING,
                results_count=0,
                kb_total=0,
                error=kb_error
            )
        
        # Try embedding search (preferred)
        results, embed_error = self.search_by_embedding(query, top_k)
        
        if results:
            # Success with embedding search
            return results, SearchMetadata(
                strategy_used=SearchStrategy.EMBEDDING,
                results_count=len(results),
                kb_total=kb_total,
                error=None,
                fallback_used=False
            )
        
        # No results from embedding - try fallback
        if allow_fallback:
            results, adv_error = self.search_by_advanced(query)
            
            if results:
                return results, SearchMetadata(
                    strategy_used=SearchStrategy.ADVANCED,
                    results_count=len(results),
                    kb_total=kb_total,
                    error=None,
                    fallback_used=True
                )
            else:
                # Neither strategy found results
                return [], SearchMetadata(
                    strategy_used=SearchStrategy.EMBEDDING,
                    results_count=0,
                    kb_total=kb_total,
                    error="No results found in knowledge base",
                    fallback_used=True
                )
        else:
            # Fallback not allowed
            return [], SearchMetadata(
                strategy_used=SearchStrategy.EMBEDDING,
                results_count=0,
                kb_total=kb_total,
                error=embed_error
            )
    
    def get_all_objects(self) -> Tuple[List[Dict], Optional[str]]:
        """
        Fetch all objects from knowledge base
        
        Returns:
            (objects_list, error)
        """
        try:
            response = requests.get(
                f"{self.teachme_url}/knowledge/objects",
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                objects = response.json().get('objects', [])
                return objects, None
            else:
                return [], f"Failed to fetch objects: HTTP {response.status_code}"
        
        except Exception as e:
            return [], f"Get objects error: {str(e)[:100]}"
    
    def get_stats(self) -> Tuple[Dict, Optional[str]]:
        """
        Get knowledge base statistics
        
        Returns:
            (stats_dict, error)
        """
        try:
            response = requests.get(
                f"{self.teachme_url}/knowledge/stats",
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                stats = response.json().get('stats', {})
                return stats, None
            else:
                return {}, f"Failed to fetch stats: HTTP {response.status_code}"
        
        except Exception as e:
            return {}, f"Get stats error: {str(e)[:100]}"


# ============================================================================
# OBJECT SERVICE
# ============================================================================

class ObjectService:
    """
    Professional service for object management in TeachMe knowledge base.
    
    Features:
    - Teach new objects with visual features and embeddings
    - Forget objects from knowledge base
    - Retrieve object details
    - Find related objects
    - Error handling with diagnostics
    """
    
    def __init__(self, timeout: int = 30):
        """
        Initialize object service
        
        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.teachme_url = ServiceConfig.TEACHME_SERVICE
    
    def teach_object(
        self,
        label: str,
        object_data: Dict[str, Any],
        tags: Optional[List[str]] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Teach a new object to the knowledge base
        
        Args:
            label: Object name/label
            object_data: Object properties and embeddings
            tags: Optional tags for categorization
        
        Returns:
            (object_id, error)
        """
        try:
            payload = {
                "name": label,
                "type": object_data.get('type', 'user_taught_object'),
                "data": {
                    "attributes": object_data
                },
                "tags": tags or [],
                "confidence": object_data.get('average_confidence', 0.5)
            }
            
            response = requests.post(
                f"{self.teachme_url}/learn",
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code in [200, 201]:
                response_data = response.json()
                # TeachMe returns 'item_id' or 'id' or 'object_id'
                object_id = (
                    response_data.get('item_id') or 
                    response_data.get('id') or 
                    response_data.get('object_id') or 
                    'unknown'
                )
                return object_id, None
            else:
                try:
                    error_data = response.json()
                    error_msg = error_data.get('detail', f'HTTP {response.status_code}')
                except:
                    error_msg = f'HTTP {response.status_code}'
                return None, f"Failed to teach object: {error_msg}"
        
        except Exception as e:
            return None, f"Teach object error: {str(e)[:100]}"
    
    def forget_object(self, object_id: str) -> Optional[str]:
        """
        Forget/delete an object from knowledge base
        
        Args:
            object_id: ID of object to forget
        
        Returns:
            error message if failed, None if successful
        """
        try:
            response = requests.delete(
                f"{self.teachme_url}/forget/{object_id}",
                timeout=self.timeout
            )
            
            if response.status_code in [200, 204]:
                return None  # Success
            else:
                return f"Failed to forget object: HTTP {response.status_code}"
        
        except Exception as e:
            return f"Forget object error: {str(e)[:100]}"
    
    def forget_by_name(self, name: str) -> Optional[str]:
        """
        Forget/delete an object by name
        
        Args:
            name: Name of object to forget
        
        Returns:
            error message if failed, None if successful
        """
        try:
            response = requests.delete(
                f"{self.teachme_url}/forget-by-name/{name}",
                timeout=self.timeout
            )
            
            if response.status_code in [200, 204]:
                return None  # Success
            else:
                return f"Failed to forget object: HTTP {response.status_code}"
        
        except Exception as e:
            return f"Forget by name error: {str(e)[:100]}"
    
    def get_object(self, object_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Retrieve details of a specific object
        
        Args:
            object_id: ID of object to retrieve
        
        Returns:
            (object_data, error)
        """
        try:
            response = requests.get(
                f"{self.teachme_url}/knowledge/objects/{object_id}",
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                return response.json(), None
            else:
                return None, f"Failed to get object: HTTP {response.status_code}"
        
        except Exception as e:
            return None, f"Get object error: {str(e)[:100]}"
    
    def get_related_objects(
        self,
        object_id: str,
        limit: int = 5
    ) -> Tuple[List[Dict], Optional[str]]:
        """
        Find objects related to a given object
        
        Args:
            object_id: ID of reference object
            limit: Maximum number of related objects
        
        Returns:
            (related_objects, error)
        """
        try:
            response = requests.get(
                f"{self.teachme_url}/knowledge/related/{object_id}",
                params={"limit": limit},
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                objects = response.json().get('related', [])
                return objects, None
            else:
                return [], f"Failed to get related objects: HTTP {response.status_code}"
        
        except Exception as e:
            return [], f"Get related objects error: {str(e)[:100]}"
    
    def teach_batch(
        self,
        objects_list: List[Dict[str, Any]]
    ) -> Tuple[List[str], List[str]]:
        """
        Teach multiple objects in batch
        
        Args:
            objects_list: List of objects to teach
                Each object should have 'name', 'type', 'data' keys
        
        Returns:
            (successful_ids, error_messages)
        """
        successful_ids = []
        errors = []
        
        try:
            response = requests.post(
                f"{self.teachme_url}/knowledge/learn-batch",
                json={"objects": objects_list},
                timeout=self.timeout
            )
            
            if response.status_code in [200, 201]:
                result_data = response.json()
                successful_ids = result_data.get('successful_ids', [])
                errors = result_data.get('errors', [])
            else:
                errors.append(f"Batch teach failed: HTTP {response.status_code}")
        
        except Exception as e:
            errors.append(f"Batch teach error: {str(e)[:100]}")
        
        return successful_ids, errors
    
    def get_all_objects(self) -> Tuple[List[Dict], Optional[str]]:
        """
        Retrieve all objects from knowledge base
        
        Returns:
            (objects_list, error)
        """
        try:
            response = requests.get(
                f"{self.teachme_url}/knowledge/objects",
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                objects = response.json().get('objects', [])
                return objects, None
            else:
                return [], f"Failed to fetch objects: HTTP {response.status_code}"
        
        except Exception as e:
            return [], f"Get all objects error: {str(e)[:100]}"
