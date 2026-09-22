"""One-off migration: adds plug_group/plug_group_enclosure (see db/schema.sql, CONTEXT.md: Plug
Group; ADR 0017) and plug.plug_group_id — a named container for several Plugs that are physically
one multi-outlet Tuya device (e.g. 3 independently-switched relays + a USB outlet + 3
hardwired-always-on outlets), created via a user-declared Plug Group Template.

No backfill needed: plug_group starts empty and plug.plug_group_id defaults NULL for every
existing row — nothing was grouped before this column existed.

Same idempotent, re-runnable, self-backing-up pattern as every other tools/migrate_* script.

Run: .venv/Scripts/python.exe tools/migrate_2026_09_21_plug_group.py
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.db import DB_PATH, SCHEMA_PATH


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def backup_db() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = DB_PATH.with_name(f"{DB_PATH.name}.bak-{stamp}")
    shutil.copy2(DB_PATH, backup_path)
    print(f"Backed up {DB_PATH} -> {backup_path}")
    return backup_path


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())  # CREATE TABLE IF NOT EXISTS plug_group/plug_group_enclosure

    if "plug_group_id" not in _existing_columns(conn, "plug"):
        conn.execute("ALTER TABLE plug ADD COLUMN plug_group_id INTEGER REFERENCES plug_group(id) ON DELETE SET NULL")
        print("  [done] plug.plug_group_id")
    else:
        print("  [skip] plug.plug_group_id already exists")


def main() -> None:
    if not DB_PATH.exists():
        print(f"No existing database at {DB_PATH} — nothing to migrate.")
        return
    backup_db()
    conn = sqlite3.connect(DB_PATH)
    try:
        with conn:
            migrate(conn)
    finally:
        conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    main()
