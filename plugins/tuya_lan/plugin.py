"""Local Tuya Plugin for Gosund Plugs (see ADR 0001 — this one containerizes fine, unlike the
Govee Plugin, since it's plain LAN traffic rather than BLE).

Polls each registered device's raw status over the LAN on a 5s cadence and drops a plug_state
Plugin Event into the Inbox on *every* poll — not just when the on/off DPS value changes. Ingest
does the edge-detection from there (see CONTEXT.md: Ingest; ADR 0013), which is also what lets Plug
Unreachable be a plain absence check, the same mechanism Sensor Unreachable already used. A nice
side effect: unlike the pre-ADR-0013 version of this file, a live Auto-Update pause (see CONTEXT.md)
now takes effect on the very next poll instead of only at process restart, since every poll re-checks
the current Registry rather than baking the flag in once at thread start.

One connection per physical device, not per registered outlet: a multi-outlet power strip (see
db/schema.sql's comment on `plug`) registers each of its switched outlets as its own Plug/external_id
sharing one Tuya device_id. Polling is grouped by device_id — one thread, one tinytuya.OutletDevice,
one status() call per cycle, fanned out to whichever outlets are registered on it — rather than one
independent connection per outlet. Cheap Tuya/Gosund hardware only accepts a handful of concurrent
local sessions; three outlets on one strip each opening their own connection every 5s starves
whichever one loses the race, seen in practice as that one outlet's Plug going persistently
Unreachable while its siblings stay healthy. Auto-Update and Command execution stay per-outlet
(a Command only ever addresses one switch_dps_key) — only the connection and the raw status() call
are shared.

After RESCAN_AFTER_CONSECUTIVE_FAILURES straight poll failures for a device (a real connection
failure — timeout, refused, undecryptable response — not just one outlet's DPS key missing from an
otherwise-good response), it does one broadcast rescan looking for that device_id's current LAN IP,
the same recovery a stale DHCP lease needs today's tools/tuya_verify_connections.py or a manual
Admin edit for. In-memory only, deliberately: a Plugin never touches the database (see CONTEXT.md:
Plugin; ADR 0013), so a recovered IP lives only as long as this process does — the next restart
starts from the stored IP again and re-earns its way back if it's still stale. See _rescan_for_ip.

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
RESCAN_AFTER_CONSECUTIVE_FAILURES = 3  # ~15s of real failures (not just a missing DPS key) before
                                        # trying a broadcast rescan — see module docstring
RESCAN_TIMEOUT_SECONDS = 6

# device_id -> {"local_key", "ip_address"} — one entry per physical device, shared by every outlet
# registered on it (see this file's module docstring on connection sharing).
_devices: dict[str, dict] = {}
# external_id -> {"device_id", "switch_dps_key", "auto_update_enabled"} — one entry per registered
# outlet Plug.
_watched: dict[str, dict] = {}


def _refresh_registry() -> None:
    devices: dict[str, dict] = {}
    watched: dict[str, dict] = {}
    for entry in read_registry(PLUGIN_NAME):
        external_id = entry["external_id"]
        device_id, dps_key = decode_external_id(external_id)
        config = unpack_config(entry.get("plugin_config"))
        # Sibling outlets on the same device_id are expected to carry identical local_key/
        # ip_address (they're the same physical device) — last one read wins on the rare occasion
        # they've drifted, same "not worth a cross-row CHECK" tradeoff as the rest of this schema.
        devices[device_id] = {"local_key": config["local_key"], "ip_address": config["ip_address"]}
        watched[external_id] = {
            "device_id": device_id,
            "switch_dps_key": dps_key,
            "auto_update_enabled": entry.get("auto_update_enabled", True),
        }
    _devices.clear()
    _devices.update(devices)
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


# A broadcast scan binds a fixed UDP discovery port — two device-group threads rescanning at once
# collide on it (confirmed live: tinytuya raises "[WinError 10048] Only one usage of each socket
# address..."). Serialized behind one lock, with the result cached briefly so a real network blip
# that knocks out several devices at once — the actual scenario this feature is for — triggers one
# shared scan instead of each thread's own redundant one.
_rescan_lock = threading.Lock()
_last_scan: dict | None = None  # {"time": monotonic(), "devices": tinytuya.deviceScan() result}
_SCAN_CACHE_SECONDS = 10


def _rescan_for_ip(device_id: str) -> str | None:
    """One broadcast discovery pass looking for device_id's current LAN IP — see module docstring.
    Returns None if it isn't found (device actually offline, or on a network segment the broadcast
    doesn't reach); never writes anywhere, in-memory recovery only (see CONTEXT.md: Plugin)."""
    global _last_scan
    with _rescan_lock:
        if _last_scan is None or (time.monotonic() - _last_scan["time"]) > _SCAN_CACHE_SECONDS:
            try:
                found = tinytuya.deviceScan(False, RESCAN_TIMEOUT_SECONDS, color=False, poll=False)
            except Exception as exc:  # tinytuya raises plain exceptions on scan-level socket errors too
                print(f"[tuya_lan] {device_id}: rescan failed ({exc})")
                return None
            _last_scan = {"time": time.monotonic(), "devices": found}
        found = _last_scan["devices"]
    for ip, info in found.items():
        if info.get("gwId") == device_id or info.get("id") == device_id:
            return ip
    return None


