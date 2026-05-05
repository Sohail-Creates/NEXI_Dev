"""
JSON persistence adapter for data storage.
Provides atomic writes, file locking, and backup management.
Temporary solution - will be replaced with PostgreSQL in Phase 2.
"""

import json
import logging
import os
from typing import Any, Optional, Dict, List
from pathlib import Path
from datetime import datetime
import threading

logger = logging.getLogger(__name__)


class JSONPersistence:
    """JSON-based persistence layer with file locking."""

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def get_file_path(self, collection: str) -> Path:
        """Get file path for collection."""
        return self.data_dir / f"{collection}.json"

    def read(self, collection: str, default: Any = None) -> Any:
        """Read data from collection."""
        with self.lock:
            file_path = self.get_file_path(collection)
            if not file_path.exists():
                return default

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in {collection}.json")
                return default
            except Exception as e:
                logger.error(f"Error reading {collection}: {e}")
                return default

    def write(self, collection: str, data: Any) -> bool:
        """Write data to collection (atomic)."""
        with self.lock:
            try:
                file_path = self.get_file_path(collection)
                file_path.parent.mkdir(parents=True, exist_ok=True)

                # Write to temp file first
                temp_path = file_path.with_suffix(".json.tmp")
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, default=str)

                # Atomic rename
                temp_path.replace(file_path)
                logger.debug(f"Wrote data to {collection}")
                return True
            except Exception as e:
                logger.error(f"Error writing {collection}: {e}")
                return False

    def append(self, collection: str, item: Dict[str, Any]) -> bool:
        """Append item to collection list."""
        with self.lock:
            data = self.read(collection, [])
            if not isinstance(data, list):
                logger.error(f"{collection} is not a list")
                return False

            data.append(item)
            return self.write(collection, data)

    def get_by_id(self, collection: str, item_id: str) -> Optional[Dict[str, Any]]:
        """Get item by ID from collection."""
        with self.lock:
            data = self.read(collection, [])
            if not isinstance(data, list):
                return None

            for item in data:
                if isinstance(item, dict) and item.get("id") == item_id:
                    return item
            return None

    def update_by_id(
        self,
        collection: str,
        item_id: str,
        updates: Dict[str, Any],
    ) -> bool:
        """Update item by ID in collection."""
        with self.lock:
            data = self.read(collection, [])
            if not isinstance(data, list):
                return False

            for item in data:
                if isinstance(item, dict) and item.get("id") == item_id:
                    item.update(updates)
                    return self.write(collection, data)
            return False

    def delete_by_id(self, collection: str, item_id: str) -> bool:
        """Delete item by ID from collection."""
        with self.lock:
            data = self.read(collection, [])
            if not isinstance(data, list):
                return False

            filtered = [item for item in data if not (isinstance(item, dict) and item.get("id") == item_id)]
            if len(filtered) < len(data):
                return self.write(collection, filtered)
            return False

    def backup(self, collection: str, backup_dir: str = "./storage/backups") -> bool:
        """Create backup of collection."""
        try:
            backup_path = Path(backup_dir)
            backup_path.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_file = backup_path / f"{collection}_{timestamp}.json"

            data = self.read(collection)
            if data is None:
                return False

            with open(backup_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)

            logger.info(f"Backed up {collection} to {backup_file}")
            return True
        except Exception as e:
            logger.error(f"Error backing up {collection}: {e}")
            return False

    def restore(self, collection: str, backup_file: str) -> bool:
        """Restore collection from backup."""
        try:
            with open(backup_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            result = self.write(collection, data)
            if result:
                logger.info(f"Restored {collection} from {backup_file}")
            return result
        except Exception as e:
            logger.error(f"Error restoring {collection}: {e}")
            return False

    def list_collections(self) -> List[str]:
        """List all collections (files)."""
        try:
            collections = []
            for file in self.data_dir.glob("*.json"):
                collections.append(file.stem)
            return sorted(collections)
        except Exception as e:
            logger.error(f"Error listing collections: {e}")
            return []

    def clear_collection(self, collection: str) -> bool:
        """Clear all data from collection."""
        return self.write(collection, [])
