"""One-off migration: pivots Smart Sensor/Plug device identity from vendor-specific columns
(sensor.mac_address; plug.tuya_device_id/tuya_local_key/tuya_ip_address/switch_dps_key) to the
generic plugin/external_id/plugin_config shape, adds plug_last_seen (drives the new absence-based
Plug Unreachable check), and adds app_setting.ingest_scan_interval_seconds. See CONTEXT.md: Plugin,
External ID, Plugin Config, Ingest; ADR 0013.

sensor/plug both gain CHECK/UNIQUE constraints on the new columns, which SQLite can't add via a
plain ALTER TABLE ADD COLUMN — this rebuilds each table under a temp name, copies data across
(translating identity columns as it goes), then swaps it into place, following SQLite's documented
12-step "table rebuild" procedure (see sqlite.org/lang_altertable.html) so tables that hold a
foreign key into sensor/plug (enclosure.fallback_sensor_id, plug_enclosure, sensor_reading, etc.)
don't end up with a dangling reference — the intermediate table is created under a name nothing
else points at, so nothing needs its own FK definition rewritten as a side effect of the swap.

Same idempotent, re-runnable, self-backing-up pattern as tools/migrate_2026_08_25_target_schedule.py.

Run: .venv/Scripts/python.exe tools/migrate_2026_08_25_plugin_architecture.py
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.db import DB_PATH, SCHEMA_PATH
from plugins.govee_ble.identity import PLUGIN_NAME as GOVEE_PLUGIN
from plugins.tuya_lan.identity import PLUGIN_NAME as TUYA_PLUGIN
from plugins.tuya_lan.identity import encode_external_id as tuya_encode_external_id
from plugins.tuya_lan.identity import pack_config as tuya_pack_config


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def backup_db() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = DB_PATH.with_name(f"{DB_PATH.name}.bak-{stamp}")
    shutil.copy2(DB_PATH, backup_path)
    print(f"Backed up {DB_PATH} -> {backup_path}")
    return backup_path


def _migrate_sensor_table(conn: sqlite3.Connection) -> None:
    # Create the new-shape table under a temp name by running the (already-updated) schema.sql
    # against a scratch connection state — simplest reliable way to stay byte-for-byte in sync with
    # schema.sql's column list without hand-duplicating it here. We do this by temporarily renaming
    # `sensor` out of the way so CREATE TABLE IF NOT EXISTS sensor (from schema.sql) creates a fresh
    # one, then immediately rename that fresh one to sensor_new and rename the original back to
    # `sensor` — the round trip through the same name pair leaves every other table's FK text
    # (e.g. enclosure.fallback_sensor_id) pointed at whichever table is currently named `sensor`,
    # which is the original data again by the time we read from it below.
    conn.execute("ALTER TABLE sensor RENAME TO sensor_old")
    conn.executescript(SCHEMA_PATH.read_text())  # recreates `sensor` fresh, new shape
    conn.execute("ALTER TABLE sensor RENAME TO sensor_new")
    conn.execute("ALTER TABLE sensor_old RENAME TO sensor")  # restore original name/rows for now

    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM sensor").fetchall()
    for row in rows:
        d = dict(row)
        mac = d.pop("mac_address")
        d["plugin"] = GOVEE_PLUGIN if mac else None
        d["external_id"] = mac.upper() if mac else None
        d["plugin_config"] = None
        columns = list(d.keys())
        conn.execute(
            f"INSERT INTO sensor_new ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
            [d[c] for c in columns],
        )
    conn.row_factory = None

    conn.execute("DROP TABLE sensor")
    conn.execute("ALTER TABLE sensor_new RENAME TO sensor")
    print(f"  [done] migrated {len(rows)} sensor row(s) to plugin/external_id/plugin_config")


def _migrate_plug_table(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE plug RENAME TO plug_old")
    conn.executescript(SCHEMA_PATH.read_text())  # recreates `plug` fresh, new shape (also plug_last_seen)
    conn.execute("ALTER TABLE plug RENAME TO plug_new")
    conn.execute("ALTER TABLE plug_old RENAME TO plug")

    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM plug").fetchall()
    for row in rows:
        d = dict(row)
        device_id = d.pop("tuya_device_id")
        local_key = d.pop("tuya_local_key")
        ip_address = d.pop("tuya_ip_address")
        dps_key = d.pop("switch_dps_key")
        if device_id:
            d["plugin"] = TUYA_PLUGIN
            d["external_id"] = tuya_encode_external_id(device_id, dps_key)
            d["plugin_config"] = tuya_pack_config(local_key, ip_address)
        else:
            d["plugin"] = None
            d["external_id"] = None
            d["plugin_config"] = None
        columns = list(d.keys())
        conn.execute(
            f"INSERT INTO plug_new ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
            [d[c] for c in columns],
        )
    conn.row_factory = None

    conn.execute("DROP TABLE plug")
    conn.execute("ALTER TABLE plug_new RENAME TO plug")
    print(f"  [done] migrated {len(rows)} plug row(s) to plugin/external_id/plugin_config")


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = OFF")  # required before a table-rebuild-style migration

    if "mac_address" in _existing_columns(conn, "sensor"):
        _migrate_sensor_table(conn)
    else:
        print("  [skip] sensor already migrated")

    if "tuya_device_id" in _existing_columns(conn, "plug"):
        _migrate_plug_table(conn)
    else:
        print("  [skip] plug already migrated")

    if "ingest_scan_interval_seconds" not in _existing_columns(conn, "app_setting"):
        conn.execute(
            "ALTER TABLE app_setting ADD COLUMN ingest_scan_interval_seconds INTEGER NOT NULL DEFAULT 5"
        )
        print("  [done] app_setting.ingest_scan_interval_seconds")
    else:
        print("  [skip] app_setting.ingest_scan_interval_seconds already exists")

    conn.executescript(SCHEMA_PATH.read_text())  # CREATE TABLE/INDEX IF NOT EXISTS — no-op here, safe

    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError(f"Migration introduced foreign key violations, rolling back: {violations}")


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
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    main()
