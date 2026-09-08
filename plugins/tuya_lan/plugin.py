"""Local Tuya Plugin for Gosund Plugs (see ADR 0001 — this one containerizes fine, unlike the
Govee Plugin, since it's plain LAN traffic rather than BLE).

Polls each registered device's raw status over the LAN on a 5s cadence and drops a plug_state
Plugin Event into the Inbox on *every* poll — not just when the on/off DPS value changes. Ingest
does the edge-detection from there (see CONTEXT.md: Ingest; ADR 0013), which is also what lets Plug
Unreachable be a plain absence check, the same mechanism Sensor Unreachable already used. A nice
side effect: unlike the pre-ADR-0013 version of this file, a live Auto-Update pause (see CONTEXT.md)
now takes effect on the very next poll instead of only at process restart, since every poll re-checks
the current Registry rather than baking the flag in once at thread start.

Also checks its own Outbox for a pending Command on every poll (see CONTEXT.md: Command, Outbox;
ADR 0014) — this is the one Plugin in this repo that implements command execution at all, since
govee_ble has nothing to actuate. A Command is executed at most once (take_command removes the file
on read) and never retried if the device is unreachable at that moment — see _execute_command.

Also drops plug_telemetry Plugin Events (watts/volts/amps/countdown, see CONTEXT.md: Data Capture)
on a slower, independent cadence from the 5s state watch above. As of this file, that's built but
empty for every registered device in this collection: a real discovery dump (devices.json, 13
devices) confirmed none of them expose cur_power/cur_voltage/cur_current at all — only switch_N/
countdown_N — and there's no per-Plug config yet for which numeric DPS key holds telemetry, so
_extract_telemetry() has nothing to read. It's still real, working machinery — the moment a
telemetry-capable plug is registered and _extract_telemetry() is taught its DPS key, capture starts
without any other code changing.

Never touches the database — see plugins/__init__.py. Registered devices come from this Plugin's
own Registry export (see CONTEXT.md: Registry), re-read every REFRESH_REGISTRY_SECONDS. If
transitions look wrong (or never fire) for a given Plug, run tools/tuya_probe.py against that
device_id first to confirm which DPS key its switch_dps_key should actually be.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import tinytuya

from plugins.common import read_registry, take_command, write_event
from plugins.tuya_lan.identity import PLUGIN_NAME, decode_external_id, unpack_config

POLL_INTERVAL_SECONDS = 5
REFRESH_REGISTRY_SECONDS = 60
DATA_CAPTURE_INTERVAL_SECONDS = 120  # 1-5 min per ADR 0009; independent of the 5s state watch

# external_id -> {"device_id", "switch_dps_key", "local_key", "ip_address", "auto_update_enabled"}
_watched: dict[str, dict] = {}


def _refresh_registry() -> None:
    watched: dict[str, dict] = {}
    for entry in read_registry(PLUGIN_NAME):
        external_id = entry["external_id"]
        device_id, dps_key = decode_external_id(external_id)
        config = unpack_config(entry.get("plugin_config"))
        watched[external_id] = {
            "device_id": device_id,
            "switch_dps_key": dps_key,
            "local_key": config["local_key"],
            "ip_address": config["ip_address"],
            "auto_update_enabled": entry.get("auto_update_enabled", True),
        }
    _watched.clear()
    _watched.update(watched)


def _extract_telemetry(dps: dict) -> dict[str, float | int | None]:
    """Pulls watts/volts/amps/countdown_seconds out of a raw local-poll DPS dict for Data Capture
    (see CONTEXT.md: Data Capture). Always empty today — see this file's module docstring for why:
    no per-Plug config yet says which numeric DPS key (if any) holds each value, and none of this
    collection's actual registered devices expose them regardless. Extend this once both exist."""
    return {"watts": None, "volts": None, "amps": None, "countdown_seconds": None}


def _capture_telemetry(external_id: str, dps: dict) -> None:
    telemetry = _extract_telemetry(dps)
    if all(value is None for value in telemetry.values()):
        return  # nothing to report — see _extract_telemetry
    write_event(PLUGIN_NAME, external_id, "plug_telemetry", telemetry)
    print(f"[tuya_lan] {external_id}: Data Capture -> {telemetry}")


