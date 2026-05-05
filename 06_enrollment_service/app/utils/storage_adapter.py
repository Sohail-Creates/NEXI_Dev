"""
Storage adapter - allows switching between sync and async storage
Provides compatibility layer for gradual async migration
"""

import asyncio
import os
from typing import Optional
from app.utils.storage import EnrollmentStorage
from app.utils.storage_async import AsyncEnrollmentStorage


class StorageAdapter:
    """
    Adapter that wraps both sync and async storage.
    Allows gradual migration from sync to async.
    """
    
    def __init__(self, storage_dir: str = "./enrollment_data", 
                 enable_encryption: bool = True,
                 use_async: bool = False) -> None:
        """
        Initialize storage adapter
        
        Args:
            storage_dir: Directory for storing enrollment data
            enable_encryption: Whether to encrypt data
            use_async: If True, use async storage; if False, use sync storage
        """
        self.storage_dir: str = storage_dir
        self.enable_encryption: bool = enable_encryption
        self.use_async: bool = use_async
        
        # Initialize both (backward compatibility)
        self.sync_storage = EnrollmentStorage(storage_dir, enable_encryption)
        self.async_storage = AsyncEnrollmentStorage(storage_dir, enable_encryption)
    
    # ========================================================================
    # SYNC METHODS (for backward compatibility)
    # ========================================================================
    
    def save_enrollment(self, user_id: str, enrollment_data: dict) -> str:
        """Save enrollment (sync)"""
        return self.sync_storage.save_enrollment(user_id, enrollment_data)
    
    def get_enrollment(self, user_id: str) -> Optional[dict]:
        """Get enrollment (sync)"""
        return self.sync_storage.get_enrollment(user_id)
    
    def update_enrollment(self, user_id: str, updates: dict) -> bool:
        """Update enrollment (sync)"""
        return self.sync_storage.update_enrollment(user_id, updates)
    
    def delete_enrollment(self, user_id: str) -> bool:
        """Delete enrollment (sync)"""
        return self.sync_storage.delete_enrollment(user_id)
    
    def list_enrollments(self) -> list:
        """List enrollments (sync)"""
        return self.sync_storage.list_enrollments()
    
    def get_storage_stats(self) -> dict:
        """Get storage stats (sync)"""
        return self.sync_storage.get_storage_stats()
    
    # ========================================================================
    # ASYNC METHODS (new non-blocking versions)
    # ========================================================================
    
    async def save_enrollment_async(self, user_id: str, enrollment_data: dict) -> str:
        """Save enrollment (async, non-blocking)"""
        return await self.async_storage.save_enrollment(user_id, enrollment_data)
    
    async def get_enrollment_async(self, user_id: str) -> Optional[dict]:
        """Get enrollment (async, non-blocking)"""
        return await self.async_storage.get_enrollment(user_id)
    
    async def update_enrollment_async(self, user_id: str, updates: dict) -> bool:
        """Update enrollment (async, non-blocking)"""
        return await self.async_storage.update_enrollment(user_id, updates)
    
    async def delete_enrollment_async(self, user_id: str) -> bool:
        """Delete enrollment (async, non-blocking)"""
        return await self.async_storage.delete_enrollment(user_id)
    
    async def get_all_users_async(self) -> list:
        """Get all users (async, non-blocking)"""
        return await self.async_storage.get_all_users()
    
    async def user_exists_async(self, user_id: str) -> bool:
        """Check if user exists (async, non-blocking)"""
        return await self.async_storage.user_exists(user_id)
    
    async def get_storage_stats_async(self) -> dict:
        """Get storage stats (async, non-blocking)"""
        return await self.async_storage.get_storage_stats()
    
    # ========================================================================
    # AUTO-SWITCHING METHODS (recommended for new code)
    # ========================================================================
    
    async def save_enrollment_smart(self, user_id: str, enrollment_data: dict) -> str:
        """
        Smart save: uses async if available, falls back to sync in thread pool
        """
        if self.use_async:
            return await self.async_storage.save_enrollment(user_id, enrollment_data)
        else:
            # Run sync version in thread pool to avoid blocking
            loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                self.sync_storage.save_enrollment,
                user_id,
                enrollment_data
            )
    
    async def get_enrollment_smart(self, user_id: str) -> Optional[dict]:
        """
        Smart get: uses async if available, falls back to sync in thread pool
        """
        if self.use_async:
            return await self.async_storage.get_enrollment(user_id)
        else:
            loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                self.sync_storage.get_enrollment,
                user_id
            )
    
    async def delete_enrollment_smart(self, user_id: str) -> bool:
        """
        Smart delete: uses async if available, falls back to sync in thread pool
        """
        if self.use_async:
            return await self.async_storage.delete_enrollment(user_id)
        else:
            loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                self.sync_storage.delete_enrollment,
                user_id
            )


# Global adapter instance
_adapter_instance: Optional[StorageAdapter] = None


def get_storage_adapter(
    storage_dir: str = "./enrollment_data",
    enable_encryption: bool = True,
    use_async: bool = False
) -> StorageAdapter:
    """Get or create storage adapter"""
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = StorageAdapter(storage_dir, enable_encryption, use_async)
    return _adapter_instance


def enable_async_storage() -> None:
    """Enable async storage globally"""
    global _adapter_instance
    if _adapter_instance:
        _adapter_instance.use_async = True


def disable_async_storage() -> None:
    """Disable async storage globally"""
    global _adapter_instance
    if _adapter_instance:
        _adapter_instance.use_async = False
