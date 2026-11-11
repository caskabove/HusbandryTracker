"""Adds `room.sort_order` (see db/schema.sql, CONTEXT.md: Room) — lets the
dashboard's Rooms be dragged up/down into a user-chosen display order instead of always sorting
alphabetically by name.

Backfills every existing Room's sort_order to its current alphabetical rank, so nothing visibly
reorders itself the moment this migration runs — the new column just makes that existing order
editable going forward. Same idempotent, re-runnable, self-backing-up pattern as every other
tools/migrate_* script.

Ported verbatim from tools/migrate_2026_11_01_room_sort_order.py (RHA-101; see db/migrate.py, ADR 0059).
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def migrate(conn: sqlite3.Connection) -> None:
    if "sort_order" in _existing_columns(conn, "room"):
        print("  [skip] room.sort_order already exists")
    else:
        conn.execute("ALTER TABLE room ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
        room_ids = [row[0] for row in conn.execute("SELECT id FROM room ORDER BY name")]
        conn.executemany(
            "UPDATE room SET sort_order = ? WHERE id = ?",
            [(order, room_id) for order, room_id in enumerate(room_ids)],
        )
        print(f"  [done] room.sort_order (backfilled {len(room_ids)} row(s) by current name order)")
    conn.executescript(SCHEMA_PATH.read_text())  # CREATE TABLE/INDEX IF NOT EXISTS — no-op here, safe
