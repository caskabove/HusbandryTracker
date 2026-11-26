"""Plugin Settings and Known Devices — the database half of each Plugin's Settings page (see
CONTEXT.md: Plugin Setting, Known Device; docs/plugin-standard.md; ADR 0061).

Nothing here is vendor-specific: a Plugin's settings fields come from its own manifest.json, and a
Known Device's external_id/plugin_config are as opaque here as they are on sensor/plug.
"""
from __future__ import annotations

import json

from db.db import get_connection


# --- Plugin Settings -----------------------------------------------------------------------------

def get_plugin_settings(plugin: str) -> dict[str, str]:
    """Every saved value for one Plugin, secrets included — for passing to its discover() only.
    Never render this dict into a page; use public_plugin_settings() for that."""
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM plugin_setting WHERE plugin = ?", (plugin,)).fetchall()
    return {row["key"]: row["value"] for row in rows}


def public_plugin_settings(plugin: str, fields: list[dict]) -> dict[str, dict]:
    """Per-field view for the Settings page: {key: {"value": shown value, "is_set": bool}}. A
    secret's value is always "" here — only whether one is saved."""
    saved = get_plugin_settings(plugin)
    view = {}
    for f in fields:
        value = saved.get(f["key"])
        is_set = bool(value)
        if f["type"] == "secret":
            shown = ""
        else:
            shown = value if value is not None else f.get("default", "")
        view[f["key"]] = {"value": shown, "is_set": is_set}
    return view


def save_plugin_settings(plugin: str, fields: list[dict], submitted: dict[str, str],
                         clear_secrets: set[str] = frozenset()) -> None:
    """Saves one Settings-page form submission. Only keys declared in the manifest's settings are
    written. A blank secret keeps whatever's already saved (the form never echoes it back, so a
    blank can't mean "erase") unless its key is in clear_secrets; a blank text field clears it; a
    select must be one of its declared options."""
    with get_connection() as conn:
        for f in fields:
            key, kind = f["key"], f["type"]
            value = (submitted.get(key) or "").strip()
            if kind == "secret":
                if key in clear_secrets:
                    conn.execute("DELETE FROM plugin_setting WHERE plugin = ? AND key = ?", (plugin, key))
                    continue
                if not value:
                    continue
            if kind == "select":
                allowed = {o["value"] for o in f["options"]}
                if value not in allowed:
                    raise ValueError(f"{f['label']} must be one of: {', '.join(sorted(allowed))}.")
            if value:
                conn.execute(
                    "INSERT INTO plugin_setting (plugin, key, value) VALUES (?, ?, ?) "
                    "ON CONFLICT (plugin, key) DO UPDATE SET value = excluded.value",
                    (plugin, key, value),
                )
            else:
                conn.execute("DELETE FROM plugin_setting WHERE plugin = ? AND key = ?", (plugin, key))


# --- Known Devices -------------------------------------------------------------------------------

def _registered_rows(conn, plugin: str) -> dict[str, dict]:
    """{external_id: {"type", "id", "label", "edit_url"}} for every Sensor/Plug already registered on this
    Plugin — the source of truth for a registered device's name."""
    found = {}
    for row in conn.execute(
        "SELECT id, label, external_id, room_id FROM sensor WHERE plugin = ? AND external_id IS NOT NULL", (plugin,)
    ):
        edit = f"/admin/room-sensors/{row['id']}/edit" if row["room_id"] is not None else f"/admin/sensors/{row['id']}/edit"
        found[row["external_id"]] = {"type": "sensor", "id": row["id"], "label": row["label"], "edit_url": edit}
    for row in conn.execute(
        "SELECT id, label, external_id FROM plug WHERE plugin = ? AND external_id IS NOT NULL", (plugin,)
    ):
        found[row["external_id"]] = {"type": "plug", "id": row["id"], "label": row["label"],
                                     "edit_url": f"/admin/plugs/{row['id']}/edit"}
    return found


def list_known_devices(plugin: str) -> list[dict]:
    """Every named device for one Plugin, plus every registered Sensor/Plug on it that was never
    named here (so the Settings page is the one place every device can be renamed). Each dict:
    external_id, name, summary, last_seen_at, plugin_config (decoded), registered (None or
    {"type", "id", "label"}). A registered device's name is its Sensor/Plug label."""
    with get_connection() as conn:
        registered = _registered_rows(conn, plugin)
        rows = conn.execute(
            "SELECT external_id, name, plugin_config, summary, last_seen_at FROM known_device WHERE plugin = ?",
            (plugin,),
        ).fetchall()
    devices = {}
    for row in rows:
        reg = registered.get(row["external_id"])
        devices[row["external_id"]] = {
            "external_id": row["external_id"],
            "name": reg["label"] if reg else row["name"],
            "summary": row["summary"],
            "last_seen_at": row["last_seen_at"],
            "plugin_config": json.loads(row["plugin_config"]) if row["plugin_config"] else None,
            "registered": reg,
        }
    for external_id, reg in registered.items():
        devices.setdefault(external_id, {
            "external_id": external_id, "name": reg["label"], "summary": None, "last_seen_at": None,
            "plugin_config": None, "registered": reg,
        })
    return sorted(devices.values(), key=lambda d: d["name"].lower())


def save_known_device(plugin: str, external_id: str, name: str, plugin_config: dict | None = None,
                      summary: str | None = None, seen: bool = False) -> None:
    """Names (or renames) one device. If it's already registered as a Sensor/Plug, that row's label
    is renamed too, so the name reads the same everywhere. plugin_config/summary are only
    overwritten when given — renaming from the saved list doesn't erase what a scan recorded."""
    name = (name or "").strip()
    external_id = (external_id or "").strip()
    if not name:
        raise ValueError("Give the device a name.")
    if not external_id:
        raise ValueError("Missing device ID.")
    config_json = json.dumps(plugin_config) if plugin_config else None
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO known_device (plugin, external_id, name, plugin_config, summary, last_seen_at)
               VALUES (?, ?, ?, ?, ?, CASE WHEN ? THEN datetime('now') END)
               ON CONFLICT (plugin, external_id) DO UPDATE SET
                   name = excluded.name,
                   plugin_config = COALESCE(excluded.plugin_config, known_device.plugin_config),
                   summary = COALESCE(excluded.summary, known_device.summary),
                   last_seen_at = COALESCE(excluded.last_seen_at, known_device.last_seen_at)""",
            (plugin, external_id, name, config_json, summary, 1 if seen else 0),
        )
        reg = _registered_rows(conn, plugin).get(external_id)
        if reg:
            conn.execute(f"UPDATE {reg['type']} SET label = ? WHERE id = ?", (name, reg["id"]))


def forget_known_device(plugin: str, external_id: str) -> None:
    """Removes a name from the list. Never touches a registered Sensor/Plug — it just stops being
    offered on Add forms (a registered one keeps showing on the Settings page by its label)."""
    with get_connection() as conn:
        conn.execute("DELETE FROM known_device WHERE plugin = ? AND external_id = ?", (plugin, external_id))


def unregistered_known_devices(plugin: str) -> list[dict]:
    """Named devices not yet registered as a Sensor/Plug — what an Add form offers to pick from."""
    return [d for d in list_known_devices(plugin) if d["registered"] is None]
