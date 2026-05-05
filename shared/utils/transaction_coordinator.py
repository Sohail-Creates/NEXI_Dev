"""
Transaction Coordinator - Ensure consistency across service calls.

FEATURE #7: TRANSACTION COORDINATION

Problem:
- User starts registration → Audio Service succeeds → Vision Service fails
- Now user has partial enrollment (audio only)
- System is inconsistent

Solution:
- Idempotency: Same request ID produces same result
- State tracking: Track what was done, enable rollback
- Retry safety: Duplicate requests don't cause issues

Architecture:
- Transaction ID (unique per user registration)
- Track operations: audio_done, vision_done, storage_done
- Rollback if any step fails
- Database persistence for durability
"""

import sqlite3
import json
import uuid
import datetime
from enum import Enum
from typing import Dict, Any, Optional, List, Callable
import logging
import os


logger = logging.getLogger("TransactionCoordinator")


class TransactionStatus(Enum):
    """Status of a coordination transaction."""
    INITIATED = "initiated"
    PHASE1_PREPARE = "phase1_prepare"
    PHASE1_FAILED = "phase1_failed"
    PHASE2_COMMIT = "phase2_commit"
    PHASE2_COMMIT_FAILED = "phase2_commit_failed"
    PHASE2_ROLLBACK = "phase2_rollback"
    COMPLETED = "completed"
    FAILED_UNRECOVERABLE = "failed_unrecoverable"


