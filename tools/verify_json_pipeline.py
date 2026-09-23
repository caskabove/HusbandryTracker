"""Read-only health check for the Registry/Inbox/Outbox filesystem contract (see CONTEXT.md:
Plugin, Registry, Inbox, Outbox, Plugin Event, Command; ADR 0013/0014) — a standalone diagnostic,
not a Plugin or Ingest itself. Never writes anything; safe to run against a live production data/
directory at any time, including while Ingest and every Plugin are running.

Cross-checks each side of the contract against the other instead of trusting either alone:
  1. Registry vs. database — every currently-registered Smart Sensor/Plug should have a matching
     entry in its Plugin's Registry export, and vice versa (a stale entry left after a device was
     deregistered means Ingest hasn't re-exported since, or is stuck).
  2. Inbox backlog — Plugin Event files older than --stuck-after-seconds mean Ingest isn't
     draining them (crashed, hung, or genuinely stopped).
  3. _rejected quarantine — anything here already failed schema validation once; Ingest never
     retries it, so it just sits there until someone looks (see ingest/ingest.py's _quarantine).
  4. Outbox backlog — Command files older than --stuck-after-seconds mean the target Plugin isn't
     polling (crashed, hung, or the device is offline and no rescan has recovered it) or the
     external_id no longer resolves to a device it's watching.
  5. Schema validation — every file currently sitting in the Inbox or Outbox is re-validated
     against schemas/plugin_event.schema.json / schemas/plug_command.schema.json right now, ahead
     of whichever process would otherwise validate it. Ingest/Plugin already do this on their own;
     this just surfaces the same failure without waiting for their poll cycle.

Exits 0 if nothing looks wrong, 1 if any check found something. Safe to run periodically (e.g.
from a cron job or the tray Supervisor) or by hand while debugging.

Run: .venv/Scripts/python.exe tools/verify_json_pipeline.py
     .venv/Scripts/python.exe tools/verify_json_pipeline.py --stuck-after-seconds 60
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jsonschema

from db.db import get_connection

REPO_ROOT = Path(__file__).resolve().parent.parent
INBOX_DIR = REPO_ROOT / "data" / "inbox"
REGISTRY_DIR = REPO_ROOT / "data" / "registry"
OUTBOX_DIR = REPO_ROOT / "data" / "outbox"
REJECTED_DIR = INBOX_DIR / "_rejected"
EVENT_KINDS = ["sensor_reading", "plug_state", "plug_telemetry"]

PLUGIN_EVENT_SCHEMA_PATH = REPO_ROOT / "schemas" / "plugin_event.schema.json"
PLUG_COMMAND_SCHEMA_PATH = REPO_ROOT / "schemas" / "plug_command.schema.json"

DEFAULT_STUCK_AFTER_SECONDS = 120  # generous multiple of both the 5s Plugin poll and Ingest's
                                    # default 5s scan interval (app_setting.ingest_scan_interval_seconds)


def _load_validator(schema_path: Path) -> jsonschema.Draft202012Validator:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


def _registered_devices() -> dict[str, set[str]]:
    """plugin -> set of external_id, for every currently-registered Smart Sensor/Plug — the same
    query ingest/ingest.py's _export_registry uses to decide what belongs in each Registry file."""
    devices: dict[str, set[str]] = {}
    with get_connection() as conn:
        for table in ("sensor", "plug"):
            rows = conn.execute(
                f"SELECT plugin, external_id FROM {table} "
                f"WHERE tracking_mode = 'smart' AND plugin IS NOT NULL"
            ).fetchall()
            for row in rows:
                devices.setdefault(row["plugin"], set()).add(row["external_id"])
    return devices


def check_registry_matches_database(issues: list[str]) -> None:
    print("== Registry vs. database ==")
    devices = _registered_devices()
    registry_files = {p.stem: p for p in REGISTRY_DIR.glob("*.json")} if REGISTRY_DIR.exists() else {}

    for plugin, external_ids in devices.items():
        path = registry_files.get(plugin)
        if path is None:
            issues.append(f"registry: {plugin} has {len(external_ids)} registered device(s) but no "
                           f"data/registry/{plugin}.json file exists yet")
            print(f"  MISSING FILE: {plugin} - {len(external_ids)} device(s) registered in the "
                  f"database, no Registry file")
            continue
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
            registry_ids = {e["external_id"] for e in entries}
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            issues.append(f"registry: {path.name} is unreadable ({exc})")
            print(f"  UNREADABLE: {path.name} ({exc})")
            continue
        missing = external_ids - registry_ids
        stale = registry_ids - external_ids
        if missing:
            issues.append(f"registry: {plugin} is missing {sorted(missing)} (registered in the "
                           f"database, absent from the Registry file)")
            print(f"  MISSING FROM FILE ({plugin}): {sorted(missing)}")
        if stale:
            issues.append(f"registry: {plugin}'s file has stale entries {sorted(stale)} (no longer "
                           f"registered in the database)")
            print(f"  STALE IN FILE ({plugin}): {sorted(stale)}")
        if not missing and not stale:
            print(f"  OK: {plugin} ({len(external_ids)} device(s), file matches database)")

    for stale_plugin in registry_files.keys() - devices.keys():
        issues.append(f"registry: {stale_plugin}.json exists but no device references that plugin "
                       f"anymore")
        print(f"  STALE FILE: {stale_plugin}.json - no registered device uses this plugin")

    if not devices and not registry_files:
        print("  (no Smart Sensors/Plugs registered, no Registry files - nothing to check)")


