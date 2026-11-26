"""The kasa_lan Plugin's identity convention (see CONTEXT.md: Plugin, External ID, Plugin Config;
docs/plugin-standard.md; ADR 0062).

External ID is the device's MAC address, upper-case and colon-separated, because a MAC never
changes when the router hands out a new IP, unlike the host. A power strip registers each outlet as
its own Plug, so an outlet appends "#<n>" (1-based, in the order the strip reports its children):
"AA:BB:CC:DD:EE:FF" is a single plug, "AA:BB:CC:DD:EE:FF#2" is outlet 2 of a strip.

Plugin Config carries only the last-known LAN address ({"host": "192.168.1.40"}). It's a hint,
not identity: the Plugin finds the device by MAC again if the address goes stale.
"""
from __future__ import annotations

import json
import re

PLUGIN_NAME = "kasa_lan"

_OUTLET_SEPARATOR = "#"
_MAC_HEX = re.compile(r"[0-9A-Fa-f]{12}")


def normalize_mac(mac: str) -> str:
    """Accepts "aa:bb:cc:dd:ee:ff", "AA-BB-CC-DD-EE-FF" or "aabbccddeeff"; returns
    "AA:BB:CC:DD:EE:FF". Raises ValueError with a user-readable message otherwise."""
    digits = re.sub(r"[^0-9A-Fa-f]", "", mac or "")
    if not _MAC_HEX.fullmatch(digits):
        raise ValueError(f"{mac!r} isn't a MAC address. It looks like AA:BB:CC:DD:EE:FF.")
    digits = digits.upper()
    return ":".join(digits[i:i + 2] for i in range(0, 12, 2))


def encode_external_id(mac: str, outlet: int | str | None = None) -> str:
    """outlet: None/""/0 for a single plug; 1, 2, 3... for a power strip's outlets."""
    normalized = normalize_mac(mac)
    if outlet in (None, "", 0, "0"):
        return normalized
    try:
        number = int(outlet)
    except (TypeError, ValueError):
        raise ValueError(f"Outlet must be a number (1, 2, 3...), not {outlet!r}.") from None
    if number < 1:
        raise ValueError("Outlet numbers start at 1.")
    return f"{normalized}{_OUTLET_SEPARATOR}{number}"


def decode_external_id(external_id: str) -> tuple[str, int | None]:
    """Returns (mac, outlet), where outlet is None for a single plug."""
    mac, _, outlet = external_id.partition(_OUTLET_SEPARATOR)
    return mac, (int(outlet) if outlet else None)


def pack_config(host: str | None) -> str | None:
    host = (host or "").strip()
    return json.dumps({"host": host}) if host else None


def unpack_config(plugin_config: str | dict | None) -> dict:
    """Same two shapes as tuya_lan's unpack_config: a raw JSON string from the DB column, or an
    already-parsed dict from a Registry export."""
    if not plugin_config:
        return {"host": None}
    data = plugin_config if isinstance(plugin_config, dict) else json.loads(plugin_config)
    return {"host": data.get("host") or None}
