"""Scan for nearby Govee BLE advertisements and dump raw bytes.

Use this to (a) find the MAC address of each H5074 so you can register it against an Enclosure,
and (b) verify collectors/govee_protocol.py's decode against real hardware before trusting it
(see that module's docstring).

Usage:
    python tools/govee_discover.py [seconds]   # default 20s
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from collectors.govee_protocol import DECODERS

seen: set[str] = set()


def _looks_like_govee(device: BLEDevice, adv: AdvertisementData) -> bool:
    name = (device.name or adv.local_name or "").lower()
    if "govee" in name or "gvh" in name:
        return True
    return any(manufacturer_id in adv.manufacturer_data for manufacturer_id, _decode in DECODERS)


def _on_detection(device: BLEDevice, adv: AdvertisementData) -> None:
    if not _looks_like_govee(device, adv):
        return

    key = f"{device.address}:{adv.rssi}:{tuple(adv.manufacturer_data.items())}"
    if key in seen:
        return
    seen.add(key)

    print(f"\n[{device.address}] name={device.name or adv.local_name!r} rssi={adv.rssi}")
    decoders_by_id = dict(DECODERS)
    for company_id, raw in adv.manufacturer_data.items():
        print(f"  manufacturer_data[0x{company_id:04X}] = {raw.hex()}")
        decode = decoders_by_id.get(company_id)
        if decode:
            reading = decode(raw)
            if reading:
                print(
                    f"    best-effort decode -> temp={reading.temperature_c:.2f}C "
                    f"humidity={reading.humidity_pct:.2f}% battery={reading.battery_pct}%  "
                    f"(VERIFY against the Govee app before trusting this)"
                )
    for service_uuid, raw in adv.service_data.items():
        print(f"  service_data[{service_uuid}] = {raw.hex()}")


async def main(seconds: float) -> None:
    print(f"Scanning for {seconds:.0f}s — put the Govee app in the foreground on your phone too, "
          f"so you can cross-check readings live...\n")
    scanner = BleakScanner(detection_callback=_on_detection)
    async with scanner:
        await asyncio.sleep(seconds)
    if not seen:
        print("No Govee-looking advertisements seen. Make sure the sensor is powered/in range, "
              "and that Bluetooth is on for this machine.")


if __name__ == "__main__":
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
    asyncio.run(main(duration))