def _execute_command(device: tinytuya.OutletDevice, external_id: str, current: dict, command: dict) -> None:
    """Executes one Command taken from the Outbox — see CONTEXT.md: Command; ADR 0014. Only
    set_power exists today. A failure (device unreachable right this moment) is dropped, not
    retried: take_command already removed the file on read, so nothing re-attempts it later — see
    ADR 0014's Considered Options for why a silently-late command would be worse than a dropped
    one for something controlling heat/humidity."""
    is_on = command["payload"]["is_on"]
    try:
        device.set_status(is_on, switch=current["switch_dps_key"])
    except Exception as exc:  # tinytuya raises plain exceptions on timeout/network errors
        print(f"[tuya_lan] {external_id}: Command failed ({exc}) — dropped, not retried")
        return
    print(f"[tuya_lan] {external_id}: Command executed -> is_on={is_on}")
    # A Command sent while Auto-Update was paused resumes it server-side
    # (web/admin_queries.py::send_plug_command) before the Outbox file is even written — correct
    # the locally-cached flag right away rather than waiting up to REFRESH_REGISTRY_SECONDS for the
    # next Registry re-read, so this same iteration's regular poll below actually reports the
    # confirming plug_state event instead of silently swallowing it under the stale flag.
    current["auto_update_enabled"] = True


def _poll_device(external_id: str, stop_event: threading.Event) -> None:
    info = _watched[external_id]
    device = tinytuya.OutletDevice(info["device_id"], info["ip_address"] or "Auto", info["local_key"], version="3.3")
    last_capture_time: float | None = None  # time.monotonic() of the last Data Capture write
    print(f"[tuya_lan] watching {external_id} (dps={info['switch_dps_key']})")

    while not stop_event.is_set():
        current = _watched.get(external_id)
        if current is None:
            print(f"[tuya_lan] {external_id}: no longer in Registry — stopping")
            return

        command = take_command(PLUGIN_NAME, external_id)
        if command is not None:
            _execute_command(device, external_id, current, command)

        try:
            status = device.status()
            dps = status.get("dps", {})
            switch_dps_key = current["switch_dps_key"]
            if switch_dps_key not in dps:
                print(f"[tuya_lan] {external_id}: no DPS key {switch_dps_key!r} in {dps} "
                      f"(run tools/tuya_probe.py to find the right key)")
            elif current["auto_update_enabled"]:  # see CONTEXT.md: Auto-Update
                write_event(PLUGIN_NAME, external_id, "plug_state", {"is_on": bool(dps[switch_dps_key])})

            if current["auto_update_enabled"]:
                now = time.monotonic()
                if last_capture_time is None or (now - last_capture_time) >= DATA_CAPTURE_INTERVAL_SECONDS:
                    last_capture_time = now
                    _capture_telemetry(external_id, dps)
        except Exception as exc:  # tinytuya raises plain exceptions on timeout/network errors
            print(f"[tuya_lan] {external_id}: poll failed ({exc})")
            # No explicit failure event — see CONTEXT.md: Unreachable, Ingest. A run of failed polls
            # just means no plug_state event arrives, which Ingest already treats as Unreachable
            # once nothing has arrived for the Alert Debounce window.

        stop_event.wait(POLL_INTERVAL_SECONDS)


def main() -> None:
    stop_event = threading.Event()
    threads: dict[str, threading.Thread] = {}

    try:
        while True:
            _refresh_registry()
            for external_id in _watched:
                if external_id not in threads:
                    t = threading.Thread(target=_poll_device, args=(external_id, stop_event), daemon=True)
                    t.start()
                    threads[external_id] = t
            time.sleep(REFRESH_REGISTRY_SECONDS)
    except KeyboardInterrupt:
        print("\n[tuya_lan] stopping...")
        stop_event.set()
        for t in threads.values():
            t.join(timeout=2)


if __name__ == "__main__":
    main()
