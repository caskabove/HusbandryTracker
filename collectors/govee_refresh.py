"""On-demand, one-shot BLE listen for a dashboard Refresh (see CONTEXT.md: Refresh, ADR 0005).

Distinct from collectors/govee_collector.py's continuous, all-devices background scan: this opens
a short-lived BleakScanner from the *web* process itself, listening only for a specific set of
MACs, and returns as soon as all of them have reported or the timeout elapses — whichever comes
first. Two processes each passively scanning BLE advertisements (this one alongside the always-on
collector) is standard Bluetooth behavior, not a conflict; see ADR 0005 for why that's fine while
two concurrent scans *within this same process* are not (hence the module-level lock below).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from collectors.govee_protocol import DECODERS, GoveeReading
from db.db import get_connection

_lock = asyncio.Lock()


async def refresh_sensors(sensor_ids_by_mac: dict[str, int], timeout_seconds: float) -> dict[str, GoveeReading]:
    """sensor_ids_by_mac: {mac_address (upper-case) -> sensor_id} for exactly the Sensors one
    Refresh click owns (see CONTEXT.md: Refresh — never more than that). Returns whichever MACs
    actually reported within timeout_seconds; each is already written to sensor_reading. A MAC
    missing from the result didn't broadcast in time — the caller decides how to tell the user.

    Serialized by _lock: a second concurrent call waits its turn rather than running alongside this
    one, then gets its own full timeout window (not shared results) — see ADR 0005.
    """
    if not sensor_ids_by_mac:
        return {}

    async with _lock:
        pending = set(sensor_ids_by_mac.keys())
        results: dict[str, GoveeReading] = {}
        done = asyncio.Event()

        def _on_detection(device: BLEDevice, adv: AdvertisementData) -> None:
            mac = device.address.upper()
            if mac not in pending:
                return
            for manufacturer_id, decode in DECODERS:
                raw = adv.manufacturer_data.get(manufacturer_id)
                if raw is None:
                    continue
                reading = decode(raw)
                if reading is not None:
                    results[mac] = reading
                    pending.discard(mac)
                break
            if not pending:
                done.set()

        scanner = BleakScanner(detection_callback=_on_detection)
        async with scanner:
            try:
                await asyncio.wait_for(done.wait(), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                pass  # whatever's in `results` is what we got — the rest just didn't report in time

        if results:
            with get_connection() as conn:
                for mac, reading in results.items():
                    conn.execute(
                        "INSERT INTO sensor_reading (sensor_id, temperature_c, humidity_pct, battery_pct) VALUES (?, ?, ?, ?)",
                        (sensor_ids_by_mac[mac], reading.temperature_c, reading.humidity_pct, reading.battery_pct),
                    )

        return results
