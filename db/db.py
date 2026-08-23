"""Shared SQLite access for every HerpMonitor process (collectors, tools, and later the web app).

All processes point at the same file, so this is the one place connection settings live.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "herpmonitor.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

_OPEN_RETRIES = 3
_OPEN_RETRY_DELAY_SECONDS = 0.2


def get_connection() -> sqlite3.Connection:
    """Open a connection configured for multiple local processes writing concurrently.

    Retries a couple times on OperationalError: confirmed live that the bind-mounted db file
    (host collector + this container both touching it) occasionally throws "unable to open
    database file" for an instant under concurrent access, even in DELETE journal mode. It clears
    on its own within milliseconds — a short retry is simpler and more honest than pretending it
    can't happen.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    last_error: sqlite3.OperationalError | None = None
    for attempt in range(_OPEN_RETRIES):
        try:
            conn = sqlite3.connect(DB_PATH, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            # NOT WAL: WAL needs shared-memory mmap, which Docker Desktop's Windows<->container
            # bind-mount bridge doesn't support reliably — confirmed live (sqlite3.OperationalError:
            # disk I/O error) the moment the web container tried to open the bind-mounted db file in
            # WAL mode. DELETE mode's brief writer-blocks-reader window during commit is a non-issue
            # at our write volume (a handful of inserts/minute across all sensors).
            conn.execute("PRAGMA journal_mode = DELETE")
            return conn
        except sqlite3.OperationalError as exc:
            last_error = exc
            if attempt < _OPEN_RETRIES - 1:
                time.sleep(_OPEN_RETRY_DELAY_SECONDS)
    raise last_error


def init_db() -> None:
    """Create tables if they don't exist yet. Safe to call on every process startup."""
    with get_connection() as conn:
        conn.executescript(SCHEMA_PATH.read_text())


if __name__ == "__main__":
    init_db()
    print(f"Initialized database at {DB_PATH}")
