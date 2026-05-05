# Configuration Management for TeachMe Service
# Centralized settings for all components

import os
from typing import Optional
from dotenv import load_dotenv  # type: ignore

# Load environment variables from .env file
load_dotenv()


class VisionServiceConfig:
    """Vision Service integration settings"""
    
    HOST: str = os.getenv("VISION_HOST", "localhost")
    PORT: int = int(os.getenv("VISION_PORT", "8001"))
    TIMEOUT: int = int(os.getenv("VISION_TIMEOUT", "30"))
    HEALTH_CHECK_TIMEOUT: int = int(os.getenv("HEALTH_CHECK_TIMEOUT", "2"))
    RETRY_COUNT: int = int(os.getenv("VISION_RETRY_COUNT", "2"))
    RETRY_DELAY: int = int(os.getenv("VISION_RETRY_DELAY", "1"))
    
    # Vision API endpoints
    ANALYZE_ENDPOINT: str = "/analyze/complete"
    HEALTH_ENDPOINT: str = "/health"
    
    # Vision analysis parameters
    DETECTOR_BACKEND: str = "opencv"
    ANALYZE_EMOTIONS: bool = False
    OBJECT_CONFIDENCE_THRESHOLD: float = float(os.getenv("OBJECT_CONFIDENCE_THRESHOLD", "0.15"))
    MIN_MATCH_CONFIDENCE: float = float(os.getenv("MIN_MATCH_CONFIDENCE", "0.3"))
    
    @classmethod
    def get_base_url(cls) -> str:
        return f"http://{cls.HOST}:{cls.PORT}"
    
    @classmethod
    def get_analyze_url(cls) -> str:
        return f"http://{cls.HOST}:{cls.PORT}{cls.ANALYZE_ENDPOINT}"
    
    @classmethod
    def get_health_url(cls) -> str:
        return f"http://{cls.HOST}:{cls.PORT}{cls.HEALTH_ENDPOINT}"


class StorageConfig:
    """Persistent storage settings"""
    
    STORAGE_FILE: str = os.getenv("STORAGE_FILE", "knowledge_data.json")
    BACKUP_DIR: str = os.getenv("BACKUP_DIR", "knowledge_backups")
    BACKUP_RETENTION: int = int(os.getenv("BACKUP_RETENTION", "10"))
    
    # File locking timeout (seconds)
    FILE_LOCK_TIMEOUT: int = int(os.getenv("FILE_LOCK_TIMEOUT", "30"))
    
    # Async save queue settings
    SAVE_QUEUE_SIZE: int = int(os.getenv("SAVE_QUEUE_SIZE", "100"))


class SearchIndexConfig:
    """Embedding search index settings"""
    
    USE_FAISS: bool = os.getenv("USE_FAISS", "true").lower() == "true"
    INDEX_DIMENSION: int = int(os.getenv("INDEX_DIMENSION", "128"))
    INDEX_METRIC: str = os.getenv("INDEX_METRIC", "cosine")
    
    # Fallback to linear search if index fails
    FALLBACK_TO_LINEAR: bool = True


class ServerConfig:
    """FastAPI server settings"""
    
    HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("SERVER_PORT", "8004"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    RELOAD: bool = os.getenv("RELOAD", "true").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


class PerformanceConfig:
    """Performance and tuning settings"""
    
    # Async I/O settings
    ASYNC_SAVE_ENABLED: bool = os.getenv("ASYNC_SAVE_ENABLED", "true").lower() == "true"
    ASYNC_BACKUP_ENABLED: bool = os.getenv("ASYNC_BACKUP_ENABLED", "true").lower() == "true"
    
    # Threading settings
    THREAD_SAFE_MODE: bool = os.getenv("THREAD_SAFE_MODE", "true").lower() == "true"
    MAX_CONCURRENT_OPERATIONS: int = int(os.getenv("MAX_CONCURRENT_OPERATIONS", "100"))


# Convenience access to all config classes
vision_config = VisionServiceConfig()
storage_config = StorageConfig()
search_index_config = SearchIndexConfig()
server_config = ServerConfig()
performance_config = PerformanceConfig()


def validate_config() -> bool:
    """Validate configuration on startup"""
    errors = []
    
    # Validate Vision Service config
    if vision_config.TIMEOUT < 5:
        errors.append("VISION_TIMEOUT must be >= 5 seconds")
    
    if vision_config.MIN_MATCH_CONFIDENCE < 0 or vision_config.MIN_MATCH_CONFIDENCE > 1:
        errors.append("MIN_MATCH_CONFIDENCE must be between 0 and 1")
    
    # Validate Storage config
    if not os.path.exists(storage_config.BACKUP_DIR):
        try:
            os.makedirs(storage_config.BACKUP_DIR, exist_ok=True)
        except Exception as e:
            errors.append(f"Cannot create backup directory: {e}")
    
    # Validate Search Index config
    if search_index_config.INDEX_DIMENSION < 1:
        errors.append("INDEX_DIMENSION must be >= 1")
    
    if errors:
        print("Configuration validation failed:")
        for error in errors:
            print(f"  - {error}")
        return False
    
    return True


if __name__ == "__main__":
    print("TeachMe Configuration")
    print("=" * 50)
    print(f"Vision Service: {vision_config.get_base_url()}")
    print(f"Storage File: {storage_config.STORAGE_FILE}")
    print(f"Backup Directory: {storage_config.BACKUP_DIR}")
    print(f"Server: {server_config.HOST}:{server_config.PORT}")
    print(f"Search Index Enabled: {search_index_config.USE_FAISS}")
    print(f"Async I/O Enabled: {performance_config.ASYNC_SAVE_ENABLED}")
    print(f"Thread Safe Mode: {performance_config.THREAD_SAFE_MODE}")
    print("=" * 50)
    
    if validate_config():
        print(" Configuration valid")
    else:
        print(" Configuration invalid")
