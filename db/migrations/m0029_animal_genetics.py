"""Adds Morph and Genetics to Animals (see db/schema.sql, CONTEXT.md: Genetics, Morph; RHA-105):
the nullable `animal.morph` column and the new `animal_gene` table. Existing Animals get no Morph
and no Genetics, which displays as "Normal".
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH


def migrate(conn: sqlite3.Connection) -> None:
    if "morph" in {row[1] for row in conn.execute("PRAGMA table_info(animal)")}:
        print("  [skip] animal.morph already exists")
    else:
        conn.execute("ALTER TABLE animal ADD COLUMN morph TEXT")
        print("  [done] animal.morph")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))  # creates animal_gene
    print("  [done] animal_gene")
