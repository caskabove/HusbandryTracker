"""Splits Salinity into two separate Target Range metrics — Specific Gravity
(unitless, e.g. 1.026) and Salinity in ppm (e.g. 35) — matching how a hydrometer/refractometer and
a salinity probe actually report readings side by side (see db/schema.sql, CONTEXT.md: Target
Range; schemas/enclosure_types.py's TARGET_RANGE_METRICS).

Adds `sensor.target_specific_gravity_min/max` and `sensor.target_salinity_ppm_min/max`, plus
`sensor_reading.specific_gravity` and `sensor_reading.salinity_ppm`. The old
`target_salinity_ppt_min/max`/`salinity_ppt` columns (parts-per-thousand) are left in place,
untouched and now unused — dropping a SQLite column means rebuilding the table, not worth it for
columns that just go quiet. Purely additive otherwise: every new column is nullable, so existing
rows are untouched and any old ppt values simply stop being read by the app.

Ported verbatim from tools/migrate_2026_09_20_salinity_specific_gravity.py (RHA-101; see db/migrate.py, ADR 0059).
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH

NEW_SENSOR_COLUMNS = [
    "target_specific_gravity_min", "target_specific_gravity_max",
    "target_salinity_ppm_min", "target_salinity_ppm_max",
]
NEW_READING_COLUMNS = ["specific_gravity", "salinity_ppm"]


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
