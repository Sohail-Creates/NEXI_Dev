"""
Dead Letter Queue - Capture permanently failed requests for analysis.

FEATURE #10: DEAD LETTER QUEUE

Handles requests that permanently fail:
1. Normal queue retries exhausted
2. System errors (not temporary)
3. Invalid requests

Benefits:
- Understand failure patterns
- Replay requests later
- Debugging support
- Alert on critical failures

Architecture:
- Separate SQLite table: dead_letter_queue
- Records: request_data, error, timestamp
- Status: pending_analysis, analyzed, resolved
"""

import sqlite3
import json
import datetime
from typing import Dict, Any, Optional, List
from enum import Enum
import logging
import os


logger = logging.getLogger("DLQ")


class DLQStatus(Enum):
    """Status of DLQ entry."""
    PENDING_ANALYSIS = "pending_analysis"
    ANALYZED = "analyzed"
    RESOLVED = "resolved"
    REPLAY_SCHEDULED = "replay_scheduled"


class DeadLetterQueue:
    """
    Manages permanently failed requests in a persistent queue.
    """
    
    def __init__(self, db_path: str = "data/dlq.db"):
        """
        Initialize Dead Letter Queue.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        # Initialize database
        self._init_db()
        
        logger.info(f"DeadLetterQueue initialized at {db_path}")
    
    def _init_db(self):
        """Initialize DLQ database table."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dead_letter_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dlq_id TEXT UNIQUE NOT NULL,
                request_type TEXT NOT NULL,
                user_id TEXT,
                request_data TEXT NOT NULL,
                error_message TEXT,
                error_type TEXT,
                status TEXT DEFAULT 'pending_analysis',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                retry_count INTEGER DEFAULT 0,
                last_retry_at TIMESTAMP,
                analysis_notes TEXT,
                resolution TEXT
            )
        ''')
        
        # Index for status queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_dlq_status 
            ON dead_letter_queue(status)
        ''')
        
        # Index for user queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_dlq_user 
            ON dead_letter_queue(user_id)
        ''')
        
        conn.commit()
        conn.close()
    
    def add_failed_request(
        self,
        dlq_id: str,
        request_type: str,
        error_message: str,
        error_type: str,
        request_data: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> bool:
        """
        Add permanently failed request to DLQ.
        
        Args:
            dlq_id: Unique identifier for this DLQ entry
            request_type: Type of request (register_user, verify_user, etc)
            error_message: Error message/description
            error_type: Error category (e.g., SERVICE_ERROR, INVALID_INPUT)
            request_data: Original request data
            user_id: Optional user identifier
        
        Returns:
            True if added successfully
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO dead_letter_queue 
                (dlq_id, request_type, user_id, request_data, error_message, 
                 error_type, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                dlq_id,
                request_type,
                user_id,
                json.dumps(request_data),
                error_message,
                error_type,
                DLQStatus.PENDING_ANALYSIS.value,
                datetime.datetime.now(),
                datetime.datetime.now()
            ))
            
            conn.commit()
            conn.close()
            
            logger.warning(
                f"Added to DLQ: {dlq_id} ({request_type}) - {error_type}"
            )
            return True
        
        except sqlite3.IntegrityError:
            logger.warning(f"DLQ entry already exists: {dlq_id}")
            return False
        except Exception as e:
            logger.error(f"Failed to add to DLQ: {e}")
            return False
    
    def get_pending_entries(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get pending analysis entries from DLQ.
        
        Args:
            limit: Maximum entries to return
        
        Returns:
            List of DLQ entries
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM dead_letter_queue
                WHERE status = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (DLQStatus.PENDING_ANALYSIS.value, limit))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
        
        except Exception as e:
            logger.error(f"Failed to get pending DLQ entries: {e}")
            return []
    
    def mark_as_analyzed(self, dlq_id: str, notes: str = "") -> bool:
        """
        Mark DLQ entry as analyzed.
        
        Args:
            dlq_id: DLQ entry ID
            notes: Analysis notes
        
        Returns:
            True if updated
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE dead_letter_queue
                SET status = ?, analysis_notes = ?, updated_at = ?
                WHERE dlq_id = ?
            ''', (
                DLQStatus.ANALYZED.value,
                notes,
                datetime.datetime.now(),
                dlq_id
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Marked DLQ entry as analyzed: {dlq_id}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to mark DLQ entry as analyzed: {e}")
            return False
    
    def mark_as_resolved(
        self,
        dlq_id: str,
        resolution: str = "manual_fix"
    ) -> bool:
        """
        Mark DLQ entry as resolved.
        
        Args:
            dlq_id: DLQ entry ID
            resolution: How it was resolved
        
        Returns:
            True if updated
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE dead_letter_queue
                SET status = ?, resolution = ?, updated_at = ?
                WHERE dlq_id = ?
            ''', (
                DLQStatus.RESOLVED.value,
                resolution,
                datetime.datetime.now(),
                dlq_id
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Marked DLQ entry as resolved: {dlq_id}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to mark DLQ entry as resolved: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get DLQ statistics.
        
        Returns:
            Dictionary with counts by status, error types, etc
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Total entries by status
            cursor.execute('''
                SELECT status, COUNT(*) as count
                FROM dead_letter_queue
                GROUP BY status
            ''')
            status_counts = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Top error types
            cursor.execute('''
                SELECT error_type, COUNT(*) as count
                FROM dead_letter_queue
                GROUP BY error_type
                ORDER BY count DESC
                LIMIT 10
            ''')
            error_types = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Top users with failures
            cursor.execute('''
                SELECT user_id, COUNT(*) as count
                FROM dead_letter_queue
                WHERE user_id IS NOT NULL
                GROUP BY user_id
                ORDER BY count DESC
                LIMIT 10
            ''')
            top_users = {row[0]: row[1] for row in cursor.fetchall()}
            
            conn.close()
            
            return {
                'total_entries': sum(status_counts.values()),
                'by_status': status_counts,
                'top_error_types': error_types,
                'top_users_with_failures': top_users
            }
        
        except Exception as e:
            logger.error(f"Failed to get DLQ stats: {e}")
            return {'error': str(e)}
    
    def cleanup_old_entries(self, days: int = 30) -> int:
        """
        Remove resolved entries older than specified days.
        
        Args:
            days: Age threshold in days
        
        Returns:
            Number of entries deleted
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
            
            cursor.execute('''
                DELETE FROM dead_letter_queue
                WHERE status = ? AND updated_at < ?
            ''', (DLQStatus.RESOLVED.value, cutoff_date))
            
            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()
            
            logger.info(f"Cleaned up {deleted_count} old DLQ entries")
            return deleted_count
        
        except Exception as e:
            logger.error(f"Failed to cleanup DLQ entries: {e}")
            return 0


# Global DLQ instance
_dlq: Optional[DeadLetterQueue] = None


def get_dlq(db_path: str = "data/dlq.db") -> DeadLetterQueue:
    """Get global DLQ instance (lazy singleton)."""
    global _dlq
    if _dlq is None:
        _dlq = DeadLetterQueue(db_path)
    return _dlq


# Version info
__version__ = "1.0.0"
__dlq_feature__ = "FEATURE #10: Dead Letter Queue"
