"""Adds the `enclosure_note` table (see db/schema.sql, CONTEXT.md: Enclosure Note; RHA-116).

Purely additive: replays schema.sql, whose CREATE TABLE/INDEX IF NOT EXISTS creates the new table
and its index and leaves everything else untouched.
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())  # CREATE TABLE IF NOT EXISTS enclosure_note
    print("  [done] enclosure_note table")
