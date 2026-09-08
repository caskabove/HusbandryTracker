"""The tuya_lan Plugin's identity convention — see CONTEXT.md: Plugin, External ID, Plugin Config;
ADR 0013. A Tuya device's External ID packs its device_id and switch_dps_key together, since a
multi-outlet power strip exposes several independently-switched Plugs on one device_id (see
db/schema.sql's comment on `plug`); its Plugin Config carries the local_key/ip_address needed to
actually reach it over LAN.
"""
from __future__ import annotations

import json

PLUGIN_NAME = "tuya_lan"

_SEPARATOR = ":"


def encode_external_id(device_id: str, switch_dps_key: str | None) -> str:
    return f"{device_id}{_SEPARATOR}{switch_dps_key or '1'}"


def decode_external_id(external_id: str) -> tuple[str, str]:
    device_id, _, dps_key = external_id.partition(_SEPARATOR)
    return device_id, dps_key or "1"


def pack_config(local_key: str | None, ip_address: str | None) -> str | None:
    if not local_key:
        return None
    return json.dumps({"local_key": local_key, "ip_address": ip_address or None})


def unpack_config(plugin_config: str | dict | None) -> dict:
    """Accepts either shape Plugin Config actually arrives in: a raw JSON string straight from the
    `plug.plugin_config` DB column, or an already-parsed dict the way it appears inside a Registry
    export (see CONTEXT.md: Registry — Ingest embeds it as a real JSON object there, not a
    double-encoded string, so a Plugin reading the Registry file doesn't have to re-parse JSON
    inside JSON)."""
    if not plugin_config:
        return {"local_key": None, "ip_address": None}
    data = plugin_config if isinstance(plugin_config, dict) else json.loads(plugin_config)
    return {"local_key": data.get("local_key"), "ip_address": data.get("ip_address")}