class TransactionCoordinator:
    """
    Coordinates transactions across multiple services.
    
    Usage:
        coord = TransactionCoordinator()
        tx_id = coord.create_transaction("user_123", "registration")
        
        # Phase 1: Prepare
        coord.record_operation(tx_id, "audio_service", "prepared", {"status": "ready"})
        coord.record_operation(tx_id, "vision_service", "prepared", {"status": "ready"})
        
        # Phase 2: Execute
        try:
            coord.record_operation(tx_id, "audio_service", "committed", {...})
            coord.record_operation(tx_id, "vision_service", "committed", {...})
            coord.mark_completed(tx_id)
        except Exception:
            coord.initiate_rollback(tx_id)
            raise
    """
    
    def __init__(self, db_path: str = "data/transactions.db"):
        """
        Initialize Transaction Coordinator.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        self._init_db()
        logger.info(f"TransactionCoordinator initialized at {db_path}")
    
    def _init_db(self):
        """Initialize transaction database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Main transactions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                operation_type TEXT NOT NULL,
                status TEXT DEFAULT 'initiated',
                idempotency_key TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                error_details TEXT
            )
        ''')
        
        # Transaction operations table (tracks each service call)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transaction_operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id TEXT NOT NULL,
                service_name TEXT NOT NULL,
                operation_name TEXT NOT NULL,
                status TEXT NOT NULL,
                operation_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id)
            )
        ''')
        
        # Indexes
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_tx_user 
            ON transactions(user_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_tx_status 
            ON transactions(status)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_tx_ops_id 
            ON transaction_operations(transaction_id)
        ''')
        
        conn.commit()
        conn.close()
    
    def create_transaction(
        self,
        user_id: str,
        operation_type: str,
        idempotency_key: Optional[str] = None
    ) -> str:
        """
        Create new transaction.
        
        Args:
            user_id: User identifier
            operation_type: Type of operation (registration, verification, etc)
            idempotency_key: Optional idempotency key for duplicate detection
        
        Returns:
            Transaction ID
        """
        transaction_id = f"tx-{uuid.uuid4().hex[:16]}"
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO transactions
                (transaction_id, user_id, operation_type, status, idempotency_key)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                transaction_id,
                user_id,
                operation_type,
                TransactionStatus.INITIATED.value,
                idempotency_key
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Created transaction {transaction_id} for user {user_id}")
            return transaction_id
        
        except sqlite3.IntegrityError:
            logger.warning(f"Idempotency key already exists, transaction may be duplicate")
            # Lookup existing transaction with this key
            return self.get_transaction_by_idempotency_key(idempotency_key) or transaction_id
        except Exception as e:
            logger.error(f"Failed to create transaction: {e}")
            raise
    
    def record_operation(
        self,
        transaction_id: str,
        service_name: str,
        operation_name: str,
        operation_data: Dict[str, Any],
        status: str = "pending"
    ) -> bool:
        """
        Record an operation within a transaction.
        
        Args:
            transaction_id: Transaction ID
            service_name: Service that performed operation
            operation_name: Name of operation (prepare, commit, rollback)
            operation_data: Data from the operation
            status: Operation status
        
        Returns:
            True if recorded successfully
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO transaction_operations
                (transaction_id, service_name, operation_name, status, operation_data)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                transaction_id,
                service_name,
                operation_name,
                status,
                json.dumps(operation_data) if operation_data else None
            ))
            
            conn.commit()
            conn.close()
            
            logger.debug(
                f"Recorded operation: tx={transaction_id}, service={service_name}, "
                f"op={operation_name}"
            )
            return True
        
        except Exception as e:
            logger.error(f"Failed to record operation: {e}")
            return False
    
    def mark_completed(self, transaction_id: str) -> bool:
        """
        Mark transaction as completed successfully.
        
        Args:
            transaction_id: Transaction ID
        
        Returns:
            True if marked successfully
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE transactions
                SET status = ?, completed_at = ?
                WHERE transaction_id = ?
            ''', (
                TransactionStatus.COMPLETED.value,
                datetime.datetime.now(),
                transaction_id
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Transaction completed: {transaction_id}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to mark transaction completed: {e}")
            return False
    
    def mark_failed(
        self,
        transaction_id: str,
        error_details: str
    ) -> bool:
        """
        Mark transaction as failed.
        
        Args:
            transaction_id: Transaction ID
            error_details: Failure reason
        
        Returns:
            True if marked successfully
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE transactions
                SET status = ?, error_details = ?, completed_at = ?
                WHERE transaction_id = ?
            ''', (
                TransactionStatus.FAILED_UNRECOVERABLE.value,
                error_details,
                datetime.datetime.now(),
                transaction_id
            ))
            
            conn.commit()
            conn.close()
            
            logger.error(f"Transaction failed: {transaction_id} - {error_details}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to mark transaction failed: {e}")
            return False
    
    def initiate_rollback(self, transaction_id: str) -> bool:
        """
        Initiate rollback of transaction.
        
        Args:
            transaction_id: Transaction ID to rollback
        
        Returns:
            True if rollback initiated
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE transactions
                SET status = ?
                WHERE transaction_id = ?
            ''', (TransactionStatus.PHASE2_ROLLBACK.value, transaction_id))
            
            conn.commit()
            conn.close()
            
            logger.warning(f"Rollback initiated for transaction: {transaction_id}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to initiate rollback: {e}")
            return False
    
    def get_transaction(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """Get transaction details."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM transactions WHERE transaction_id = ?', (transaction_id,))
            row = cursor.fetchone()
            
            # Also get all operations for this transaction
            cursor.execute(
                'SELECT * FROM transaction_operations WHERE transaction_id = ?',
                (transaction_id,)
            )
            operations = [dict(op) for op in cursor.fetchall()]
            
            conn.close()
            
            if row:
                tx_dict = dict(row)
                tx_dict['operations'] = operations
                return tx_dict
            
            return None
        
        except Exception as e:
            logger.error(f"Failed to get transaction: {e}")
            return None
    
    def get_transaction_by_idempotency_key(
        self,
        idempotency_key: str
    ) -> Optional[str]:
        """
        Get transaction ID by idempotency key.
        Useful for detecting and handling duplicate requests.
        
        Args:
            idempotency_key: Idempotency key to lookup
        
        Returns:
            Transaction ID or None
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                'SELECT transaction_id FROM transactions WHERE idempotency_key = ?',
                (idempotency_key,)
            )
            row = cursor.fetchone()
            conn.close()
            
            return row[0] if row else None
        
        except Exception as e:
            logger.error(f"Failed to lookup transaction by key: {e}")
            return None
    
    def get_user_transactions(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get all transactions for a user."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM transactions
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (user_id, limit))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
        
        except Exception as e:
            logger.error(f"Failed to get user transactions: {e}")
            return []


# Global coordinator instance
_coordinator: Optional[TransactionCoordinator] = None


def get_transaction_coordinator(
    db_path: str = "data/transactions.db"
) -> TransactionCoordinator:
    """Get global transaction coordinator (lazy singleton)."""
    global _coordinator
    if _coordinator is None:
        _coordinator = TransactionCoordinator(db_path)
    return _coordinator


# Version info
__version__ = "1.0.0"
__transaction_feature__ = "FEATURE #7: Transaction Coordination"
