"""Adds the water-chemistry Reading columns to sensor_reading (see
db/schema.sql, CONTEXT.md: Reading; ADR 0011) — ph, ammonia_ppm, nitrite_ppm, nitrate_ppm,
salinity_ppt, alkalinity_dkh, calcium_ppm, magnesium_ppm, phosphate_ppm.

`sensor` (the Target Range side) has carried these 9 metrics since ADR 0011 — this was the
explicitly deferred other half (see ingest/alerts.py's old module docstring, and
schemas/enclosure_types.py's TARGET_RANGE_METRICS.reading_column): a Manual Sensor tracking, say,
pH had somewhere to configure a Target Range but nowhere to log an actual Reading against it until
now.

Purely additive — every new column is nullable, so existing rows (all Smart Sensor
temperature_c/humidity_pct/battery_pct data, and any prior Manual Sensor temp/humidity Readings)
are untouched.

Ported verbatim from tools/migrate_2026_09_14_sensor_reading_metrics.py (RHA-101; see db/migrate.py, ADR 0059).
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH

NEW_COLUMNS = [
    "ph", "ammonia_ppm", "nitrite_ppm", "nitrate_ppm",
    "salinity_ppt", "alkalinity_dkh", "calcium_ppm", "magnesium_ppm", "phosphate_ppm",
]


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def migrate(conn: sqlite3.Connection) -> None:
    existing = _existing_columns(conn, "sensor_reading")
    added = []
    for column in NEW_COLUMNS:
        if column in existing:
            print(f"  [skip] sensor_reading.{column} already exists")
            continue
        conn.execute(f"ALTER TABLE sensor_reading ADD COLUMN {column} REAL")
        added.append(column)
    if added:
        print(f"  [done] sensor_reading.{', '.join(added)}")

    conn.executescript(SCHEMA_PATH.read_text())  # CREATE TABLE/INDEX IF NOT EXISTS — no-op here, safe
