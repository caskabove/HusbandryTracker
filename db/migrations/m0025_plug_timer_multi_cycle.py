"""Adds plug.target_on_time_2/target_off_time_2 and
plug.target_on_time_3/target_off_time_3 (see db/schema.sql, CONTEXT.md: Target Schedule) — up to 2
extra on/off cycles alongside the existing cycle 1 (target_on_time/target_off_time). All 4 start
NULL, meaning "cycle not configured", so existing rows need no backfill.

Ported verbatim from tools/migrate_2026_11_04_plug_timer_multi_cycle.py (RHA-101; see db/migrate.py, ADR 0059).
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH

NEW_COLUMNS = ["target_on_time_2", "target_off_time_2", "target_on_time_3", "target_off_time_3"]


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def migrate(conn: sqlite3.Connection) -> None:
    existing = _existing_columns(conn, "plug")
    added = []
    for column in NEW_COLUMNS:
        if column in existing:
            print(f"  [skip] plug.{column} already exists")
            continue
        conn.execute(f"ALTER TABLE plug ADD COLUMN {column} TEXT")
        added.append(column)
    if added:
        print(f"  [done] plug.{', '.join(added)}")

    conn.executescript(SCHEMA_PATH.read_text())  # CREATE TABLE/INDEX IF NOT EXISTS — no-op here, safe
