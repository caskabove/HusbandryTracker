"""Automatic schema migration runner (RHA-101; ADR 0059).

Brings data/husbandrytracker.db up to the schema this build expects, before anything else uses it.
Called by the Supervisor before it starts any child process (tray/supervisor.py), and again from
db.db.init_db() for processes run on their own (a dev uvicorn, tools, tests), where it's a no-op
once the database is current.

How a database is tracked: SQLite's built-in `PRAGMA user_version` holds the number of the last
migration applied (db/migrations/__init__.py's MIGRATIONS).

- **Brand-new database** (no file, or no tables yet): created straight from schema.sql and stamped
  with the latest version. No migrations run, since schema.sql is already the latest shape.
- **Current**: nothing happens: no backup, no writes.
- **Behind**: a backup is taken first (data/backups/husbandrytracker-<stamp>-premigration.db, which
  the tray's Restore menu lists like any other backup), then each pending migration runs in order,
  with schema.sql replayed and user_version bumped after each one commits. Every existing database
  starts at version 0, whatever hand-run tools/migrate_* scripts it did or didn't get; migrations
  1-26 are those scripts, all idempotent, so each one either does its work or skips it.
- **A migration fails**: the backup is copied back over the database and MigrationError is raised.
  Callers must not start the app on top of it: a half-migrated database is worse than a stopped
  app (ADR 0059).
- **Newer than this build** (e.g. after installing an older version over a newer one):
  MigrationError, nothing touched. This build doesn't know that schema.

Output from migrations goes to data/logs/migrations.log.
"""
from __future__ import annotations

import contextlib
import os
import sqlite3
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from db.migrations import LATEST_VERSION, MIGRATIONS, SEEDS
from db.migrations._common import SCHEMA_PATH

# Another process already migrating? Wait for it, up to this long, before giving up.
_LOCK_WAIT_SECONDS = 600
# A lock file older than this is from a process that died mid-run; take it over.
_STALE_LOCK_SECONDS = 900
_LOCK_POLL_SECONDS = 0.5


class MigrationError(RuntimeError):
    """The database couldn't be brought up to date; the app must not start."""


def run_migrations() -> int:
    """Apply any pending migrations. Returns how many ran (0 for a fresh or current database).

    Raises MigrationError if the database can't be brought up to date. When a migration itself
    failed, the database has already been restored from the pre-migration backup by then.
    """
    import db.db as db_module  # read DB_PATH at call time; tests point it at a temp file

    db_path: Path = db_module.DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with _exclusive_lock(db_path.parent / "migrating.lock"):
        if _is_fresh(db_path):
            _create_fresh(db_path)
            return 0

        version = _user_version(db_path)
        if version > LATEST_VERSION:
            raise MigrationError(
                f"The database is from a newer version of Husbandry Tracker (schema version {version}; "
                f"this version only knows up to {LATEST_VERSION}). Install the newer version again, "
                "or restore a backup made by this one."
            )
        pending = [m for m in MIGRATIONS if m[0] > version]
        if not pending:
            return 0

        backup_path = _premigration_backup_path(db_path)
        try:
            db_module.backup_database(backup_path)
        except Exception as exc:
            raise MigrationError(
                f"Couldn't back up the database before upgrading it, so nothing was changed: {exc}"
            ) from exc

        with _migration_log(db_path) as log:
            print(f"Database at schema version {version}; applying {len(pending)} migration(s). "
                  f"Backup: {backup_path}", file=log)
            for number, name, migrate in pending:
                print(f"[{number}] {name}", file=log)
                try:
                    with contextlib.redirect_stdout(log):
                        _apply(db_path, number, migrate)
                except Exception as exc:
                    print(f"[{number}] FAILED: {exc!r}; restoring {backup_path.name}", file=log)
                    _restore(backup_path, db_path)
                    raise MigrationError(
                        f"Upgrading the database failed at migration {number} ({name}): {exc}\n\n"
                        f"The database was restored from {backup_path.name}, so no data was lost. "
                        f"Details are in {log.name}."
                    ) from exc
            print(f"Done; now at schema version {LATEST_VERSION}.", file=log)
        return len(pending)


def _apply(db_path: Path, number: int, migrate) -> None:
    # A plain connection, as the old tools/migrate_* scripts used: no foreign_keys = ON, since
    # table-rebuild migrations turn foreign keys off themselves and that only works outside a
    # transaction. `with conn` commits on success and rolls back on an exception, same as their main().
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        with conn:
            migrate(conn)
        conn.executescript(SCHEMA_PATH.read_text())
        conn.execute(f"PRAGMA user_version = {int(number)}")
        conn.commit()
    finally:
        conn.close()


def _is_fresh(db_path: Path) -> bool:
    if not db_path.exists():
        return True
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        (tables,) = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()
    finally:
        conn.close()
    return tables == 0


def _create_fresh(db_path: Path) -> None:
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA_PATH.read_text())
        for seed in SEEDS:  # seed data that, on an existing database, a migration adds
            seed(conn)
        conn.execute(f"PRAGMA user_version = {LATEST_VERSION}")
        conn.commit()
    finally:
        conn.close()


def _user_version(db_path: Path) -> int:
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        (version,) = conn.execute("PRAGMA user_version").fetchone()
    finally:
        conn.close()
    return version


def _premigration_backup_path(db_path: Path) -> Path:
    # Same naming as ingest.py's backups (husbandrytracker-<YYYYMMDD>-<HHMMSS>-<reason>.db), so the
    # tray's Restore menu lists and labels it and ingest's retention pruning eventually removes it.
    backup_dir = db_path.parent / "backups"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = backup_dir / f"husbandrytracker-{stamp}-premigration.db"
    suffix = 1
    while path.exists():
        path = backup_dir / f"husbandrytracker-{stamp}-premigration-{suffix}.db"
        suffix += 1
    return path


def _restore(backup_path: Path, db_path: Path) -> None:
    # Online Backup API in reverse: overwrites every page of the live file with the backup's, which
    # is safe even if some other process happens to hold a connection, unlike a raw file copy.
    source = sqlite3.connect(backup_path)
    dest = sqlite3.connect(db_path, timeout=30)
    try:
        source.backup(dest)
    finally:
        source.close()
        dest.close()


@contextlib.contextmanager
def _migration_log(db_path: Path) -> Iterator:
    log_dir = db_path.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(log_dir / "migrations.log", "a", encoding="utf-8", errors="replace") as log:
        print(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} (pid {os.getpid()}) ===", file=log)
        yield log


@contextlib.contextmanager
def _exclusive_lock(lock_path: Path) -> Iterator[None]:
    """Cross-process mutex via an exclusively-created file, so two processes started together
    without the Supervisor (e.g. Website and Ingest by hand) can't migrate at once. The loser waits,
    then finds nothing pending."""
    deadline = time.monotonic() + _LOCK_WAIT_SECONDS
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > _STALE_LOCK_SECONDS:
                    lock_path.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() > deadline:
                raise MigrationError(
                    f"Another Husbandry Tracker process has been upgrading the database for over "
                    f"{_LOCK_WAIT_SECONDS // 60} minutes. If none is running, delete {lock_path} and start again."
                )
            time.sleep(_LOCK_POLL_SECONDS)
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        lock_path.unlink(missing_ok=True)
