"""Decoding for Govee H5074 BLE advertisements.

Verified 2026-08-22 against 4 real H5074 sensors via `tools/govee_discover.py`: little-endian
temp/humidity int16 fields produce physically plausible readings (26-30C, 73-96% humidity) where
the original big-endian guess produced nonsense (192C, 258% humidity). Distinct from the H5075,
which packs temp+humidity into a single encoded integer — the H5074 sends them as two plain
little-endian fields, which is why it's the easier model to decode.

Still worth a final sanity check the first time you register a real sensor: cross-check the
decoded temp/humidity against what the Govee app shows for that sensor at the same moment.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

# Company ID Govee commonly uses for manufacturer-specific data in the H5074/H5075 family.
# bleak's manufacturer_data dict is already keyed by this integer (little-endian company ID
# stripped out for you) — do not add the 0x88EC byte-swapped form here.
MANUFACTURER_ID = 0xEC88


@dataclass
class GoveeReading:
    temperature_c: float
    humidity_pct: float
    battery_pct: int


def decode_h5074(data: bytes) -> GoveeReading | None:
    """Decode H5074 manufacturer-specific data. See module docstring — verified against real hardware."""
    # Layout: [flags/unknown byte] [temp: int16 LE, /100 = C] [humidity: uint16 LE, /100 = %RH] [battery: uint8]
    if len(data) < 6:
        return None
    try:
        _flags, temp_raw, humidity_raw, battery = struct.unpack_from("<BhHB", data, 0)
    except struct.error:
        return None
    return GoveeReading(
        temperature_c=temp_raw / 100.0,
        humidity_pct=humidity_raw / 100.0,
        battery_pct=battery,
    )
