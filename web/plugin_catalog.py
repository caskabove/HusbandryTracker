"""Discovers, validates, and (de)activates Plugins — see docs/plugin-standard.md, CONTEXT.md: Plugin
Contract, Plugin Standard; ADR 0045/0061.

"Available" is scanning plugins/ for Plugin-shaped folders. Every one is checked against the Plugin
Standard (schemas/plugin_manifest.schema.json plus the required files) on every listing; one that
fails is still listed — as Invalid, with its reasons — so a half-written Plugin is visible in Admin
instead of silently missing, but it can't be activated until it conforms.

Activation is one atomic action from the caller's point of view: a Plugin's own init.activate()
runs first, synchronously, and only on success does its name actually get added to
active_plugins.json — never a state where a Plugin is listed Active but its init never ran (ADR
0045). Deactivation is the mirror: init.deactivate() runs first, then the name is removed.
"""
from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import jsonschema

from active_plugins import read_active_plugins, write_active_plugins
from app_paths import APP_ROOT

PLUGINS_DIR = APP_ROOT / "plugins"
_MANIFEST_SCHEMA_PATH = APP_ROOT / "schemas" / "plugin_manifest.schema.json"

# A folder counts as an attempted Plugin (and so gets validated and listed, Invalid or not) if it
# has any one of these — enough to catch a half-written Plugin without listing helper packages.
_PLUGIN_MARKERS = ("manifest.json", "init.py", "plugin.py")


@dataclass
class PluginInfo:
    name: str
    display_name: str
    description: str
    kind: str  # "device" or "skill"
    active: bool
    version: str = ""
    how_it_works: str = ""
    can: list[str] = field(default_factory=list)
    cannot: list[str] = field(default_factory=list)
    device_types: list[str] = field(default_factory=list)
    discovery: dict | None = None
    settings: list[dict] = field(default_factory=list)
    setup_help: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


