"""Adds animal.species_profile (see db/schema.sql, CONTEXT.md: Species Profile)
— the Species Profile key picked for an Animal in the Setup Wizard, so a later "Add Sensor" on its
Enclosure can pre-fill its own Species Profile instead of asking again (RHA-94).

No backfill: there's nothing to derive a past Animal's Species Profile from (it was never captured
anywhere before this column existed) — every existing Animal just gets NULL, same as one added
without picking a profile.

Ported verbatim from tools/migrate_2026_10_29_animal_species_profile.py (RHA-101; see db/migrate.py, ADR 0059).
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def migrate(conn: sqlite3.Connection) -> None:
    if "species_profile" not in _existing_columns(conn, "animal"):
        conn.execute("ALTER TABLE animal ADD COLUMN species_profile TEXT")
        print("  [done] animal.species_profile")
    else:
        print("  [skip] animal.species_profile already exists")

    conn.executescript(SCHEMA_PATH.read_text())  # CREATE TABLE/INDEX IF NOT EXISTS — no-op here, safe
