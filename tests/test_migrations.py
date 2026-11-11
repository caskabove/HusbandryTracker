"""Automatic schema migration runner — db/migrate.py (RHA-101; ADR 0059)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import db.db as db_module
import db.migrate as migrate_module
from db.migrate import MigrationError, run_migrations
from db.migrations import LATEST_VERSION, MIGRATIONS


@pytest.fixture()
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "husbandrytracker.db"
    monkeypatch.setattr(db_module, "DB_PATH", path)
    return path


def _query(path: Path, sql: str, params=()):
    conn = sqlite3.connect(path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _version(path: Path) -> int:
    return _query(path, "PRAGMA user_version")[0][0]


def _columns(path: Path, table: str) -> set[str]:
    return {row[1] for row in _query(path, f"PRAGMA table_info({table})")}


def _backups(path: Path) -> list[Path]:
    return sorted((path.parent / "backups").glob("husbandrytracker-*-premigration*.db"))


def _execute(path: Path, *statements: str) -> None:
    conn = sqlite3.connect(path)
    try:
        for sql in statements:
            conn.execute(sql)
        conn.commit()
    finally:
        conn.close()


def _make_current_db(path: Path) -> None:
    run_migrations()
    assert _version(path) == LATEST_VERSION


def test_registry_is_numbered_one_to_n():
    assert [n for n, _, _ in MIGRATIONS] == list(range(1, len(MIGRATIONS) + 1))
    assert LATEST_VERSION == len(MIGRATIONS)


def test_fresh_database_is_created_at_latest_version_without_running_migrations(db_path):
    assert run_migrations() == 0
    assert _version(db_path) == LATEST_VERSION
    assert "animal" in {r[0] for r in _query(db_path, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert _backups(db_path) == []


def test_empty_file_counts_as_fresh(db_path):
    db_path.touch()
    assert run_migrations() == 0
    assert _version(db_path) == LATEST_VERSION


def test_current_database_is_a_no_op_with_no_backup(db_path):
    _make_current_db(db_path)
    assert run_migrations() == 0
    assert _backups(db_path) == []


def test_init_db_runs_migrations_first(db_path):
    db_module.init_db()
    assert _version(db_path) == LATEST_VERSION


def test_database_at_version_zero_missing_some_migrations_is_repaired(db_path):
    """Every existing database reports user_version 0. Simulate one that missed some of the old
    hand-run scripts (plug.always_on from 8, animal.species_profile from 16, room.sort_order from
    22, enclosure.image_filename from 23),
    with data in it, and check all 26 run, fill the gaps, and keep the data."""
    _make_current_db(db_path)
    _execute(
        db_path,
        "INSERT INTO room (id, name) VALUES (1, 'Reptile room')",
        "INSERT INTO enclosure (id, name, room_id) VALUES (1, 'Rack A', 1)",
        "INSERT INTO animal (id, enclosure_id, name) VALUES (1, 1, 'Ziggy')",
        "ALTER TABLE room DROP COLUMN sort_order",
        "ALTER TABLE animal DROP COLUMN species_profile",
        "ALTER TABLE enclosure DROP COLUMN image_filename",
        "ALTER TABLE plug DROP COLUMN always_on",
        "PRAGMA user_version = 0",
    )
    assert "sort_order" not in _columns(db_path, "room")

    assert run_migrations() == LATEST_VERSION

    assert _version(db_path) == LATEST_VERSION
    assert "sort_order" in _columns(db_path, "room")
    assert "species_profile" in _columns(db_path, "animal")
    assert "image_filename" in _columns(db_path, "enclosure")
    assert "always_on" in _columns(db_path, "plug")
    assert _query(db_path, "SELECT name FROM animal WHERE id = 1") == [("Ziggy",)]
    assert len(_backups(db_path)) == 1
    log = (db_path.parent / "logs" / "migrations.log").read_text(encoding="utf-8")
    assert "[22] room_sort_order" in log and "[done] room.sort_order" in log


def test_only_pending_migrations_run(db_path, monkeypatch):
    _make_current_db(db_path)
    _execute(db_path, "PRAGMA user_version = 24")
    ran = []
    monkeypatch.setattr(
        migrate_module,
        "MIGRATIONS",
        [(n, name, (lambda conn, n=n: ran.append(n))) for n, name, _ in MIGRATIONS],
    )
    assert run_migrations() == LATEST_VERSION - 24
    assert ran == list(range(25, LATEST_VERSION + 1))
    assert _version(db_path) == LATEST_VERSION


def test_failed_migration_restores_backup_and_raises(db_path, monkeypatch):
    _make_current_db(db_path)
    _execute(db_path, "INSERT INTO room (id, name) VALUES (1, 'Reptile room')")

    def good(conn):
        conn.execute("ALTER TABLE room ADD COLUMN good_column TEXT")

    def boom(conn):
        conn.execute("ALTER TABLE room ADD COLUMN half_done TEXT")  # DDL autocommits: really applied
        conn.execute("DELETE FROM room")
        raise RuntimeError("simulated failure")

    good_n, boom_n = LATEST_VERSION + 1, LATEST_VERSION + 2
    monkeypatch.setattr(migrate_module, "MIGRATIONS", MIGRATIONS + [(good_n, "good", good), (boom_n, "boom", boom)])
    monkeypatch.setattr(migrate_module, "LATEST_VERSION", boom_n)

    with pytest.raises(MigrationError) as excinfo:
        run_migrations()

    message = str(excinfo.value)
    assert f"migration {boom_n} (boom)" in message and "simulated failure" in message and "restored" in message
    # Everything from this run is undone, including the migration that succeeded before the failure.
    assert _version(db_path) == LATEST_VERSION
    assert {"good_column", "half_done"}.isdisjoint(_columns(db_path, "room"))
    assert _query(db_path, "SELECT name FROM room") == [("Reptile room",)]
    assert len(_backups(db_path)) == 1
    assert not (db_path.parent / "migrating.lock").exists()


def test_database_from_a_newer_version_is_refused_untouched(db_path):
    _make_current_db(db_path)
    _execute(db_path, f"PRAGMA user_version = {LATEST_VERSION + 5}")
    with pytest.raises(MigrationError, match="newer version"):
        run_migrations()
    assert _version(db_path) == LATEST_VERSION + 5
    assert _backups(db_path) == []


def test_stale_lock_from_a_dead_process_is_taken_over(db_path, monkeypatch):
    lock = db_path.parent / "migrating.lock"
    lock.write_text("12345")
    monkeypatch.setattr(migrate_module, "_STALE_LOCK_SECONDS", -1)
    assert run_migrations() == 0
    assert not lock.exists()


def test_live_lock_held_too_long_raises(db_path, monkeypatch):
    lock = db_path.parent / "migrating.lock"
    lock.write_text("12345")
    monkeypatch.setattr(migrate_module, "_LOCK_WAIT_SECONDS", 0)
    with pytest.raises(MigrationError, match="Another Husbandry Tracker process"):
        run_migrations()
    assert lock.exists()  # not ours to delete
