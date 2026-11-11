"""Adds enclosure.show_feeding_on_dashboard / show_watering_on_dashboard /
show_spot_clean_on_dashboard / show_deep_clean_on_dashboard (see db/schema.sql, CONTEXT.md: Care
Interval) — per-Care-kind opt-in for whether that kind's pill shows on the Dashboard's Enclosure
panel, same pattern as animal/sensor/plug.show_on_dashboard.

Unlike those three, there's no "top N by default" backfill needed here — a fixed 4 Care kinds per
Enclosure is never enough to warrant hiding any by default, so every column just defaults to 1
(shown) and stays there for existing rows.

Ported verbatim from tools/migrate_2026_09_26_care_dashboard_visibility.py (RHA-101; see db/migrate.py, ADR 0059).
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH

NEW_COLUMNS = [
    "show_feeding_on_dashboard", "show_watering_on_dashboard",
    "show_spot_clean_on_dashboard", "show_deep_clean_on_dashboard",
]


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def migrate(conn: sqlite3.Connection) -> None:
    existing = _existing_columns(conn, "enclosure")
    added = []
    for column in NEW_COLUMNS:
        if column in existing:
            print(f"  [skip] enclosure.{column} already exists")
            continue
        conn.execute(f"ALTER TABLE enclosure ADD COLUMN {column} INTEGER NOT NULL DEFAULT 1")
        added.append(column)
    if added:
        print(f"  [done] enclosure.{', '.join(added)}")

    conn.executescript(SCHEMA_PATH.read_text())  # CREATE TABLE/INDEX IF NOT EXISTS — no-op here, safe
