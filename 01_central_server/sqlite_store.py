"""Transactional storage preserving the existing JSON record shapes and order."""

from contextlib import contextmanager, closing
from contextvars import ContextVar
from functools import wraps
import json
import os
from pathlib import Path
import sqlite3
from shared.secure_storage import ENCRYPTED_PREFIX, RotatingFernet


DATABASE = Path(os.getenv("CENTRAL_DB_PATH", str(Path(__file__).parent / "data" / "central.sqlite3")))
_connection = ContextVar("central_store_connection", default=None)


def _encode_record(table, record):
    raw = json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return RotatingFernet().encrypt_text(raw) if table == "users" else raw


def _decode_record(table, raw):
    if table == "users":
        if not raw.encode("ascii", errors="ignore").startswith(ENCRYPTED_PREFIX):
            raise RuntimeError("Plaintext biometric user record rejected; run ensure_users_encrypted")
        raw = RotatingFernet().decrypt_text(raw)
    return json.loads(raw)


def ensure_users_encrypted(database=DATABASE):
    """Idempotently encrypt legacy plaintext user rows in one transaction."""
    cipher = RotatingFernet()
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("PRAGMA secure_delete=ON")
        rows = list(conn.execute("SELECT position, record FROM users"))
        migrated = 0
        for position, raw in rows:
            if raw.encode("ascii", errors="ignore").startswith(ENCRYPTED_PREFIX):
                # Also proves the configured current/previous key can read it.
                plaintext = cipher.decrypt_text(raw)
                if cipher.is_current(raw.encode("ascii")):
                    continue
                conn.execute("UPDATE users SET record=? WHERE position=?", (cipher.encrypt_text(plaintext), position))
                migrated += 1
                continue
            json.loads(raw)
            conn.execute("UPDATE users SET record=? WHERE position=?", (cipher.encrypt_text(raw), position))
            migrated += 1
    if migrated:
        with closing(sqlite3.connect(database)) as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.execute("VACUUM")
    return {"examined": len(rows), "encrypted": migrated, "unchanged": len(rows) - migrated}


def initialize(database=DATABASE):
    database = Path(database)
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (position INTEGER PRIMARY KEY, record TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS conversations (position INTEGER PRIMARY KEY, record TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS migration (source TEXT PRIMARY KEY, digest TEXT NOT NULL);
        """)


def connect():
    if not DATABASE.exists():
        raise RuntimeError("Central SQLite store missing; run migrate_sqlite.py before startup")
    conn = sqlite3.connect(DATABASE, timeout=30, check_same_thread=False)
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA secure_delete=ON")
    return conn


@contextmanager
def transaction():
    if _connection.get() is not None:
        yield _connection.get()
        return
    conn = connect()
    token = _connection.set(conn)
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        _connection.reset(token)
        conn.close()


def transactional(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with transaction():
            return function(*args, **kwargs)
    return wrapped


def read_records(table, connection=None):
    if table not in ("users", "conversations"):
        raise ValueError("Unknown collection")
    conn = connection or _connection.get()
    if conn is None:
        with transaction() as conn:
            return read_records(table, conn)
    return [_decode_record(table, row[0]) for row in conn.execute(f"SELECT record FROM {table} ORDER BY position")]


def write_records(table, records, connection=None):
    if table not in ("users", "conversations"):
        raise ValueError("Unknown collection")
    encoded = [_encode_record(table, record) for record in records]
    conn = connection or _connection.get()
    if conn is None:
        with transaction() as conn:
            return write_records(table, records, conn)
    if table != "conversations":
        conn.execute(f"DELETE FROM {table}")
        conn.executemany(
            f"INSERT INTO {table} (position, record) VALUES (?, ?)", enumerate(encoded)
        )
        return

    columns = {row[1] for row in conn.execute("PRAGMA table_info(conversations)")}
    if "synced" not in columns:
        conn.execute("DELETE FROM conversations")
        conn.executemany(
            "INSERT INTO conversations (position, record) VALUES (?, ?)", enumerate(encoded)
        )
        return

    # Keep outbox state by stable conversation_id across the established
    # full-list persistence rewrite.
    previous = {}
    for row in conn.execute(
        """SELECT record, synced, batch_id, sync_attempted_at, sync_succeeded_at
           FROM conversations"""
    ):
        conversation_id = json.loads(row[0]).get("conversation_id")
        if conversation_id:
            previous[conversation_id] = tuple(row[1:])
    conn.execute("DELETE FROM conversations")
    values = []
    for position, (record, raw) in enumerate(zip(records, encoded)):
        state = previous.get(record.get("conversation_id"), (0, None, None, None))
        values.append((position, raw, *state))
    conn.executemany(
        """INSERT INTO conversations
           (position, record, synced, batch_id, sync_attempted_at, sync_succeeded_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        values,
    )
