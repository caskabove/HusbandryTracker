"""Adds the TDS (Total Dissolved Solids) Target Range metric (see ADR 0060; RHA-115):
`sensor.target_tds_ppm_min/max`, `sensor.volatility_tds`, and `sensor_reading.tds_ppm`.

Purely additive — every new column is nullable, so existing rows are untouched. The same change
retired Ammonia/Nitrite, but only in code (schemas/enclosure_types.py's
RETIRED_TARGET_RANGE_METRICS): their columns are deliberately left in place, so nothing here drops
or rewrites them.
"""
from __future__ import annotations

import sqlite3

NEW_COLUMNS = [
    ("sensor", "target_tds_ppm_min", "target_tds_ppm_min REAL"),
    ("sensor", "target_tds_ppm_max", "target_tds_ppm_max REAL"),
    ("sensor", "volatility_tds",
     "volatility_tds TEXT CHECK (volatility_tds IS NULL OR volatility_tds IN ('fast', 'slow'))"),
    ("sensor_reading", "tds_ppm", "tds_ppm REAL"),
]


def migrate(conn: sqlite3.Connection) -> None:
    for table, column, ddl in NEW_COLUMNS:
        if column in {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}:
            print(f"  [skip] {table}.{column} already exists")
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
        print(f"  [done] {table}.{column}")
