"""Adds Animal Photo and Enclosure Photo support (see CONTEXT.md: Animal Photo,
Enclosure Photo, Dashboard Thumbnail) — `animal.image_filename`, and `enclosure.image_filename` /
`dashboard_thumbnail_source` / `dashboard_thumbnail_animal_id`.

Every existing row just gets NULL/'enclosure' defaults — nothing visibly changes until a photo is
actually uploaded. Same idempotent, re-runnable, self-backing-up pattern as every other
tools/migrate_* script.

Ported verbatim from tools/migrate_2026_11_02_animal_enclosure_images.py (RHA-101; see db/migrate.py, ADR 0059).
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def migrate(conn: sqlite3.Connection) -> None:
    animal_columns = _existing_columns(conn, "animal")
    if "image_filename" in animal_columns:
        print("  [skip] animal.image_filename already exists")
    else:
        conn.execute("ALTER TABLE animal ADD COLUMN image_filename TEXT")
        print("  [done] animal.image_filename")

    enclosure_columns = _existing_columns(conn, "enclosure")
    if "image_filename" in enclosure_columns:
        print("  [skip] enclosure.image_filename already exists")
    else:
        conn.execute("ALTER TABLE enclosure ADD COLUMN image_filename TEXT")
        print("  [done] enclosure.image_filename")
    if "dashboard_thumbnail_source" in enclosure_columns:
        print("  [skip] enclosure.dashboard_thumbnail_source already exists")
    else:
        conn.execute(
            "ALTER TABLE enclosure ADD COLUMN dashboard_thumbnail_source TEXT NOT NULL DEFAULT 'enclosure'"
        )
        print("  [done] enclosure.dashboard_thumbnail_source (defaulted to 'enclosure' for every existing row)")
    if "dashboard_thumbnail_animal_id" in enclosure_columns:
        print("  [skip] enclosure.dashboard_thumbnail_animal_id already exists")
    else:
        conn.execute(
            "ALTER TABLE enclosure ADD COLUMN dashboard_thumbnail_animal_id INTEGER REFERENCES animal(id) ON DELETE SET NULL"
        )
        print("  [done] enclosure.dashboard_thumbnail_animal_id")

    conn.executescript(SCHEMA_PATH.read_text())  # CREATE TABLE/INDEX IF NOT EXISTS — no-op here, safe
