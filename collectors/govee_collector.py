"""Govee H5074 collector — runs as a host process (not in Docker; see ADR 0001, BLE doesn't
pass through Docker Desktop on Windows cleanly).

Listens for BLE advertisements, and for every registered Sensor MAC it hears from, decodes and
writes a sensor_reading row. Devices not yet registered (via tools/register_device.py) are logged
once and otherwise ignored, so registering a new sensor doesn't require restarting a running scan
for more than the refresh interval below.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from collectors.govee_protocol import MANUFACTURER_ID, MANUFACTURER_ID_H5102, decode_h5074, decode_h5102
from db.db import get_connection, init_db

REFRESH_REGISTRY_SECONDS = 60
UNKNOWN_MAC_LOG_LIMIT = 200  # avoid unbounded growth if something noisy is nearby for days

# Each supported model broadcasts under its own company ID with its own decode function — see
# collectors/govee_protocol.py's module docstring. A device only ever matches one of these.
_DECODERS = [
    (MANUFACTURER_ID, decode_h5074),
    (MANUFACTURER_ID_H5102, decode_h5102),
]

_registered_macs: dict[str, int] = {}  # mac_address -> sensor_id
_logged_unknown: set[str] = set()


def _refresh_registry() -> None:
    # Manual Sensors have no mac_address to listen for — see CONTEXT.md: Tracking Mode. Their
    # Readings are hand-logged through the Admin UI instead of collected here.
    with get_connection() as conn:
        rows = conn.execute("SELECT id, mac_address FROM sensor WHERE tracking_mode = 'smart'").fetchall()
    _registered_macs.clear()
    _registered_macs.update({row["mac_address"].upper(): row["id"] for row in rows})


def _on_detection(device: BLEDevice, adv: AdvertisementData) -> None:
    for manufacturer_id, decode in _DECODERS:
        raw = adv.manufacturer_data.get(manufacturer_id)
        if raw is not None:
            break
    else:
        return

    mac = device.address.upper()
    sensor_id = _registered_macs.get(mac)
    if sensor_id is None:
        if mac not in _logged_unknown and len(_logged_unknown) < UNKNOWN_MAC_LOG_LIMIT:
            print(f"[govee] seeing unregistered device {mac} — run tools/register_device.py sensor-add to track it")
            _logged_unknown.add(mac)
        return

    reading = decode(raw)
    if reading is None:
        print(f"[govee] {mac}: couldn't decode advertisement (len={len(raw)})")
        return

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO sensor_reading (sensor_id, temperature_c, humidity_pct, battery_pct) VALUES (?, ?, ?, ?)",
            (sensor_id, reading.temperature_c, reading.humidity_pct, reading.battery_pct),
        )
    print(f"[govee] {mac}: {reading.temperature_c:.2f}C {reading.humidity_pct:.1f}% batt={reading.battery_pct}%")


async def _registry_refresh_loop() -> None:
    while True:
        _refresh_registry()
        await asyncio.sleep(REFRESH_REGISTRY_SECONDS)


async def main() -> None:
    init_db()
    _refresh_registry()
    print(f"[govee] tracking {len(_registered_macs)} registered sensor(s); scanning...")

    scanner = BleakScanner(detection_callback=_on_detection)
    async with scanner:
        await _registry_refresh_loop()  # runs forever; Ctrl+C to stop


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[govee] stopped")