@lru_cache(maxsize=1)
def _manifest_validator() -> jsonschema.Draft202012Validator:
    schema = json.loads(_MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


def validate_plugin_dir(plugin_dir: Path) -> tuple[dict, list[str]]:
    """Checks one plugins/<name>/ folder against the Plugin Standard. Returns the manifest (empty if
    unreadable) and a list of human-readable problems — empty means it conforms. Never imports the
    Plugin's code: listing Admin's Plugins card must not run anything a Plugin ships."""
    manifest_path = plugin_dir / "manifest.json"
    if not manifest_path.exists():
        return {}, ["missing manifest.json"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, [f"manifest.json isn't valid JSON ({exc.msg}, line {exc.lineno})"]
    if not isinstance(manifest, dict):
        return {}, ["manifest.json must be a JSON object"]

    errors = []
    for error in sorted(_manifest_validator().iter_errors(manifest), key=lambda e: list(e.absolute_path)):
        where = ".".join(str(p) for p in error.absolute_path) or "manifest"
        errors.append(f"manifest.json {where}: {error.message}")

    if manifest.get("name") and manifest["name"] != plugin_dir.name:
        errors.append(f"manifest.json name {manifest['name']!r} must match its folder name {plugin_dir.name!r}")
    if not (plugin_dir / "__init__.py").exists():
        errors.append("missing __init__.py (the folder must be an importable package)")
    if not (plugin_dir / "init.py").exists():
        errors.append("missing init.py (activate()/deactivate() hooks)")
    entry_point = manifest.get("entry_point")
    if isinstance(entry_point, str) and entry_point and not (plugin_dir / entry_point).exists():
        errors.append(f"entry_point {entry_point!r} doesn't exist")
    if manifest.get("discovery") and not (plugin_dir / "discover.py").exists():
        errors.append("manifest.json declares discovery but discover.py is missing")
    if (plugin_dir / "discover.py").exists() and not manifest.get("discovery"):
        errors.append("discover.py exists but manifest.json has no discovery section")
    setting_keys = {s.get("key") for s in manifest.get("settings", []) if isinstance(s, dict)}
    for key in (manifest.get("discovery") or {}).get("requires_settings", []):
        if key not in setting_keys:
            errors.append(f"discovery.requires_settings names {key!r}, which isn't one of this Plugin's settings")
    return manifest, errors


def _plugin_info(plugin_dir: Path, active: set[str]) -> PluginInfo:
    manifest, errors = validate_plugin_dir(plugin_dir)
    name = plugin_dir.name
    return PluginInfo(
        name=name,
        display_name=manifest.get("display_name") or name,
        description=manifest.get("description", ""),
        kind=manifest.get("kind", "device"),
        active=name in active,
        version=manifest.get("version", ""),
        how_it_works=manifest.get("how_it_works", ""),
        can=list(manifest.get("can", [])),
        cannot=list(manifest.get("cannot", [])),
        device_types=list(manifest.get("device_types", [])),
        discovery=manifest.get("discovery"),
        settings=list(manifest.get("settings", [])),
        setup_help=list(manifest.get("setup_help", [])),
        errors=errors,
    )


def _plugin_dirs() -> list[Path]:
    if not PLUGINS_DIR.is_dir():
        return []
    return [
        d for d in sorted(PLUGINS_DIR.iterdir())
        if d.is_dir() and not d.name.startswith(("_", ".")) and any((d / m).exists() for m in _PLUGIN_MARKERS)
    ]


def list_plugins() -> list[PluginInfo]:
    """Every Plugin-shaped folder under plugins/, valid or not, alphabetical by folder name."""
    active = set(read_active_plugins())
    return [_plugin_info(d, active) for d in _plugin_dirs()]


def get_plugin(name: str) -> PluginInfo | None:
    plugin_dir = PLUGINS_DIR / name
    if not name or "/" in name or "\\" in name or name.startswith(("_", ".")) or plugin_dir not in _plugin_dirs():
        return None
    return _plugin_info(plugin_dir, set(read_active_plugins()))


def _require(name: str) -> PluginInfo:
    plugin = get_plugin(name)
    if plugin is None:
        raise ValueError(f"No such Plugin: {name!r}")
    return plugin


def activate_plugin(name: str) -> None:
    plugin = _require(name)
    if not plugin.valid:
        raise ValueError(f"{name} doesn't meet the Plugin Standard, so it can't be activated: " + "; ".join(plugin.errors))
    init = importlib.import_module(f"plugins.{name}.init")
    init.activate()  # runs first — see this module's own docstring for why
    names = read_active_plugins()
    if name not in names:
        write_active_plugins([*names, name])


def deactivate_plugin(name: str) -> None:
    """Allowed even for an Invalid Plugin, so a broken one can always be switched off — its init's
    deactivate() runs only if it actually has one."""
    _require(name)
    if (PLUGINS_DIR / name / "init.py").exists():
        importlib.import_module(f"plugins.{name}.init").deactivate()
    write_active_plugins([n for n in read_active_plugins() if n != name])


def _discover_module(name: str):
    plugin = _require(name)
    if not plugin.valid or not plugin.discovery:
        raise ValueError(f"{name} doesn't support device discovery.")
    return importlib.import_module(f"plugins.{name}.discover")


async def run_discovery(name: str, settings: dict[str, str]) -> list[dict]:
    """Runs a Plugin's discover.discover(settings). Any exception it raises carries a message meant
    to be shown to the user as-is (see docs/plugin-standard.md)."""
    return await _discover_module(name).discover(settings)


def registration_fields(name: str, external_id: str, plugin_config: dict | None) -> dict[str, str]:
    """The Add Sensor/Add Plug form fields for one Known Device — from the Plugin's own optional
    discover.registration_fields(); empty if it doesn't provide one."""
    module = _discover_module(name)
    hook = getattr(module, "registration_fields", None)
    return hook(external_id, plugin_config) if hook else {}
