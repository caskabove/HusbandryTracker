"""Shared helpers for this repo's built-in Plugins (see CONTEXT.md: Plugin; ADR 0013) — writing
Plugin Events to the Inbox, and reading a Plugin's own Registry export. A third-party Plugin in
another language re-implements this itself; it's convenience shared between the two Plugins that
happen to live in this repo, not part of the Plugin/Ingest contract.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INBOX_DIR = REPO_ROOT / "data" / "inbox"
REGISTRY_DIR = REPO_ROOT / "data" / "registry"

_UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')


def now_observed_at() -> str:
    """UTC timestamp formatted exactly like SQLite's datetime('now') — see
    schemas/plugin_event.schema.json's observed_at pattern for why this exact shape matters."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".tmp-{os.getpid()}-{os.urandom(4).hex()}")
    tmp_path.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp_path, path)  # atomic on both POSIX and Windows


def write_event(plugin: str, external_id: str, kind: str, payload: dict, observed_at: str | None = None) -> None:
    """Drops one Plugin Event JSON file into data/inbox/<kind>/ — see CONTEXT.md: Plugin Event,
    Inbox; schemas/plugin_event.schema.json. observed_at defaults to now; pass it explicitly when
    the observation happened slightly before the write (rare for these two Plugins)."""
    event = {
        "schema_version": 1,
        "plugin": plugin,
        "kind": kind,
        "external_id": external_id,
        "observed_at": observed_at or now_observed_at(),
        "payload": payload,
    }
    safe_id = _UNSAFE_FILENAME_CHARS.sub("_", external_id)
    filename = f"{plugin}__{safe_id}__{time.time_ns()}_{os.urandom(3).hex()}.json"
    _atomic_write_json(INBOX_DIR / kind / filename, event)


def read_registry(plugin: str) -> list[dict]:
    """Reads this Plugin's Registry export (see CONTEXT.md: Registry) — a list of
    {external_id, plugin_config, auto_update_enabled}. Missing file (nothing registered yet, or
    Ingest hasn't run since the last device was removed) is treated the same as an empty list."""
    path = REGISTRY_DIR / f"{plugin}.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []  # a mid-write read; Ingest writes atomically, so this should be rare/transient
