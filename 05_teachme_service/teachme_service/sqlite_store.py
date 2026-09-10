"""SQLite knowledge records with optimistic conflict detection between writers."""

from contextlib import closing
from functools import wraps
import json
from pathlib import Path
import sqlite3


def locked(function):
    @wraps(function)
    def wrapped(self, *args, **kwargs):
        with self._storage_lock:
            return function(self, *args, **kwargs)
    return wrapped


def initialize(database):
    database = Path(database)
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS knowledge (id TEXT PRIMARY KEY, record TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS metadata (id INTEGER PRIMARY KEY CHECK (id=1), record TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS migration (source TEXT PRIMARY KEY, digest TEXT NOT NULL);
        """)


class KnowledgeStore:
    def __init__(self, database):
        self.database = Path(database)
        if not self.database.exists():
            raise RuntimeError("TeachMe SQLite store missing; run migrate_sqlite.py before startup")

    def read(self):
        with closing(sqlite3.connect(self.database)) as conn:
            conn.execute("BEGIN")
            return self._read(conn)

    @staticmethod
    def _read(conn):
        metadata = conn.execute("SELECT record FROM metadata WHERE id=1").fetchone()
        return {"storage": {key: json.loads(value) for key, value in conn.execute("SELECT id, record FROM knowledge ORDER BY rowid")},
                "metadata": json.loads(metadata[0]) if metadata else {}}

    def save(self, baseline, proposed, metadata):
        """Merge independent changes; reject competing edits instead of losing one."""
        changed = {key for key in baseline.keys() | proposed.keys() if baseline.get(key) != proposed.get(key)}
        with closing(sqlite3.connect(self.database, timeout=30)) as conn, conn:
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("BEGIN IMMEDIATE")
            current = self._read(conn)["storage"]
            for key in changed:
                if current.get(key) != baseline.get(key) and current.get(key) != proposed.get(key):
                    raise RuntimeError(f"Concurrent knowledge update conflict for {key}; reload before retrying")
            for key in changed:
                if key in proposed:
                    conn.execute("INSERT INTO knowledge VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET record=excluded.record",
                                 (key, json.dumps(proposed[key], ensure_ascii=False, allow_nan=False)))
                    current[key] = proposed[key]
                else:
                    conn.execute("DELETE FROM knowledge WHERE id=?", (key,))
                    current.pop(key, None)
            metadata["total_items"] = len(current)
            metadata["objects_count"] = sum(row["type"] == "object" for row in current.values())
            metadata["facts_count"] = sum(row["type"] == "fact" for row in current.values())
            conn.execute("INSERT INTO metadata VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET record=excluded.record",
                         (json.dumps(metadata, allow_nan=False),))
            return current

    def backup(self, destination):
        with closing(sqlite3.connect(self.database)) as source, closing(sqlite3.connect(destination)) as target:
            source.backup(target)
