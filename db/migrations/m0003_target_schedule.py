"""Renames plug.declared_on_time/declared_off_time to target_on_time/
target_off_time and adds app_setting.schedule_drift_threshold_minutes, for Target Schedule / Timer
Warning (see CONTEXT.md: Target Schedule, Detected Schedule, Timer Warning; ADR 0012).

Ported verbatim from tools/migrate_2026_08_25_target_schedule.py (RHA-101; see db/migrate.py, ADR 0059).
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


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
