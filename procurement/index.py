"""Transactionally index versioned UK procurement notices in SQLite."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

SCHEMA = """
PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS release(
    ocid TEXT NOT NULL, id TEXT NOT NULL, published TEXT NOT NULL,
    tags TEXT NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL,
    PRIMARY KEY(ocid, id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS by_time ON release(ocid, published DESC, id DESC);
CREATE TABLE IF NOT EXISTS page(hash TEXT PRIMARY KEY, digest TEXT NOT NULL) WITHOUT ROWID;
"""


def connect(path):
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    return db


def stamp(value):
    value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        raise ValueError("An offset is required")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def apply_page(db, data, *, replay=False):
    rows = data["page"]["releases"]
    page_id = hashlib.sha256(data["source"].encode()).hexdigest()
    page_digest = hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    with db:
        existing = db.execute("SELECT digest FROM page WHERE hash=?", (page_id,)).fetchone()
        if existing is not None:
            if existing[0] != page_digest:
                raise ValueError("Cached page content changed under the same cursor")
            if not replay:
                return False
        for row in rows:
            core = {key: row[key] for key in ("ocid", "id", "date", "tag")}
            payload = json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            digest = hashlib.sha256(payload.encode()).hexdigest()
            db.execute("INSERT INTO release VALUES (?,?,?,?,?,?) ON CONFLICT(ocid,id) DO NOTHING",
                       (row["ocid"], row["id"], stamp(row["date"]), json.dumps(row["tag"]), payload, digest))
            old, = db.execute("SELECT digest FROM release WHERE ocid=? AND id=?",
                              (row["ocid"], row["id"])).fetchone()
            if old != digest:
                raise ValueError("Release ID reused with changed content")
        db.execute("INSERT INTO page VALUES (?,?) ON CONFLICT DO NOTHING", (page_id, page_digest))
        return True


def load(db, files, *, replay=False):
    applied = 0
    for file in files:
        applied += apply_page(db, json.loads(file.read_text()), replay=replay)
    return applied


def state(db):
    digest = hashlib.sha256()
    count = 0
    for row in db.execute("SELECT ocid,id,digest FROM release ORDER BY ocid,id"):
        digest.update(json.dumps(row).encode())
        count += 1
    return count, digest.hexdigest()


def history(db, ocid, before):
    return [json.loads(row[0]) for row in db.execute(
        "SELECT payload FROM release WHERE ocid=? AND published <= ? ORDER BY published,id",
        (ocid, stamp(before)))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/tender_index"))
    parser.add_argument("--db", type=Path, default=Path("results/notices.sqlite3"))
    parser.add_argument("--as-of", nargs=2, metavar=("OCID", "TIMESTAMP"))
    args = parser.parse_args()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    db = connect(args.db)
    try:
        if args.as_of:
            print(json.dumps(history(db, *args.as_of), indent=2))
        else:
            files = sorted(args.data.glob("[0-9][0-9][0-9][0-9].json"))
            if not files:
                parser.error("No cached pages found in the data directory")
            applied = load(db, files)
            count, digest = state(db)
            print(f"Imported {applied} pages; {count:,} releases; SHA-256 {digest}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
