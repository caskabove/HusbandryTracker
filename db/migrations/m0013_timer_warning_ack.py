"""Adds plug.timer_ack_on_time / plug.timer_ack_off_time (see db/schema.sql,
CONTEXT.md: Timer Warning) — the Detected Schedule times a user cleared a Timer Warning against.
Both start NULL, meaning "never cleared", so existing rows need no backfill.

Ported verbatim from tools/migrate_2026_10_04_timer_warning_ack.py (RHA-101; see db/migrate.py, ADR 0059).
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH

NEW_COLUMNS = ["timer_ack_on_time", "timer_ack_off_time"]


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
