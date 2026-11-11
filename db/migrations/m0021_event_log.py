"""Adds event_log (see db/schema.sql, CONTEXT.md: Log Event; ADR 0044) — a
free-form log table any Plugin or AI skill can write to via a new "log" Plugin Event kind,
alongside the three existing observation kinds (sensor_reading/plug_state/plug_telemetry).

No backfill needed: the table starts empty — nothing was recorded in this shape before it existed.

Ported verbatim from tools/migrate_2026_10_31_event_log.py (RHA-101; see db/migrate.py, ADR 0059).
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())  # CREATE TABLE IF NOT EXISTS event_log
    print("  [done] event_log")
