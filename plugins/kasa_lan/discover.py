"""kasa_lan's discovery hook (see docs/plugin-standard.md section 5, CONTEXT.md: Known Device;
ADR 0062). Runs inside the web process when someone clicks Scan on this Plugin's Settings page, or
Discover Devices on a Kasa/Tapo Plug form.

Unlike tuya_lan, nothing here asks a cloud: TP-Link plugs answer a broadcast on the local network,
so this finds every plug on the same Wi-Fi as this computer. Read-only: it never switches or
renames a device.
"""
from __future__ import annotations

from plugins.kasa_lan.identity import decode_external_id, encode_external_id


async def discover(settings: dict[str, str]) -> list[dict]:
    from plugins.kasa_lan import kasa_io  # imported lazily so importing this module stays cheap

    credentials = kasa_io.credentials_from(settings)
    devices, needs_login = await kasa_io.scan(credentials)
    found: list[dict] = []
    try:
        for device in devices:
            mac = kasa_io.safe_mac(device)
            if not mac:
                continue
            model = device.model or "TP-Link device"
            for outlet, switch in kasa_io.outlets(device):
                state = "on" if switch.is_on else "off"
                where = f"outlet {outlet} of {model}" if outlet else model
                meter = ", reports power use" if kasa_io.energy(switch) or kasa_io.energy(device) else ""
                found.append({
                    "external_id": encode_external_id(mac, outlet),
                    "suggested_name": switch.alias or (f"{device.alias} {outlet}" if outlet else device.alias) or mac,
                    "summary": f"{where} at {device.host}, currently {state}{meter}",
                    "plugin_config": {"host": device.host},
                })
    finally:
        for device in devices:
            await kasa_io.disconnect(device)

    if needs_login:
        if credentials is None:
            hint = ("need your TP-Link login (the email and password you use in the Kasa or Tapo "
                    "app). Save them under Settings and scan again.")
        else:
            hint = ("refused the TP-Link login saved under Settings. Check the email and password "
                    "match the Kasa or Tapo app, then scan again.")
        message = f"{needs_login} TP-Link device{'s' if needs_login != 1 else ''} {hint}"
        if not found:
            raise RuntimeError(message)
        # The scan result has no separate "notes" slot, so the warning rides on the last row
        # rather than being dropped.
        found[-1]["summary"] += f". Also: {message}"
    return found


def registration_fields(external_id: str, plugin_config: dict | None) -> dict[str, str]:
    """What a Kasa/Tapo Add Plug form's fields should be filled with for this Known Device."""
    mac, outlet = decode_external_id(external_id)
    return {
        "plug_plugin": "kasa_lan",
        "kasa_mac": mac,
        "kasa_outlet": str(outlet) if outlet else "",
        "kasa_host": (plugin_config or {}).get("host") or "",
    }
