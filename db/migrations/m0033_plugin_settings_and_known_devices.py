"""Adds `plugin_setting` and `known_device` (see db/schema.sql, CONTEXT.md: Plugin Setting, Known
Device; ADR 0061), and moves the Tuya Cloud Credentials out of `app_setting` into `plugin_setting`
under tuya_lan, now that they're edited on tuya_lan's own Settings page. The old app_setting
columns are left in place but no longer read — SQLite can't drop a column without rebuilding the
table, and nothing is gained by doing so.
"""
from __future__ import annotations

import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS plugin_setting (
            plugin TEXT NOT NULL,
            key    TEXT NOT NULL,
            value  TEXT NOT NULL,
            PRIMARY KEY (plugin, key)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS known_device (
            id            INTEGER PRIMARY KEY,
            plugin        TEXT NOT NULL,
            external_id   TEXT NOT NULL,
            name          TEXT NOT NULL CHECK (length(trim(name)) > 0),
            plugin_config TEXT,
            summary       TEXT,
            last_seen_at  TEXT,
            created_at    TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (plugin, external_id)
        )"""
    )
    print("  [done] plugin_setting, known_device")

    columns = {row[1] for row in conn.execute("PRAGMA table_info(app_setting)")}
    if not {"tuya_access_id", "tuya_access_secret", "tuya_api_region"} <= columns:
        return
    row = conn.execute(
        "SELECT tuya_access_id, tuya_access_secret, tuya_api_region FROM app_setting WHERE id = 1"
    ).fetchone()
    if row is None:
        return
    moved = 0
    for key, value in zip(("access_id", "access_secret", "api_region"), row):
        if value:
            conn.execute(
                "INSERT OR IGNORE INTO plugin_setting (plugin, key, value) VALUES ('tuya_lan', ?, ?)",
                (key, value),
            )
            moved += 1
    print(f"  [done] moved {moved} Tuya Cloud Credential value(s) to plugin_setting")
