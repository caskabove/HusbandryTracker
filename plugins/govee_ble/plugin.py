"""Govee H5074/H5102 Plugin — runs as a host process (not in Docker; see ADR 0001, BLE doesn't
pass through Docker Desktop on Windows cleanly).

Listens for BLE advertisements from every device in its Registry export (see CONTEXT.md: Registry,
Plugin; ADR 0013) and, for each one it hears from, decodes and drops a sensor_reading Plugin Event
into the Inbox for Ingest to pick up. A MAC not in the Registry is logged once and otherwise
ignored, so registering a new sensor doesn't require restarting a running scan for more than the
refresh interval below. Never touches the database — see plugins/__init__.py.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from plugins.common import read_registry, write_event
from plugins.govee_ble.identity import PLUGIN_NAME
from plugins.govee_ble.protocol import DECODERS

REFRESH_REGISTRY_SECONDS = 60
UNKNOWN_MAC_LOG_LIMIT = 200  # avoid unbounded growth if something noisy is nearby for days

# Some Govee devices send each advertisement twice a second or so apart for reliability — without
# this, that shows up as two identical Plugin Events per real broadcast. Only suppresses a write
# that's both identical AND this soon after the last one; a stable room legitimately reporting the
# same value on its *next real* broadcast (10-30s+ later) still gets recorded, so "as of" staleness
# on the dashboard keeps meaning what it says.
DEDUPE_WINDOW_SECONDS = 5

_watched: dict[str, bool] = {}  # mac_address (upper) -> auto_update_enabled, from the Registry
_logged_unknown: set[str] = set()
_last_write: dict[str, tuple[tuple[float, float, int], float]] = {}  # mac -> (reading tuple, monotonic time)


def _refresh_registry() -> None:
    entries = read_registry(PLUGIN_NAME)
    _watched.clear()
    _watched.update({entry["external_id"].upper(): entry.get("auto_update_enabled", True) for entry in entries})


def _on_detection(device: BLEDevice, adv: AdvertisementData) -> None:
    for manufacturer_id, decode in DECODERS:
        raw = adv.manufacturer_data.get(manufacturer_id)
        if raw is not None:
            break
    else:
        return

    mac = device.address.upper()
    if mac not in _watched:
        if mac not in _logged_unknown and len(_logged_unknown) < UNKNOWN_MAC_LOG_LIMIT:
            print(f"[govee_ble] seeing unregistered device {mac} — register it in Admin to track it")
            _logged_unknown.add(mac)
        return
    if not _watched[mac]:
        return  # Auto-Update paused for this Sensor — see CONTEXT.md: Auto-Update

    reading = decode(raw)
    if reading is None:
        print(f"[govee_ble] {mac}: couldn't decode advertisement (len={len(raw)})")
        return

    key = (reading.temperature_c, reading.humidity_pct, reading.battery_pct)
    now = time.monotonic()
    prev = _last_write.get(mac)
    if prev is not None and prev[0] == key and (now - prev[1]) < DEDUPE_WINDOW_SECONDS:
        return  # duplicate send of the same broadcast, not a new reading
    _last_write[mac] = (key, now)

    write_event(PLUGIN_NAME, mac, "sensor_reading", {
        "temperature_c": reading.temperature_c,
        "humidity_pct": reading.humidity_pct,
        "battery_pct": reading.battery_pct,
    })
    print(f"[govee_ble] {mac}: {reading.temperature_c:.2f}C {reading.humidity_pct:.1f}% batt={reading.battery_pct}%")


async def _registry_refresh_loop() -> None:
    while True:
        _refresh_registry()
        await asyncio.sleep(REFRESH_REGISTRY_SECONDS)


async def main() -> None:
    _refresh_registry()
    print(f"[govee_ble] watching {len(_watched)} registered device(s); scanning...")

    scanner = BleakScanner(detection_callback=_on_detection)
    async with scanner:
        await _registry_refresh_loop()  # runs forever; Ctrl+C to stop


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[govee_ble] stopped")
