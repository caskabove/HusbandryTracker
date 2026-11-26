"""tuya_lan's discovery hook — see docs/plugin-standard.md (discover.py), CONTEXT.md: Known Device;
ADR 0061. Runs inside the web process when someone clicks this Plugin's Scan button on its Settings
page. Asks Tuya's cloud (with the Access ID/Secret saved as this Plugin's settings) which devices
are linked to the user's account — the only place a plug's local key lives — via
web/tuya_discover.py, the same lookup the Add Plug form's Discover Devices button already uses.
"""
from __future__ import annotations

from plugins.tuya_lan.identity import decode_external_id, encode_external_id


async def discover(settings: dict[str, str]) -> list[dict]:
    from web.tuya_discover import discover_tuya  # imported lazily: only the web process calls this

    access_id = settings.get("access_id")
    access_secret = settings.get("access_secret")
    if not access_id or not access_secret:
        raise RuntimeError("Save your Tuya Cloud Access ID and Access Secret below first.")
    found = []
    for device in await discover_tuya(access_id, access_secret, settings.get("api_region") or "us"):
        found.append({
            "external_id": encode_external_id(device["id"], device.get("switch_key_guess")),
            "suggested_name": device["name"],
            "summary": (device.get("category") or "device")
                       + ("" if device.get("switch_key_guess") else " — outlet number unknown, check it with Probe"),
            "plugin_config": {"local_key": device.get("local_key", ""), "ip_address": None},
        })
    return found


def registration_fields(external_id: str, plugin_config: dict | None) -> dict[str, str]:
    """What an Add Plug form's fields should be filled with for this Known Device."""
    device_id, dps_key = decode_external_id(external_id)
    config = plugin_config or {}
    return {
        "tuya_device_id": device_id,
        "switch_dps_key": dps_key,
        "tuya_local_key": config.get("local_key") or "",
        "tuya_ip_address": config.get("ip_address") or "",
    }

