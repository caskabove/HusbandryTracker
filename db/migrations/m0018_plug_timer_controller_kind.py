"""Widens plug.controller_kind's CHECK constraint to allow 'timer' alongside
'none'/'thermostat'/'hydrostat' (see db/schema.sql, CONTEXT.md: Controller Kind, Timer-Controlled;
RHA-95) — a third, non-'none' Controller Kind whose whole point IS a Target Schedule (on/off
time), which 'none' no longer carries at all now that it's split out (see RHA-95's own
accompanying code changes in web/admin_queries.py).

SQLite can't ALTER a CHECK constraint in place, so this rebuilds the table following SQLite's own
documented procedure for "other kinds of table schema changes": disable foreign key enforcement,
create plug_new with the widened CHECK (otherwise byte-for-byte identical to the live schema),
copy every row across unchanged, drop the old table, rename plug_new to plug, verify no foreign
key is left dangling, then re-enable enforcement. No index/trigger/view is defined directly on
plug itself (confirmed against db/schema.sql — the only plug-related indexes are on the child
tables plug_state_transition/plug_command_log/plug_reading, keyed by plug_id, untouched by this),
so nothing else needs recreating. Every *_id column elsewhere that points at plug(id) keeps
pointing at the same rows, since the rebuilt table reuses the exact same `id INTEGER PRIMARY KEY`
rowids by copying them verbatim rather than letting them reassign.

No backfill: every existing Plug keeps its current controller_kind untouched ('timer' is only
ever chosen going forward, from the Admin/Setup Wizard forms RHA-95 also updated).

Ported verbatim from tools/migrate_2026_10_29_plug_timer_controller_kind.py (RHA-101; see db/migrate.py, ADR 0059).
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH

_NEW_PLUG_TABLE_SQL = """
CREATE TABLE plug_new (
    id                  INTEGER PRIMARY KEY,
    room_id             INTEGER REFERENCES room(id) ON DELETE CASCADE,
    plug_group_id       INTEGER REFERENCES plug_group(id) ON DELETE SET NULL,
    label               TEXT NOT NULL,
    purpose             TEXT NOT NULL CHECK (length(purpose) > 0),
    tracking_mode       TEXT NOT NULL DEFAULT 'smart' CHECK (tracking_mode IN ('smart', 'manual')),
    plugin              TEXT,
    external_id         TEXT,
    plugin_config       TEXT,
    auto_update_enabled INTEGER NOT NULL DEFAULT 1,
    show_on_dashboard   INTEGER NOT NULL DEFAULT 1,
    target_on_time      TEXT,
    target_off_time     TEXT,
    always_on           INTEGER NOT NULL DEFAULT 0,
    timer_ack_on_time   TEXT,
    timer_ack_off_time  TEXT,
    controller_kind     TEXT NOT NULL DEFAULT 'none' CHECK (controller_kind IN ('none', 'timer', 'thermostat', 'hydrostat')),
    target_temp_c       REAL,
    target_humidity_pct REAL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (plugin, external_id),
    CHECK (
        (tracking_mode = 'smart' AND plugin IS NOT NULL AND external_id IS NOT NULL) OR
        (tracking_mode = 'manual' AND plugin IS NULL AND external_id IS NULL)
    )
)
"""

_PLUG_COLUMNS = (
    "id, room_id, plug_group_id, label, purpose, tracking_mode, plugin, external_id, "
    "plugin_config, auto_update_enabled, show_on_dashboard, target_on_time, target_off_time, "
    "always_on, timer_ack_on_time, timer_ack_off_time, controller_kind, target_temp_c, "
    "target_humidity_pct, created_at"
)


def _already_widened(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'plug'"
    ).fetchone()
    # Matches the CHECK clause's own value list specifically, not just the word "timer" anywhere
    # in the table's stored SQL — schema.sql's own comment above this column mentions "'timer'"
    # too, which a bare substring check would also (wrongly) match.
    return row is not None and "controller_kind IN ('none', 'timer'" in row[0]


def migrate(conn: sqlite3.Connection) -> None:
    if _already_widened(conn):
        print("  [skip] plug.controller_kind's CHECK already allows 'timer'")
        return

    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(_NEW_PLUG_TABLE_SQL)
    conn.execute(f"INSERT INTO plug_new ({_PLUG_COLUMNS}) SELECT {_PLUG_COLUMNS} FROM plug")
    conn.execute("DROP TABLE plug")
    conn.execute("ALTER TABLE plug_new RENAME TO plug")
    dangling = conn.execute("PRAGMA foreign_key_check").fetchall()
    if dangling:
        raise RuntimeError(f"Rebuild left dangling foreign keys, aborting: {dangling!r}")
    print("  [done] plug.controller_kind CHECK widened to allow 'timer'")
