"""
Async Persistence Layer for NEXI
- Non-blocking file operations with aiofiles
- Atomic writes with versioning
- Automatic backups
- Full async/await support
"""

import aiofiles
import json
import logging
import os
import asyncio
from typing import Any, Dict, Optional, List
from datetime import datetime
from pathlib import Path
import shutil

logger = logging.getLogger(__name__)


class AsyncPersistenceError(Exception):
    """Custom exception for async persistence operations"""
    pass


class AsyncPersistenceLayer:
    """
    Fast and reliable async data persistence.
    
    Features:
    - Non-blocking file I/O with aiofiles
    - Atomic writes (write to temp, then rename)
    - Automatic backups with versioning
    - Write buffering (batch multiple writes)
    - Fast JSON loading
    - Recovery from corrupted files
    """

    def __init__(self, config_persistence: Any):
        self.config = config_persistence
        self.data_dir = Path(config_persistence.data_dir)
        self.backup_dir = Path(config_persistence.backup_dir)
        
        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.config.backup_enabled:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Write buffer for batch operations
        self.write_buffer: Dict[str, Any] = {}
        self.buffer_lock = asyncio.Lock()
        
        # Version tracking
        self.versions: Dict[str, int] = {}
        
        logger.info(
            f"AsyncPersistenceLayer initialized (data_dir={self.data_dir}, "
            f"backups={self.config.backup_enabled})"
        )

    # ========================================================================
    # HIGH-LEVEL API (ALL ASYNC)
    # ========================================================================

    async def load(self, file_key: str) -> Any:
        """
        Async load data from file with recovery.
        
        Args:
            file_key: Identifier (e.g., 'users', 'objects', 'knowledge')
        
        Returns:
            Loaded data or empty list/dict if missing
        """
        file_path = self.data_dir / f"{file_key}.json"
        
        if not file_path.exists():
            logger.debug(f"File not found (will create): {file_key}")
            return [] if file_key in ['users', 'objects', 'knowledge'] else {}
        
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading {file_key}: {e}")
            return await self._recover_from_backup(file_key)

    async def save(self, file_key: str, data: Any, immediate: bool = False) -> bool:
        """
        Async save data to file with atomic write.
        
        Args:
            file_key: Identifier
            data: Data to save
            immediate: Skip buffering, write immediately
        
        Returns:
            True if successful
        """
        if immediate:
            return await self._write_atomic(file_key, data)
        
        # Buffer for batch writes
        async with self.buffer_lock:
            self.write_buffer[file_key] = data
            return True

    async def flush_buffer(self) -> int:
        """
        Async flush all buffered writes to disk.
        
        Returns:
            Number of files written
        """
        async with self.buffer_lock:
            if not self.write_buffer:
                return 0
            
            count = 0
            for file_key, data in self.write_buffer.items():
                if await self._write_atomic(file_key, data):
                    count += 1
            
            self.write_buffer.clear()
            return count

    async def backup(self, file_key: str) -> bool:
        """
        Async create versioned backup of a file.
        
        Args:
            file_key: File to backup
        
        Returns:
            True if successful
        """
        if not self.config.backup_enabled:
            return False
        
        file_path = self.data_dir / f"{file_key}.json"
        if not file_path.exists():
            return False
        
        try:
            timestamp = datetime.utcnow().isoformat().replace(':', '-')
            version = self.versions.get(file_key, 0) + 1
            self.versions[file_key] = version
            
            backup_name = f"{file_key}_v{version}_{timestamp}.json.backup"
            backup_path = self.backup_dir / backup_name
            
            # Use loop.run_in_executor for synchronous shutil operation
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, shutil.copy2, file_path, backup_path)
            
            logger.info(f"Backup created: {backup_name}")
            
            # Clean up old backups
            await self._cleanup_old_backups(file_key)
            
            return True
        except Exception as e:
            logger.error(f"Backup failed for {file_key}: {e}")
            return False

    async def get_backups(self, file_key: str) -> List[Dict[str, Any]]:
        """Async get list of available backups for a file"""
        if not self.config.backup_enabled:
            return []
        
        backups = []
        pattern = f"{file_key}_v*.json.backup"
        
        for backup_file in self.backup_dir.glob(pattern):
            stat = backup_file.stat()
            backups.append({
                "name": backup_file.name,
                "path": str(backup_file),
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
        
        return sorted(backups, key=lambda x: x['created'], reverse=True)

    async def restore_from_backup(self, file_key: str, backup_name: str) -> bool:
        """Async restore file from backup"""
        if not self.config.backup_enabled:
            return False
        
        backup_path = self.backup_dir / backup_name
        if not backup_path.exists():
            logger.error(f"Backup not found: {backup_name}")
            return False
        
        try:
            file_path = self.data_dir / f"{file_key}.json"
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, shutil.copy2, backup_path, file_path)
            logger.info(f"Restored from backup: {backup_name}")
            return True
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            return False

    def get_size_stats(self) -> Dict[str, Any]:
        """Get storage size statistics (sync operation)"""
        stats = {
            "data_dir": {
                "path": str(self.data_dir),
                "size_bytes": 0,
                "files": 0,
            },
            "backup_dir": {
                "path": str(self.backup_dir) if self.config.backup_enabled else None,
                "size_bytes": 0,
                "files": 0,
            }
        }
        
        # Data directory
        for file_path in self.data_dir.glob("*.json"):
            stats["data_dir"]["size_bytes"] += file_path.stat().st_size
            stats["data_dir"]["files"] += 1
        
        # Backup directory
        if self.config.backup_enabled:
            for file_path in self.backup_dir.glob("*.backup"):
                stats["backup_dir"]["size_bytes"] += file_path.stat().st_size
                stats["backup_dir"]["files"] += 1
        
        return stats

    # ========================================================================
    # PRIVATE METHODS (ALL ASYNC)
    # ========================================================================

    async def _write_atomic(self, file_key: str, data: Any) -> bool:
        """
        Async atomic write using temp file + rename.
        
        Guarantees:
        - No partial writes
        - No corruption
        - Automatic recovery possible
        """
        file_path = self.data_dir / f"{file_key}.json"
        temp_path = self.data_dir / f"{file_key}.json.tmp"
        
        try:
            # Create backup before writing
            if file_path.exists() and self.config.backup_enabled:
                await self.backup(file_key)
            
            # Write to temp file first (async)
            json_str = json.dumps(data, indent=2, ensure_ascii=False)
            async with aiofiles.open(temp_path, 'w', encoding='utf-8') as f:
                await f.write(json_str)
            
            # Atomic rename (synchronous, but very fast)
            temp_path.replace(file_path)
            
            logger.debug(f"Saved: {file_key}")
            return True
            
        except Exception as e:
            logger.error(f"Write failed for {file_key}: {e}")
            
            # Clean up temp file
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            
            return False

    async def _recover_from_backup(self, file_key: str) -> Any:
        """Async recover from most recent backup"""
        if not self.config.backup_enabled:
            logger.warning(f"No backup available for {file_key}")
            return [] if file_key in ['users', 'objects', 'knowledge'] else {}
        
        backups = await self.get_backups(file_key)
        if not backups:
            logger.warning(f"No backups found for {file_key}")
            return [] if file_key in ['users', 'objects', 'knowledge'] else {}
        
        try:
            most_recent = backups[0]
            async with aiofiles.open(most_recent['path'], 'r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
            logger.info(f"Recovered {file_key} from backup: {most_recent['name']}")
            return data
        except Exception as e:
            logger.error(f"Recovery failed for {file_key}: {e}")
            return [] if file_key in ['users', 'objects', 'knowledge'] else {}

    async def _cleanup_old_backups(self, file_key: str) -> None:
        """Remove old backup versions beyond max count"""
        if self.config.max_backup_versions <= 0:
            return
        
        try:
            backups = await self.get_backups(file_key)
            
            if len(backups) > self.config.max_backup_versions:
                to_delete = backups[self.config.max_backup_versions:]
                for backup in to_delete:
                    Path(backup['path']).unlink()
                    logger.debug(f"Deleted old backup: {backup['name']}")
                    
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")


# Global async persistence layer (initialized in main)
async_persistence_layer: Optional[AsyncPersistenceLayer] = None


async def init_async_persistence_layer(config_persistence: Any) -> AsyncPersistenceLayer:
    """Initialize async persistence layer"""
    global async_persistence_layer
    async_persistence_layer = AsyncPersistenceLayer(config_persistence)
    return async_persistence_layer


def get_async_persistence_layer() -> AsyncPersistenceLayer:
    """Get async persistence layer instance"""
    if async_persistence_layer is None:
        raise RuntimeError("AsyncPersistenceLayer not initialized")
    return async_persistence_layer
