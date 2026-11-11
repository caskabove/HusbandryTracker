"""Adds the Care Setup Prompt's nag-tracking columns to `enclosure` (see
db/schema.sql, CONTEXT.md: Care Setup Prompt, Care Interval; ADR 0040).

Adds, per Care kind (feeding/watering/spot_clean/deep_clean): `{kind}_nag_count` (INTEGER, default
0) and `{kind}_nag_last_date` (TEXT, nullable). Purely additive: every existing row starts at 0/NULL,
same as a freshly-created Enclosure. Same idempotent, re-runnable, self-backing-up pattern as every
other tools/migrate_* script.

Ported verbatim from tools/migrate_2026_10_29_care_nag_count.py (RHA-101; see db/migrate.py, ADR 0059).
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH

CARE_KINDS = ["feeding", "watering", "spot_clean", "deep_clean"]


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
    _add_columns(conn, "enclosure", [f"{kind}_nag_count" for kind in CARE_KINDS], "INTEGER NOT NULL DEFAULT 0")
    _add_columns(conn, "enclosure", [f"{kind}_nag_last_date" for kind in CARE_KINDS], "TEXT")
    conn.executescript(SCHEMA_PATH.read_text())  # CREATE TABLE/INDEX IF NOT EXISTS — no-op here, safe
