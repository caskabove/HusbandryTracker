"""One-off migration: adds UVB Index as a Sensor Target Range metric (see db/schema.sql,
schemas/enclosure_types.py's TARGET_RANGE_METRICS, CONTEXT.md: Target Range) — UV Index, not raw
uW/cm^2 irradiance, matching what a consumer meter (e.g. Solarmeter 6.5R) displays directly and the
Ferguson-zone target ranges most reptile keepers already think in. Offered on Basic and Amphibian
Enclosure Types only (a Freshwater/Saltwater tank has no basking area).

Adds `sensor.target_uvb_index_min/max` and `sensor_reading.uvb_index`. Purely additive: both new
columns are nullable, so every existing row is untouched.

Same idempotent, re-runnable, self-backing-up pattern as every other tools/migrate_* script.

Run: .venv/Scripts/python.exe tools/migrate_2026_09_22_uvb_index.py
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.db import DB_PATH, SCHEMA_PATH

NEW_SENSOR_COLUMNS = ["target_uvb_index_min", "target_uvb_index_max"]
NEW_READING_COLUMNS = ["uvb_index"]


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def backup_db() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = DB_PATH.with_name(f"{DB_PATH.name}.bak-{stamp}")
    shutil.copy2(DB_PATH, backup_path)
    print(f"Backed up {DB_PATH} -> {backup_path}")
    return backup_path


def _add_columns(conn: sqlite3.Connection, table: str, columns: list[str]) -> None:
    existing = _existing_columns(conn, table)
    added = []
    for column in columns:
        if column in existing:
            print(f"  [skip] {table}.{column} already exists")
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} REAL")
        added.append(column)
    if added:
        print(f"  [done] {table}.{', '.join(added)}")


def migrate(conn: sqlite3.Connection) -> None:
    _add_columns(conn, "sensor", NEW_SENSOR_COLUMNS)
    _add_columns(conn, "sensor_reading", NEW_READING_COLUMNS)
    conn.executescript(SCHEMA_PATH.read_text())  # CREATE TABLE/INDEX IF NOT EXISTS — no-op here, safe


def main() -> None:
    if not DB_PATH.exists():
        print(f"No existing database at {DB_PATH} — nothing to migrate.")
        return
    backup_db()
    conn = sqlite3.connect(DB_PATH)
    try:
        with conn:
            migrate(conn)
    finally:
        conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    main()
