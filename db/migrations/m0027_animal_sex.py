"""Adds `animal.sex` (see db/schema.sql, CONTEXT.md: Animal; RHA-102) — Male / Female / Unknown on
every Animal, defaulting to Unknown so existing Animals need no backfill.

ADD COLUMN carries the same CHECK as schema.sql: SQLite allows a CHECK on an added column as long
as the default satisfies it, which 'unknown' does.
"""
from __future__ import annotations

import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    if "sex" in {row[1] for row in conn.execute("PRAGMA table_info(animal)")}:
        print("  [skip] animal.sex already exists")
        return
    conn.execute(
        "ALTER TABLE animal ADD COLUMN sex TEXT NOT NULL DEFAULT 'unknown' "
        "CHECK (sex IN ('male', 'female', 'unknown'))"
    )
    print("  [done] animal.sex (existing Animals set to unknown)")
