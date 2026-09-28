"""Husbandry Tracker Tuya Plug Report - a plain-language status check for non-technical users.

Covers three things about the tuya_lan Plugin (Gosund/Tuya smart plugs over the LAN - see
CONTEXT.md: Plugin; plugins/tuya_lan/plugin.py):
  1. Every Plug the app currently knows about - its last known on/off state, whether it can
     actually be reached on the network right now, and when it was last heard from.
  2. Any Tuya device found broadcasting on the local network that ISN'T registered in the app yet.
  3. Whether the app's saved files for this Plugin (its Registry export, Inbox reports, Outbox
     commands) look healthy - the same filesystem contract every Plugin uses (see CONTEXT.md:
     Registry, Inbox, Outbox; ADR 0013/0014).

This never changes anything the app has saved - it only reads the database and the data/registry,
data/inbox, data/outbox folders, plus makes read-only status() calls to your actual Tuya plugs and
one broadcast scan of the local network. Safe to run at any time, including while the app is
running. The reachability check and network scan below mean this can take up to about 20 seconds
if you have several plugs.

This is Tuya-specific. For a general check that the app can save/load its files at all (not tied
to any one brand), see tools/connection_test.py. For a from-scratch technical breakdown, see
tools/tuya_verify_connections.py and tools/verify_json_pipeline.py.

Run: .venv/Scripts/python.exe tools/tuya_status_check.py
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tinytuya

from db.db import get_connection
from plugins.tuya_lan.identity import PLUGIN_NAME, decode_external_id, unpack_config

CONNECTION_TIMEOUT_SECONDS = 6
SCAN_SECONDS = 8
STUCK_AFTER_SECONDS = 120  # generous multiple of the 5s poll/scan cadences described in CONTEXT.md

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_DIR = REPO_ROOT / "data" / "registry"
INBOX_DIR = REPO_ROOT / "data" / "inbox"
OUTBOX_DIR = REPO_ROOT / "data" / "outbox"
REJECTED_DIR = INBOX_DIR / "_rejected"


@dataclass
class Outlet:
    plug_id: int
    label: str
    external_id: str
    switch_dps_key: str
    local_key: str | None
    ip_address: str | None
    last_seen_at: str | None
    last_is_on: int | None


@dataclass
class DeviceGroup:
    device_id: str
    outlets: list[Outlet] = field(default_factory=list)


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


def _load_device_groups() -> dict[str, DeviceGroup]:
    groups: dict[str, DeviceGroup] = {}
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT p.id, p.label, p.external_id, p.plugin_config, pls.last_seen_at, "
            "(SELECT is_on FROM plug_state_transition WHERE plug_id = p.id "
            " ORDER BY recorded_at DESC LIMIT 1) AS last_is_on "
            "FROM plug p LEFT JOIN plug_last_seen pls ON pls.plug_id = p.id "
            "WHERE p.plugin = ? ORDER BY p.external_id",
            (PLUGIN_NAME,),
        ).fetchall()
    for row in rows:
        device_id, dps_key = decode_external_id(row["external_id"])
        config = unpack_config(row["plugin_config"])
        groups.setdefault(device_id, DeviceGroup(device_id)).outlets.append(Outlet(
            row["id"], row["label"], row["external_id"], dps_key,
            config["local_key"], config["ip_address"], row["last_seen_at"], row["last_is_on"],
        ))
    return groups


def _check_reachable(group: DeviceGroup) -> tuple[bool, str]:
    """One shared connection per physical device, same as the live Plugin - see
    plugins/tuya_lan/plugin.py's module docstring on why outlets share a connection."""
    primary = group.outlets[0]
    if not primary.local_key:
        return False, "no saved connection key for this device"
    device = tinytuya.OutletDevice(
        group.device_id, primary.ip_address or "Auto", primary.local_key, version="3.3",
        connection_timeout=CONNECTION_TIMEOUT_SECONDS, connection_retry_limit=1,
    )
    try:
        status = device.status()
    except Exception as exc:  # tinytuya raises plain exceptions on timeout/network errors
        return False, f"couldn't connect ({exc})"
    if not status or "Error" in status:
        return False, f"couldn't connect ({status.get('Error') if status else 'no response'})"
    return True, ""


