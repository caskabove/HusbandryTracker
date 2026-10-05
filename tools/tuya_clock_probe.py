"""Husbandry Tracker Tuya Clock Probe - does a Gosund/Tuya smart plug report its own clock?

Read-only. Connects to ONE Tuya plug (by its Plug label as the app knows it), asks for the raw
status() DPS dictionary, and prints every value. It also flags any value that looks like a clock
time ("HH:MM") or a Unix timestamp, so we can tell whether the device exposes its own time at all.
It never sends a Command, never changes the database, and never touches data/.

If nothing time-like shows up, the plug does not expose its clock through this local status call,
and Detected Schedule will keep meaning "when this PC saw the switch change" (see ADR 0012).

Run: .venv/Scripts/python.exe tools/tuya_clock_probe.py "<Plug label>"
     (run with no argument to list the Tuya Plugs the app knows about)
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tinytuya

from db.db import get_connection
from plugins.tuya_lan.identity import PLUGIN_NAME, decode_external_id, unpack_config

CONNECTION_TIMEOUT_SECONDS = 6
HH_MM = re.compile(r"^\d{1,2}:\d{2}$")


def _load_plugs() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, label, external_id, plugin_config FROM plug WHERE plugin = ? ORDER BY label",
            (PLUGIN_NAME,),
        ).fetchall()
    plugs = []
    for row in rows:
        device_id, dps_key = decode_external_id(row["external_id"])
        config = unpack_config(row["plugin_config"])
        plugs.append({
            "label": row["label"], "device_id": device_id, "dps_key": dps_key,
            "local_key": config["local_key"], "ip": config["ip_address"] or "Auto",
        })
    return plugs


def _looks_like_time(value) -> str | None:
    """Returns a note if the value could be a clock time or a Unix timestamp, else None."""
    if isinstance(value, str) and HH_MM.match(value):
        return "looks like a clock time (HH:MM)"
    if isinstance(value, int) and not isinstance(value, bool):
        # Unix timestamps for 2001..2100 - wide enough to catch any recent clock, narrow enough to
        # skip ordinary counters and watt readings.
        if 1_000_000_000 <= value <= 4_102_444_800:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(value))
            return f"looks like a Unix timestamp ({stamp} local)"
    return None


def main(argv: list[str]) -> int:
    plugs = _load_plugs()
    if not plugs:
        print("No Tuya Plugs in the app yet (Admin > + Plug).")
        return 1

    if len(argv) < 2:
        print("Tuya Plugs the app knows about:")
        for p in plugs:
            print(f"  {p['label']}  (device {p['device_id']}, switch {p['dps_key']})")
        print('\nRun again with the label, e.g.: python tools/tuya_clock_probe.py "' + plugs[0]["label"] + '"')
        return 0

    matches = [p for p in plugs if p["label"] == argv[1]]
    if not matches:
        print(f"No Tuya Plug labelled {argv[1]!r}. Known labels: {[p['label'] for p in plugs]}")
        return 1
    plug = matches[0]
    if not plug["local_key"]:
        print("This Plug has no saved local key, so it can't be queried locally.")
        return 1

    device = tinytuya.OutletDevice(
        plug["device_id"], plug["ip"], plug["local_key"], version="3.3",
        connection_timeout=CONNECTION_TIMEOUT_SECONDS, connection_retry_limit=1,
    )
    status = device.status()
    if not status or "Error" in status:
        print(f"Couldn't read status from {plug['label']}: {status}")
        return 1

    print(f"Raw status for {plug['label']} (device {plug['device_id']}):")
    print(json.dumps(status, indent=2, sort_keys=True))
    print()

    found_any = False
    candidates = {k: v for k, v in status.items() if k != "dps"}
    candidates.update({f"dps {k}": v for k, v in (status.get("dps") or {}).items()})
    for name, value in candidates.items():
        note = _looks_like_time(value)
        if note:
            found_any = True
            print(f"  {name} = {value!r}: {note}")
    if not found_any:
        print("No value looks like a clock time or timestamp. This plug does not expose its clock")
        print("through the local status call.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
