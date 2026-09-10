"""Idempotent JSON import and non-overwriting rollback export for Central."""

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from sqlite_store import DATABASE, initialize


def migrate(source_dir, database, allow_missing_users=False):
    sources = {}
    for table in ("users", "conversations"):
        path = source_dir / (table + ".json")
        if table == "users" and not path.exists() and allow_missing_users:
            raw = b"[]"
        else:
            raw = path.read_bytes()
        data = json.loads(raw)
        if table == "conversations":
            if not isinstance(data, dict) or set(data) != {"conversations"}:
                raise ValueError("Unexpected conversations document schema; no migration performed")
            data = data[table]
        if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
            raise ValueError(f"Unexpected {table} records; no migration performed")
        for index, record in enumerate(data):
            if table == "users":
                allowed = {"name", "user_name", "user_id", "email", "age", "relation", "has_voice", "has_face",
                           "enrollment_timestamp", "last_updated", "audio_samples", "voice_embedding",
                           "voice_embeddings", "face_embeddings", "speaker_enrollment", "face_confidences",
                           "voice_qualities", "status", "total_voice_embeddings", "total_face_embeddings",
                           "num_voice_samples", "embedding_size", "avg_face_confidence", "avg_voice_quality",
                           "sample_count"}
                if set(record) - allowed:
                    raise ValueError(f"users[{index}]: unknown fields {sorted(set(record) - allowed)}; migration stopped")
                if not isinstance(record.get("name"), str) or not record["name"]:
                    raise ValueError(f"users[{index}]: invalid name; migration stopped")
                for key in ("voice_embeddings", "face_embeddings", "face_confidences", "voice_qualities", "audio_samples"):
                    if key in record and not isinstance(record[key], list):
                        raise ValueError(f"users[{index}]: invalid {key} type; migration stopped")
                for key, value in record.items():
                    if key in {"has_voice", "has_face"} and type(value) is not bool:
                        raise ValueError(f"users[{index}]: invalid {key} type; migration stopped")
                    if key in {"total_voice_embeddings", "total_face_embeddings", "num_voice_samples", "embedding_size"} and type(value) is not int:
                        raise ValueError(f"users[{index}]: invalid {key} type; migration stopped")
                    if key in {"speaker_enrollment", "sample_count"} and not isinstance(value, dict):
                        raise ValueError(f"users[{index}]: invalid {key} type; migration stopped")
                    if key in {"name", "user_name", "user_id", "email", "relation", "enrollment_timestamp", "last_updated", "status"} and value is not None and not isinstance(value, str):
                        raise ValueError(f"users[{index}]: invalid {key} type; migration stopped")
                    if key == "age" and value is not None and type(value) not in (int, str):
                        raise ValueError(f"users[{index}]: invalid age type; migration stopped")
                    if key in {"avg_face_confidence", "avg_voice_quality"} and value is not None and type(value) not in (int, float):
                        raise ValueError(f"users[{index}]: invalid {key} type; migration stopped")
            else:
                expected = {"conversation_id", "user_id", "timestamp", "user_message",
                            "assistant_response", "mood", "language", "metadata"}
                if set(record) != expected or not isinstance(record["metadata"], dict):
                    raise ValueError(f"conversations[{index}]: unexpected schema; migration stopped")
                if any(not isinstance(record[key], str) for key in expected - {"metadata", "language"}):
                    raise ValueError(f"conversations[{index}]: unexpected type; migration stopped")
                if record["language"] is not None and not isinstance(record["language"], str):
                    raise ValueError(f"conversations[{index}]: invalid language; migration stopped")
            json.dumps(record, allow_nan=False)
        sources[table] = (data, hashlib.sha256(raw).hexdigest())
    initialize(database)
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        for table, (data, digest) in sources.items():
            previous = conn.execute("SELECT digest FROM migration WHERE source=?", (table,)).fetchone()
            if previous:
                if previous[0] != digest:
                    raise ValueError(f"{table}: source changed after migration; refusing overwrite")
            else:
                if conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]:
                    raise ValueError(f"{table}: destination is not empty; refusing overwrite")
                conn.executemany(f"INSERT INTO {table} VALUES (?, ?)",
                                 ((i, json.dumps(row, ensure_ascii=False, allow_nan=False)) for i, row in enumerate(data)))
                conn.execute("INSERT INTO migration VALUES (?, ?)", (table, digest))
            stored = [json.loads(row[0]) for row in conn.execute(f"SELECT record FROM {table} ORDER BY position")]
            print(f"{table}: JSON={len(data)} SQLite={len(stored)} action={'unchanged' if previous else 'imported'} parity={stored == data}")


def export(database, destination):
    destination.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)) as conn:
        for table in ("users", "conversations"):
            rows = [json.loads(row[0]) for row in conn.execute(f"SELECT record FROM {table} ORDER BY position")]
            data = rows if table == "users" else {table: rows}
            with (destination / (table + ".json")).open("x", encoding="utf-8") as output:
                json.dump(data, output, ensure_ascii=False, allow_nan=False)
            print(f"EXPORTED {table}={len(rows)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path(__file__).parent / "data")
    parser.add_argument("--database", type=Path, default=DATABASE)
    parser.add_argument("--allow-missing-users", action="store_true")
    parser.add_argument("--export-dir", type=Path)
    args = parser.parse_args()
    if args.export_dir:
        export(args.database, args.export_dir)
    else:
        migrate(args.source_dir, args.database, args.allow_missing_users)
