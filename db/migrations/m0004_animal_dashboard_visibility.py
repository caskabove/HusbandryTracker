"""Adds animal.show_on_dashboard (see db/schema.sql, CONTEXT.md: Animal) —
per-Animal opt-in for whether it shows on the Dashboard's Enclosure panel.

Backfill: the column defaults to 1 (shown) at the ALTER, so a fresh column would leave every
existing Animal shown. That's wrong for an Enclosure that already houses more than 3 Animals — the
Dashboard is meant to default to showing the first 3 per Enclosure only (ordered by id, i.e.
creation order) — so this walks every Enclosure with more than 3 Animals and turns the flag off for
everything past the third.

Ported verbatim from tools/migrate_2026_09_13_animal_dashboard_visibility.py (RHA-101; see db/migrate.py, ADR 0059).
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def migrate(conn: sqlite3.Connection) -> None:
    added = "show_on_dashboard" not in _existing_columns(conn, "animal")
    if added:
        conn.execute("ALTER TABLE animal ADD COLUMN show_on_dashboard INTEGER NOT NULL DEFAULT 1")
        print("  [done] animal.show_on_dashboard")
    else:
        print("  [skip] animal.show_on_dashboard already exists")

    if added:
        enclosure_ids = [row[0] for row in conn.execute(
            "SELECT enclosure_id FROM animal GROUP BY enclosure_id HAVING COUNT(*) > 3"
        )]
        backfilled = 0
        for enclosure_id in enclosure_ids:
            keep_ids = [row[0] for row in conn.execute(
                "SELECT id FROM animal WHERE enclosure_id = ? ORDER BY id LIMIT 3", (enclosure_id,)
            )]
            placeholders = ",".join("?" * len(keep_ids))
            cur = conn.execute(
                f"UPDATE animal SET show_on_dashboard = 0 "
                f"WHERE enclosure_id = ? AND id NOT IN ({placeholders})",
                (enclosure_id, *keep_ids),
            )
            backfilled += cur.rowcount
        if enclosure_ids:
            print(f"  [done] defaulted {backfilled} Animal(s) past the first 3 in "
                  f"{len(enclosure_ids)} Enclosure(s) to hidden on the Dashboard")

    conn.executescript(SCHEMA_PATH.read_text())  # CREATE TABLE/INDEX IF NOT EXISTS — no-op here, safe
