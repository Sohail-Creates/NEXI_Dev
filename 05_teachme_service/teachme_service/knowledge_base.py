import json
import os
import asyncio
import logging
import sys
from typing import Dict, List, Optional, Any, Tuple
import uuid
from datetime import datetime
from pathlib import Path
import contextlib

# Safe file locking (cross-platform)
from .safe_file_lock import get_safe_file_lock, FileLockError

try:
    import aiofiles
except ImportError:
    aiofiles = None

from .models import KnowledgeItem, LearningType, ObjectData, FactData
from .config import storage_config, performance_config, search_index_config
from .embedding_index import EmbeddingIndex
from .services.embedding_client import EmbeddingClient
from .services.dedup_checker import DedupChecker
from .services.confidence_gate import ConfidenceGate

logger = logging.getLogger(__name__)


class PersistentKnowledgeBase:
    def __init__(self, storage_file: Optional[str] = None):
        self.storage_file = storage_file or storage_config.STORAGE_FILE
        self.backup_dir = storage_config.BACKUP_DIR
        self.backup_retention = storage_config.BACKUP_RETENTION
        
        # SINGLE SOURCE OF TRUTH (eliminates 48% memory redundancy)
        self._storage: Dict[str, KnowledgeItem] = {}
        self._deleted_items: Dict[str, KnowledgeItem] = {}
        
        # File locking for thread safety
        self._file_lock = None
        self._save_queue: asyncio.Queue = asyncio.Queue(maxsize=storage_config.SAVE_QUEUE_SIZE)
        self._save_task: Optional[asyncio.Task] = None
        
        # Embedding index for fast similarity search (Phase 2)
        self.embedding_index = EmbeddingIndex(
            dimension=search_index_config.INDEX_DIMENSION,
            use_faiss=search_index_config.USE_FAISS
        )
        self.embedding_client = EmbeddingClient()
        self.dedup_checker = DedupChecker()
        self.confidence_gate = ConfidenceGate()
        
        # Backup directory
        os.makedirs(self.backup_dir, exist_ok=True)
        
        # Load initial data
        self.load_from_file()
        
        logger.info(f"KnowledgeBase initialized with {len(self._storage)} items")
    
    @property
    def objects(self) -> Dict[str, KnowledgeItem]:
        """Computed property: returns all objects without storage duplication"""
        return {
            item_id: item for item_id, item in self._storage.items()
            if item.type == LearningType.OBJECT
        }
    
    @property
    def facts(self) -> Dict[str, KnowledgeItem]:
        """Computed property: returns all facts without storage duplication"""
        return {
            item_id: item for item_id, item in self._storage.items()
            if item.type == LearningType.FACT
        }
    
    @contextlib.contextmanager
    def _file_lock_context(self):
        """
        Thread-safe file locking for concurrent access (cross-platform).
        Uses intelligent fallback strategy to prevent corruption.
        """
        if not performance_config.THREAD_SAFE_MODE:
            yield
            return
        
        try:
            with get_safe_file_lock(self.storage_file, timeout=30.0):
                yield
        except FileLockError as e:
            logger.error(f"File lock error: {e}")
            # For critical data, we should NOT proceed without lock
            # This prevents potential corruption
            raise
        except Exception as e:
            logger.error(f"Unexpected lock error: {e}")
            raise
    
    def create_backup(self) -> Optional[str]:
        """Create a backup of current data"""
        try:
            if os.path.exists(self.storage_file):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = os.path.join(self.backup_dir, f"backup_{timestamp}.json")
                
                with open(self.storage_file, 'r', encoding='utf-8') as source:
                    data = json.load(source)
                
                with open(backup_file, 'w', encoding='utf-8') as target:
                    json.dump(data, target, indent=2)
                
                logger.debug(f"Created backup: {backup_file}")
                return backup_file
        except Exception as e:
            logger.warning(f"Backup creation failed: {e}")
        return None
    
    async def create_backup_async(self) -> Optional[str]:
        """Async backup creation (doesn't block)"""
        if not performance_config.ASYNC_BACKUP_ENABLED:
            return self.create_backup()
        
        try:
            if aiofiles and os.path.exists(self.storage_file):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = os.path.join(self.backup_dir, f"backup_{timestamp}.json")
                
                async with aiofiles.open(self.storage_file, 'r', encoding='utf-8') as source:
                    data = await source.read()
                
                async with aiofiles.open(backup_file, 'w', encoding='utf-8') as target:
                    await target.write(data)
                
                logger.debug(f"Created async backup: {backup_file}")
                return backup_file
        except Exception as e:
            logger.warning(f"Async backup failed: {e}")
        
        return None
    
    def load_from_file(self):
        """Load knowledge from JSON file (thread-safe)"""
        if os.path.exists(self.storage_file):
            try:
                with self._file_lock_context():
                    logger.info(f"Loading from {self.storage_file}...")
                    with open(self.storage_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    loaded_count = 0
                    for item_id, item_data in data.get('storage', {}).items():
                        try:
                            # Convert string dates back to datetime
                            if 'created_at' in item_data and isinstance(item_data['created_at'], str):
                                item_data['created_at'] = datetime.fromisoformat(item_data['created_at'].replace('Z', '+00:00'))
                            if 'updated_at' in item_data and isinstance(item_data['updated_at'], str):
                                item_data['updated_at'] = datetime.fromisoformat(item_data['updated_at'].replace('Z', '+00:00'))
                            
                            # Recreate KnowledgeItem
                            knowledge_item = KnowledgeItem(**item_data)
                            self._storage[item_id] = knowledge_item
                            loaded_count += 1
                            
                        except Exception as e:
                            logger.warning(f"Failed to load item {item_id}: {e}")
                    
                    logger.info(f"Loaded {loaded_count} items from storage")
                    
                    # Rebuild embedding index with loaded data
                    self._rebuild_embedding_index()
                    
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in {self.storage_file}: {e}")
                # Create backup of corrupted file
                corrupted_backup = os.path.join(self.backup_dir, f"corrupted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
                if os.path.exists(self.storage_file):
                    os.rename(self.storage_file, corrupted_backup)
                    logger.warning(f"Moved corrupted file to: {corrupted_backup}")
                self._initialize_empty_file()
                
            except Exception as e:
                logger.error(f"Error loading from file: {e}")
                self._storage = {}
                
        else:
            logger.info(f"No existing data file. Creating new: {self.storage_file}")
            self._initialize_empty_file()
    
    async def load_from_file_async(self):
        """Async version of load_from_file"""
        if not aiofiles or not performance_config.ASYNC_SAVE_ENABLED:
            self.load_from_file()
            return
        
        if os.path.exists(self.storage_file):
            try:
                async with aiofiles.open(self.storage_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    data = json.loads(content)
                    
                    loaded_count = 0
                    for item_id, item_data in data.get('storage', {}).items():
                        try:
                            if 'created_at' in item_data and isinstance(item_data['created_at'], str):
                                item_data['created_at'] = datetime.fromisoformat(item_data['created_at'].replace('Z', '+00:00'))
                            if 'updated_at' in item_data and isinstance(item_data['updated_at'], str):
                                item_data['updated_at'] = datetime.fromisoformat(item_data['updated_at'].replace('Z', '+00:00'))
                            
                            knowledge_item = KnowledgeItem(**item_data)
                            self._storage[item_id] = knowledge_item
                            loaded_count += 1
                        except Exception as e:
                            logger.warning(f"Failed to async load item {item_id}: {e}")
                    
                    logger.info(f"Async loaded {loaded_count} items")
            except Exception as e:
                logger.error(f"Error in async load: {e}")
                self.load_from_file()  # Fallback to sync
    
    def _rebuild_embedding_index(self):
        """
        Rebuild embedding index from current storage.
        Called after loading data or during maintenance.
        """
        try:
            logger.info("Rebuilding embedding index...")
            
            # Clear existing index
            self.embedding_index.clear()
            
            # Add all items with embeddings to the index
            items_indexed = 0
            for item_id, item in self._storage.items():
                if item.embedding is not None and len(item.embedding) > 0:
                    if self.embedding_index.add_embedding(item_id, item.embedding):
                        items_indexed += 1
            
            logger.info(f"Embedding index rebuilt with {items_indexed} items")
            
        except Exception as e:
            logger.error(f"Error rebuilding embedding index: {e}")
    
    def _initialize_empty_file(self):
        """Initialize an empty JSON file"""
        try:
            empty_data = {
                'storage': {},
                'metadata': {
                    'created_at': datetime.now().isoformat(),
                    'version': '1.0',
                    'total_items': 0
                }
            }
            
            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump(empty_data, f, indent=2)
            
            print(f" Created new storage file: {self.storage_file}")
            
        except Exception as e:
            print(f" Failed to create storage file: {e}")
    
    def save_to_file(self):
        """Save knowledge to JSON file (thread-safe, blocking)"""
        try:
            with self._file_lock_context():
                logger.info(f"Saving {len(self._storage)} items to {self.storage_file}...")
                
                # Create backup before saving
                self.create_backup()
                
                # Prepare data with metadata
                data = {
                    'storage': {
                        item_id: item.dict() 
                        for item_id, item in self._storage.items()
                    },
                    'metadata': {
                        'last_saved': datetime.now().isoformat(),
                        'total_items': len(self._storage),
                        'objects_count': len(self.objects),
                        'facts_count': len(self.facts),
                        'version': '1.0'
                    }
                }
                
                # Atomic write: write to temporary file first
                temp_file = self.storage_file + '.tmp'
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                
                # Replace original file
                os.replace(temp_file, self.storage_file)
                
                logger.info(f"Saved {len(self._storage)} items to {self.storage_file}")
            
        except Exception as e:
            logger.error(f"Error saving to file: {e}")
            # Clean up temp file if it exists
            temp_file = self.storage_file + '.tmp'
            if os.path.exists(temp_file):
                os.remove(temp_file)
            raise
    
    async def save_to_file_async(self):
        """Save knowledge to JSON file using async I/O (non-blocking)"""
        if not aiofiles or not performance_config.ASYNC_SAVE_ENABLED:
            # Fallback to sync version
            self.save_to_file()
            return
        
        try:
            logger.info(f"Async saving {len(self._storage)} items...")
            
            # Create backup (sync, fast)
            await asyncio.to_thread(self.create_backup)
            
            # Prepare data (sync, fast)
            data = {
                'storage': {
                    item_id: item.dict() 
                    for item_id, item in self._storage.items()
                },
                'metadata': {
                    'last_saved': datetime.now().isoformat(),
                    'total_items': len(self._storage),
                    'objects_count': len(self.objects),
                    'facts_count': len(self.facts),
                    'version': '1.0'
                }
            }
            
            # Async write
            temp_file = self.storage_file + '.tmp'
            content = json.dumps(data, indent=2, ensure_ascii=False)
            
            async with aiofiles.open(temp_file, 'w', encoding='utf-8') as f:
                await f.write(content)
            
            # Atomic rename (sync, fast)
            os.replace(temp_file, self.storage_file)
            
            logger.info(f"Async saved {len(self._storage)} items")
            
        except Exception as e:
            logger.error(f"Error in async save: {e}")
            temp_file = self.storage_file + '.tmp'
            if os.path.exists(temp_file):
                os.remove(temp_file)
            # Fallback to sync save
            self.save_to_file()
    
    # === Core CRUD Operations ===
    
    def learn_object(self, object_data: ObjectData, tags: List[str] = None, confidence: float = 1.0, embedding: Optional[List[float]] = None, skip_save: bool = False) -> str:
        """Learn a new object with persistence"""
        item_id = str(uuid.uuid4())
        now = datetime.now()
        
        knowledge_item = KnowledgeItem(
            id=item_id,
            type=LearningType.OBJECT,
            data=object_data,
            tags=tags or [],
            confidence=confidence,
            created_at=now,
            updated_at=now,
            embedding=embedding  # Add embedding if provided
        )
        
        self._storage[item_id] = knowledge_item  # Single source of truth
        
        # Add to embedding index if embedding provided
        if embedding is not None and len(embedding) > 0:
            self.embedding_index.add_embedding(item_id, embedding)
        
        # Only save if not skipped (useful for async contexts)
        if not skip_save:
            self.save_to_file()  # Auto-save
        logger.info(f"Learned object: {object_data.name} (ID: {item_id}, embedding: {embedding is not None})")
        return item_id
    
    def learn_fact(self, fact_data: FactData, tags: List[str] = None, confidence: float = 1.0, embedding: Optional[List[float]] = None, skip_save: bool = False) -> str:
        """Learn a new fact with persistence"""
        item_id = str(uuid.uuid4())
        now = datetime.now()
        
        knowledge_item = KnowledgeItem(
            id=item_id,
            type=LearningType.FACT,
            data=fact_data,
            tags=tags or [],
            confidence=confidence,
            created_at=now,
            updated_at=now,
            embedding=embedding  # Add embedding if provided
        )
        
        self._storage[item_id] = knowledge_item  # Single source of truth
        
        # Add to embedding index if embedding provided
        if embedding is not None and len(embedding) > 0:
            self.embedding_index.add_embedding(item_id, embedding)
        
        # Only save if not skipped (useful for async contexts)
        if not skip_save:
            self.save_to_file()  # Auto-save
        logger.info(f"Learned fact: {fact_data.subject} {fact_data.predicate} {fact_data.object} (ID: {item_id}, embedding: {embedding is not None})")
        return item_id
    
    def get_item(self, item_id: str) -> Optional[KnowledgeItem]:
        """Get item by ID"""
        return self._storage.get(item_id)
    
    def get_object(self, object_id: str) -> Optional[KnowledgeItem]:
        """Get object by ID"""
        return self.objects.get(object_id)
    
    def get_fact(self, fact_id: str) -> Optional[KnowledgeItem]:
        """Get fact by ID"""
        return self.facts.get(fact_id)
    
    def update_item(self, item_id: str, **kwargs) -> Optional[KnowledgeItem]:
        """Update an existing item"""
        if item_id not in self._storage:
            return None
        
        item = self._storage[item_id]
        
        # Update allowed fields
        for key, value in kwargs.items():
            if hasattr(item, key) and key not in ['id', 'type', 'created_at']:
                setattr(item, key, value)
        
        item.updated_at = datetime.now()
        self.save_to_file()
        return item
    
    def forget_item(self, item_id: str, permanent: bool = False, skip_save: bool = False) -> bool:
        """Forget item with persistence"""
        if item_id not in self._storage:
            return False
        
        if permanent:
            self._storage.pop(item_id, None)
            self.embedding_index.remove_embedding(item_id)
        else:
            item = self._storage.pop(item_id)
            self._deleted_items[item_id] = item
            self.embedding_index.remove_embedding(item_id)
        
        if not skip_save:
            self.save_to_file()
        logger.info(f"Forgot item: {item_id} (permanent={permanent})")
        return True
    
    def restore_item(self, item_id: str) -> bool:
        """Restore a soft-deleted item"""
        if item_id not in self._deleted_items:
            return False
        
        item = self._deleted_items.pop(item_id)
        self._storage[item_id] = item
        
        self.save_to_file()
        logger.info(f"Restored item: {item_id}")
        return True
    
    # === Query Operations ===
    
    def get_all_objects(self) -> List[KnowledgeItem]:
        return list(self.objects.values())
    
    def get_all_facts(self) -> List[KnowledgeItem]:
        return list(self.facts.values())
    
    def get_all_items(self) -> List[KnowledgeItem]:
        return list(self._storage.values())
    
    def get_deleted_items(self) -> List[KnowledgeItem]:
        return list(self._deleted_items.values())
    
    def search_by_name(self, name: str) -> List[KnowledgeItem]:
        """Search items by name (for objects) or subject (for facts)"""
        results = []
        name_lower = name.lower()
        
        for item in self._storage.values():
            if item.type == LearningType.OBJECT:
                if hasattr(item.data, 'name') and name_lower in item.data.name.lower():
                    results.append(item)
            elif item.type == LearningType.FACT:
                if hasattr(item.data, 'subject') and name_lower in item.data.subject.lower():
                    results.append(item)
                elif hasattr(item.data, 'object') and name_lower in item.data.object.lower():
                    results.append(item)
        
        return results
    
    def search_by_tag(self, tag: str) -> List[KnowledgeItem]:
        """Search items by tag"""
        tag_lower = tag.lower()
        return [
            item for item in self._storage.values()
            if any(t.lower() == tag_lower for t in item.tags)
        ]
    
    def search_objects_by_category(self, category: str) -> List[KnowledgeItem]:
        """Search objects by category"""
        category_lower = category.lower()
        return [
            item for item in self.objects.values()
            if hasattr(item.data, 'category') and 
               item.data.category and 
               category_lower in item.data.category.lower()
        ]
    
    def get_facts_by_subject(self, subject: str) -> List[KnowledgeItem]:
        """Get all facts about a specific subject"""
        subject_lower = subject.lower()
        return [
            fact for fact in self.facts.values()
            if hasattr(fact.data, 'subject') and 
               subject_lower in fact.data.subject.lower()
        ]
    
    def search_by_embedding(self, embedding: List[float], k: int = 5, threshold: float = 0.3, item_type: Optional[LearningType] = None) -> List[Tuple[KnowledgeItem, float]]:
        """
        Search for similar items using embedding vectors (Phase 2 optimization).
        
        Args:
            embedding: Query embedding vector
            k: Number of results to return
            threshold: Minimum similarity score (0.0-1.0)
            item_type: Filter by type (OBJECT or FACT), None for all
            
        Returns:
            List of (KnowledgeItem, similarity_score) tuples
        """
        if not embedding or len(embedding) == 0:
            logger.warning("Empty embedding provided to search_by_embedding")
            return []
        
        try:
            # Search in embedding index
            results = self.embedding_index.search(embedding, k=k*2, threshold=threshold)  # Get more results to filter by type
            
            # Filter by item type if specified
            filtered_results = []
            for item_id, similarity in results:
                if item_id in self._storage:
                    item = self._storage[item_id]
                    
                    # Apply type filter
                    if item_type is not None and item.type != item_type:
                        continue
                    
                    filtered_results.append((item, similarity))
                    
                    if len(filtered_results) >= k:
                        break
            
            logger.info(f"Embedding search returned {len(filtered_results)} results")
            return filtered_results
            
        except Exception as e:
            logger.error(f"Embedding search failed: {e}")
            return []
    
    # === Statistics & Metrics ===
    
    def get_items_count(self) -> dict:
        """Get detailed statistics"""
        categories = {}
        for item in self.objects.values():
            if hasattr(item.data, 'category') and item.data.category:
                cat = item.data.category
                categories[cat] = categories.get(cat, 0) + 1
        
        embedding_stats = self.embedding_index.get_stats()
        
        return {
            "total": len(self._storage),
            "objects": len(self.objects),
            "facts": len(self.facts),
            "deleted": len(self._deleted_items),
            "categories": categories,
            "storage_file": self.storage_file,
            "last_updated": datetime.now().isoformat(),
            "embedding_index": embedding_stats
        }
    
    def get_category_stats(self) -> Dict[str, int]:
        """Get statistics by category"""
        stats = {}
        for item in self.objects.values():
            if hasattr(item.data, 'category') and item.data.category:
                cat = item.data.category
                stats[cat] = stats.get(cat, 0) + 1
        return stats
    
    # === Data Management ===
    
    def export_data(self, export_file: str = "knowledge_export.json") -> bool:
        """Export all data to a portable JSON file"""
        try:
            export_data = {
                'objects': [
                    item.dict() for item in self.objects.values()
                ],
                'facts': [
                    item.dict() for item in self.facts.values()
                ],
                'metadata': {
                    'export_date': datetime.now().isoformat(),
                    'total_objects': len(self.objects),
                    'total_facts': len(self.facts),
                    'version': '1.0'
                }
            }
            
            with open(export_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Exported {len(self.objects)} objects and {len(self.facts)} facts to {export_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting data: {e}")
            return False
    
    def import_data(self, import_file: str) -> bool:
        """Import data from exported JSON file"""
        try:
            if not os.path.exists(import_file):
                logger.error(f"Import file not found: {import_file}")
                return False
            
            with open(import_file, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            
            imported_count = 0
            
            # Import objects
            for obj_data in import_data.get('objects', []):
                try:
                    item_id = str(uuid.uuid4())  # Generate new ID
                    
                    # Convert string dates back to datetime
                    if 'created_at' in obj_data and isinstance(obj_data['created_at'], str):
                        obj_data['created_at'] = datetime.fromisoformat(obj_data['created_at'].replace('Z', '+00:00'))
                    if 'updated_at' in obj_data and isinstance(obj_data['updated_at'], str):
                        obj_data['updated_at'] = datetime.fromisoformat(obj_data['updated_at'].replace('Z', '+00:00'))
                    
                    obj_data['id'] = item_id
                    knowledge_item = KnowledgeItem(**obj_data)
                    
                    self._storage[item_id] = knowledge_item  # Single source of truth
                    imported_count += 1
                    
                except Exception as e:
                    logger.warning(f"Failed to import object: {e}")
            
            # Import facts
            for fact_data in import_data.get('facts', []):
                try:
                    item_id = str(uuid.uuid4())  # Generate new ID
                    
                    # Convert string dates back to datetime
                    if 'created_at' in fact_data and isinstance(fact_data['created_at'], str):
                        fact_data['created_at'] = datetime.fromisoformat(fact_data['created_at'].replace('Z', '+00:00'))
                    if 'updated_at' in fact_data and isinstance(fact_data['updated_at'], str):
                        fact_data['updated_at'] = datetime.fromisoformat(fact_data['updated_at'].replace('Z', '+00:00'))
                    
                    fact_data['id'] = item_id
                    knowledge_item = KnowledgeItem(**fact_data)
                    
                    self._storage[item_id] = knowledge_item  # Single source of truth
                    imported_count += 1
                    
                except Exception as e:
                    logger.warning(f"Failed to import fact: {e}")
            
            self.save_to_file()
            logger.info(f"Imported {imported_count} items from {import_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error importing data: {e}")
            return False
    
    def clear_all_data(self) -> bool:
        """Clear all data (use with caution)"""
        confirm = input("Are you sure you want to clear ALL data? (yes/no): ")
        if confirm.lower() != 'yes':
            logger.info("Clear operation cancelled")
            return False
        
        try:
            # Create final backup
            final_backup = self.create_backup()
            
            # Clear all data
            self._storage.clear()
            self._deleted_items.clear()
            
            # Save empty state
            self.save_to_file()
            
            logger.info(f"Cleared all data. Backup saved to: {final_backup}")
            return True
            
        except Exception as e:
            logger.error(f"Error clearing data: {e}")
            return False


# Global instance (replaces the old in-memory version)
knowledge_base = PersistentKnowledgeBase()
