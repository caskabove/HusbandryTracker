"""Decoding for Govee BLE advertisements. Two distinct models/protocols are supported so far —
each Govee model family encodes its manufacturer data completely differently, so a new model
needs its own decode function verified independently; nothing here generalizes across models.

H5074 — verified 2026-08-22 against 4 real H5074 sensors via `tools/govee_discover.py`:
little-endian temp/humidity int16 fields produce physically plausible readings (26-30C, 73-96%
humidity) where the original big-endian guess produced nonsense (192C, 258% humidity).

H5102 — verified 2026-08-23 against 1 real H5102 sensor: a 24-bit big-endian packed field (temp
and humidity combined into one integer, H5075-style) matched the Govee app's reading once the
app's own calibration offset was accounted for (the app applies a user-configurable +/- correction
on top of the raw sensor value; HerpMonitor stores the raw value, same as it does for the H5074s,
not the calibrated one). Broadcasts under manufacturer ID 0x0001, not 0xEC88 — a completely
different company ID from the H5074, despite being the same brand.

Still worth a final sanity check the first time you register a real sensor of either kind:
cross-check the decoded temp/humidity against what the Govee app shows for that sensor at the same
moment (and note any calibration offset configured there — it won't match the raw value on purpose).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

# Company ID Govee commonly uses for manufacturer-specific data in the H5074/H5075 family.
# bleak's manufacturer_data dict is already keyed by this integer (little-endian company ID
# stripped out for you) — do not add the 0x88EC byte-swapped form here.
MANUFACTURER_ID = 0xEC88

# The H5102 (and apparently its mini-hygrometer siblings) broadcasts under this company ID
# instead — plain BLE SIG-assigned ID 0x0001, nothing Govee-specific about the number itself.
MANUFACTURER_ID_H5102 = 0x0001


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


def decode_h5102(data: bytes) -> GoveeReading | None:
    """Decode H5102 manufacturer-specific data. See module docstring — verified against real hardware."""
    # Layout: [2 header bytes, always seen as 01 01] [temp+humidity: uint24 BE, packed] [battery: uint8]
    # Packed field: value / 10000 = temp C (negative if bit 0x800000 is set, cleared before
    # dividing), value % 1000 / 10 = humidity %RH — the two overlap in the packed int's digits by
    # design (this is Govee's known H5075-family packing, not something specific to the H5102).
    if len(data) < 6:
        return None
    packed = int.from_bytes(data[2:5], byteorder="big")
    is_negative = bool(packed & 0x800000)
    if is_negative:
        packed &= 0x7FFFFF
    temperature_c = packed / 10000.0
    if is_negative:
        temperature_c = -temperature_c
    humidity_pct = (packed % 1000) / 10.0
    battery = data[5]
    return GoveeReading(temperature_c=temperature_c, humidity_pct=humidity_pct, battery_pct=battery)
