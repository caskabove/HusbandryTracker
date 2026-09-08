"""Core's write side of the Outbox — see CONTEXT.md: Outbox, Command; ADR 0014.

Deliberately self-contained rather than importing plugins/common.py's OUTBOX_DIR/write helpers:
that module's own docstring scopes it to Plugin-role convenience (reading a Registry/Outbox,
writing to the Inbox), not Core's. ingest/ingest.py already keeps its own local
_atomic_write_json() rather than sharing plugins/common.py's, for the same reason — each process's
own half of a filesystem contract stays independently readable, the same way a third-party Plugin
in another language would never import this file either.

Only writes the Outbox file itself — the plug_command_log DB row, the Interruption determination,
and the Auto-Update-resume side effect (see ADR 0014) are the caller's job, not this module's. See
web/admin_queries.py for where those get wired in.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTBOX_DIR = REPO_ROOT / "data" / "outbox"

_UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')


def _now_requested_at() -> str:
    """UTC timestamp formatted exactly like SQLite's datetime('now') — see
    schemas/plug_command.schema.json's requested_at pattern for why this exact shape matters."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".tmp-{os.getpid()}-{os.urandom(4).hex()}")
    tmp_path.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp_path, path)  # atomic on both POSIX and Windows


def write_command(plugin: str, external_id: str, is_on: bool, request_id: int | None = None) -> None:
    """Drops (or overwrites) one set_power Command file into data/outbox/<plugin>/ for that Plugin
    to pick up on its own poll cadence — see CONTEXT.md: Command, Outbox; ADR 0014. Fixed filename
    per external_id, not timestamped like an Inbox event: a second call before the Plugin gets to
    the first simply overwrites it, since only the latest desired state matters — Commands don't
    queue. Only a Smart Plug (tracking_mode = 'smart') has a plugin/external_id to call this with
    at all; a Manual Plug's Command never reaches this module — see ADR 0014."""
    command = {
        "schema_version": 1,
        "plugin": plugin,
        "external_id": external_id,
        "command": "set_power",
        "requested_at": _now_requested_at(),
        "request_id": request_id,
        "payload": {"is_on": is_on},
    }
    safe_id = _UNSAFE_FILENAME_CHARS.sub("_", external_id)
    _atomic_write_json(OUTBOX_DIR / plugin / f"{safe_id}.json", command)
