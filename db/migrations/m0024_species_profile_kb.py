"""Adds the 7 Species Profile Knowledge Base tables (snake_profile,
lizard_profile, insect_profile, saltwater_fish_profile, freshwater_fish_profile,
saltwater_invert_profile, freshwater_invert_profile — see db/schema.sql, CONTEXT.md: Knowledge
Base, Species Profile; ADR 0054), pre-seeded with reference data, and retires the old hardcoded
SPECIES_PROFILES/SPECIES_PROFILE_GROUPS literal from web/static/app.js.

No backfill needed on `animal`: snake_profile/lizard_profile reuse the exact same profile_key
values the old SPECIES_PROFILES literal used, so any Animal row already carrying a
species_profile value (e.g. "ball_python") keeps resolving to the same row.

Ported verbatim from tools/migrate_2026_11_02_species_profile_kb.py (RHA-101; see db/migrate.py, ADR 0059).
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH


def migrate(conn: sqlite3.Connection) -> None:
    # CREATE TABLE IF NOT EXISTS + INSERT OR IGNORE seed rows for the 7 new tables — both no-ops on
    # a re-run, same as every other migrate_* script's trailing executescript call.
    conn.executescript(SCHEMA_PATH.read_text())
    print("  [done] snake_profile, lizard_profile, insect_profile, saltwater_fish_profile, "
          "freshwater_fish_profile, saltwater_invert_profile, freshwater_invert_profile")
