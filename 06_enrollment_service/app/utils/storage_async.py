"""
Async storage utilities for enrollment data
- Non-blocking file operations with aiofiles
- Full async/await support for all persistence operations
"""

import os
import json
import asyncio
import aiofiles
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path
from app.utils.encryption import get_encryption_manager
from shared.secure_storage import require_encryption_enabled


class AsyncEnrollmentStorage:
    """Async handles secure storage of enrollment data"""
    
    def __init__(self, storage_dir: str = "./enrollment_data", enable_encryption: bool = True):
        require_encryption_enabled()
        if not enable_encryption:
            raise RuntimeError("Enrollment metadata encryption is mandatory")
        self.storage_dir = storage_dir
        self.enable_encryption = True
        self.encryption_manager = get_encryption_manager()
        
        # Create storage directory
        os.makedirs(storage_dir, exist_ok=True)
        
        # Create subdirectories
        self.users_dir = os.path.join(storage_dir, "users")
        self.logs_dir = os.path.join(storage_dir, "logs")
        
        os.makedirs(self.users_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)
    
    async def save_enrollment(self, user_id: str, enrollment_data: Dict) -> str:
        """
        Async save enrollment data securely
        
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
            
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(encrypted_data)
        else:
            # Save plain JSON
            data_str = json.dumps(enrollment_data, indent=2)
            async with aiofiles.open(file_path, 'w') as f:
                await f.write(data_str)
        
        # Log enrollment
        await self._log_enrollment(user_id, "created")
        
        return file_path
    
    async def get_enrollment(self, user_id: str) -> Optional[Dict]:
        """
        Async retrieve enrollment data
        
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
            async with aiofiles.open(file_path, 'rb') as f:
                encrypted_data = await f.read()
            
            data_str = self.encryption_manager.decrypt(encrypted_data)
            return json.loads(data_str)
        else:
            # Read plain JSON
            async with aiofiles.open(file_path, 'r') as f:
                content = await f.read()
                return json.loads(content)
    
    async def update_enrollment(self, user_id: str, updates: Dict) -> bool:
        """
        Async update existing enrollment data
        
        Args:
            user_id: User identifier
            updates: Dictionary of updates to apply
            
        Returns:
            True if successful
        """
        # Get existing data
        enrollment_data = await self.get_enrollment(user_id)
        if enrollment_data is None:
            return False
        
        # Apply updates
        enrollment_data.update(updates)
        enrollment_data['updated_at'] = datetime.utcnow().isoformat()
        
        # Save
        await self.save_enrollment(user_id, enrollment_data)
        await self._log_enrollment(user_id, "updated")
        
        return True
    
    async def delete_enrollment(self, user_id: str) -> bool:
        """
        Async delete user enrollment and all associated data
        
        Args:
            user_id: User identifier
            
        Returns:
            True if successful
        """
        user_dir = os.path.join(self.users_dir, user_id)
        
        if not os.path.exists(user_dir):
            return False
        
        try:
            # Use loop.run_in_executor for sync shutil operation
            import shutil
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, shutil.rmtree, user_dir)
            
            await self._log_enrollment(user_id, "deleted")
            return True
        except Exception as e:
            print(f"Error deleting enrollment for {user_id}: {e}")
            return False
    
    async def get_all_users(self) -> List[str]:
        """Async get list of all enrolled users"""
        if not os.path.exists(self.users_dir):
            return []
        
        users = []
        for item in os.listdir(self.users_dir):
            item_path = os.path.join(self.users_dir, item)
            if os.path.isdir(item_path):
                users.append(item)
        
        return sorted(users)
    
    async def user_exists(self, user_id: str) -> bool:
        """Async check if user enrollment exists"""
        enrollment = await self.get_enrollment(user_id)
        return enrollment is not None
    
    async def _log_enrollment(self, user_id: str, action: str) -> None:
        """Async log enrollment action"""
        log_file = os.path.join(self.logs_dir, "enrollments.json")
        
        # Read existing logs
        logs = []
        if os.path.exists(log_file):
            try:
                async with aiofiles.open(log_file, 'r') as f:
                    content = await f.read()
                    logs = json.loads(content)
            except:
                logs = []
        
        # Add new log entry
        logs.append({
            "user_id": user_id,
            "action": action,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Write logs
        data_str = json.dumps(logs, indent=2)
        async with aiofiles.open(log_file, 'w') as f:
            await f.write(data_str)
    
    async def get_logs(self, user_id: Optional[str] = None) -> List[Dict]:
        """Async get enrollment logs"""
        log_file = os.path.join(self.logs_dir, "enrollments.json")
        
        if not os.path.exists(log_file):
            return []
        
        try:
            async with aiofiles.open(log_file, 'r') as f:
                content = await f.read()
                logs = json.loads(content)
            
            if user_id:
                logs = [log for log in logs if log.get("user_id") == user_id]
            
            return logs
        except:
            return []
    
    async def get_storage_stats(self) -> Dict:
        """Async get storage statistics"""
        stats = {
            "total_users": 0,
            "total_size_bytes": 0,
            "users_dir_path": self.users_dir,
            "logs_dir_path": self.logs_dir,
        }
        
        # Count users and calculate size
        if os.path.exists(self.users_dir):
            for user_id in os.listdir(self.users_dir):
                user_path = os.path.join(self.users_dir, user_id)
                if os.path.isdir(user_path):
                    stats["total_users"] += 1
                    for root, dirs, files in os.walk(user_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            try:
                                stats["total_size_bytes"] += os.path.getsize(file_path)
                            except:
                                pass
        
        return stats


# Global instance
_async_storage: Optional[AsyncEnrollmentStorage] = None


async def init_async_storage(storage_dir: str = "./enrollment_data", 
                             enable_encryption: bool = True) -> AsyncEnrollmentStorage:
    """Initialize async storage"""
    global _async_storage
    _async_storage = AsyncEnrollmentStorage(storage_dir, enable_encryption)
    return _async_storage


def get_async_storage() -> AsyncEnrollmentStorage:
    """Get async storage instance"""
    if _async_storage is None:
        raise RuntimeError("AsyncEnrollmentStorage not initialized")
    return _async_storage
