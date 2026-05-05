"""
RAG Orchestrator - Complete RAG pipeline coordination

Provides end-to-end RAG pipeline:
1. Extract entities from user query (QueryProcessorService)
2. Validate knowledge base (SearchService)
3. Search for relevant knowledge (SearchService)
4. Format results for LLM context
5. Handle errors with fallback strategies

Single orchestration point for all RAG operations.
"""

from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from .query_processor import QueryProcessorService
from teachme_service.client import SearchService, SearchResult, SearchMetadata
import logging

logger = logging.getLogger(__name__)


@dataclass
class RAGPipeline:
    """Result of complete RAG pipeline execution"""
    success: bool
    entities: List[str]
    kb_valid: bool
    kb_total: int
    search_results: List[SearchResult]
    search_metadata: SearchMetadata
    knowledge_context: List[Dict]
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/debugging"""
        return {
            "success": self.success,
            "entities": self.entities,
            "kb_valid": self.kb_valid,
            "kb_total": self.kb_total,
            "results_count": len(self.search_results),
            "strategy": self.search_metadata.strategy_used.value,
            "error": self.error
        }


class RAGOrchestrator:
    """
    Complete RAG pipeline coordinator
    
    Pipeline:
    1. Extract entities from user query (NLP)
    2. Validate knowledge base availability
    3. Search knowledge base with automatic fallback
    4. Format results for LLM context
    5. Return diagnostic metadata
    
    Example:
        orchestrator = RAGOrchestrator()
        pipeline = orchestrator.process_query("What is my coffee cup?")
        
        if pipeline.success:
            for result in pipeline.search_results:
                print(f"{result.name}: {result.similarity:.1%}")
        else:
            print(f"RAG Error: {pipeline.error}")
    """
    
    def __init__(
        self,
        similarity_threshold: float = 0.5,
        top_k: int = 5,
        timeout: int = 30
    ):
        """
        Initialize RAG orchestrator
        
        Args:
            similarity_threshold: Minimum similarity score (0.0-1.0)
            top_k: Maximum search results to return
            timeout: Request timeout in seconds
        """
        self.query_processor = QueryProcessorService()
        self.search_service = SearchService(
            timeout=timeout,
            similarity_threshold=similarity_threshold
        )
        self.top_k = top_k
        self.timeout = timeout
    
    def process_query(self, transcription: str) -> RAGPipeline:
        """
        Process user query through complete RAG pipeline
        
        Pipeline:
        1. Extract entities
        2. Validate KB
        3. Search
        4. Format results
        
        Args:
            transcription: Raw user input/transcription
        
        Returns:
            RAGPipeline with complete results and metadata
        """
        try:
            # Step 1: Extract entities from transcription
            entities = self.query_processor.extract_entities(transcription)
            
            if not entities:
                return RAGPipeline(
                    success=False,
                    entities=[],
                    kb_valid=False,
                    kb_total=0,
                    search_results=[],
                    search_metadata=SearchMetadata(
                        strategy_used='embedding',
                        results_count=0,
                        kb_total=0,
                        error="No entities extracted from query"
                    ),
                    knowledge_context=[],
                    error="No entities extracted from query"
                )
            
            # Step 2: Validate KB
            is_valid, kb_total, kb_error = self.search_service.validate_kb()
            
            if not is_valid:
                return RAGPipeline(
                    success=False,
                    entities=entities,
                    kb_valid=False,
                    kb_total=kb_total,
                    search_results=[],
                    search_metadata=SearchMetadata(
                        strategy_used='embedding',
                        results_count=0,
                        kb_total=kb_total,
                        error=kb_error
                    ),
                    knowledge_context=[],
                    error=kb_error
                )
            
            # Step 3: Search KB (try each entity)
            all_results = {}
            
            for entity in entities:
                results, metadata = self.search_service.search(
                    entity,
                    top_k=self.top_k,
                    allow_fallback=True
                )
                
                # Collect unique results (avoid duplicates)
                for result in results:
                    obj_name = result.name.lower()
                    if obj_name not in all_results:
                        all_results[obj_name] = result
                    else:
                        # Keep highest similarity
                        if result.similarity > all_results[obj_name].similarity:
                            all_results[obj_name] = result
            
            # Step 4: Get metadata from last search
            results_list = list(all_results.values())
            _, final_metadata = self.search_service.search(
                entities[0],
                top_k=self.top_k,
                allow_fallback=True
            )
            
            # Update metadata with actual results
            final_metadata.results_count = len(results_list)
            
            # Step 5: Format for LLM context
            knowledge_context = [
                {
                    "object_name": result.name,
                    "confidence": result.similarity,
                    "category": result.category,
                    "tags": result.tags or [],
                    "description": result.description
                }
                for result in results_list
            ]
            
            return RAGPipeline(
                success=True,
                entities=entities,
                kb_valid=True,
                kb_total=kb_total,
                search_results=results_list,
                search_metadata=final_metadata,
                knowledge_context=knowledge_context,
                error=None
            )
        
        except Exception as e:
            error_msg = f"RAG pipeline error: {str(e)[:100]}"
            logger.error(error_msg, exc_info=True)
            
            return RAGPipeline(
                success=False,
                entities=[],
                kb_valid=False,
                kb_total=0,
                search_results=[],
                search_metadata=SearchMetadata(
                    strategy_used='embedding',
                    results_count=0,
                    kb_total=0,
                    error=error_msg
                ),
                knowledge_context=[],
                error=error_msg
            )
    
    def process_multiple_queries(
        self,
        transcriptions: List[str]
    ) -> List[RAGPipeline]:
        """
        Process multiple queries efficiently
        
        Args:
            transcriptions: List of user inputs
        
        Returns:
            List of RAGPipeline results
        """
        return [self.process_query(t) for t in transcriptions]
    
    def get_knowledge_context(self, transcription: str) -> Tuple[List[Dict], bool]:
        """
        Simplified interface - just returns knowledge context
        
        Args:
            transcription: User query
        
        Returns:
            (knowledge list, success boolean)
        """
        pipeline = self.process_query(transcription)
        return pipeline.knowledge_context, pipeline.success
    
    def get_diagnostic_info(self, transcription: str) -> Dict[str, Any]:
        """
        Get diagnostic information about RAG execution
        
        Useful for debugging and monitoring
        
        Args:
            transcription: User query
        
        Returns:
            Dictionary with diagnostic information
        """
        pipeline = self.process_query(transcription)
        
        return {
            "success": pipeline.success,
            "error": pipeline.error,
            "pipeline": pipeline.to_dict(),
            "search_metadata": pipeline.search_metadata.to_dict(),
            "results": [
                {
                    "name": r.name,
                    "similarity": r.similarity,
                    "category": r.category
                }
                for r in pipeline.search_results
            ]
        }
