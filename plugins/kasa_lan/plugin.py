"""Local TP-Link Kasa / Tapo Plugin for Plugs (see docs/plugin-standard.md section 7; ADR 0062).

Same runtime contract as tuya_lan (ADR 0013/0014): it never opens the database. It reads what to
watch from its own Registry export (data/registry/kasa_lan.json) and the TP-Link login from its
runtime settings (data/registry/settings/kasa_lan.json, written by Ingest). It drops a plug_state
Plugin Event into the Inbox on every poll, not just on change, takes on/off Commands from its
Outbox, and writes plug_telemetry (watts/volts/amps) on a slower cadence for models with an energy
meter.

One connection per physical device, not per outlet: a power strip's outlets (External IDs
"<MAC>#1", "<MAC>#2"...) share one python-kasa Device, one update() per poll, fanned out to each
registered outlet. Cheap smart plugs only accept a few local sessions, which is the same reason
tuya_lan groups by device_id.

Devices are tracked by MAC, not IP. If a device stops answering for
RESCAN_AFTER_CONSECUTIVE_FAILURES polls in a row, the Plugin broadcasts once to find that MAC's
current address and uses it for the rest of this run (in memory only, never written back, since a
Plugin never touches the database). A Plug registered with no IP at all is found the same way.

A Command is executed at most once and never retried (take_command removes the file on read), the
same rule as tuya_lan: a late "turn the heat on" is worse than a dropped one.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from kasa import AuthenticationError

from plugins.common import read_plugin_settings, read_registry, take_command, write_event
from plugins.kasa_lan import kasa_io
from plugins.kasa_lan.identity import PLUGIN_NAME, decode_external_id, normalize_mac, unpack_config

POLL_INTERVAL_SECONDS = 5
REFRESH_REGISTRY_SECONDS = 60
DATA_CAPTURE_INTERVAL_SECONDS = 120  # 1-5 min per ADR 0009; independent of the 5s state watch
RESCAN_AFTER_CONSECUTIVE_FAILURES = 3

# mac -> last-known host from the Registry (None when the Plug was registered without an IP).
_hosts: dict[str, str | None] = {}
# external_id -> {"mac", "outlet", "auto_update_enabled"}, one entry per registered outlet Plug.
_watched: dict[str, dict] = {}
_settings: dict[str, str] = {}


def _log(message: str) -> None:
    print(f"[{PLUGIN_NAME}] {message}", flush=True)


def refresh_registry() -> None:
    hosts: dict[str, str | None] = {}
    watched: dict[str, dict] = {}
    for entry in read_registry(PLUGIN_NAME):
        external_id = entry["external_id"]
        try:
            mac, outlet = decode_external_id(external_id)
            mac = normalize_mac(mac)
        except ValueError:
            _log(f"skipping unreadable External ID {external_id!r}")
            continue
        host = unpack_config(entry.get("plugin_config"))["host"]
        if host or mac not in hosts:
            hosts[mac] = host  # sibling outlets share one host; any non-empty one wins
        watched[external_id] = {
            "mac": mac,
            "outlet": outlet,
            "auto_update_enabled": entry.get("auto_update_enabled", True),
        }
    _hosts.clear()
    _hosts.update(hosts)
    _watched.clear()
    _watched.update(watched)
    _settings.clear()
    _settings.update(read_plugin_settings(PLUGIN_NAME))


def outlets_for(mac: str) -> list[str]:
    return [external_id for external_id, info in _watched.items() if info["mac"] == mac]


# One broadcast at a time: several devices failing together (router reboot) share one scan.
_scan_lock = asyncio.Lock()
_last_scan: dict | None = None  # {"time": monotonic, "hosts": {mac: host}}
_SCAN_CACHE_SECONDS = 15


async def find_host(mac: str) -> str | None:
    """Broadcasts once (or reuses a scan from the last few seconds) to find mac's current address.
    In-memory only; see module docstring."""
    global _last_scan
    async with _scan_lock:
        if _last_scan is None or time.monotonic() - _last_scan["time"] > _SCAN_CACHE_SECONDS:
            hosts: dict[str, str] = {}
            try:
                devices, _ = await kasa_io.scan(kasa_io.credentials_from(_settings))
            except Exception as exc:  # socket errors etc.; try again next time
                _log(f"rescan failed ({exc})")
                return None
            for device in devices:
                found_mac = kasa_io.safe_mac(device)
                if found_mac:
                    try:
                        hosts[normalize_mac(found_mac)] = device.host
                    except ValueError:
                        pass
                await kasa_io.disconnect(device)
            _last_scan = {"time": time.monotonic(), "hosts": hosts}
        return _last_scan["hosts"].get(mac)


async def execute_command(device, external_id: str, current: dict, command: dict) -> None:
    """Executes one Command from the Outbox (see CONTEXT.md: Command; ADR 0014). Only set_power
    exists. A failure is dropped, not retried; see module docstring."""
    is_on = command["payload"]["is_on"]
    switch = kasa_io.outlet_device(device, current["outlet"])
    if switch is None:
        _log(f"{external_id}: Command dropped, this device has no outlet {current['outlet']}")
        return
    try:
        await (switch.turn_on() if is_on else switch.turn_off())
    except Exception as exc:
        _log(f"{external_id}: Command failed ({exc}), dropped, not retried")
        return
    _log(f"{external_id}: Command executed -> is_on={is_on}")
    # A Command sent while Auto-Update was paused resumes it server-side; reflect that now so this
    # same poll reports the confirming plug_state (same reasoning as tuya_lan).
    current["auto_update_enabled"] = True


def report(device, outlet_ids: list[str], capture_telemetry: bool) -> bool:
    """Writes plug_state (and, when due, plug_telemetry) for each registered outlet. Returns
    whether any outlet has Auto-Update on, which is what makes telemetry due at all."""
    any_auto_update = False
    for external_id in outlet_ids:
        current = _watched.get(external_id)
        if current is None:
            continue
        switch = kasa_io.outlet_device(device, current["outlet"])
        if switch is None:
            _log(f"{external_id}: this device reports {len(device.children or [])} outlets, "
                 f"none numbered {current['outlet']}. Fix the outlet number on the Plug's Edit page.")
            continue
        if not current["auto_update_enabled"]:  # see CONTEXT.md: Auto-Update
            continue
        any_auto_update = True
        write_event(PLUGIN_NAME, external_id, "plug_state", {"is_on": bool(switch.is_on)})
        if capture_telemetry:
            # A strip without per-outlet meters only reports its own total, which isn't any one
            # outlet's draw, so it's only used for a single plug (outlet None).
            reading = kasa_io.energy(switch) or (kasa_io.energy(device) if current["outlet"] is None else None)
            if reading:
                write_event(PLUGIN_NAME, external_id, "plug_telemetry", {**reading, "countdown_seconds": None})
    return any_auto_update


async def poll_device(mac: str, stop: asyncio.Event) -> None:
    host = _hosts.get(mac)
    seen_registry_host = host
    device = None
    failures = 0
    last_capture: float | None = None
    _log(f"watching {mac} at {host or '(address unknown, will search)'} (outlets: {', '.join(outlets_for(mac))})")
    try:
        while not stop.is_set():
            outlet_ids = outlets_for(mac)
            if not outlet_ids:
                _log(f"{mac}: no Plugs left in the Registry, stopping")
                return
            registry_host = _hosts.get(mac)
            if registry_host != seen_registry_host:
                # The user edited the IP on the Plug's page; prefer it over anything found by a
                # rescan, and reconnect to it.
                seen_registry_host = registry_host
                if registry_host:
                    host = registry_host
                    device = await _drop(device)
            try:
                if device is None:
                    if not host:
                        host = await find_host(mac)
                        if not host:
                            raise RuntimeError("not found on the network")
                    device = await kasa_io.connect(host, kasa_io.credentials_from(_settings))
                    if device is None:
                        raise RuntimeError(f"nothing TP-Link answered at {host}")
                    found_mac = kasa_io.safe_mac(device)
                    if found_mac and normalize_mac(found_mac) != mac:
                        stale = host
                        host = None  # that address belongs to another device now; search by MAC
                        raise RuntimeError(f"{stale} is now a different device ({found_mac})")
                    _log(f"{mac}: connected at {host} ({device.model})")
                for external_id in outlet_ids:
                    current = _watched.get(external_id)
                    if current is None:
                        continue
                    command = take_command(PLUGIN_NAME, external_id)
                    if command is not None:
                        await execute_command(device, external_id, current, command)
                await device.update()
                failures = 0
                now = time.monotonic()
                due = last_capture is None or now - last_capture >= DATA_CAPTURE_INTERVAL_SECONDS
                if report(device, outlet_ids, due) and due:
                    last_capture = now
            except AuthenticationError:
                _log(f"{mac}: the plug refused the TP-Link login. Save the email and password you use "
                     f"in the Kasa/Tapo app on this Plugin's Settings page.")
                device = await _drop(device)
            except Exception as exc:
                # No failure event: a run of missing plug_state events is what Ingest already treats
                # as Unreachable (see CONTEXT.md: Unreachable).
                _log(f"{mac}: poll failed ({exc})")
                device = await _drop(device)
                failures += 1
                if failures >= RESCAN_AFTER_CONSECUTIVE_FAILURES:
                    failures = 0
                    new_host = await find_host(mac)
                    if new_host and new_host != host:
                        _log(f"{mac}: found at {new_host} (was {host!r}); using it for this run (not saved)")
                        host = new_host
            try:
                await asyncio.wait_for(stop.wait(), timeout=POLL_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass
    finally:
        await _drop(device)


async def _drop(device) -> None:
    if device is not None:
        await kasa_io.disconnect(device)
    return None


async def run(stop: asyncio.Event) -> None:
    tasks: dict[str, asyncio.Task] = {}
    while not stop.is_set():
        refresh_registry()
        for mac in _hosts:
            task = tasks.get(mac)
            if task is None or task.done():
                tasks[mac] = asyncio.create_task(poll_device(mac, stop))
        try:
            await asyncio.wait_for(stop.wait(), timeout=REFRESH_REGISTRY_SECONDS)
        except asyncio.TimeoutError:
            pass
    await asyncio.gather(*tasks.values(), return_exceptions=True)


def main() -> None:
    stop = asyncio.Event()
    try:
        asyncio.run(run(stop))
    except KeyboardInterrupt:
        _log("stopping...")


if __name__ == "__main__":
    main()
