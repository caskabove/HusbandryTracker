"""Husbandry Tracker Govee Sensor Report - a plain-language status check for non-technical users.

Covers three things about the govee_ble Plugin (Govee H5074/H5102 BLE thermometer/hygrometers -
see CONTEXT.md: Plugin; plugins/govee_ble/plugin.py):
  1. Every Sensor the app currently knows about - its last reported reading, whether it actually
     broadcast during this check, and when it was last heard from.
  2. Any Govee-looking BLE device heard nearby that ISN'T registered in the app yet.
  3. Whether the app's saved files for this Plugin (its Registry export, Inbox reports) look
     healthy - the same filesystem contract every Plugin uses (see CONTEXT.md: Registry, Inbox;
     ADR 0013).

Govee sensors are BLE broadcasters, not something you can "call up" on demand the way a Tuya plug
answers a status request (see tools/tuya_status_check.py for that) - the only way to know if one
is working is to listen for a while and see what turns up, the same passive approach
plugins/govee_ble/plugin.py and tools/govee_discover.py use. This listens once for
--listen-seconds (20s by default) and covers both "are my registered sensors broadcasting" and
"is there a new one nearby" in that single pass.

There's no Outbox check here - see CONTEXT.md's Outbox entry: Govee Sensors are read-only and
never receive Commands, unlike a Tuya Plug.

This never changes anything the app has saved - it only reads the database and the data/registry
and data/inbox folders, plus passively listens for Bluetooth advertisements (it never connects to
anything). Safe to run at any time, including while the app is running.

Run: .venv/Scripts/python.exe tools/govee_status_check.py
     .venv/Scripts/python.exe tools/govee_status_check.py --listen-seconds 30
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from db.db import get_connection
from plugins.govee_ble.identity import PLUGIN_NAME
from plugins.govee_ble.protocol import DECODERS, GoveeReading

DEFAULT_LISTEN_SECONDS = 20.0

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_DIR = REPO_ROOT / "data" / "registry"
INBOX_DIR = REPO_ROOT / "data" / "inbox"
REJECTED_DIR = INBOX_DIR / "_rejected"


@dataclass
class KnownSensor:
    sensor_id: int
    label: str
    location: str
    mac: str
    last_recorded_at: str | None
    last_temperature_c: float | None
    last_humidity_pct: float | None
    last_battery_pct: int | None

    @property
    def display_name(self) -> str:
        # Several Sensors sharing a generic label like "ambient" is common (see CONTEXT.md: Room,
        # ambient-monitoring) - the Room/Enclosure name is what actually tells them apart here.
        return f"{self.label} ({self.location})" if self.location else self.label


def _friendly_age(timestamp: str | None) -> str:
    if not timestamp:
        return "never"
    then = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    seconds = max(0.0, (datetime.now(timezone.utc) - then).total_seconds())
    if seconds < 20:
        return "just now"
    if seconds < 60:
        return f"{int(seconds)} seconds ago"
    minutes = seconds / 60
    if minutes < 60:
        return f"{int(minutes)} minute{'s' if minutes >= 2 else ''} ago"
    hours = minutes / 60
    if hours < 24:
        return f"{int(hours)} hour{'s' if hours >= 2 else ''} ago"
    days = hours / 24
    return f"{int(days)} day{'s' if days >= 2 else ''} ago"


def _load_known_sensors() -> list[KnownSensor]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT s.id, s.label, s.external_id, "
            "COALESCE(e.name, r.name, '') AS location, "
            "(SELECT recorded_at FROM sensor_reading WHERE sensor_id = s.id "
            " ORDER BY recorded_at DESC LIMIT 1) AS last_recorded_at, "
            "(SELECT temperature_c FROM sensor_reading WHERE sensor_id = s.id "
            " ORDER BY recorded_at DESC LIMIT 1) AS last_temperature_c, "
            "(SELECT humidity_pct FROM sensor_reading WHERE sensor_id = s.id "
            " ORDER BY recorded_at DESC LIMIT 1) AS last_humidity_pct, "
            "(SELECT battery_pct FROM sensor_reading WHERE sensor_id = s.id "
            " ORDER BY recorded_at DESC LIMIT 1) AS last_battery_pct "
            "FROM sensor s "
            "LEFT JOIN enclosure e ON e.id = s.enclosure_id "
            "LEFT JOIN room r ON r.id = s.room_id "
            "WHERE s.plugin = ? ORDER BY location, s.external_id",
            (PLUGIN_NAME,),
        ).fetchall()
    return [KnownSensor(r["id"], r["label"], r["location"], r["external_id"], r["last_recorded_at"],
                         r["last_temperature_c"], r["last_humidity_pct"], r["last_battery_pct"])
            for r in rows]


def _reading_text(sensor: KnownSensor) -> str:
    if sensor.last_recorded_at is None:
        return "no data yet"
    parts = []
    if sensor.last_temperature_c is not None:
        parts.append(f"{sensor.last_temperature_c:.1f}C")
    if sensor.last_humidity_pct is not None:
        parts.append(f"{sensor.last_humidity_pct:.0f}%")
    if sensor.last_battery_pct is not None:
        parts.append(f"batt {sensor.last_battery_pct}%")
    return ", ".join(parts) if parts else "no data yet"


async def _listen(known_macs: set[str], seconds: float) -> tuple[dict[str, GoveeReading], list[tuple[str, str, int]]]:
    """One passive BLE listen covering both known-sensor reachability and new-device discovery in
    a single pass - see this file's module docstring for why that's the natural shape for BLE,
    unlike Tuya's per-device active connection check."""
    heard: dict[str, GoveeReading] = {}
    new_candidates: dict[str, tuple[str, int]] = {}  # mac -> (name, rssi), latest advertisement wins

    def _on_detection(device: BLEDevice, adv: AdvertisementData) -> None:
        mac = device.address.upper()
        raw = None
        decode = None
        for manufacturer_id, dec in DECODERS:
            candidate = adv.manufacturer_data.get(manufacturer_id)
            if candidate is not None:
                raw, decode = candidate, dec
                break

        if mac in known_macs:
            if raw is not None and decode is not None:
                reading = decode(raw)
                if reading is not None:
                    heard[mac] = reading
            return

        name = (device.name or adv.local_name or "")
        looks_govee = "govee" in name.lower() or "gvh" in name.lower() or raw is not None
        if looks_govee:
            new_candidates[mac] = (name, adv.rssi)

    scanner = BleakScanner(detection_callback=_on_detection)
    async with scanner:
        await asyncio.sleep(seconds)

    return heard, [(mac, name, rssi) for mac, (name, rssi) in new_candidates.items()]


