"""Adds `user.theme` (see db/schema.sql, web/theme.py, CONTEXT.md: Theme; RHA-118): each User
Account's chosen color Theme. Nullable with no default, so every existing user stays on the
Default theme until they pick one on the Settings page.
"""
from __future__ import annotations

import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    if "theme" in {row[1] for row in conn.execute("PRAGMA table_info(user)")}:
        print("  [skip] user.theme already exists")
        return
    conn.execute("ALTER TABLE user ADD COLUMN theme TEXT")
    print("  [done] user.theme (existing users stay on the Default theme)")
