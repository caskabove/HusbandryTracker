"""govee_ble's discovery hook — see docs/plugin-standard.md (discover.py), CONTEXT.md: Known Device;
ADR 0061. Runs inside the web process when someone clicks this Plugin's Scan button on its Settings
page, never inside the background Plugin process, so it may import Core's own BLE helper: it reuses
web/govee_refresh.py's discover_govee() rather than opening a second scanner, because that module's
lock is what keeps a scan from colliding with a dashboard Refresh in the same process.
"""
from __future__ import annotations

from plugins.govee_ble.identity import encode_external_id


async def discover(settings: dict[str, str]) -> list[dict]:
    from web.govee_refresh import discover_govee  # imported lazily: only the web process calls this

    found = []
    for device in await discover_govee():
        temp_f = device["temperature_c"] * 9 / 5 + 32
        found.append({
            "external_id": encode_external_id(device["mac"]),
            "suggested_name": device.get("name") or device["mac"],
            "summary": f"{temp_f:.1f}°F / {device['humidity_pct']:.0f}% RH"
                       + (f", battery {device['battery_pct']}%" if device.get("battery_pct") is not None else ""),
            "plugin_config": None,
        })
    return found


def registration_fields(external_id: str, plugin_config: dict | None) -> dict[str, str]:
    """What an Add Sensor form's fields should be filled with for this Known Device."""
    return {"mac_address": external_id}
