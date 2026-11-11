"""Adds plug.always_on (see db/schema.sql, CONTEXT.md: Always On) — a Plug
attribute for one meant to run continuously with no on/off cycle (e.g. a pump), mutually exclusive
with Target Schedule and only meaningful when controller_kind = 'none'.

No backfill needed: default 0 is correct for every existing row — nothing was "Always On" before
this column existed, and a Plug with no Target Schedule set today simply stays in the existing
"no schedule set yet" state, not silently reinterpreted as Always On.

Ported verbatim from tools/migrate_2026_09_15_plug_always_on.py (RHA-101; see db/migrate.py, ADR 0059).
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def migrate(conn: sqlite3.Connection) -> None:
    if "always_on" not in _existing_columns(conn, "plug"):
        conn.execute("ALTER TABLE plug ADD COLUMN always_on INTEGER NOT NULL DEFAULT 0")
        print("  [done] plug.always_on")
    else:
        print("  [skip] plug.always_on already exists")

    conn.executescript(SCHEMA_PATH.read_text())  # CREATE TABLE/INDEX IF NOT EXISTS — no-op here, safe