def check_inbox_backlog(issues: list[str], stuck_after_seconds: float) -> None:
    print("== Inbox backlog ==")
    now = time.time()
    found_any = False
    for kind in EVENT_KINDS:
        kind_dir = INBOX_DIR / kind
        if not kind_dir.is_dir():
            continue
        for path in sorted(kind_dir.glob("*.json")):
            found_any = True
            age = now - path.stat().st_mtime
            if age > stuck_after_seconds:
                issues.append(f"inbox: {path.relative_to(REPO_ROOT)} is {age:.0f}s old and still "
                               f"undrained — Ingest may not be running")
                print(f"  STUCK: {path.relative_to(REPO_ROOT)} ({age:.0f}s old)")
    if not found_any:
        print("  (empty - Ingest is keeping up, or nothing has reported yet)")


def check_rejected_quarantine(issues: list[str]) -> None:
    print("== Rejected (quarantine) ==")
    if not REJECTED_DIR.exists():
        print("  (no _rejected directory - nothing has ever been quarantined)")
        return
    files = sorted(REJECTED_DIR.rglob("*.json"))
    if not files:
        print("  (empty)")
        return
    for path in files:
        issues.append(f"rejected: {path.relative_to(REPO_ROOT)} was quarantined and never "
                       f"reprocessed — see ingest/ingest.py's _quarantine")
        print(f"  QUARANTINED: {path.relative_to(REPO_ROOT)}")


def check_outbox_backlog(issues: list[str], stuck_after_seconds: float) -> None:
    print("== Outbox backlog ==")
    if not OUTBOX_DIR.exists():
        print("  (no Outbox directory yet - no Command has ever been issued)")
        return
    devices = _registered_devices()
    now = time.time()
    found_any = False
    for plugin_dir in sorted(p for p in OUTBOX_DIR.iterdir() if p.is_dir()):
        for path in sorted(plugin_dir.glob("*.json")):
            found_any = True
            age = now - path.stat().st_mtime
            try:
                command = json.loads(path.read_text(encoding="utf-8"))
                external_id = command.get("external_id")
            except json.JSONDecodeError:
                external_id = None
            if external_id is not None and external_id not in devices.get(plugin_dir.name, set()):
                issues.append(f"outbox: {path.relative_to(REPO_ROOT)} targets {external_id!r}, "
                               f"which isn't currently registered under {plugin_dir.name}")
                print(f"  ORPHAN: {path.relative_to(REPO_ROOT)} (external_id {external_id!r} not "
                      f"registered)")
            if age > stuck_after_seconds:
                issues.append(f"outbox: {path.relative_to(REPO_ROOT)} is {age:.0f}s old and still "
                               f"pending — the {plugin_dir.name} Plugin may not be polling")
                print(f"  STUCK: {path.relative_to(REPO_ROOT)} ({age:.0f}s old)")
    if not found_any:
        print("  (empty - no Command is currently pending)")


def check_schema_validity(issues: list[str]) -> None:
    print("== Schema validation (files currently on disk) ==")
    event_validator = _load_validator(PLUGIN_EVENT_SCHEMA_PATH)
    command_validator = _load_validator(PLUG_COMMAND_SCHEMA_PATH)
    checked = 0

    for kind in EVENT_KINDS:
        kind_dir = INBOX_DIR / kind
        if not kind_dir.is_dir():
            continue
        for path in sorted(kind_dir.glob("*.json")):
            checked += 1
            try:
                event_validator.validate(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError as exc:
                issues.append(f"schema: {path.relative_to(REPO_ROOT)} is invalid JSON ({exc})")
                print(f"  INVALID JSON: {path.relative_to(REPO_ROOT)}")
            except jsonschema.ValidationError as exc:
                issues.append(f"schema: {path.relative_to(REPO_ROOT)} violates plugin_event.schema.json "
                               f"({exc.message})")
                print(f"  SCHEMA VIOLATION: {path.relative_to(REPO_ROOT)} ({exc.message})")

    if OUTBOX_DIR.exists():
        for plugin_dir in sorted(p for p in OUTBOX_DIR.iterdir() if p.is_dir()):
            for path in sorted(plugin_dir.glob("*.json")):
                checked += 1
                try:
                    command_validator.validate(json.loads(path.read_text(encoding="utf-8")))
                except json.JSONDecodeError as exc:
                    issues.append(f"schema: {path.relative_to(REPO_ROOT)} is invalid JSON ({exc})")
                    print(f"  INVALID JSON: {path.relative_to(REPO_ROOT)}")
                except jsonschema.ValidationError as exc:
                    issues.append(f"schema: {path.relative_to(REPO_ROOT)} violates "
                                   f"plug_command.schema.json ({exc.message})")
                    print(f"  SCHEMA VIOLATION: {path.relative_to(REPO_ROOT)} ({exc.message})")

    if checked == 0:
        print("  (no Inbox/Outbox files currently on disk to check)")
    else:
        print(f"  ({checked} file(s) checked)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stuck-after-seconds", type=float, default=DEFAULT_STUCK_AFTER_SECONDS,
                         help=f"age threshold for flagging an undrained Inbox/Outbox file "
                              f"(default: {DEFAULT_STUCK_AFTER_SECONDS})")
    args = parser.parse_args()

    issues: list[str] = []
    check_registry_matches_database(issues)
    check_inbox_backlog(issues, args.stuck_after_seconds)
    check_rejected_quarantine(issues)
    check_outbox_backlog(issues, args.stuck_after_seconds)
    check_schema_validity(issues)

    print()
    if issues:
        print(f"{len(issues)} issue(s) found:")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("No issues found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
