"""One-off migration: renames plug.declared_on_time/declared_off_time to target_on_time/
target_off_time and adds app_setting.schedule_drift_threshold_minutes, for Target Schedule / Timer
Warning (see CONTEXT.md: Target Schedule, Detected Schedule, Timer Warning; ADR 0012).

Same idempotent, re-runnable, self-backing-up pattern as
tools/migrate_2026_08_24_action_tracking.py — see that file for why this exists instead of a real
migration framework.

Run: .venv/Scripts/python.exe tools/migrate_2026_08_25_target_schedule.py
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
    plug_columns = _existing_columns(conn, "plug")
    if "declared_on_time" in plug_columns and "target_on_time" not in plug_columns:
        conn.execute("ALTER TABLE plug RENAME COLUMN declared_on_time TO target_on_time")
        conn.execute("ALTER TABLE plug RENAME COLUMN declared_off_time TO target_off_time")
        print("  [done] plug.declared_on_time/declared_off_time -> target_on_time/target_off_time")
    else:
        print("  [skip] plug already has target_on_time/target_off_time")

    if "schedule_drift_threshold_minutes" not in _existing_columns(conn, "app_setting"):
        conn.execute(
            "ALTER TABLE app_setting ADD COLUMN schedule_drift_threshold_minutes INTEGER NOT NULL DEFAULT 15"
        )
        print("  [done] app_setting.schedule_drift_threshold_minutes")
    else:
        print("  [skip] app_setting.schedule_drift_threshold_minutes already exists")

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
