"""Shared pytest fixtures for the JSON contract tests (plugins/test_common.py,
ingest/test_ingest.py, web/test_outbox.py, tests/test_json_contract_roundtrip.py).

Both fixtures monkeypatch module-level Path constants rather than passing paths as
arguments, because that's how the app itself is wired (plugins/common.py, ingest/ingest.py,
web/outbox.py, and db/db.py all hardcode their own paths at import time) — see each
module's docstring. ingest/ingest.py additionally derives REJECTED_DIR = INBOX_DIR /
"_rejected" once at import time, so redirecting INBOX_DIR alone would leave REJECTED_DIR
pointed at the real data/inbox/_rejected; json_dirs patches it separately for that reason.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


@pytest.fixture()
def json_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Redirects every process's view of data/inbox, data/registry, data/outbox to a private
    tmp_path tree, so no test can read or write anything under the repo's real data/ directory."""
    inbox_dir = tmp_path / "inbox"
    registry_dir = tmp_path / "registry"
    outbox_dir = tmp_path / "outbox"
    rejected_dir = inbox_dir / "_rejected"

    import plugins.common as plugins_common
    monkeypatch.setattr(plugins_common, "INBOX_DIR", inbox_dir)
    monkeypatch.setattr(plugins_common, "REGISTRY_DIR", registry_dir)
    monkeypatch.setattr(plugins_common, "OUTBOX_DIR", outbox_dir)

    import ingest.ingest as ingest_module
    monkeypatch.setattr(ingest_module, "INBOX_DIR", inbox_dir)
    monkeypatch.setattr(ingest_module, "REGISTRY_DIR", registry_dir)
    monkeypatch.setattr(ingest_module, "REJECTED_DIR", rejected_dir)

    import web.outbox as web_outbox
    monkeypatch.setattr(web_outbox, "OUTBOX_DIR", outbox_dir)

    return {"inbox": inbox_dir, "registry": registry_dir, "outbox": outbox_dir, "rejected": rejected_dir}


@pytest.fixture()
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> sqlite3.Connection:
    """Points db.db.DB_PATH at a private tmp_path file and initializes it from the real
    db/schema.sql, so ingest._apply_event's own get_connection() calls (it opens a fresh
    connection per DB operation, so an in-memory ":memory:" database wouldn't survive between
    them) land in an isolated file instead of the real data/herpmonitor.db."""
    import db.db as db_module
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")
    db_module.init_db()
    conn = db_module.get_connection()
    try:
        yield conn
    finally:
        conn.close()
