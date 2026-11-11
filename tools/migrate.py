"""Apply pending schema migrations by hand (RHA-101; ADR 0059).

Normally unnecessary: the Supervisor runs them automatically before starting anything, and every
process's init_db() does too. Useful after pulling new code while the app is stopped, or to see a
failure's message directly. Stop Husbandry Tracker first.

Run: .venv/Scripts/python.exe tools/migrate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.db import DB_PATH  # noqa: E402
from db.migrate import MigrationError, run_migrations  # noqa: E402
from db.migrations import LATEST_VERSION  # noqa: E402


def main() -> int:
    try:
        applied = run_migrations()
    except MigrationError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    if applied:
        print(f"Applied {applied} migration(s); {DB_PATH} is at schema version {LATEST_VERSION}.")
    else:
        print(f"{DB_PATH} is already at schema version {LATEST_VERSION}; nothing to do.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