def _outlets_for(device_id: str) -> list[str]:
    """Every currently-registered outlet (external_id) sharing this physical device_id, in no
    particular order — recomputed fresh each poll cycle so an outlet added/removed/paused via
    Auto-Update takes effect on the very next poll, same as before this file grouped by device_id."""
    return [external_id for external_id, info in _watched.items() if info["device_id"] == device_id]


def _poll_device_group(device_id: str, stop_event: threading.Event) -> None:
    """One physical Tuya device, one shared connection, fanned out to every outlet registered on
    it — see this file's module docstring for why (a multi-outlet strip's outlets used to each open
    their own connection and starve each other out)."""
    info = _devices[device_id]
    device = tinytuya.OutletDevice(device_id, info["ip_address"] or "Auto", info["local_key"], version="3.3")
    last_capture_time: float | None = None  # time.monotonic() of the last Data Capture write
    # Straight failed-poll count, not tied to _refresh_registry's 60s cadence — see
    # RESCAN_AFTER_CONSECUTIVE_FAILURES. A rescan that finds a new IP rebuilds `device` and updates
    # `info` locally only; it's never written back to _devices or the database (see module docstring).
    consecutive_failures = 0
    print(f"[tuya_lan] watching {device_id} (outlets: {', '.join(_outlets_for(device_id))})")

    while not stop_event.is_set():
        outlet_ids = _outlets_for(device_id)
        if not outlet_ids:
            print(f"[tuya_lan] {device_id}: no outlets left in Registry — stopping")
            return

        for external_id in outlet_ids:
            current = _watched.get(external_id)
            if current is None:
                continue
            command = take_command(PLUGIN_NAME, external_id)
            if command is not None:
                _execute_command(device, external_id, current, command)

        try:
            status = device.status()
            if not status or "Error" in status:
                # tinytuya sometimes returns this instead of raising (see plug_probe.py's identical
                # normalization) — treat it the same as a raised exception so it counts toward
                # RESCAN_AFTER_CONSECUTIVE_FAILURES instead of silently landing as a missing DPS key.
                raise RuntimeError(status.get("Error", "no response from device") if status else "no response from device")
            consecutive_failures = 0
            dps = status.get("dps", {})
            any_auto_update = False
            for external_id in outlet_ids:
                current = _watched.get(external_id)
                if current is None:
                    continue
                switch_dps_key = current["switch_dps_key"]
                if switch_dps_key not in dps:
                    print(f"[tuya_lan] {external_id}: no DPS key {switch_dps_key!r} in {dps} "
                          f"(run tools/tuya_probe.py to find the right key)")
                elif current["auto_update_enabled"]:  # see CONTEXT.md: Auto-Update
                    write_event(PLUGIN_NAME, external_id, "plug_state", {"is_on": bool(dps[switch_dps_key])})
                any_auto_update = any_auto_update or current["auto_update_enabled"]

            if any_auto_update:
                now = time.monotonic()
                if last_capture_time is None or (now - last_capture_time) >= DATA_CAPTURE_INTERVAL_SECONDS:
                    last_capture_time = now
                    for external_id in outlet_ids:
                        _capture_telemetry(external_id, dps)
        except Exception as exc:  # tinytuya raises plain exceptions on timeout/network errors
            print(f"[tuya_lan] {device_id}: poll failed ({exc})")
            # No explicit failure event — see CONTEXT.md: Unreachable, Ingest. A run of failed polls
            # just means no plug_state event arrives, which Ingest already treats as Unreachable
            # once nothing has arrived for the Alert Debounce window.
            consecutive_failures += 1
            if consecutive_failures >= RESCAN_AFTER_CONSECUTIVE_FAILURES:
                print(f"[tuya_lan] {device_id}: {consecutive_failures} straight failures — "
                      f"rescanning the LAN for a new IP")
                consecutive_failures = 0  # cooldown regardless of outcome — see _rescan_for_ip
                new_ip = _rescan_for_ip(device_id)
                old_ip = info.get("ip_address")
                if new_ip and new_ip != old_ip:
                    print(f"[tuya_lan] {device_id}: found at {new_ip} (was {old_ip!r}) — "
                          f"using it for the rest of this run (not saved)")
                    info = {**info, "ip_address": new_ip}
                    device = tinytuya.OutletDevice(device_id, new_ip, info["local_key"], version="3.3")
                elif new_ip:
                    print(f"[tuya_lan] {device_id}: rescan found it at the same address "
                          f"({new_ip}) — the IP isn't the problem")
                else:
                    print(f"[tuya_lan] {device_id}: rescan didn't find this device on the network")

        stop_event.wait(POLL_INTERVAL_SECONDS)


def main() -> None:
    stop_event = threading.Event()
    threads: dict[str, threading.Thread] = {}

    try:
        while True:
            _refresh_registry()
            for device_id in _devices:
                if device_id not in threads:
                    t = threading.Thread(target=_poll_device_group, args=(device_id, stop_event), daemon=True)
                    t.start()
                    threads[device_id] = t
            time.sleep(REFRESH_REGISTRY_SECONDS)
    except KeyboardInterrupt:
        print("\n[tuya_lan] stopping...")
        stop_event.set()
        for t in threads.values():
            t.join(timeout=2)


if __name__ == "__main__":
    main()