def print_known_plugs(groups: dict[str, DeviceGroup]) -> dict[str, tuple[bool, str]]:
    print("== Plugs this app knows about ==")
    if not groups:
        print("  No Tuya Plugs have been added yet (Admin > + Plug).")
        print()
        return {}

    print(f"  Checking {len(groups)} device(s) are reachable - this can take a few seconds...")
    reachability = {device_id: _check_reachable(group) for device_id, group in groups.items()}

    name_w = max(len(o.label) for g in groups.values() for o in g.outlets)
    name_w = max(name_w, len("Name"))
    header = f"  {'Name':<{name_w}}  {'Status':<8}  {'Reachable':<9}  Last heard from"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for device_id, group in sorted(groups.items()):
        reachable, detail = reachability[device_id]
        for o in group.outlets:
            status = "unknown" if o.last_is_on is None else ("On" if o.last_is_on else "Off")
            reachable_text = "Yes" if reachable else "No"
            line = (f"  {o.label:<{name_w}}  {status:<8}  {reachable_text:<9}  "
                    f"{_friendly_age(o.last_seen_at)}")
            if detail:
                line += f"  ({detail})"
            print(line)
    print()
    return reachability


def scan_for_new_devices(known_device_ids: set[str]) -> None:
    print(f"== Scanning your network for Tuya devices (up to {SCAN_SECONDS}s) ==")
    try:
        found = tinytuya.deviceScan(False, SCAN_SECONDS, color=False, poll=False)
    except Exception as exc:  # tinytuya raises plain exceptions on scan-level socket errors
        print(f"  Couldn't scan the network ({exc})")
        print()
        return

    new_devices = []
    for ip, info in found.items():
        device_id = info.get("gwId") or info.get("id")
        if device_id and device_id not in known_device_ids:
            new_devices.append((device_id, ip))

    if not new_devices:
        if found:
            print(f"  Found {len(found)} Tuya device(s) on your network - all of them are already "
                  f"added to Husbandry Tracker.")
        else:
            print("  No Tuya devices responded to the scan. This is normal if your network/router")
            print("  blocks broadcast discovery - it doesn't necessarily mean anything is wrong.")
        print()
        return

    print(f"  Found {len(new_devices)} device(s) on your network that aren't in Husbandry Tracker yet:")
    for device_id, ip in new_devices:
        print(f"    - {device_id}  (at {ip}) - add it from Admin > + Plug")
    print()


def check_files(known_external_ids: set[str]) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    path = REGISTRY_DIR / f"{PLUGIN_NAME}.json"
    if not path.exists():
        if known_external_ids:
            results.append(("Device list is up to date", False,
                             "no file yet - the app may not have run since these Plugs were added"))
        else:
            results.append(("Device list is up to date", True, "no Tuya Plugs registered yet"))
    else:
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
            registry_ids = {e["external_id"] for e in entries}
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            results.append(("Device list is up to date", False, f"file is unreadable ({exc})"))
        else:
            missing = known_external_ids - registry_ids
            stale = registry_ids - known_external_ids
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

    stuck = []
    plugin_outbox = OUTBOX_DIR / PLUGIN_NAME
    if plugin_outbox.exists():
        now = time.time()
        stuck = [f for f in plugin_outbox.glob("*.json") if now - f.stat().st_mtime > STUCK_AFTER_SECONDS]
    if stuck:
        results.append(("No commands stuck waiting", False,
                         f"{len(stuck)} command(s) haven't been picked up - is the app running?"))
    else:
        results.append(("No commands stuck waiting", True, ""))

    return results


def print_file_health(results: list[tuple[str, bool, str]]) -> bool:
    print("== Is the app saving/loading its Tuya files correctly? ==")
    name_w = max(len(name) for name, _, _ in results)
    for name, passed, detail in results:
        text = "PASS" if passed else "FAIL"
        line = f"  {name:<{name_w}}  {text}"
        if detail:
            line += f"  - {detail}"
        print(line)
    print()
    return all(passed for _, passed, _ in results)


def main() -> int:
    print()
    print("=" * 60)
    print("  Husbandry Tracker Tuya Plug Report")
    print("=" * 60)
    print()

    groups = _load_device_groups()
    reachability = print_known_plugs(groups)

    known_device_ids = set(groups.keys())
    scan_for_new_devices(known_device_ids)

    known_external_ids = {o.external_id for g in groups.values() for o in g.outlets}
    file_results = check_files(known_external_ids)
    files_ok = print_file_health(file_results)

    all_reachable = all(ok for ok, _ in reachability.values())
    if all_reachable and files_ok:
        print("Everything looks good.")
        return 0
    print("Some things need attention - see 'No'/FAIL above and docs/DEBUGGING_JSON_PIPELINE.md.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
