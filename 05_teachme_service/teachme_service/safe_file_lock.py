"""
Safe File Locking Module
Cross-platform file locking with intelligent fallback strategies
"""

import os
import sys
import logging
import time
from typing import Optional, Generator
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

# Platform detection
IS_WINDOWS = sys.platform == "win32"
IS_UNIX = sys.platform in ("linux", "darwin")

# Import platform-specific locking
if IS_UNIX:
    try:
        import fcntl
        HAS_FCNTL = True
    except ImportError:
        HAS_FCNTL = False
else:
    HAS_FCNTL = False


class FileLockError(Exception):
    """File locking operation failed"""
    pass


class SafeFileLock:
    """
    Cross-platform file locking with intelligent fallback
    
    Strategy:
    1. Try OS-specific locking (fcntl on Unix, msvcrt on Windows)
    2. If that fails, use fallback lock file mechanism
    3. Log all lock operations for debugging
    """
    
    def __init__(self, file_path: str, timeout: float = 30.0):
        self.file_path = file_path
        self.lock_file = f"{file_path}.lock"
        self.timeout = timeout
        self.lock_handle = None
        self.is_locked = False
        self.platform = "windows" if IS_WINDOWS else "unix" if IS_UNIX else "unknown"
    
    @contextmanager
    def acquire(self) -> Generator:
        """
        Acquire file lock with intelligent fallback
        
        Yields:
            After successfully acquiring lock
            
        Raises:
            FileLockError: If lock cannot be acquired within timeout
        """
        success = False
        
        try:
            if IS_UNIX and HAS_FCNTL:
                success = self._acquire_unix_lock()
            elif IS_WINDOWS:
                success = self._acquire_windows_lock()
            else:
                success = self._acquire_fallback_lock()
            
            if not success:
                raise FileLockError(f"Could not acquire lock on {self.file_path} within {self.timeout}s")
            
            self.is_locked = True
            yield
            
        finally:
            self._release_lock()
    
    def _acquire_unix_lock(self) -> bool:
        """Acquire file lock using fcntl (Unix)"""
        try:
            lock_file_path = self.lock_file
            Path(lock_file_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Open lock file
            lock_file = open(lock_file_path, 'w')
            
            # Try to acquire exclusive lock with timeout
            start_time = time.time()
            while True:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self.lock_handle = lock_file
                    logger.debug(f"Acquired Unix fcntl lock on {self.file_path}")
                    return True
                    
                except (IOError, OSError) as e:
                    if time.time() - start_time >= self.timeout:
                        lock_file.close()
                        return False
                    
                    time.sleep(0.1)  # Brief wait before retry
                    
        except Exception as e:
            logger.warning(f"Unix lock acquisition failed: {e}")
            return False
    
    def _acquire_windows_lock(self) -> bool:
        """Acquire file lock using Windows mechanisms"""
        try:
            lock_file_path = self.lock_file
            Path(lock_file_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Try to create lock file exclusively (atomic on Windows)
            start_time = time.time()
            retry_count = 0
            max_retries = int(self.timeout * 10)  # Retry every 0.1s
            
            while retry_count < max_retries:
                try:
                    # Open with exclusive creation (fails if exists)
                    lock_file = open(lock_file_path, 'x')
                    lock_file.close()
                    
                    self.lock_file_created = True
                    logger.debug(f"Acquired Windows lock on {self.file_path}")
                    return True
                    
                except FileExistsError:
                    # Lock file exists, check if it's stale (older than timeout)
                    try:
                        file_age = time.time() - os.path.getmtime(lock_file_path)
                        if file_age > self.timeout * 2:
                            # Stale lock file, remove it and try again
                            logger.warning(f"Removing stale lock file: {lock_file_path}")
                            os.remove(lock_file_path)
                            continue
                    except OSError:
                        pass
                    
                    retry_count += 1
                    time.sleep(0.1)
                    
            logger.warning(f"Windows lock acquisition timeout on {self.file_path}")
            return False
            
        except Exception as e:
            logger.warning(f"Windows lock acquisition failed: {e}")
            return False
    
    def _acquire_fallback_lock(self) -> bool:
        """Generic fallback lock mechanism"""
        try:
            lock_file_path = self.lock_file
            Path(lock_file_path).parent.mkdir(parents=True, exist_ok=True)
            
            start_time = time.time()
            
            while time.time() - start_time < self.timeout:
                try:
                    # Try to create lock directory (atomic operation)
                    os.makedirs(f"{lock_file_path}.d", exist_ok=False)
                    logger.debug(f"Acquired fallback lock on {self.file_path}")
                    self.lock_dir_created = True
                    return True
                    
                except (OSError, FileExistsError):
                    time.sleep(0.1)
            
            logger.warning(f"Fallback lock acquisition timeout on {self.file_path}")
            return False
            
        except Exception as e:
            logger.warning(f"Fallback lock acquisition failed: {e}")
            return False
    
    def _release_lock(self) -> None:
        """Release file lock"""
        try:
            if IS_UNIX and HAS_FCNTL and self.lock_handle:
                try:
                    fcntl.flock(self.lock_handle.fileno(), fcntl.LOCK_UN)
                    self.lock_handle.close()
                except Exception as e:
                    logger.warning(f"Error releasing Unix lock: {e}")
            
            # Remove Windows lock file if created
            if IS_WINDOWS and hasattr(self, 'lock_file_created'):
                try:
                    if os.path.exists(self.lock_file):
                        os.remove(self.lock_file)
                    logger.debug(f"Released Windows lock on {self.file_path}")
                except Exception as e:
                    logger.warning(f"Error removing Windows lock file: {e}")
            
            # Remove fallback lock directory if created
            if hasattr(self, 'lock_dir_created'):
                try:
                    lock_dir = f"{self.lock_file}.d"
                    if os.path.exists(lock_dir):
                        os.rmdir(lock_dir)
                    logger.debug(f"Released fallback lock on {self.file_path}")
                except Exception as e:
                    logger.warning(f"Error removing fallback lock: {e}")
            
            self.is_locked = False
            
        except Exception as e:
            logger.error(f"Error during lock release: {e}")
    
    def __enter__(self):
        """Context manager entry"""
        # Note: This creates a generator, doesn't directly acquire lock
        self._lock_context = self.acquire()
        return self._lock_context.__enter__()
    
    def __exit__(self, *args):
        """Context manager exit"""
        return self._lock_context.__exit__(*args)


@contextmanager
def get_safe_file_lock(file_path: str, timeout: float = 30.0) -> Generator:
    """
    Get a safe file lock as context manager
    
    Usage:
        with get_safe_file_lock('data.json'):
            # Perform file operations
            with open('data.json', 'w') as f:
                json.dump(data, f)
    """
    lock = SafeFileLock(file_path, timeout)
    with lock.acquire():
        yield lock
