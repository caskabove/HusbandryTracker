"""Adds UVB Index as a Sensor Target Range metric (see db/schema.sql,
schemas/enclosure_types.py's TARGET_RANGE_METRICS, CONTEXT.md: Target Range) — UV Index, not raw
uW/cm^2 irradiance, matching what a consumer meter (e.g. Solarmeter 6.5R) displays directly and the
Ferguson-zone target ranges most reptile keepers already think in. Offered on Basic and Amphibian
Enclosure Types only (a Freshwater/Saltwater tank has no basking area).

Adds `sensor.target_uvb_index_min/max` and `sensor_reading.uvb_index`. Purely additive: both new
columns are nullable, so every existing row is untouched.

Ported verbatim from tools/migrate_2026_09_22_uvb_index.py (RHA-101; see db/migrate.py, ADR 0059).
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH

NEW_SENSOR_COLUMNS = ["target_uvb_index_min", "target_uvb_index_max"]
NEW_READING_COLUMNS = ["uvb_index"]


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


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
