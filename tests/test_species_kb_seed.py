"""Built-in Knowledge Base species are seeded once, not replayed from schema.sql on every startup,
so one the user deletes stays deleted (RHA-113; see db/migrations/m0024_species_profile_kb.py)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import db.db as db_module
from db.migrate import run_migrations
from db.migrations import LATEST_VERSION
from web import species_kb_queries as kbq

KB_TABLES = ["snake_profile", "lizard_profile", "insect_profile", "saltwater_fish_profile",
             "freshwater_fish_profile", "saltwater_invert_profile", "freshwater_invert_profile"]


def _count(conn, table: str, key: str | None = None) -> int:
    if key is None:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return conn.execute(f"SELECT COUNT(*) FROM {table} WHERE profile_key = ?", (key,)).fetchone()[0]


def test_schema_sql_no_longer_seeds_the_knowledge_base():
    assert "INSERT OR IGNORE INTO snake_profile" not in db_module.SCHEMA_PATH.read_text(encoding="utf-8")


def test_fresh_install_is_seeded(temp_db):
    # A brand-new database skips migrations; SEEDS must cover it.
    assert all(_count(temp_db, t) > 0 for t in KB_TABLES)
    assert _count(temp_db, "snake_profile", "corn_snake") == 1


def test_a_deleted_built_in_species_stays_deleted_after_restart(temp_db):
    corn = temp_db.execute("SELECT id FROM snake_profile WHERE profile_key = 'corn_snake'").fetchone()["id"]
    kbq.delete_profile("snake", corn)
    db_module.init_db()  # a tray restart replays schema.sql
    db_module.init_db()
    assert _count(temp_db, "snake_profile", "corn_snake") == 0
    assert _count(temp_db, "snake_profile", "ball_python") == 1


def test_an_old_database_is_seeded_once_by_migration_24(tmp_path: Path, monkeypatch):
    path = tmp_path / "husbandrytracker.db"
    monkeypatch.setattr(db_module, "DB_PATH", path)
    run_migrations()
    conn = sqlite3.connect(path)
    for table in KB_TABLES:
        conn.execute(f"DROP TABLE {table}")
    conn.execute("PRAGMA user_version = 23")
    conn.commit()
    conn.close()

    assert run_migrations() == LATEST_VERSION - 23
    conn = sqlite3.connect(path)
    assert all(_count(conn, t) > 0 for t in KB_TABLES)
    conn.execute("DELETE FROM snake_profile WHERE profile_key = 'corn_snake'")
    conn.commit()
    conn.close()

    db_module.init_db()
    conn = sqlite3.connect(path)
    assert _count(conn, "snake_profile", "corn_snake") == 0
    conn.close()
