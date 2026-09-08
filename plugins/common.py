"""Shared helpers for this repo's built-in Plugins (see CONTEXT.md: Plugin; ADR 0013) — writing
Plugin Events to the Inbox, reading a Plugin's own Registry export, and reading its own Outbox of
pending Commands (see CONTEXT.md: Command, Outbox; ADR 0014). A third-party Plugin in another
language re-implements this itself; it's convenience shared between the two Plugins that happen to
live in this repo, not part of the Plugin/Ingest contract.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import jsonschema

REPO_ROOT = Path(__file__).resolve().parent.parent
INBOX_DIR = REPO_ROOT / "data" / "inbox"
REGISTRY_DIR = REPO_ROOT / "data" / "registry"
OUTBOX_DIR = REPO_ROOT / "data" / "outbox"
_COMMAND_SCHEMA_PATH = REPO_ROOT / "schemas" / "plug_command.schema.json"

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


@lru_cache(maxsize=1)
def _command_validator() -> jsonschema.Draft202012Validator:
    schema = json.loads(_COMMAND_SCHEMA_PATH.read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


def take_command(plugin: str, external_id: str) -> dict | None:
    """Reads and removes this Plugin's pending Command for one device from the Outbox (see
    CONTEXT.md: Command, Outbox; ADR 0014), if one exists — at most one file ever sits there per
    (plugin, external_id), since Core overwrites rather than queues (see web/outbox.py's
    write_command). Returns None if there's nothing pending.

    A missing, mid-write, corrupt, or schema-invalid file is all treated the same as nothing
    pending, same tolerance read_registry already gives a missing Registry file — Core's next
    write simply tries again, and a malformed file (never expected from Core's own writer, but
    cheap to guard regardless — same instinct as Ingest quarantining a bad Inbox event) is removed
    rather than retried forever."""
    safe_id = _UNSAFE_FILENAME_CHARS.sub("_", external_id)
    path = OUTBOX_DIR / plugin / f"{safe_id}.json"
    if not path.exists():
        return None
    try:
        command = json.loads(path.read_text(encoding="utf-8"))
        _command_validator().validate(command)
    except (json.JSONDecodeError, jsonschema.ValidationError) as exc:
        print(f"[{plugin}] dropping unreadable Command for {external_id}: {exc}")
        path.unlink(missing_ok=True)
        return None
    path.unlink(missing_ok=True)
    return command
