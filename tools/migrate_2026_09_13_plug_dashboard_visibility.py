"""One-off migration: adds plug.show_on_dashboard (see db/schema.sql, CONTEXT.md: Plug) —
per-Plug opt-in for whether its current status (on/off, or Unreachable) shows on the Dashboard.
Same idea as animal.show_on_dashboard / sensor.show_on_dashboard (see
tools/migrate_2026_09_13_animal_dashboard_visibility.py's module docstring for the full
reasoning) — this one just applies it to `plug`.

The backfill is trickier than Animal's or Sensor's: a Plug's parent is either a Room (room_id
column, same as those two) OR one-or-more Enclosures via the plug_enclosure join table (see
CONTEXT.md: Plug, ADR 0006) — there's no plug.enclosure_id column to GROUP BY. So the Enclosure
side walks plug_enclosure instead, scoping "top 3" per enclosure_id there; a Plug shared across
several Enclosures ("everything on one switch") only needs ONE of those Enclosures to already
have 3 shown to get hidden — same "every parent must have room" reasoning
web/admin_queries.py's create_plug() uses going forward, just applied as a backfill here.

Same idempotent, re-runnable, self-backing-up pattern as every other tools/migrate_* script.

Run: .venv/Scripts/python.exe tools/migrate_2026_09_13_plug_dashboard_visibility.py
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


def _backfill_room_plugs(conn: sqlite3.Connection) -> int:
    room_ids = [row[0] for row in conn.execute(
        "SELECT room_id FROM plug WHERE room_id IS NOT NULL GROUP BY room_id HAVING COUNT(*) > 3"
    )]
    hidden = 0
    for room_id in room_ids:
        keep_ids = [row[0] for row in conn.execute(
            "SELECT id FROM plug WHERE room_id = ? ORDER BY id LIMIT 3", (room_id,)
        )]
        placeholders = ",".join("?" * len(keep_ids))
        cur = conn.execute(
            f"UPDATE plug SET show_on_dashboard = 0 WHERE room_id = ? AND id NOT IN ({placeholders})",
            (room_id, *keep_ids),
        )
        hidden += cur.rowcount
    return hidden


def _backfill_enclosure_plugs(conn: sqlite3.Connection) -> int:
    enclosure_ids = [row[0] for row in conn.execute(
        "SELECT enclosure_id FROM plug_enclosure GROUP BY enclosure_id HAVING COUNT(*) > 3"
    )]
    hide_ids: set[int] = set()
    for enclosure_id in enclosure_ids:
        all_ids = [row[0] for row in conn.execute(
            """SELECT p.id FROM plug p JOIN plug_enclosure pe ON pe.plug_id = p.id
               WHERE pe.enclosure_id = ? ORDER BY p.id""",
            (enclosure_id,),
        )]
        hide_ids.update(all_ids[3:])
    hidden = 0
    for plug_id in hide_ids:
        conn.execute("UPDATE plug SET show_on_dashboard = 0 WHERE id = ?", (plug_id,))
        hidden += 1
    return hidden


def migrate(conn: sqlite3.Connection) -> None:
    added = "show_on_dashboard" not in _existing_columns(conn, "plug")
    if added:
        conn.execute("ALTER TABLE plug ADD COLUMN show_on_dashboard INTEGER NOT NULL DEFAULT 1")
        print("  [done] plug.show_on_dashboard")
    else:
        print("  [skip] plug.show_on_dashboard already exists")

    if added:
        hidden = _backfill_room_plugs(conn) + _backfill_enclosure_plugs(conn)
        if hidden:
            print(f"  [done] defaulted {hidden} Plug(s) past the first 3 under the same parent to hidden on the Dashboard")

    conn.executescript(SCHEMA_PATH.read_text())  # CREATE TABLE/INDEX IF NOT EXISTS — no-op here, safe


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
