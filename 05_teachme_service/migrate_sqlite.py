"""Strict, idempotent migration of TeachMe's existing knowledge document."""

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from teachme_service.sqlite_store import initialize
from teachme_service.models import KnowledgeItem, ObjectData, FactData
from shared.semantic_embeddings import (
    SEMANTIC_EMBEDDING_DIMENSION,
    embed_text,
    knowledge_text,
)


def migrate(source, database):
    raw = source.read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict) or set(data) != {"storage", "metadata"}:
        raise ValueError("Unexpected knowledge document schema; migration stopped")
    if not isinstance(data["storage"], dict) or not isinstance(data["metadata"], dict):
        raise ValueError("Unexpected storage/metadata type; migration stopped")
    allowed_metadata = {"created_at", "last_saved", "version", "total_items", "objects_count", "facts_count"}
    if set(data["metadata"]) - allowed_metadata:
        raise ValueError("Unknown metadata fields; migration stopped")
    for key, value in data["metadata"].items():
        expected = int if key.endswith("count") or key == "total_items" else str
        if type(value) is not expected:
            raise ValueError(f"Invalid metadata type: {key}; migration stopped")
    for key, record in data["storage"].items():
        if not isinstance(record, dict) or set(record) - set(KnowledgeItem.model_fields):
            raise ValueError(f"Unknown knowledge fields for {key}; migration stopped")
        model = ObjectData if record.get("type") == "object" else FactData
        if not isinstance(record.get("data"), dict) or set(record["data"]) - set(model.model_fields):
            raise ValueError(f"Unknown nested knowledge fields for {key}; migration stopped")
        validated = KnowledgeItem.model_validate_json(json.dumps(record), strict=True)
        if validated.id != key:
            raise ValueError(f"Knowledge key/id mismatch for {key}; migration stopped")
    if data["metadata"].get("total_items", len(data["storage"])) != len(data["storage"]):
        raise ValueError("Knowledge metadata count mismatch; migration stopped")
    json.dumps(data, allow_nan=False)
    digest = hashlib.sha256(raw).hexdigest()
    initialize(database)
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        previous = conn.execute("SELECT digest FROM migration WHERE source='knowledge'").fetchone()
        if previous:
            if previous[0] != digest:
                raise ValueError("Source changed after migration; refusing overwrite")
        else:
            if conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]:
                raise ValueError("Destination is not empty; refusing overwrite")
            conn.executemany("INSERT INTO knowledge VALUES (?, ?)",
                             ((key, json.dumps(record, ensure_ascii=False, allow_nan=False)) for key, record in data["storage"].items()))
            conn.execute("INSERT INTO metadata VALUES (1, ?)", (json.dumps(data["metadata"]),))
            conn.execute("INSERT INTO migration VALUES ('knowledge', ?)", (digest,))
        stored = {key: json.loads(record) for key, record in conn.execute("SELECT id, record FROM knowledge")}
        stored_metadata = json.loads(conn.execute("SELECT record FROM metadata WHERE id=1").fetchone()[0])
        print(f"knowledge: JSON={len(data['storage'])} SQLite={len(stored)} action={'unchanged' if previous else 'imported'} parity={stored == data['storage']} metadata_parity={stored_metadata == data['metadata']}")


def export(database, destination):
    from teachme_service.sqlite_store import KnowledgeStore
    data = KnowledgeStore(database).read()
    with destination.open("x", encoding="utf-8") as output:
        json.dump(data, output, ensure_ascii=False, allow_nan=False)
    print(f"EXPORTED knowledge={len(data['storage'])}")


def reembed(database):
    """Idempotently replace missing/legacy vectors with configured semantic vectors."""
    initialize(database)
    examined = updated = 0
    with closing(sqlite3.connect(database, timeout=30)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = list(conn.execute("SELECT id, record FROM knowledge ORDER BY rowid"))
        for item_id, raw_record in rows:
            record = json.loads(raw_record)
            KnowledgeItem.model_validate(record)
            examined += 1
            vector = embed_text(knowledge_text(record["type"], record["data"]))
            existing = record.get("embedding")
            if existing is not None and len(existing) == SEMANTIC_EMBEDDING_DIMENSION and existing == vector:
                continue
            record["embedding"] = vector
            conn.execute(
                "UPDATE knowledge SET record=? WHERE id=?",
                (json.dumps(record, ensure_ascii=False, allow_nan=False), item_id),
            )
            updated += 1
    print(
        f"REEMBED examined={examined} updated={updated} unchanged={examined - updated} "
        f"dimension={SEMANTIC_EMBEDDING_DIMENSION}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).parent / "knowledge_data.json")
    parser.add_argument("--database", type=Path)
    parser.add_argument("--export", type=Path)
    parser.add_argument("--reembed", action="store_true")
    args = parser.parse_args()
    database = args.database or args.source.with_suffix(".sqlite3")
    if args.reembed:
        reembed(database)
    elif args.export:
        export(database, args.export)
    else:
        migrate(args.source, database)
