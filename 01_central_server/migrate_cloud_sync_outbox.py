"""Idempotently add the Phase 7 conversation outbox schema."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sqlite3

from sqlite_store import DATABASE, initialize


OUTBOX_COLUMNS: dict[str, str] = {
    "synced": "INTEGER NOT NULL DEFAULT 0 CHECK (synced IN (0, 1))",
    "batch_id": "TEXT",
    "sync_attempted_at": "TEXT",
    "sync_succeeded_at": "TEXT",
}


def migrate_outbox(database: Path | str = DATABASE) -> dict[str, object]:
    database = Path(database)
    initialize(database)
    with sqlite3.connect(database) as connection:
        before = int(connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0])
        existing = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(conversations)")
        }
        added: list[str] = []
        for name, declaration in OUTBOX_COLUMNS.items():
            if name not in existing:
                connection.execute(
                    f"ALTER TABLE conversations ADD COLUMN {name} {declaration}"
                )
                added.append(name)
        connection.execute(
            """CREATE TABLE IF NOT EXISTS sync_state (
                   key TEXT PRIMARY KEY,
                   value TEXT NOT NULL
               )"""
        )
        after = int(connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0])
        columns = [
            str(row[1]) for row in connection.execute("PRAGMA table_info(conversations)")
        ]
    result = {
        "before": before,
        "after": after,
        "parity": before == after,
        "added": added,
        "columns": columns,
    }
    print(
        f"conversations: before={before} after={after} parity={before == after} "
        f"added={','.join(added) if added else 'none'}"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DATABASE)
    args = parser.parse_args()
    migrate_outbox(args.database)
