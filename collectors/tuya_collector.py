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

Also writes Data Capture (plug_reading — watts/volts/amps/countdown, see CONTEXT.md: Data Capture,
ADR 0009) on a slower, independent cadence from the 5s on/off watch above. As of this file, that's
built but empty for every registered device: a real discovery dump of this collection's actual
Tuya devices (devices.json, 13 devices) confirmed none of them expose cur_power/cur_voltage/
cur_current at all — only switch_N/countdown_N — and unlike switch_dps_key (configured per-Plug,
usually "1"), there's no per-Plug config yet for which numeric DPS key holds telemetry, so
_extract_telemetry() has nothing to read. It's still real, working machinery — the moment a
telemetry-capable plug is registered and _extract_telemetry() is taught its DPS key, capture starts
without any other code changing.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tinytuya

from collectors import alerts
from db.db import get_connection, init_db

POLL_INTERVAL_SECONDS = 5
REFRESH_REGISTRY_SECONDS = 60
DATA_CAPTURE_INTERVAL_SECONDS = 120  # 1-5 min per ADR 0009; independent of the 5s on/off watch


def _load_registered_plugs() -> list[dict]:
    # Manual Plugs have no Tuya device to poll — see CONTEXT.md: Tracking Mode. They carry a
    # Declared Schedule (on-time/off-time entered directly) instead of an observed one.
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id, label, tuya_device_id, tuya_local_key, tuya_ip_address, switch_dps_key
               FROM plug WHERE tracking_mode = 'smart' AND auto_update_enabled = 1"""
        ).fetchall()
    return [dict(row) for row in rows]


def _record_transition(plug_id: int, is_on: bool) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO plug_state_transition (plug_id, is_on) VALUES (?, ?)",
            (plug_id, int(is_on)),
        )


def _extract_telemetry(dps: dict) -> dict[str, float | int | None]:
    """Pulls watts/volts/amps/countdown_seconds out of a raw local-poll DPS dict for Data Capture
    (see CONTEXT.md: Data Capture). Always empty today — see this file's module docstring for why:
    no per-Plug config yet says which numeric DPS key (if any) holds each value, and none of this
    collection's actual registered devices expose them regardless. Extend this once both exist."""
    return {"watts": None, "volts": None, "amps": None, "countdown_seconds": None}


def _capture_data(plug: dict, dps: dict) -> None:
    telemetry = _extract_telemetry(dps)
    if all(value is None for value in telemetry.values()):
        print(f"[tuya] {plug['label']!r}: no telemetry DPS mapped — skipping Data Capture "
              f"(see _extract_telemetry in this file)")
        return
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO plug_reading (plug_id, watts, volts, amps, countdown_seconds)
               VALUES (?, ?, ?, ?, ?)""",
            (plug["id"], telemetry["watts"], telemetry["volts"], telemetry["amps"], telemetry["countdown_seconds"]),
        )
    print(f"[tuya] {plug['label']!r}: Data Capture -> {telemetry}")
    alerts.evaluate_plug_zero_power(plug["id"])  # see CONTEXT.md: Zero Power While On


def _poll_plug(plug: dict, stop_event: threading.Event) -> None:
    device = tinytuya.OutletDevice(
        plug["tuya_device_id"],
        plug["tuya_ip_address"] or "Auto",
        plug["tuya_local_key"],
        version="3.3",
    )
    last_state: bool | None = None
    last_capture_time: float | None = None  # time.monotonic() of the last Data Capture write
    switch_dps_key = plug["switch_dps_key"]
    print(f"[tuya] watching {plug['label']!r} ({plug['tuya_device_id']} dps={switch_dps_key})")

    while not stop_event.is_set():
        try:
            status = device.status()
            dps = status.get("dps", {})
            alerts.record_plug_poll(plug["id"], ok=True)  # see CONTEXT.md: Alert Condition, Unreachable
            if switch_dps_key in dps:
                current_state = bool(dps[switch_dps_key])
                if current_state != last_state:
                    _record_transition(plug["id"], current_state)
                    print(f"[tuya] {plug['label']!r} -> {'ON' if current_state else 'OFF'}")
                    last_state = current_state
            else:
                print(f"[tuya] {plug['label']!r}: no DPS key {switch_dps_key!r} in {dps} "
                      f"(run tools/tuya_probe.py to find the right key)")

            now = time.monotonic()
            if last_capture_time is None or (now - last_capture_time) >= DATA_CAPTURE_INTERVAL_SECONDS:
                last_capture_time = now
                _capture_data(plug, dps)
        except Exception as exc:  # tinytuya raises plain exceptions on timeout/network errors
            alerts.record_plug_poll(plug["id"], ok=False)
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
