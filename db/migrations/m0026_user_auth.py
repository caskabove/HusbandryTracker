"""Adds the auth tables (see CONTEXT.md: User Account, Role, Session, Audit
Log; ADR 0058; RHA-99 Phase 1) — `user`, `session`, `audit_log`. Purely additive — no existing
table gains a column — so this just re-runs db/schema.sql via executescript(), same shape as
tools/migrate_2026_10_30_feeding_detail_and_shed_log.py and
tools/migrate_2026_11_02_species_profile_kb.py. No backfill needed: a freshly-created `user` table
starts empty, and the app's own first-run gate (web/auth.py's AuthMiddleware) sends the next
visitor to /setup-admin to create the first admin.

Ported verbatim from tools/migrate_2026_11_05_user_auth.py (RHA-101; see db/migrate.py, ADR 0059).
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())  # CREATE TABLE/INDEX IF NOT EXISTS — no-op if already present
    print("  [done] user, session, audit_log tables")
