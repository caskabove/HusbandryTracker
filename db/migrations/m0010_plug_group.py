"""Adds plug_group/plug_group_enclosure (see db/schema.sql, CONTEXT.md: Plug
Group; ADR 0017) and plug.plug_group_id — a named container for several Plugs that are physically
one multi-outlet Tuya device (e.g. 3 independently-switched relays + a USB outlet + 3
hardwired-always-on outlets), created via a user-declared Plug Group Template.

No backfill needed: plug_group starts empty and plug.plug_group_id defaults NULL for every
existing row — nothing was grouped before this column existed.

Ported verbatim from tools/migrate_2026_09_21_plug_group.py (RHA-101; see db/migrate.py, ADR 0059).
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())  # CREATE TABLE IF NOT EXISTS plug_group/plug_group_enclosure

    if "plug_group_id" not in _existing_columns(conn, "plug"):
        conn.execute("ALTER TABLE plug ADD COLUMN plug_group_id INTEGER REFERENCES plug_group(id) ON DELETE SET NULL")
        print("  [done] plug.plug_group_id")
    else:
        print("  [skip] plug.plug_group_id already exists")