def print_known_sensors(sensors: list[KnownSensor], heard: dict[str, GoveeReading]) -> bool:
    print("== Sensors this app knows about ==")
    if not sensors:
        print("  No Govee Sensors have been added yet (Admin > + Sensor).")
        print()
        return True

    name_w = max(len(s.display_name) for s in sensors)
    name_w = max(name_w, len("Name"))
    reading_w = max(len(_reading_text(s)) for s in sensors)
    reading_w = max(reading_w, len("Last reading"))

    header = f"  {'Name':<{name_w}}  {'Last reading':<{reading_w}}  {'Heard now?':<10}  Last heard from"
    print(header)
    print("  " + "-" * (len(header) - 2))
    all_heard = True
    for s in sensors:
        heard_now = s.mac in heard
        all_heard = all_heard and heard_now
        heard_text = "Yes" if heard_now else "No"
        print(f"  {s.display_name:<{name_w}}  {_reading_text(s):<{reading_w}}  {heard_text:<10}  "
              f"{_friendly_age(s.last_recorded_at)}")
    print()
    return all_heard


def print_new_devices(new_candidates: list[tuple[str, str, int]]) -> None:
    print("== Govee-looking devices heard nearby that aren't in Husbandry Tracker yet ==")
    if not new_candidates:
        print("  None heard during this check.")
        print()
        return
    for mac, name, rssi in sorted(new_candidates, key=lambda c: c[0]):
        label = f" ({name})" if name else ""
        print(f"  - {mac}{label}  signal strength: {rssi} dBm  - add it from Admin > + Sensor")
    print()


