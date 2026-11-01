"""Discovers and (de)activates Plugins that follow the Plugin Contract (see CONTEXT.md: Plugin
Contract; ADR 0045) — a manifest.json, an init.py, and the Plugin's own implementation file,
all under plugins/<name>/. "Available" is just scanning plugins/ for folders with a manifest.json;
`tuya_lan`/`govee_ble` are deliberately not retrofitted onto this contract yet (ADR 0045), so they
have no manifest.json and never show up here — that's expected, not a bug, until that separate
migration happens.

Activation is one atomic action from the caller's point of view: a Plugin's own init.activate()
runs first, synchronously, and only on success does its name actually get added to
active_plugins.json — never a state where a Plugin is listed Active but its init never ran (ADR
0045). Deactivation is the mirror: init.deactivate() runs first, then the name is removed.
"""
from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path

from active_plugins import read_active_plugins, write_active_plugins
from app_paths import APP_ROOT

PLUGINS_DIR = APP_ROOT / "plugins"


@dataclass
class PluginInfo:
    name: str
    description: str
    kind: str  # "device" or "skill" — see manifest.json's own "kind" field
    active: bool


def _read_manifest(plugin_dir: Path) -> dict | None:
    manifest_path = plugin_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def list_plugins() -> list[PluginInfo]:
    """Every plugins/<name>/ folder with a readable manifest.json, newest-discovered-last isn't
    meaningful here so this is alphabetical by name for a stable Admin listing."""
    if not PLUGINS_DIR.is_dir():
        return []
    active = set(read_active_plugins())
    found: list[PluginInfo] = []
    for plugin_dir in sorted(PLUGINS_DIR.iterdir()):
        if not plugin_dir.is_dir():
            continue
        manifest = _read_manifest(plugin_dir)
        if manifest is None:
            continue
        found.append(PluginInfo(
            name=manifest.get("name", plugin_dir.name),
            description=manifest.get("description", ""),
            kind=manifest.get("kind", "device"),
            active=manifest.get("name", plugin_dir.name) in active,
        ))
    return found


def _load_init(name: str):
    if not (PLUGINS_DIR / name / "manifest.json").exists():
        raise ValueError(f"No such Plugin: {name!r}")
    try:
        return importlib.import_module(f"plugins.{name}.init")
    except ModuleNotFoundError:
        raise ValueError(f"Plugin {name!r} has no init.py — it can't be activated/deactivated yet.")


def activate_plugin(name: str) -> None:
    init = _load_init(name)
    init.activate()  # runs first — see this module's own docstring for why
    names = read_active_plugins()
    if name not in names:
        write_active_plugins([*names, name])


def deactivate_plugin(name: str) -> None:
    init = _load_init(name)
    init.deactivate()
    names = [n for n in read_active_plugins() if n != name]
    write_active_plugins(names)
