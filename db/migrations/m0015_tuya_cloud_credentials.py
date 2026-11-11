"""Adds Tuya Cloud credentials to app_setting (see db/schema.sql, ADR 0030).

Adds `app_setting.tuya_access_id` (TEXT, nullable), `app_setting.tuya_access_secret` (TEXT,
nullable), and `app_setting.tuya_api_region` (TEXT, default 'us'). Purely additive: every existing
row is untouched. Same idempotent, re-runnable, self-backing-up pattern as every other
tools/migrate_* script.

Ported verbatim from tools/migrate_2026_10_18_tuya_cloud_credentials.py (RHA-101; see db/migrate.py, ADR 0059).
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_columns(conn: sqlite3.Connection, table: str, columns: list[str], sql_type: str) -> None:
    existing = _existing_columns(conn, table)
    added = []
    for column in columns:
        if column in existing:
            print(f"  [skip] {table}.{column} already exists")
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")
        added.append(column)
    if added:
        print(f"  [done] {table}.{', '.join(added)}")


def migrate(conn: sqlite3.Connection) -> None:
    _add_columns(conn, "app_setting", ["tuya_access_id", "tuya_access_secret"], "TEXT")
    _add_columns(conn, "app_setting", ["tuya_api_region"], "TEXT NOT NULL DEFAULT 'us'")
    conn.executescript(SCHEMA_PATH.read_text())  # CREATE TABLE/INDEX IF NOT EXISTS — no-op here, safe
