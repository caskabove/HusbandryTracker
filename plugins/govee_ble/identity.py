"""The govee_ble Plugin's identity convention — see CONTEXT.md: Plugin, External ID; ADR 0013.
Trivial for this Plugin: a Govee device's External ID *is* its MAC address, upper-cased, and it
needs no Plugin Config at all (nothing beyond the MAC to reach it over BLE).
"""
from __future__ import annotations

PLUGIN_NAME = "govee_ble"


def encode_external_id(mac_address: str) -> str:
    return mac_address.strip().upper()
