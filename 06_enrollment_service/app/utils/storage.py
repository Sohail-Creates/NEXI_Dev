"""
Secure storage utilities for enrollment data
"""
import os
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path
from app.utils.encryption import get_encryption_manager


class EnrollmentStorage:
    """Handles secure storage of enrollment data"""
    
    def __init__(self, storage_dir: str = "./enrollment_data", enable_encryption: bool = True):
        self.storage_dir = storage_dir
        self.enable_encryption = enable_encryption
        self.encryption_manager = get_encryption_manager() if enable_encryption else None
        
        # Create storage directory
        os.makedirs(storage_dir, exist_ok=True)
        
        # Create subdirectories
        self.users_dir = os.path.join(storage_dir, "users")
        self.logs_dir = os.path.join(storage_dir, "logs")
        
        os.makedirs(self.users_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)
    
    def save_enrollment(self, user_id: str, enrollment_data: Dict) -> str:
        """
        Save enrollment data securely
        
        Args:
            user_id: Unique user identifier
            enrollment_data: Complete enrollment information
            
        Returns:
            Path to saved file
        """
        # Add metadata
        enrollment_data['saved_at'] = datetime.utcnow().isoformat()
        enrollment_data['storage_version'] = '1.0'
        
        # Create user-specific directory
        user_dir = os.path.join(self.users_dir, user_id)
        os.makedirs(user_dir, exist_ok=True)
        
        # Save enrollment data
        file_path = os.path.join(user_dir, "enrollment.json")
        
        if self.enable_encryption:
            # Encrypt and save
            data_str = json.dumps(enrollment_data, indent=2)
            encrypted_data = self.encryption_manager.encrypt(data_str)
            
            with open(file_path, 'wb') as f:
                f.write(encrypted_data)
        else:
            # Save plain JSON
            with open(file_path, 'w') as f:
                json.dump(enrollment_data, f, indent=2)
        
        # Log enrollment
        self._log_enrollment(user_id, "created")
        
        return file_path
    
    def get_enrollment(self, user_id: str) -> Optional[Dict]:
        """
        Retrieve enrollment data
        
        Args:
            user_id: User identifier
            
        Returns:
            Enrollment data or None if not found
        """
        file_path = os.path.join(self.users_dir, user_id, "enrollment.json")
        
        if not os.path.exists(file_path):
            return None
        
        if self.enable_encryption:
            # Read and decrypt
            with open(file_path, 'rb') as f:
                encrypted_data = f.read()
            
            data_str = self.encryption_manager.decrypt(encrypted_data)
            return json.loads(data_str)
        else:
            # Read plain JSON
            with open(file_path, 'r') as f:
                return json.load(f)
    
    def update_enrollment(self, user_id: str, updates: Dict) -> bool:
        """
        Update existing enrollment data
        
        Args:
            user_id: User identifier
            updates: Fields to update
            
        Returns:
            True if successful, False otherwise
        """
        enrollment_data = self.get_enrollment(user_id)
        
        if not enrollment_data:
            return False
        
        # Update fields
        enrollment_data.update(updates)
        enrollment_data['updated_at'] = datetime.utcnow().isoformat()
        
        # Save updated data
        self.save_enrollment(user_id, enrollment_data)
        
        # Log update
        self._log_enrollment(user_id, "updated")
        
        return True
    
    def delete_enrollment(self, user_id: str) -> bool:
        """
        Delete enrollment data
        
        Args:
            user_id: User identifier
            
        Returns:
            True if successful, False otherwise
        """
        user_dir = os.path.join(self.users_dir, user_id)
        
        if not os.path.exists(user_dir):
            return False
        
        # Delete directory and all contents
        import shutil
        shutil.rmtree(user_dir)
        
        # Log deletion
        self._log_enrollment(user_id, "deleted")
        
        return True
    
    def list_enrollments(self) -> List[str]:
        """
        List all enrolled user IDs
        
        Returns:
            List of user IDs
        """
        if not os.path.exists(self.users_dir):
            return []
        
        return [
            d for d in os.listdir(self.users_dir)
            if os.path.isdir(os.path.join(self.users_dir, d))
        ]
    
    def get_enrollment_count(self) -> int:
        """Get total number of enrollments"""
        return len(self.list_enrollments())
    
    def _log_enrollment(self, user_id: str, action: str):
        """Log enrollment action"""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'user_id': user_id,
            'action': action
        }
        
        # Append to daily log file
        log_file = os.path.join(
            self.logs_dir,
            f"enrollment_log_{datetime.utcnow().strftime('%Y%m%d')}.json"
        )
        
        # Read existing logs
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                logs = json.load(f)
        else:
            logs = []
        
        # Append new log
        logs.append(log_entry)
        
        # Save logs
        with open(log_file, 'w') as f:
            json.dump(logs, f, indent=2)
    
    def get_storage_stats(self) -> Dict:
        """Get storage statistics"""
        return {
            'total_enrollments': self.get_enrollment_count(),
            'storage_directory': self.storage_dir,
            'encryption_enabled': self.enable_encryption,
            'disk_usage_mb': self._get_directory_size() / (1024 * 1024)
        }
    
    def _get_directory_size(self) -> int:
        """Calculate total size of storage directory in bytes"""
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(self.storage_dir):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                if os.path.exists(filepath):
                    total_size += os.path.getsize(filepath)
        return total_size


# Global storage instance
_storage_instance = None


def get_storage(
    storage_dir: str = "./enrollment_data",
    enable_encryption: bool = True
) -> EnrollmentStorage:
    """Get or create global storage instance"""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = EnrollmentStorage(storage_dir, enable_encryption)
    return _storage_instance