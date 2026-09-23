"""Covers plugins/common.py's three JSON contract functions from the Plugin side: writing a
Plugin Event to the Inbox, reading a Plugin's Registry export, and taking a pending Outbox
Command. See CONTEXT.md: Plugin, Plugin Event, Inbox, Registry, Outbox, Command; ADR 0013/0014.

Run with: pytest plugins/test_common.py
"""
from __future__ import annotations

import json

from plugins.common import _UNSAFE_FILENAME_CHARS, read_registry, take_command, write_event


# --- write_event -----------------------------------------------------------------------------

def test_write_event_lands_in_inbox_kind_dir(json_dirs) -> None:
    write_event("tuya_lan", "abc123:1", "plug_state", {"is_on": True})

    files = list((json_dirs["inbox"] / "plug_state").glob("*.json"))
    assert len(files) == 1
    event = json.loads(files[0].read_text(encoding="utf-8"))
    assert event == {
        "schema_version": 1,
        "plugin": "tuya_lan",
        "kind": "plug_state",
        "external_id": "abc123:1",
        "observed_at": event["observed_at"],  # asserted shape below, not a fixed value
        "payload": {"is_on": True},
    }
    assert len(event["observed_at"]) == 19  # "YYYY-MM-DD HH:MM:SS"


def test_write_event_uses_explicit_observed_at(json_dirs) -> None:
    write_event("govee_ble", "AA:BB:CC:DD:EE:FF", "sensor_reading",
                {"temperature_c": 24.5}, observed_at="2026-01-01 00:00:00")

    files = list((json_dirs["inbox"] / "sensor_reading").glob("*.json"))
    event = json.loads(files[0].read_text(encoding="utf-8"))
    assert event["observed_at"] == "2026-01-01 00:00:00"


# --- read_registry -----------------------------------------------------------------------------

def test_read_registry_happy_path(json_dirs) -> None:
    entries = [{"external_id": "abc123:1", "plugin_config": {"local_key": "k", "ip_address": "10.0.0.5"},
                "auto_update_enabled": True}]
    json_dirs["registry"].mkdir(parents=True, exist_ok=True)
    (json_dirs["registry"] / "tuya_lan.json").write_text(json.dumps(entries), encoding="utf-8")

    assert read_registry("tuya_lan") == entries


def test_read_registry_missing_file_returns_empty_list(json_dirs) -> None:
    assert read_registry("tuya_lan") == []


def test_read_registry_corrupt_json_returns_empty_list(json_dirs) -> None:
    json_dirs["registry"].mkdir(parents=True, exist_ok=True)
    (json_dirs["registry"] / "tuya_lan.json").write_text("{not valid json", encoding="utf-8")

    assert read_registry("tuya_lan") == []


# --- take_command -----------------------------------------------------------------------------

def _write_outbox_file(json_dirs, plugin: str, external_id: str, raw: str) -> None:
    # take_command looks up the same sanitized filename write_command produces — see
    # plugins/common.py's _UNSAFE_FILENAME_CHARS (a Tuya external_id contains ":", which isn't
    # filename-safe on Windows).
    safe_id = _UNSAFE_FILENAME_CHARS.sub("_", external_id)
    plugin_dir = json_dirs["outbox"] / plugin
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / f"{safe_id}.json").write_text(raw, encoding="utf-8")


def test_take_command_happy_path_removes_file(json_dirs) -> None:
    command = {
        "schema_version": 1, "plugin": "tuya_lan", "external_id": "abc123:1",
        "command": "set_power", "requested_at": "2026-01-01 00:00:00",
        "request_id": 42, "payload": {"is_on": True},
    }
    _write_outbox_file(json_dirs, "tuya_lan", "abc123:1", json.dumps(command))

    result = take_command("tuya_lan", "abc123:1")

    assert result == command
    assert not (json_dirs["outbox"] / "tuya_lan" / "abc123_1.json").exists()


def test_take_command_missing_file_returns_none(json_dirs) -> None:
    assert take_command("tuya_lan", "abc123:1") is None


def test_take_command_corrupt_json_drops_file_and_returns_none(json_dirs) -> None:
    _write_outbox_file(json_dirs, "tuya_lan", "abc123:1", "{not valid json")

    assert take_command("tuya_lan", "abc123:1") is None
    assert not (json_dirs["outbox"] / "tuya_lan" / "abc123_1.json").exists()


def test_take_command_schema_invalid_drops_file_and_returns_none(json_dirs) -> None:
    # Missing the required "payload" key entirely.
    bad_command = {
        "schema_version": 1, "plugin": "tuya_lan", "external_id": "abc123:1",
        "command": "set_power", "requested_at": "2026-01-01 00:00:00", "request_id": None,
    }
    _write_outbox_file(json_dirs, "tuya_lan", "abc123:1", json.dumps(bad_command))

    assert take_command("tuya_lan", "abc123:1") is None
    assert not (json_dirs["outbox"] / "tuya_lan" / "abc123_1.json").exists()
