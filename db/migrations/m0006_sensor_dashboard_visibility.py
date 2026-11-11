"""Adds sensor.show_on_dashboard (see db/schema.sql, CONTEXT.md: Sensor) —
per-Sensor opt-in for whether its Reading shows on the Dashboard (an Enclosure panel's Temp/
Humidity section, or a Room's ambient strip). Same idea as
tools/migrate_2026_09_13_animal_dashboard_visibility.py's animal.show_on_dashboard — see that
file's module docstring for the full reasoning; this one just applies it to `sensor`, scoped per
parent (enclosure_id or room_id, whichever the row has — see CONTEXT.md: Sensor) instead of always
enclosure_id.

Ported verbatim from tools/migrate_2026_09_13_sensor_dashboard_visibility.py (RHA-101; see db/migrate.py, ADR 0059).
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _backfill_top_3(conn: sqlite3.Connection, parent_column: str) -> None:
    parent_ids = [row[0] for row in conn.execute(
        f"SELECT {parent_column} FROM sensor WHERE {parent_column} IS NOT NULL "
        f"GROUP BY {parent_column} HAVING COUNT(*) > 3"
    )]
    backfilled = 0
    for parent_id in parent_ids:
        keep_ids = [row[0] for row in conn.execute(
            f"SELECT id FROM sensor WHERE {parent_column} = ? ORDER BY id LIMIT 3", (parent_id,)
        )]
        placeholders = ",".join("?" * len(keep_ids))
        cur = conn.execute(
            f"UPDATE sensor SET show_on_dashboard = 0 "
            f"WHERE {parent_column} = ? AND id NOT IN ({placeholders})",
            (parent_id, *keep_ids),
        )
        backfilled += cur.rowcount
    if parent_ids:
        print(f"  [done] defaulted {backfilled} Sensor(s) past the first 3 in "
              f"{len(parent_ids)} {parent_column.replace('_id', '')}(s) to hidden on the Dashboard")


def migrate(conn: sqlite3.Connection) -> None:
    added = "show_on_dashboard" not in _existing_columns(conn, "sensor")
    if added:
        conn.execute("ALTER TABLE sensor ADD COLUMN show_on_dashboard INTEGER NOT NULL DEFAULT 1")
        print("  [done] sensor.show_on_dashboard")
    else:
        print("  [skip] sensor.show_on_dashboard already exists")

    if added:
        _backfill_top_3(conn, "enclosure_id")
        _backfill_top_3(conn, "room_id")

    conn.executescript(SCHEMA_PATH.read_text())  # CREATE TABLE/INDEX IF NOT EXISTS — no-op here, safe
