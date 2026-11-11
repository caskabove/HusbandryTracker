"""Adds Volatility overrides and the Interpolation Gap Cap setting (see
db/schema.sql, CONTEXT.md: Volatility, Interpolated Point; ADR 0025).

Adds `sensor.volatility_<metric>` (one nullable TEXT column per schemas/enclosure_types.py's
TARGET_RANGE_METRICS, NULL meaning "use that metric's own default_volatility") and
`app_setting.interpolation_gap_cap_hours` (INTEGER, default 48). Purely additive: every existing
row is untouched. The CHECK constraints schema.sql declares on the new sensor columns aren't
re-added here — SQLite's ALTER TABLE ADD COLUMN can't add them to an existing table either, same
asymmetry as every other tools/migrate_* script's new columns (e.g. plug.timer_ack_on_time);
schema.sql stays the authoritative, fully-constrained definition for a fresh install.

Ported verbatim from tools/migrate_2026_10_16_volatility_and_interpolation_gap_cap.py (RHA-101; see db/migrate.py, ADR 0059).
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH

NEW_SENSOR_COLUMNS = [
    "volatility_temperature", "volatility_humidity", "volatility_uvb", "volatility_ph",
    "volatility_ammonia", "volatility_nitrite", "volatility_nitrate", "volatility_specific_gravity",
    "volatility_salinity", "volatility_alkalinity", "volatility_calcium", "volatility_magnesium",
    "volatility_phosphate",
]


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_columns(conn: sqlite3.Connection, table: str, columns: list[str], sql_type: str) -> None:
    existing = _existing_columns(conn, table)
    added = []
    for column in columns:
        if column in existing:
            print(f"  [skip] {table}.{column} already exists")
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")
        added.append(column)
    if added:
        print(f"  [done] {table}.{', '.join(added)}")


def migrate(conn: sqlite3.Connection) -> None:
    _add_columns(conn, "sensor", NEW_SENSOR_COLUMNS, "TEXT")
    _add_columns(conn, "app_setting", ["interpolation_gap_cap_hours"], "INTEGER NOT NULL DEFAULT 48")
    conn.executescript(SCHEMA_PATH.read_text())  # CREATE TABLE/INDEX IF NOT EXISTS — no-op here, safe
