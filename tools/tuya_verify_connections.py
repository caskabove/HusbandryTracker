"""Verifies every registered Tuya (Gosund) Plug is actually reachable, without touching the
running app — a standalone health check for plugins/tuya_lan/plugin.py's device connections (see
CONTEXT.md: Plugin).

Groups Plugs by physical device_id, same as the live Plugin's own connection-sharing (see
plugins/tuya_lan/plugin.py's module docstring) — a multi-outlet strip gets one connection here too,
not one per outlet. For each device_id it:
  1. Checks every outlet sharing that device_id stores the same local_key/ip_address — they're the
     same physical device, so they must agree; a mismatch here (an outlet with a stale/wrong key)
     is a real bug, not a network problem, and won't be fixed by anything on the LAN side.
  2. Makes one status() call and confirms every outlet's switch_dps_key actually shows up in the
     response.

Reads Plug rows directly from the database — this is a diagnostic, not a Plugin, so it doesn't go
through the Registry/Inbox contract (ADR 0013); it's fine for it to query the DB the way
tools/register_device.py and the Admin UI already do.

Exits 0 if every device passes, 1 if anything failed — safe to run periodically or by hand.

Run: .venv/Scripts/python.exe tools/tuya_verify_connections.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tinytuya

from db.db import get_connection
from plugins.tuya_lan.identity import decode_external_id, unpack_config

CONNECTION_TIMEOUT_SECONDS = 6


@dataclass
class Outlet:
    plug_id: int
    label: str
    external_id: str
    switch_dps_key: str
    local_key: str | None
    ip_address: str | None


@dataclass
class DeviceGroup:
    device_id: str
    outlets: list[Outlet] = field(default_factory=list)


def _load_device_groups() -> dict[str, DeviceGroup]:
    groups: dict[str, DeviceGroup] = {}
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, label, external_id, plugin_config FROM plug "
            "WHERE plugin = 'tuya_lan' ORDER BY external_id"
        ).fetchall()
    for row in rows:
        device_id, dps_key = decode_external_id(row["external_id"])
        config = unpack_config(row["plugin_config"])
        groups.setdefault(device_id, DeviceGroup(device_id)).outlets.append(
            Outlet(row["id"], row["label"], row["external_id"], dps_key,
                   config["local_key"], config["ip_address"])
        )
    return groups


def _check_consistency(group: DeviceGroup) -> list[str]:
    """Sibling outlets on one physical device must share the same local_key/ip_address — a
    mismatch means one of them has stale/wrong stored credentials (the exact bug this tool exists
    to catch), not a connectivity problem."""
    problems = []
    keys = {o.local_key for o in group.outlets}
    ips = {o.ip_address for o in group.outlets}
    if len(keys) > 1:
        for o in group.outlets:
            problems.append(f"  local_key mismatch: Plug {o.plug_id} ({o.label!r}) has a "
                             f"different local_key than its sibling outlet(s) on this device")
    if len(ips) > 1:
        for o in group.outlets:
            problems.append(f"  ip_address mismatch: Plug {o.plug_id} ({o.label!r}) has "
                             f"ip_address={o.ip_address!r}, a sibling outlet has a different one")
    return problems


def _check_connection(group: DeviceGroup) -> list[str]:
    problems = []
    # Consistency already reported separately — connect using whichever config the *first* outlet
    # has, since that's what a shared connection would actually use in practice.
    primary = group.outlets[0]
    if not primary.local_key:
        return [f"  no local_key stored for any outlet on this device — can't connect at all"]
    device = tinytuya.OutletDevice(
        group.device_id, primary.ip_address or "Auto", primary.local_key, version="3.3",
        connection_timeout=CONNECTION_TIMEOUT_SECONDS, connection_retry_limit=1,
    )
    try:
        status = device.status()
    except Exception as exc:  # tinytuya raises plain exceptions on timeout/network errors
        return [f"  connection failed: {exc}"]
    if not status or "Error" in status:
        return [f"  connection failed: {status.get('Error') if status else 'no response from device'}"]
    dps = status.get("dps", {})
    for outlet in group.outlets:
        if outlet.switch_dps_key not in dps:
            problems.append(f"  Plug {outlet.plug_id} ({outlet.label!r}): no DPS key "
                             f"{outlet.switch_dps_key!r} in response {dps} — wrong switch_dps_key? "
                             f"(see tools/tuya_probe.py)")
    return problems


def main() -> None:
    groups = _load_device_groups()
    if not groups:
        print("No registered Tuya Plugs found.")
        return

    failed = 0
    for device_id, group in sorted(groups.items()):
        labels = ", ".join(f"{o.label!r} ({o.external_id})" for o in group.outlets)
        print(f"{device_id}  [{labels}]")

        problems = _check_consistency(group) + _check_connection(group)
        if problems:
            failed += 1
            print("  FAIL")
            for line in problems:
                print(line)
        else:
            print("  OK")

    total = len(groups)
    print(f"\n{total - failed}/{total} devices OK")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
