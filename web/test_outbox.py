"""Covers web/outbox.py's write_command — Core's write side of the Outbox. See CONTEXT.md:
Outbox, Command; ADR 0014.

Run with: pytest web/test_outbox.py
"""
from __future__ import annotations

import json

from web.outbox import write_command


def test_write_command_happy_path(json_dirs) -> None:
    write_command("tuya_lan", "dev1:1", True, request_id=7)

    # write_command sanitizes ":" out of the filename (not filename-safe on Windows) — see
    # web/outbox.py's _UNSAFE_FILENAME_CHARS.
    path = json_dirs["outbox"] / "tuya_lan" / "dev1_1.json"
    command = json.loads(path.read_text(encoding="utf-8"))
    assert command == {
        "schema_version": 1,
        "plugin": "tuya_lan",
        "external_id": "dev1:1",
        "command": "set_power",
        "requested_at": command["requested_at"],  # asserted shape below
        "request_id": 7,
        "payload": {"is_on": True},
    }
    assert len(command["requested_at"]) == 19  # "YYYY-MM-DD HH:MM:SS"


def test_write_command_overwrites_not_queues(json_dirs) -> None:
    write_command("tuya_lan", "dev1:1", True, request_id=1)
    write_command("tuya_lan", "dev1:1", False, request_id=2)

    plugin_dir = json_dirs["outbox"] / "tuya_lan"
    files = list(plugin_dir.glob("*.json"))
    assert len(files) == 1  # second call overwrote the first, never queued alongside it

    command = json.loads(files[0].read_text(encoding="utf-8"))
    assert command["payload"] == {"is_on": False}
    assert command["request_id"] == 2