def check_files(known_macs: set[str]) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    path = REGISTRY_DIR / f"{PLUGIN_NAME}.json"
    if not path.exists():
        if known_macs:
            results.append(("Device list is up to date", False,
                             "no file yet - the app may not have run since these Sensors were added"))
        else:
            results.append(("Device list is up to date", True, "no Govee Sensors registered yet"))
    else:
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
            registry_macs = {e["external_id"] for e in entries}
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            results.append(("Device list is up to date", False, f"file is unreadable ({exc})"))
        else:
            missing = known_macs - registry_macs
            stale = registry_macs - known_macs
            if not missing and not stale:
                results.append(("Device list is up to date", True, ""))
            else:
                parts = []
                if missing:
                    parts.append(f"missing {sorted(missing)}")
                if stale:
                    parts.append(f"has old entries {sorted(stale)}")
                results.append(("Device list is up to date", False, "; ".join(parts)))

    rejected = []
    if REJECTED_DIR.exists():
        for kind_dir in REJECTED_DIR.iterdir():
            rejected.extend(kind_dir.glob(f"{PLUGIN_NAME}__*.json"))
    if rejected:
        results.append(("No reports were rejected", False,
                         f"{len(rejected)} file(s) in data/inbox/_rejected"))
    else:
        results.append(("No reports were rejected", True, ""))

    return results


def print_file_health(results: list[tuple[str, bool, str]]) -> bool:
    print("== Is the app saving/loading its Govee files correctly? ==")
    name_w = max(len(name) for name, _, _ in results)
    for name, passed, detail in results:
        text = "PASS" if passed else "FAIL"
        line = f"  {name:<{name_w}}  {text}"
        if detail:
            line += f"  - {detail}"
        print(line)
    print("  (No Outbox check - Govee Sensors are read-only and never receive Commands.)")
    print()
    return all(passed for _, passed, _ in results)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--listen-seconds", type=float, default=DEFAULT_LISTEN_SECONDS,
                         help=f"how long to listen for Bluetooth advertisements "
                              f"(default: {DEFAULT_LISTEN_SECONDS:.0f})")
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("  Husbandry Tracker Govee Sensor Report")
    print("=" * 60)
    print()

    sensors = _load_known_sensors()
    known_macs = {s.mac for s in sensors}

    print(f"Listening for Bluetooth advertisements for {args.listen_seconds:.0f} seconds...")
    print("(Each sensor only broadcasts every few seconds, so this needs a little patience.)")
    print()
    try:
        heard, new_candidates = asyncio.run(_listen(known_macs, args.listen_seconds))
    except Exception as exc:  # bleak raises plain exceptions for e.g. no Bluetooth adapter
        print(f"Couldn't listen for Bluetooth devices ({exc})")
        print("Make sure Bluetooth is turned on for this machine and try again.")
        return 1

    all_heard = print_known_sensors(sensors, heard)
    print_new_devices(new_candidates)

    file_results = check_files(known_macs)
    files_ok = print_file_health(file_results)

    if all_heard and files_ok:
        print("Everything looks good.")
        return 0
    print("Some things need attention - see 'No'/FAIL above and docs/DEBUGGING_JSON_PIPELINE.md.")
    if not all_heard:
        print("(A sensor not heard during this one listen isn't necessarily broken - BLE broadcasts")
        print(" can be missed if it's out of range or the timing didn't line up. Try again, or use")
        print(" a longer --listen-seconds, before assuming it's a real problem.)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
