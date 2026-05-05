"""
Queue Service for Offline Command Management.

This service provides SQLite-based persistent storage for commands when the backend
is unreachable. Commands are queued with retry tracking and automatic cleanup.

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

from ..utils.errors import (
    DatabaseError,
    QueueError,
    ConfigurationError
)


logger = logging.getLogger(__name__)


class QueueService:
    """
    Manages offline command queue using SQLite for persistent storage.
    
    Features:
    - Thread-safe database operations
    - Automatic retry tracking
    - Command prioritization
    - Configurable retention policy
    - Connection pooling
    """
    
    def __init__(
        self,
        db_path: str = "data/command_queue.db",
        max_retry_count: int = 3,
        max_queue_size: int = 1000
    ):
        """
        Initialize queue service.
        
        Args:
            db_path: Path to SQLite database file
            max_retry_count: Maximum retry attempts per command
            max_queue_size: Maximum number of commands to store
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
            f"Queue service initialized with db_path={db_path}, "
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
                    raise DatabaseError(f"Database connection failed: {e}")
        
        try:
            yield self._connection_pool[thread_id]
        except sqlite3.Error as e:
            logger.error(f"Database operation failed: {e}")
            raise DatabaseError(f"Database operation failed: {e}")
    
    def _initialize_database(self):
        """Create database schema if not exists."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Create commands table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS command_queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        command_type TEXT NOT NULL,
                        command_data TEXT NOT NULL,
                        audio_file_path TEXT,
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
                    CREATE INDEX IF NOT EXISTS idx_status_priority 
                    ON command_queue(status, priority DESC, created_at ASC)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_created_at 
                    ON command_queue(created_at)
                """)
                
                conn.commit()
                logger.info("Database schema initialized successfully")
                
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise ConfigurationError(f"Database initialization failed: {e}")
    
    def enqueue_command(
        self,
        command_type: str,
        command_data: Dict[str, Any],
        audio_file_path: Optional[str] = None,
        priority: int = 5
    ) -> int:
        """
        Add command to queue.
        
        Args:
            command_type: Type of command (e.g., 'transcribe', 'verify_speaker')
            command_data: Command payload as dictionary
            audio_file_path: Optional path to audio file
            priority: Command priority (1=highest, 10=lowest)
        
        Returns:
            int: Queue entry ID
        
        Raises:
            QueueError: If queue is full or operation fails
        """
        try:
            # Check queue size limit
            queue_size = self.get_queue_size()
            if queue_size >= self.max_queue_size:
                logger.warning(f"Queue full ({queue_size}/{self.max_queue_size})")
                # Remove oldest processed commands to make space
                self._cleanup_old_commands(limit=100)
                
                # Check again
                queue_size = self.get_queue_size()
                if queue_size >= self.max_queue_size:
                    raise QueueError(
                        f"Queue is full ({queue_size}/{self.max_queue_size}). "
                        "Cannot add new commands."
                    )
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO command_queue 
                    (command_type, command_data, audio_file_path, priority)
                    VALUES (?, ?, ?, ?)
                """, (
                    command_type,
                    json.dumps(command_data),
                    audio_file_path,
                    priority
                ))
                
                conn.commit()
                command_id = cursor.lastrowid
                
                logger.info(
                    f"Command enqueued: id={command_id}, type={command_type}, "
                    f"priority={priority}"
                )
                
                return command_id
                
        except QueueError:
            raise
        except Exception as e:
            logger.error(f"Failed to enqueue command: {e}")
            raise QueueError(f"Failed to enqueue command: {e}")
    
    def dequeue_command(self) -> Optional[Dict[str, Any]]:
        """
        Get next pending command from queue.
        
        Returns:
            Optional[Dict]: Command data or None if queue empty
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id, command_type, command_data, audio_file_path,
                           created_at, retry_count, priority
                    FROM command_queue
                    WHERE status = 'pending' AND retry_count < ?
                    ORDER BY priority ASC, created_at ASC
                    LIMIT 1
                """, (self.max_retry_count,))
                
                row = cursor.fetchone()
                
                if row is None:
                    return None
                
                command = {
                    'id': row['id'],
                    'command_type': row['command_type'],
                    'command_data': json.loads(row['command_data']),
                    'audio_file_path': row['audio_file_path'],
                    'created_at': row['created_at'],
                    'retry_count': row['retry_count'],
                    'priority': row['priority']
                }
                
                return command
                
        except Exception as e:
            logger.error(f"Failed to dequeue command: {e}")
            raise QueueError(f"Failed to dequeue command: {e}")
    
    def mark_command_processing(self, command_id: int):
        """Mark command as currently being processed."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    UPDATE command_queue
                    SET status = 'processing',
                        last_retry_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (command_id,))
                
                conn.commit()
                
                logger.debug(f"Command {command_id} marked as processing")
                
        except Exception as e:
            logger.error(f"Failed to mark command processing: {e}")
            raise QueueError(f"Failed to mark command processing: {e}")
    
    def mark_command_success(self, command_id: int):
        """Mark command as successfully processed."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    UPDATE command_queue
                    SET status = 'completed'
                    WHERE id = ?
                """, (command_id,))
                
                conn.commit()
                
                logger.info(f"Command {command_id} completed successfully")
                
        except Exception as e:
            logger.error(f"Failed to mark command success: {e}")
            raise QueueError(f"Failed to mark command success: {e}")
    
    def mark_command_failed(self, command_id: int, error_message: str):
        """
        Mark command as failed and increment retry count.
        
        Args:
            command_id: Command ID
            error_message: Error description
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Increment retry count
                cursor.execute("""
                    UPDATE command_queue
                    SET retry_count = retry_count + 1,
                        last_retry_at = CURRENT_TIMESTAMP,
                        error_message = ?,
                        status = CASE 
                            WHEN retry_count + 1 >= ? THEN 'failed'
                            ELSE 'pending'
                        END
                    WHERE id = ?
                """, (error_message, self.max_retry_count, command_id))
                
                conn.commit()
                
                # Get updated retry count
                cursor.execute(
                    "SELECT retry_count FROM command_queue WHERE id = ?",
                    (command_id,)
                )
                row = cursor.fetchone()
                retry_count = row['retry_count'] if row else 0
                
                if retry_count >= self.max_retry_count:
                    logger.warning(
                        f"Command {command_id} failed permanently after "
                        f"{retry_count} retries: {error_message}"
                    )
                else:
                    logger.info(
                        f"Command {command_id} failed (retry {retry_count}/"
                        f"{self.max_retry_count}): {error_message}"
                    )
                
        except Exception as e:
            logger.error(f"Failed to mark command failed: {e}")
            raise QueueError(f"Failed to mark command failed: {e}")
    
    def get_queue_size(self, status: Optional[str] = None) -> int:
        """
        Get number of commands in queue.
        
        Args:
            status: Optional status filter ('pending', 'processing', 'completed', 'failed')
        
        Returns:
            int: Number of commands
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                if status:
                    cursor.execute(
                        "SELECT COUNT(*) as count FROM command_queue WHERE status = ?",
                        (status,)
                    )
                else:
                    cursor.execute("SELECT COUNT(*) as count FROM command_queue")
                
                row = cursor.fetchone()
                return row['count'] if row else 0
                
        except Exception as e:
            logger.error(f"Failed to get queue size: {e}")
            return 0
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
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
            logger.error(f"Failed to get queue stats: {e}")
            return {
                'total': 0,
                'pending': 0,
                'processing': 0,
                'completed': 0,
                'failed': 0
            }
    
    def _cleanup_old_commands(self, limit: int = 100):
        """
        Remove old completed/failed commands.
        
        Args:
            limit: Maximum number of commands to remove
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    DELETE FROM command_queue
                    WHERE id IN (
                        SELECT id FROM command_queue
                        WHERE status IN ('completed', 'failed')
                        ORDER BY created_at ASC
                        LIMIT ?
                    )
                """, (limit,))
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} old commands")
                
        except Exception as e:
            logger.error(f"Failed to cleanup old commands: {e}")
    
    def clear_queue(self, status: Optional[str] = None):
        """
        Clear queue commands.
        
        Args:
            status: Optional status filter, clears all if None
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                if status:
                    cursor.execute(
                        "DELETE FROM command_queue WHERE status = ?",
                        (status,)
                    )
                else:
                    cursor.execute("DELETE FROM command_queue")
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                logger.info(f"Cleared {deleted_count} commands from queue")
                
        except Exception as e:
            logger.error(f"Failed to clear queue: {e}")
            raise QueueError(f"Failed to clear queue: {e}")
    
    def close(self):
        """Close all database connections."""
        with self._lock:
            for conn in self._connection_pool.values():
                try:
                    conn.close()
                except Exception as e:
                    logger.error(f"Error closing connection: {e}")
            
            self._connection_pool.clear()
            logger.info("Queue service closed")
