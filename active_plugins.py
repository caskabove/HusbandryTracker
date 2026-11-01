"""The Active Plugin list — see CONTEXT.md: Active Plugin; ADR 0045. A plain JSON array of
currently-Active Plugin names at `data/active_plugins.json`, owned and written by Core (the web
app's Admin "Plugins" card, or a Setup Wizard step) rather than hand-edited, even though nothing
stops a user from hand-editing it directly — same as every other half of this app's filesystem
contracts. A missing or empty file means no Plugin is Active, deliberately not "everything is
Active."

Shared between web (writes it) and ingest (reads it) — neither `plugins/` nor `ingest/` nor `web/`
is the right home for something both sides need, so it lives at the repo root next to app_paths.py,
the other cross-cutting path module everything already imports from.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from app_paths import APP_ROOT

ACTIVE_PLUGINS_PATH = APP_ROOT / "data" / "active_plugins.json"


def read_active_plugins() -> list[str]:
    """A missing or corrupt file is treated the same as an empty list — see this module's own
    docstring for why missing never means "everything is Active." A mid-write read (another process
    writing concurrently) is the only realistic way this gets corrupt, given _write below is
    atomic; same tolerance plugins/common.py's read_registry() already gives a missing/corrupt
    Registry file."""
    if not ACTIVE_PLUGINS_PATH.exists():
        return []
    try:
        names = json.loads(ACTIVE_PLUGINS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return [name for name in names if isinstance(name, str)]


def _atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".tmp-{os.getpid()}-{os.urandom(4).hex()}")
    tmp_path.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp_path, path)  # atomic on both POSIX and Windows


def write_active_plugins(names: list[str]) -> None:
    _atomic_write_json(ACTIVE_PLUGINS_PATH, names)


def is_plugin_active(name: str) -> bool:
    return name in read_active_plugins()
