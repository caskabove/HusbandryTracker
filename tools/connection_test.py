"""Husbandry Tracker App Connection Test - a plain-language check for non-technical users.

Confirms the app can actually save and load the small text files (JSON) it uses to talk to
Smart Sensors and Smart Plugs, in the real folders the running app uses (data/registry/,
data/inbox/, data/outbox/) - see CONTEXT.md: Plugin, Registry, Inbox, Outbox; ADR 0013/0014.

Each check below writes ONE temporary test record using a reserved fake device name
("_connection_test") that no real Sensor or Plug ever uses, reads it back through the app's own
code, and deletes it again - it never reads, writes, or deletes anything belonging to a real
device. Safe to run at any time, including while the app is running normally.

This is different from tools/verify_json_pipeline.py, which inspects your REAL sensors/plugs for
problems but never writes anything. Run this one first to confirm the plumbing itself works; run
that one if a specific device looks wrong.

Run: .venv/Scripts/python.exe tools/connection_test.py
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jsonschema

from plugins.common import (
    INBOX_DIR, REGISTRY_DIR, _atomic_write_json, read_registry, take_command, write_event,
)
from web.outbox import write_command

TEST_PLUGIN = "_connection_test"  # reserved name - no real Plugin is ever named this
TEST_DEVICE = "connection-test-probe"  # reserved id - no real device is ever named this

PLUGIN_EVENT_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "plugin_event.schema.json"
# How long to wait for a live Ingest process to notice and drain our test Inbox file before we
# give up and check it ourselves - a live app polls every few seconds (see
# app_setting.ingest_scan_interval_seconds), so either outcome below counts as a pass.
INBOX_WAIT_SECONDS = 3.0


@dataclass
class CheckResult:
    name: str
    what_it_checks: str
    passed: bool
    details: str = ""


def _cleanup(path: Path) -> None:
    path.unlink(missing_ok=True)


def check_registry() -> CheckResult:
    """Writes a fake device list the way Ingest does for a real Plugin, then reads it back the
    way a Plugin does - proving the app can save and reload the list of devices to watch."""
    name = "Device list"
    what = "Saves which Sensors/Plugs to watch"
    path = REGISTRY_DIR / f"{TEST_PLUGIN}.json"
    try:
        _atomic_write_json(path, [{"external_id": TEST_DEVICE, "plugin_config": None,
                                    "auto_update_enabled": True}])
        entries = read_registry(TEST_PLUGIN)
        if entries and entries[0].get("external_id") == TEST_DEVICE:
            return CheckResult(name, what, True)
        return CheckResult(name, what, False, "wrote the file but couldn't read the same data back")
    except OSError as exc:
        return CheckResult(name, what, False, f"couldn't write the file ({exc})")
    finally:
        _cleanup(path)


def check_inbox(kind: str, name: str, what: str, sample_payload: dict) -> CheckResult:
    """Writes one sample report the way a Plugin would, then confirms it's a well-formed report
    the app can actually understand (validated against the same rules Ingest uses)."""
    validator = jsonschema.Draft202012Validator(
        json.loads(PLUGIN_EVENT_SCHEMA_PATH.read_text(encoding="utf-8"))
    )
    before = {p.name for p in (INBOX_DIR / kind).glob("*.json")} if (INBOX_DIR / kind).exists() else set()
    write_event(TEST_PLUGIN, TEST_DEVICE, kind, sample_payload)
    after = {p.name for p in (INBOX_DIR / kind).glob("*.json")} if (INBOX_DIR / kind).exists() else set()
    new_files = after - before
    if not new_files:
        return CheckResult(name, what, False, "the file didn't appear where it was expected")
    path = INBOX_DIR / kind / next(iter(new_files))

    # Give a live app a moment to notice and process it on its own, same as it would for a real
    # device - if it's gone, the running app already picked it up, which is itself a pass.
    deadline = time.monotonic() + INBOX_WAIT_SECONDS
    while path.exists() and time.monotonic() < deadline:
        time.sleep(0.2)

    if not path.exists():
        return CheckResult(name, what, True, "the running app picked it up immediately (good sign)")

    try:
        event = json.loads(path.read_text(encoding="utf-8"))
        validator.validate(event)
        return CheckResult(name, what, True)
    except (json.JSONDecodeError, jsonschema.ValidationError) as exc:
        return CheckResult(name, what, False, f"the saved file wasn't valid ({exc})")
    finally:
        _cleanup(path)


def check_outbox() -> CheckResult:
    """Tells a (fake) Smart Plug to turn on the way Admin does, then confirms the app can read
    that instruction back the way a Plugin would when it checks for pending commands."""
    name = "Plug commands"
    what = "Turns a Smart Plug on or off"
    try:
        write_command(TEST_PLUGIN, TEST_DEVICE, True, request_id=None)
    except OSError as exc:
        return CheckResult(name, what, False, f"couldn't write the command ({exc})")

    command = take_command(TEST_PLUGIN, TEST_DEVICE)  # also cleans up the file itself
    if command is not None and command.get("payload", {}).get("is_on") is True:
        return CheckResult(name, what, True)
    return CheckResult(name, what, False, "wrote the command but couldn't read the same data back")


def _print_report(results: list[CheckResult]) -> bool:
    print()
    print("=" * 60)
    print("  Husbandry Tracker App Connection Test")
    print("=" * 60)
    print()
    print("This checks whether the app can properly save and load the small")
    print("files it uses to talk to your Smart Sensors and Plugs. It only")
    print("writes temporary test data and cleans up after itself - none of")
    print("your real sensors, plugs, or history are touched.")
    print()

    name_width = max(len(r.name) for r in results)
    what_width = max(len(r.what_it_checks) for r in results)
    name_width = max(name_width, len("Check"))
    what_width = max(what_width, len("What it does"))

    header = f"{'Check':<{name_width}}  {'What it does':<{what_width}}  {'Result':<6}  Details"
    print(header)
    print("-" * len(header))
    for r in results:
        result_text = "PASS" if r.passed else "FAIL"
        result_field = f"{result_text:<6}" if r.details else result_text
        line = f"{r.name:<{name_width}}  {r.what_it_checks:<{what_width}}  {result_field}"
        if r.details:
            line += f"  {r.details}"
        print(line)

    print()
    failed = [r for r in results if not r.passed]
    if not failed:
        print(f"All {len(results)} checks passed. The app is correctly saving and loading its data.")
    else:
        print(f"{len(failed)} of {len(results)} check(s) failed:")
        for r in failed:
            print(f"  - {r.name}: {r.details}")
        print()
        print("See docs/DEBUGGING_JSON_PIPELINE.md for what to try next.")
    print()
    return not failed


def main() -> int:
    results = [
        check_registry(),
        check_inbox("plug_state", "Plug status",
                    "Reports when a Smart Plug turns on/off",
                    {"is_on": True}),
        check_inbox("sensor_reading", "Sensor readings",
                    "Reports a Sensor's temperature/humidity",
                    {"temperature_c": 24.5, "humidity_pct": 55.0}),
        check_inbox("plug_telemetry", "Plug power reports",
                    "Reports a Smart Plug's power usage",
                    {"watts": 12.3, "volts": None, "amps": None, "countdown_seconds": None}),
        check_outbox(),
    ]
    all_passed = _print_report(results)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
