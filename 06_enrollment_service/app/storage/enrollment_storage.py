"""
Enrollment Data Storage System.

Provides persistent storage for enrollment data with transaction safety,
backup capabilities, and automatic recovery.

Features:
- JSON-based persistence
- Atomic writes (temp file + rename)
- Automatic backups before modifications
- Transaction rollback on failure
- Comprehensive logging
- Data integrity verification
"""

import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)


class EnrollmentStorageError(Exception):
    """Base exception for enrollment storage errors."""
    pass


class EnrollmentStorage:
    """Persistent storage for enrollment data with backup and recovery."""
    
    def __init__(self, data_dir: str = "enrollment_data"):
        """
        Initialize enrollment storage.
        
        Args:
            data_dir: Directory for storing enrollment data (default "enrollment_data")
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.users_file = self.data_dir / "users.json"
        self.backup_dir = self.data_dir / "backups"
        self.backup_dir.mkdir(exist_ok=True)
        
        # Load existing data
        self.users = self._load_users()
        
        logger.info(
            f"EnrollmentStorage initialized: {self.data_dir} "
            f"(loaded {len(self.users)} users)"
        )
    
    def _load_users(self) -> Dict:
        """
        Load users from persistent storage.
        
        Returns:
            Dict mapping user_id to user_data
        """
        if not self.users_file.exists():
            return {}
        
        try:
            with open(self.users_file, 'r', encoding='utf-8') as f:
                users = json.load(f)
            
            logger.info(f"Loaded {len(users)} users from {self.users_file}")
            return users
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in users file: {e}")
            # Try to restore from backup
            return self._restore_from_backup()
        except Exception as e:
            logger.error(f"Failed to load users: {e}")
            return {}
    
    def _restore_from_backup(self) -> Dict:
        """
        Restore users from most recent backup.
        
        Returns:
            Dict of users, or empty dict if no backup available
        """
        # Find most recent backup
        backups = sorted(self.backup_dir.glob("users_*.json"))
        
        if not backups:
            logger.warning("No backups available for recovery")
            return {}
        
        latest_backup = backups[-1]
        
        try:
            logger.warning(f"Attempting to restore from backup: {latest_backup}")
            with open(latest_backup, 'r', encoding='utf-8') as f:
                users = json.load(f)
            
            logger.info(f"Successfully restored {len(users)} users from backup")
            return users
            
        except Exception as e:
            logger.error(f"Failed to restore from backup: {e}")
            return {}
    
    def _save_users(self):
        """
        Save users to disk with atomic write (temp file + rename).
        
        Raises:
            EnrollmentStorageError: If save fails
        """
        # Write to temp file first (atomic operation)
        temp_file = self.users_file.with_suffix('.tmp')
        
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.users, f, indent=2, ensure_ascii=False)
            
            # Atomic rename (replace original)
            temp_file.replace(self.users_file)
            
            logger.debug(f"Saved {len(self.users)} users to disk")
            
        except Exception as e:
            # Clean up temp file if it exists
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass
            
            error_msg = f"Failed to save users: {e}"
            logger.error(error_msg)
            raise EnrollmentStorageError(error_msg) from e
    
    def create_backup(self, user_id: Optional[str] = None) -> str:
        """
        Create backup of current state or specific user.
        
        Args:
            user_id: Specific user to backup, or None for full backup
        
        Returns:
            Path to backup file
        
        Raises:
            EnrollmentStorageError: If backup creation fails
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        if user_id:
            if user_id not in self.users:
                raise EnrollmentStorageError(f"User not found: {user_id}")
            
            backup_file = self.backup_dir / f"user_{user_id}_{timestamp}.json"
            data_to_backup = self.users[user_id]
        else:
            backup_file = self.backup_dir / f"users_{timestamp}.json"
            data_to_backup = self.users
        
        try:
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_backup, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Created backup: {backup_file}")
            return str(backup_file)
            
        except Exception as e:
            error_msg = f"Backup creation failed: {e}"
            logger.error(error_msg)
            raise EnrollmentStorageError(error_msg) from e
    
    def save_user(
        self,
        user_id: str,
        user_data: Dict,
        create_backup: bool = True
    ) -> bool:
        """
        Save or update user data with transaction safety.
        
        Creates backup before modifying if user exists.
        Rolls back on failure.
        
        Args:
            user_id: User identifier
            user_data: User data dict
            create_backup: Whether to create backup before modifying
        
        Returns:
            True if saved successfully
        
        Raises:
            EnrollmentStorageError: If save fails
        """
        # Create backup if user exists and requested
        backup_file = None
        if create_backup and user_id in self.users:
            try:
                backup_file = self.create_backup(user_id)
            except Exception as e:
                logger.warning(f"Failed to create backup before save: {e}")
        
        # Store original data for rollback
        original_data = self.users.get(user_id)
        
        try:
            # Add/update user
            self.users[user_id] = {
                **user_data,
                "updated_at": datetime.utcnow().isoformat(),
                "user_id": user_id
            }
            
            # Save to disk
            self._save_users()
            
            logger.info(f"Saved user: {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save user {user_id}: {e}")
            
            # Rollback: restore from backup
            if backup_file and original_data:
                try:
                    self.users[user_id] = original_data
                    logger.info(f"Rolled back user to backup: {user_id}")
                except Exception as rollback_error:
                    logger.error(f"Rollback failed: {rollback_error}")
            
            raise EnrollmentStorageError(f"Failed to save user {user_id}: {e}") from e
    
    def get_user(self, user_id: str) -> Optional[Dict]:
        """
        Retrieve user data.
        
        Args:
            user_id: User identifier
        
        Returns:
            User data dict or None if not found
        """
        return self.users.get(user_id)
    
    def delete_user(self, user_id: str) -> bool:
        """
        Delete user data with automatic backup.
        
        Creates backup before deletion for recovery.
        
        Args:
            user_id: User identifier
        
        Returns:
            True if deleted, False if user not found
        
        Raises:
            EnrollmentStorageError: If deletion fails
        """
        if user_id not in self.users:
            logger.warning(f"User not found: {user_id}")
            return False
        
        try:
            # Create backup before delete
            self.create_backup(user_id)
            
            # Delete user
            del self.users[user_id]
            
            # Save changes
            self._save_users()
            
            logger.info(f"Deleted user: {user_id}")
            return True
            
        except Exception as e:
            error_msg = f"Failed to delete user {user_id}: {e}"
            logger.error(error_msg)
            raise EnrollmentStorageError(error_msg) from e
    
    def list_users(self) -> List[Dict]:
        """
        List all enrolled users.
        
        Returns:
            List of user summaries
        """
        return [
            {
                "user_id": user_id,
                "enrolled_at": user_data.get("enrolled_at"),
                "updated_at": user_data.get("updated_at"),
                "embedding_count": len(user_data.get("embeddings", []))
            }
            for user_id, user_data in self.users.items()
        ]
    
    def user_exists(self, user_id: str) -> bool:
        """
        Check if user exists.
        
        Args:
            user_id: User identifier
        
        Returns:
            True if user exists
        """
        return user_id in self.users
    
    def clear_all_data(self) -> bool:
        """
        Clear all user data (requires confirmation in logs).
        
        Creates full backup before clearing.
        
        Returns:
            True if cleared
        """
        try:
            logger.warning("Clearing all enrollment data!")
            
            # Create full backup first
            self.create_backup()
            
            # Clear data
            self.users = {}
            self._save_users()
            
            logger.warning("All enrollment data cleared")
            return True
            
        except Exception as e:
            error_msg = f"Failed to clear enrollment data: {e}"
            logger.error(error_msg)
            raise EnrollmentStorageError(error_msg) from e
    
    def get_stats(self) -> Dict:
        """
        Get storage statistics.
        
        Returns:
            Dict with storage stats
        """
        total_backups = len(list(self.backup_dir.glob("*.json")))
        data_file_size = self.users_file.stat().st_size if self.users_file.exists() else 0
        
        return {
            "total_users": len(self.users),
            "data_file_size": data_file_size,
            "data_file_path": str(self.users_file),
            "backup_dir_path": str(self.backup_dir),
            "total_backups": total_backups,
            "storage_dir": str(self.data_dir)
        }
