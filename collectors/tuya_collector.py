"""Local Tuya collector for Gosund Plugs (see ADR 0001 — this one containerizes fine, unlike the
Govee collector, since it's plain LAN traffic rather than BLE).

Polls each registered Plug's raw status over the LAN and writes a plug_state_transition row only
when the on/off DPS value actually changes (edge-triggered, not a poll log) — Schedule is derived
from these transitions later.

Each Plug row has its own switch_dps_key (default "1") — most single-outlet Tuya plugs use "1",
but multi-outlet power strips expose several switches ("1"/"2"/"3" for AC outlets, "7" for USB) on
ONE device_id, registered as separate Plug rows sharing that device_id (see db/schema.sql). If
transitions look wrong (or never fire) for a given Plug, run tools/tuya_probe.py against that
device_id first to confirm which DPS key its switch_dps_key should actually be.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tinytuya

from db.db import get_connection, init_db

POLL_INTERVAL_SECONDS = 5
REFRESH_REGISTRY_SECONDS = 60


def _load_registered_plugs() -> list[dict]:
    # Manual Plugs have no Tuya device to poll — see CONTEXT.md: Tracking Mode. They carry a
    # Declared Schedule (on-time/off-time entered directly) instead of an observed one.
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id, label, tuya_device_id, tuya_local_key, tuya_ip_address, switch_dps_key
               FROM plug WHERE tracking_mode = 'smart'"""
        ).fetchall()
    return [dict(row) for row in rows]


def _record_transition(plug_id: int, is_on: bool) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO plug_state_transition (plug_id, is_on) VALUES (?, ?)",
            (plug_id, int(is_on)),
        )


def _poll_plug(plug: dict, stop_event: threading.Event) -> None:
    device = tinytuya.OutletDevice(
        plug["tuya_device_id"],
        plug["tuya_ip_address"] or "Auto",
        plug["tuya_local_key"],
        version="3.3",
    )
    last_state: bool | None = None
    switch_dps_key = plug["switch_dps_key"]
    print(f"[tuya] watching {plug['label']!r} ({plug['tuya_device_id']} dps={switch_dps_key})")

    while not stop_event.is_set():
        try:
            status = device.status()
            dps = status.get("dps", {})
            if switch_dps_key in dps:
                current_state = bool(dps[switch_dps_key])
                if current_state != last_state:
                    _record_transition(plug["id"], current_state)
                    print(f"[tuya] {plug['label']!r} -> {'ON' if current_state else 'OFF'}")
                    last_state = current_state
            else:
                print(f"[tuya] {plug['label']!r}: no DPS key {switch_dps_key!r} in {dps} "
                      f"(run tools/tuya_probe.py to find the right key)")
        except Exception as exc:  # tinytuya raises plain exceptions on timeout/network errors
            print(f"[tuya] {plug['label']!r}: poll failed ({exc})")

        stop_event.wait(POLL_INTERVAL_SECONDS)


def main() -> None:
    init_db()
    stop_event = threading.Event()
    threads: dict[int, threading.Thread] = {}

    try:
        while True:
            for plug in _load_registered_plugs():
                if plug["id"] not in threads:
                    t = threading.Thread(target=_poll_plug, args=(plug, stop_event), daemon=True)
                    t.start()
                    threads[plug["id"]] = t
            time.sleep(REFRESH_REGISTRY_SECONDS)
    except KeyboardInterrupt:
        print("\n[tuya] stopping...")
        stop_event.set()
        for t in threads.values():
            t.join(timeout=2)


if __name__ == "__main__":
    main()
