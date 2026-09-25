"""
Embedding Index for Fast Similarity Search
Supports FAISS-based indexing with fallback to linear search
"""

import numpy as np  # type: ignore
import logging
from typing import List, Dict, Tuple, Optional, Any
from .config import search_index_config

logger = logging.getLogger(__name__)

# Try to import FAISS
try:
    import faiss  # type: ignore
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False
    logger.warning("FAISS not available - using linear search fallback")


class EmbeddingIndex:
    """
    Manages vector embeddings with optional FAISS acceleration.
    Falls back to linear search if FAISS unavailable or disabled.
    """
    
    def __init__(self, dimension: int = 128, use_faiss: bool = True):
        """
        Initialize the embedding index.
        
        Args:
            dimension: Vector dimension (128 is standard)
            use_faiss: Whether to use FAISS if available
        """
        self.dimension = dimension
        self.use_faiss = use_faiss and HAS_FAISS and search_index_config.USE_FAISS
        self.embeddings: Dict[str, np.ndarray] = {}  # item_id -> embedding vector
        self.index: Optional[Any] = None  # FAISS index
        self.index_mapping: List[str] = []  # Maps FAISS index position to item_id
        
        logger.info(f"EmbeddingIndex initialized (FAISS: {self.use_faiss}, dimension: {dimension})")
        
        if self.use_faiss:
            self._initialize_faiss_index()
    
    def _initialize_faiss_index(self):
        """Initialize FAISS index"""
        try:
            # Sentence-transformer vectors are normalized. Inner product is
            # therefore cosine similarity and keeps FAISS results identical to
            # the linear fallback's score semantics.
            self.index = faiss.IndexFlatIP(self.dimension)
            logger.info("FAISS index created (cosine similarity)")
        except Exception as e:
            logger.error(f"Failed to initialize FAISS index: {e}")
            self.use_faiss = False
            self.index = None
    
    def add_embedding(self, item_id: str, embedding: List[float]) -> bool:
        """
        Add an embedding to the index.
        
        Args:
            item_id: Unique identifier for the item
            embedding: Vector embedding (list of floats)
            
        Returns:
            True if added successfully, False otherwise
        """
        if embedding is None or len(embedding) == 0:
            return False
        
        try:
            vector = np.array([embedding], dtype=np.float32)
            
            # Validate dimension
            if vector.shape[1] != self.dimension:
                logger.warning(f"Embedding dimension mismatch for {item_id}: expected {self.dimension}, got {vector.shape[1]}")
                return False

            norm = np.linalg.norm(vector, axis=1, keepdims=True)
            if np.any(norm == 0):
                logger.warning("Refusing zero-length embedding for %s", item_id)
                return False
            vector = vector / norm
            
            # Store in memory
            self.embeddings[item_id] = vector[0]
            
            # Add to FAISS if enabled
            if self.use_faiss and self.index is not None:
                try:
                    self.index.add(vector)
                    self.index_mapping.append(item_id)
                except Exception as e:
                    logger.warning(f"Failed to add to FAISS index: {e}")
                    # Continue with linear search as fallback
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding embedding for {item_id}: {e}")
            return False
    
    def remove_embedding(self, item_id: str) -> bool:
        """
        Remove an embedding from the index.
        
        Args:
            item_id: Identifier of item to remove
            
        Returns:
            True if removed, False if not found
        """
        if item_id not in self.embeddings:
            return False
        
        del self.embeddings[item_id]
        
        # FAISS doesn't support efficient removal, so rebuild if needed
        if self.use_faiss and item_id in self.index_mapping:
            self._rebuild_faiss_index()
        
        return True
    
    def _rebuild_faiss_index(self):
        """Rebuild FAISS index from current embeddings"""
        try:
            if self.index is None:
                self._initialize_faiss_index()
            else:
                self.index.reset()
            
            self.index_mapping.clear()
            
            if not self.embeddings:
                return
            
            # Rebuild from memory
            vectors = []
            for item_id in self.embeddings.keys():
                vectors.append(self.embeddings[item_id])
                self.index_mapping.append(item_id)
            
            vectors_array = np.array(vectors, dtype=np.float32)
            norms = np.linalg.norm(vectors_array, axis=1, keepdims=True)
            vectors_array = vectors_array / np.where(norms == 0, 1.0, norms)
            self.index.add(vectors_array)
            
            logger.info(f"FAISS index rebuilt with {len(vectors)} embeddings")
            
        except Exception as e:
            logger.error(f"Error rebuilding FAISS index: {e}")
            self.use_faiss = False
    
    def search(self, query_embedding: List[float], k: int = 5, threshold: float = 0.3) -> List[Tuple[str, float]]:
        """
        Search for similar embeddings.
        
        Args:
            query_embedding: Query vector (list of floats or numpy array)
            k: Number of results to return
            threshold: Minimum similarity score (0.0-1.0), higher = more similar
            
        Returns:
            List of (item_id, similarity_score) tuples, sorted by similarity
        """
        # Handle numpy array input
        if hasattr(query_embedding, 'tolist'):
            query_embedding = query_embedding.tolist()
        
        if not query_embedding or len(query_embedding) == 0:
            return []
        
        try:
            query_vector = np.array([query_embedding], dtype=np.float32)
            norm = np.linalg.norm(query_vector, axis=1, keepdims=True)
            if np.any(norm == 0):
                return []
            query_vector = query_vector / norm
            
            # Use FAISS if available and working
            if self.use_faiss and self.index is not None and len(self.index_mapping) > 0:
                return self._faiss_search(query_vector, k, threshold)
            else:
                # Fallback to linear search
                return self._linear_search(query_vector, k, threshold)
                
        except Exception as e:
            logger.error(f"Error during embedding search: {e}")
            return []
    
    def _faiss_search(self, query_vector: np.ndarray, k: int, threshold: float) -> List[Tuple[str, float]]:
        """Search using FAISS"""
        try:
            similarities, indices = self.index.search(query_vector, min(k, len(self.index_mapping)))
            
            results = []
            for score, idx in zip(similarities[0], indices[0]):
                if idx == -1:  # Invalid index
                    continue
                
                if idx >= len(self.index_mapping):
                    logger.warning(f"Invalid FAISS index mapping: {idx} >= {len(self.index_mapping)}")
                    continue
                
                item_id = self.index_mapping[idx]
                similarity = float(score)
                
                if similarity >= threshold:
                    results.append((item_id, similarity))
            
            return sorted(results, key=lambda x: x[1], reverse=True)
            
        except Exception as e:
            logger.error(f"FAISS search failed: {e}, falling back to linear search")
            self.use_faiss = False
            return self._linear_search(query_vector, k, threshold)
    
    def _linear_search(self, query_vector: np.ndarray, k: int, threshold: float) -> List[Tuple[str, float]]:
        """Fallback linear search through all embeddings"""
        results = []
        
        query = query_vector[0]
        
        for item_id, embedding in self.embeddings.items():
            # Calculate cosine similarity
            dot_product = np.dot(query, embedding)
            norm_query = np.linalg.norm(query)
            norm_embedding = np.linalg.norm(embedding)
            
            if norm_query == 0 or norm_embedding == 0:
                similarity = 0.0
            else:
                similarity = float(dot_product / (norm_query * norm_embedding))
            
            if similarity >= threshold:
                results.append((item_id, similarity))
        
        # Sort by similarity descending and return top k
        return sorted(results, key=lambda x: x[1], reverse=True)[:k]
    
    def clear(self):
        """Clear all embeddings and index"""
        self.embeddings.clear()
        self.index_mapping.clear()
        
        if self.use_faiss and self.index is not None:
            self._initialize_faiss_index()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the index"""
        return {
            "total_embeddings": len(self.embeddings),
            "dimension": self.dimension,
            "using_faiss": self.use_faiss,
            "index_size": len(self.index_mapping) if self.use_faiss else 0,
            "memory_usage_mb": (len(self.embeddings) * self.dimension * 4) / 1024 / 1024  # Rough estimate
        }
