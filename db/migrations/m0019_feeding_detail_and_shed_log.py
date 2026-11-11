"""Adds feeding_detail and shed_log (see db/schema.sql, CONTEXT.md: Feeding
Detail, Shed Log; ADR 0042; RHA-91) — Feeding Detail is a 1:1 extension of a Feeding care_event
(prey/count/live-or-frozen/accepted-or-refused), Shed Log is a new per-Animal observation table.

No backfill needed: both tables start empty — nothing was recorded in this shape before they
existed, and feeding_detail's care_event_id FK only ever points at a Feeding logged after this
migration runs (an older Feeding simply has no matching feeding_detail row, same as an older Plug
with no row in a table a later feature added).

Ported verbatim from tools/migrate_2026_10_30_feeding_detail_and_shed_log.py (RHA-101; see db/migrate.py, ADR 0059).
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())  # CREATE TABLE IF NOT EXISTS feeding_detail/shed_log
    print("  [done] feeding_detail, shed_log")
