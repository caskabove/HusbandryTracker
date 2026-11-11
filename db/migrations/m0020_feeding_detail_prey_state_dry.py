"""Widens feeding_detail.prey_state's CHECK constraint to allow 'dry' alongside
'live'/'frozen_thawed' (see db/schema.sql, CONTEXT.md: Feeding Detail, Log Feeding Dialog; ADR
0042, ADR 0043) — covers pelleted/flake food, distinct from live or frozen-thawed prey.

SQLite can't ALTER a CHECK constraint in place, so this rebuilds the table following the same
documented procedure tools/migrate_2026_10_29_plug_timer_controller_kind.py already used: disable
foreign key enforcement, create feeding_detail_new with the widened CHECK (otherwise byte-for-byte
identical to the live schema), copy every row across unchanged, drop the old table, rename
feeding_detail_new to feeding_detail, verify no foreign key is left dangling, then re-enable
enforcement. No index/trigger/view is defined on feeding_detail itself (confirmed against
db/schema.sql), so nothing else needs recreating.

No backfill: every existing feeding_detail row keeps its current prey_state untouched ('dry' is
only ever chosen going forward, from the Log Feeding Dialog this same change introduces).

Ported verbatim from tools/migrate_2026_10_30_feeding_detail_prey_state_dry.py (RHA-101; see db/migrate.py, ADR 0059).
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH

_NEW_FEEDING_DETAIL_TABLE_SQL = """
CREATE TABLE feeding_detail_new (
    id            INTEGER PRIMARY KEY,
    care_event_id INTEGER NOT NULL UNIQUE REFERENCES care_event(id) ON DELETE CASCADE,
    food          TEXT,
    count         INTEGER,
    prey_state    TEXT CHECK (prey_state IN ('live', 'frozen_thawed', 'dry')),
    result        TEXT NOT NULL DEFAULT 'accepted' CHECK (result IN ('accepted', 'refused'))
)
"""

_FEEDING_DETAIL_COLUMNS = "id, care_event_id, food, count, prey_state, result"


def _already_widened(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'feeding_detail'"
    ).fetchone()
    return row is not None and "prey_state IN ('live', 'frozen_thawed', 'dry')" in row[0]


def migrate(conn: sqlite3.Connection) -> None:
    if _already_widened(conn):
        print("  [skip] feeding_detail.prey_state's CHECK already allows 'dry'")
        return

    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(_NEW_FEEDING_DETAIL_TABLE_SQL)
    conn.execute(
        f"INSERT INTO feeding_detail_new ({_FEEDING_DETAIL_COLUMNS}) "
        f"SELECT {_FEEDING_DETAIL_COLUMNS} FROM feeding_detail"
    )
    conn.execute("DROP TABLE feeding_detail")
    conn.execute("ALTER TABLE feeding_detail_new RENAME TO feeding_detail")
    dangling = conn.execute("PRAGMA foreign_key_check").fetchall()
    if dangling:
        raise RuntimeError(f"Rebuild left dangling foreign keys, aborting: {dangling!r}")
    print("  [done] feeding_detail.prey_state CHECK widened to allow 'dry'")
