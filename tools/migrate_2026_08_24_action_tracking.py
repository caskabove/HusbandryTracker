"""One-off migration: brings an existing data/herpmonitor.db up to the schema added for the
Trackable Actions / Enclosure Type work (ADR 0008-0011, see CONTEXT.md).

There's no migration framework in this project (db/db.py's init_db() only does
CREATE TABLE IF NOT EXISTS, which never alters an existing table) — schema changes to an
already-created table have so far been applied by hand directly against the live file. This script
does that by hand, but as a checked-in, idempotent, re-runnable script instead of ad-hoc commands:
every ALTER is guarded by a check against PRAGMA table_info, so running this twice is a harmless
no-op the second time.

Backs up data/herpmonitor.db (timestamped, same naming convention as the existing manual
.bak-YYYYMMDD-HHMMSS copies in that folder) before making any change.

Run: .venv/Scripts/python.exe tools/migrate_2026_08_24_action_tracking.py
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


def _add_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    if column in _existing_columns(conn, table):
        print(f"  [skip] {table}.{column} already exists")
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
    print(f"  [done] {table}.{column}")


def backup_db() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = DB_PATH.with_name(f"{DB_PATH.name}.bak-{stamp}")
    shutil.copy2(DB_PATH, backup_path)
    print(f"Backed up {DB_PATH} -> {backup_path}")
    return backup_path


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = OFF")  # dropping/rebuilding columns mid-transaction

    print("app_setting: Alert Debounce + ntfy settings (ADR 0010)")
    _add_column(conn, "app_setting", "alert_debounce_minutes",
                "alert_debounce_minutes INTEGER NOT NULL DEFAULT 10")
    _add_column(conn, "app_setting", "ntfy_server_url", "ntfy_server_url TEXT")
    _add_column(conn, "app_setting", "ntfy_topic", "ntfy_topic TEXT")

    print("enclosure: Enclosure Type (ADR 0011)")
    _add_column(conn, "enclosure", "enclosure_type",
                "enclosure_type TEXT NOT NULL DEFAULT 'basic' "
                "CHECK (enclosure_type IN ('basic', 'freshwater', 'saltwater', 'amphibian'))")

    print("sensor: Auto-Update + water-chemistry Target Range columns (ADR 0010, ADR 0011)")
    _add_column(conn, "sensor", "auto_update_enabled",
                "auto_update_enabled INTEGER NOT NULL DEFAULT 1")
    for metric in ("ph",):
        _add_column(conn, "sensor", f"target_{metric}_min", f"target_{metric}_min REAL")
        _add_column(conn, "sensor", f"target_{metric}_max", f"target_{metric}_max REAL")
    for metric_unit in (
        "ammonia_ppm", "nitrite_ppm", "nitrate_ppm",
        "salinity_ppt", "alkalinity_dkh", "calcium_ppm", "magnesium_ppm", "phosphate_ppm",
    ):
        _add_column(conn, "sensor", f"target_{metric_unit}_min", f"target_{metric_unit}_min REAL")
        _add_column(conn, "sensor", f"target_{metric_unit}_max", f"target_{metric_unit}_max REAL")

    print("plug: Auto-Update, Controller Kind replacing is_thermostat_controlled (ADR 0008, ADR 0010)")
    _add_column(conn, "plug", "auto_update_enabled", "auto_update_enabled INTEGER NOT NULL DEFAULT 1")
    plug_columns = _existing_columns(conn, "plug")
    if "controller_kind" not in plug_columns:
        conn.execute(
            "ALTER TABLE plug ADD COLUMN controller_kind TEXT NOT NULL DEFAULT 'none' "
            "CHECK (controller_kind IN ('none', 'thermostat', 'hydrostat'))"
        )
        if "is_thermostat_controlled" in plug_columns:
            conn.execute(
                "UPDATE plug SET controller_kind = 'thermostat' WHERE is_thermostat_controlled = 1"
            )
            (n,) = conn.execute(
                "SELECT COUNT(*) FROM plug WHERE controller_kind = 'thermostat'"
            ).fetchone()
            print(f"  [done] plug.controller_kind (backfilled {n} row(s) from is_thermostat_controlled)")
        else:
            print("  [done] plug.controller_kind")
    else:
        print("  [skip] plug.controller_kind already exists")
    _add_column(conn, "plug", "target_humidity_pct", "target_humidity_pct REAL")
    if "is_thermostat_controlled" in _existing_columns(conn, "plug"):
        conn.execute("ALTER TABLE plug DROP COLUMN is_thermostat_controlled")
        print("  [done] dropped plug.is_thermostat_controlled (superseded by controller_kind)")
    else:
        print("  [skip] plug.is_thermostat_controlled already gone")

    print("care_event: Spot-feed animal_id (see CONTEXT.md: Spot-feed)")
    _add_column(conn, "care_event", "animal_id",
                "animal_id INTEGER REFERENCES animal(id) ON DELETE SET NULL")

    conn.execute("PRAGMA foreign_keys = ON")

    print("Creating brand-new tables (plant, plant_health_log, sensor_alert_state, "
          "plug_alert_state, plug_reading) — CREATE TABLE IF NOT EXISTS, safe to re-run")
    conn.executescript(SCHEMA_PATH.read_text())


def main() -> None:
    if not DB_PATH.exists():
        print(f"No existing database at {DB_PATH} — nothing to migrate (init_db() will create "
              f"a fresh one from the current schema.sql directly).")
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
