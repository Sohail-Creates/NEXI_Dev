"""
FEATURE #3: Vision Service Request Queue

Manages SQLite-based persistent queue for face detection requests.
Queues requests when Vision Service is unavailable, with retry tracking.

Author: Integration Team
"""

import sqlite3
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path
import threading
from contextlib import contextmanager


logger = logging.getLogger(__name__)


class VisionQueueService:
    """
    Manages offline vision request queue using SQLite for persistent storage.
    
    Features:
    - Thread-safe database operations
    - Automatic retry tracking
    - Request prioritization
    - Configurable retention policy
    """
    
    def __init__(
        self,
        db_path: str = "02_vision_service/vision_service/data/queue.db",
        max_retry_count: int = 3,
        max_queue_size: int = 1000
    ):
        """
        Initialize vision queue service.
        
        Args:
            db_path: Path to SQLite database file
            max_retry_count: Maximum retry attempts per request
            max_queue_size: Maximum number of requests to store
        """
        self.db_path = Path(db_path)
        self.max_retry_count = max_retry_count
        self.max_queue_size = max_queue_size
        self._lock = threading.Lock()
        self._connection_pool = {}
        
        # Ensure data directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database schema
        self._initialize_database()
        
        logger.info(
            f"Vision queue service initialized with db_path={db_path}, "
            f"max_retry={max_retry_count}, max_size={max_queue_size}"
        )
    
    @contextmanager
    def _get_connection(self):
        """
        Thread-safe database connection context manager.
        
        Yields:
            sqlite3.Connection: Database connection
        """
        thread_id = threading.get_ident()
        
        with self._lock:
            if thread_id not in self._connection_pool:
                try:
                    conn = sqlite3.connect(
                        str(self.db_path),
                        check_same_thread=False,
                        timeout=30.0
                    )
                    conn.row_factory = sqlite3.Row
                    self._connection_pool[thread_id] = conn
                except sqlite3.Error as e:
                    logger.error(f"Failed to create database connection: {e}")
                    raise Exception(f"Database connection failed: {e}")
        
        try:
            yield self._connection_pool[thread_id]
        except sqlite3.Error as e:
            logger.error(f"Database operation failed: {e}")
            raise Exception(f"Database operation failed: {e}")
    
    def _initialize_database(self):
        """Create database schema if not exists."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Create vision_queue table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS vision_queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        request_type TEXT NOT NULL,
                        request_data TEXT NOT NULL,
                        image_file_path TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        retry_count INTEGER DEFAULT 0,
                        last_retry_at TIMESTAMP,
                        status TEXT DEFAULT 'pending',
                        error_message TEXT,
                        priority INTEGER DEFAULT 5
                    )
                """)
                
                # Create indexes for efficient querying
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_vision_status_priority 
                    ON vision_queue(status, priority DESC, created_at ASC)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_vision_created_at 
                    ON vision_queue(created_at)
                """)
                
                conn.commit()
                logger.info("Vision queue database schema initialized successfully")
                
        except Exception as e:
            logger.error(f"Failed to initialize vision queue database: {e}")
            raise
    
    def enqueue_request(
        self,
        request_type: str,
        request_data: Dict[str, Any],
        image_file_path: Optional[str] = None,
        priority: int = 5
    ) -> int:
        """
        Add face detection request to queue.
        
        Args:
            request_type: Type of request (e.g., 'face_detection', 'embedding_extraction')
            request_data: Request payload as dictionary
            image_file_path: Optional path to image file
            priority: Request priority (1=highest, 10=lowest)
        
        Returns:
            int: Queue entry ID
        
        Raises:
            Exception: If queue is full or operation fails
        """
        try:
            # Check queue size limit
            queue_size = self.get_queue_size()
            if queue_size >= self.max_queue_size:
                logger.warning(f"Vision queue full ({queue_size}/{self.max_queue_size})")
                # Remove oldest processed requests to make space
                self._cleanup_old_requests(limit=100)
                
                # Check again
                queue_size = self.get_queue_size()
                if queue_size >= self.max_queue_size:
                    raise Exception(
                        f"Vision queue is full ({queue_size}/{self.max_queue_size}). "
                        "Cannot add new requests."
                    )
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO vision_queue 
                    (request_type, request_data, image_file_path, priority)
                    VALUES (?, ?, ?, ?)
                """, (
                    request_type,
                    json.dumps(request_data),
                    image_file_path,
                    priority
                ))
                
                conn.commit()
                request_id = cursor.lastrowid
                
                logger.info(
                    f"Vision request enqueued: id={request_id}, type={request_type}, "
                    f"priority={priority}"
                )
                
                return request_id
                
        except Exception as e:
            logger.error(f"Failed to enqueue vision request: {e}")
            raise
    
    def dequeue_request(self) -> Optional[Dict[str, Any]]:
        """
        Get next pending request from queue.
        
        Returns:
            Optional[Dict]: Request data or None if queue empty
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id, request_type, request_data, image_file_path,
                           created_at, retry_count, priority
                    FROM vision_queue
                    WHERE status = 'pending' AND retry_count < ?
                    ORDER BY priority ASC, created_at ASC
                    LIMIT 1
                """, (self.max_retry_count,))
                
                row = cursor.fetchone()
                
                if row is None:
                    return None
                
                request = {
                    'id': row['id'],
                    'request_type': row['request_type'],
                    'request_data': json.loads(row['request_data']),
                    'image_file_path': row['image_file_path'],
                    'created_at': row['created_at'],
                    'retry_count': row['retry_count'],
                    'priority': row['priority']
                }
                
                return request
                
        except Exception as e:
            logger.error(f"Failed to dequeue vision request: {e}")
            raise
    
    def mark_request_processing(self, request_id: int):
        """Mark request as currently being processed."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    UPDATE vision_queue
                    SET status = 'processing',
                        last_retry_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (request_id,))
                
                conn.commit()
                
                logger.debug(f"Vision request {request_id} marked as processing")
                
        except Exception as e:
            logger.error(f"Failed to mark vision request processing: {e}")
            raise
    
    def mark_request_success(self, request_id: int):
        """Mark request as successfully processed."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    UPDATE vision_queue
                    SET status = 'completed'
                    WHERE id = ?
                """, (request_id,))
                
                conn.commit()
                
                logger.info(f"Vision request {request_id} completed successfully")
                
        except Exception as e:
            logger.error(f"Failed to mark vision request success: {e}")
            raise
    
    def mark_request_failed(self, request_id: int, error_message: str):
        """
        Mark request as failed and increment retry count.
        
        Args:
            request_id: Request ID
            error_message: Error description
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Increment retry count
                cursor.execute("""
                    UPDATE vision_queue
                    SET retry_count = retry_count + 1,
                        last_retry_at = CURRENT_TIMESTAMP,
                        error_message = ?,
                        status = CASE 
                            WHEN retry_count + 1 >= ? THEN 'failed'
                            ELSE 'pending'
                        END
                    WHERE id = ?
                """, (error_message, self.max_retry_count, request_id))
                
                conn.commit()
                
                # Get updated retry count
                cursor.execute(
                    "SELECT retry_count FROM vision_queue WHERE id = ?",
                    (request_id,)
                )
                row = cursor.fetchone()
                retry_count = row['retry_count'] if row else 0
                
                if retry_count >= self.max_retry_count:
                    logger.warning(
                        f"Vision request {request_id} failed permanently after "
                        f"{retry_count} retries: {error_message}"
                    )
                else:
                    logger.info(
                        f"Vision request {request_id} failed (retry {retry_count}/"
                        f"{self.max_retry_count}): {error_message}"
                    )
                
        except Exception as e:
            logger.error(f"Failed to mark vision request failed: {e}")
            raise
    
    def get_queue_size(self, status: Optional[str] = None) -> int:
        """
        Get number of requests in queue.
        
        Args:
            status: Optional status filter ('pending', 'processing', 'completed', 'failed')
        
        Returns:
            int: Number of requests
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                if status:
                    cursor.execute(
                        "SELECT COUNT(*) as count FROM vision_queue WHERE status = ?",
                        (status,)
                    )
                else:
                    cursor.execute("SELECT COUNT(*) as count FROM vision_queue")
                
                row = cursor.fetchone()
                return row['count'] if row else 0
                
        except Exception as e:
            logger.error(f"Failed to get vision queue size: {e}")
            return 0
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """Get vision queue statistics."""
        try:
            stats = {
                'total': self.get_queue_size(),
                'pending': self.get_queue_size('pending'),
                'processing': self.get_queue_size('processing'),
                'completed': self.get_queue_size('completed'),
                'failed': self.get_queue_size('failed')
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get vision queue stats: {e}")
            return {
                'total': 0,
                'pending': 0,
                'processing': 0,
                'completed': 0,
                'failed': 0
            }
    
    def _cleanup_old_requests(self, limit: int = 100):
        """
        Remove old completed/failed requests.
        
        Args:
            limit: Maximum number of requests to remove
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    DELETE FROM vision_queue
                    WHERE id IN (
                        SELECT id FROM vision_queue
                        WHERE status IN ('completed', 'failed')
                        ORDER BY created_at ASC
                        LIMIT ?
                    )
                """, (limit,))
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} old vision requests")
                
        except Exception as e:
            logger.error(f"Failed to cleanup old vision requests: {e}")
    
    def clear_queue(self, status: Optional[str] = None):
        """
        Clear vision queue requests.
        
        Args:
            status: Optional status filter, clears all if None
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                if status:
                    cursor.execute(
                        "DELETE FROM vision_queue WHERE status = ?",
                        (status,)
                    )
                else:
                    cursor.execute("DELETE FROM vision_queue")
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                logger.info(f"Cleared {deleted_count} requests from vision queue")
                
        except Exception as e:
            logger.error(f"Failed to clear vision queue: {e}")
            raise
    
    def close(self):
        """Close all database connections."""
        with self._lock:
            for conn in self._connection_pool.values():
                try:
                    conn.close()
                except Exception as e:
                    logger.error(f"Error closing connection: {e}")
            
            self._connection_pool.clear()
            logger.info("Vision queue service closed")
