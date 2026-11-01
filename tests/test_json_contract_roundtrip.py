"""End-to-end sanity check for the full filesystem contract described in CONTEXT.md (Plugin,
Registry, Inbox, Outbox; ADR 0013/0014). The per-module test files
(plugins/test_common.py, ingest/test_ingest.py, web/test_outbox.py) cover each function in
isolation; this file wires the two directions together the way a real deployment actually uses
them, so a change that breaks the *interface* between two modules (not just one module's own
logic) still gets caught even if each module's own unit tests still pass.

Direction 1 (Core -> Plugin -> Ingest): a device registered in the database is exported to its
Plugin's Registry file, the Plugin (simulated here, since no real Tuya/BLE hardware is available
in a test run) reads that Registry and reports an observation via write_event, and Ingest drains
that observation back into the database.

Direction 2 (Core -> Plugin): Core issues a Command via write_command, and the Plugin
(simulated) takes it via take_command.

Direction 3 (AI skill -> Ingest, no Registry involved at all): an AI skill — not a device
Plugin, just anything that speaks the same JSON contract — reports a Log Event (see
CONTEXT.md: Log Event; ADR 0044) via the same write_event Plugins already use, and Ingest
drains it straight into event_log with no Sensor/Plug to resolve against.

Direction 4 (Skill -> Ingest, resolved ids instead of a device Registry): log_husbandry writes a
Care Event Plugin Event (see CONTEXT.md: Care Event Plugin Event; ADR 0046) the same way via
write_event, and Ingest resolves/applies it into a real care_event row.

Run with: pytest tests/test_json_contract_roundtrip.py
"""
from __future__ import annotations

from active_plugins import write_active_plugins
from ingest.ingest import _drain_inbox, _export_registry, _load_validator
from plugins.common import read_registry, take_command, write_event
from web.outbox import write_command


def test_registry_to_inbox_roundtrip(json_dirs, temp_db, active_plugins_path) -> None:
    # See CONTEXT.md: Active Plugin; ADR 0047 — govee_ble must be an Active Plugin before Ingest
    # exports its Registry or accepts its Inbox events at all.
    write_active_plugins(["govee_ble"])
    temp_db.execute("INSERT INTO room (name) VALUES ('Reptile Room')")
    temp_db.commit()
    room_id = temp_db.execute("SELECT id FROM room WHERE name = 'Reptile Room'").fetchone()["id"]
    temp_db.execute(
        "INSERT INTO sensor (room_id, label, tracking_mode, plugin, external_id, plugin_config, "
        "auto_update_enabled) VALUES (?, 'warm side', 'smart', 'govee_ble', 'AA:BB:CC:DD:EE:FF', NULL, 1)",
        (room_id,),
    )
    temp_db.commit()
    sensor_id = temp_db.execute(
        "SELECT id FROM sensor WHERE external_id = 'AA:BB:CC:DD:EE:FF'"
    ).fetchone()["id"]

    # 1. Core/Ingest exports the Registry from the database.
    _export_registry()

    # 2. The Plugin reads its Registry the same way plugins/govee_ble/plugin.py would.
    registry_entries = read_registry("govee_ble")
    assert len(registry_entries) == 1
    assert registry_entries[0]["external_id"] == "AA:BB:CC:DD:EE:FF"

    # 3. The Plugin reports an observation for exactly the device the Registry told it to watch.
    write_event("govee_ble", registry_entries[0]["external_id"], "sensor_reading",
                {"temperature_c": 26.5, "humidity_pct": 55.0, "battery_pct": 90})

    # 4. Ingest drains the Inbox, and the reading lands against the right sensor row.
    _drain_inbox(_load_validator())

    reading = temp_db.execute(
        "SELECT temperature_c, humidity_pct, battery_pct FROM sensor_reading WHERE sensor_id = ?",
        (sensor_id,),
    ).fetchone()
    assert reading is not None
    assert reading["temperature_c"] == 26.5
    assert reading["humidity_pct"] == 55.0
    assert reading["battery_pct"] == 90


def test_outbox_command_roundtrip(json_dirs) -> None:
    # 1. Core issues a Command.
    write_command("tuya_lan", "dev1:1", True, request_id=99)

    # 2. The Plugin takes it on its next poll, the same way plugins/tuya_lan/plugin.py would.
    command = take_command("tuya_lan", "dev1:1")

    assert command is not None
    assert command["payload"] == {"is_on": True}
    assert command["request_id"] == 99
    # Taken exactly once — a second poll before Core issues a new one sees nothing pending.
    assert take_command("tuya_lan", "dev1:1") is None


def test_skill_log_event_roundtrip(json_dirs, temp_db) -> None:
    # 1. An AI skill reports a Log Event the same way a Plugin reports any other kind — no
    #    Sensor/Plug registration, no Registry export, needed first.
    write_event("feeding_skill", "enclosure:3", "log",
                {"level": "info", "message": "Logged feeding via voice command"})

    # 2. Ingest drains the Inbox and writes it straight into event_log.
    _drain_inbox(_load_validator())

    row = temp_db.execute(
        "SELECT source, scope, level, message FROM event_log WHERE source = 'feeding_skill'"
    ).fetchone()
    assert row is not None
    assert row["scope"] == "enclosure:3"
    assert row["level"] == "info"
    assert row["message"] == "Logged feeding via voice command"


def test_skill_care_event_roundtrip(json_dirs, temp_db, active_plugins_path) -> None:
    write_active_plugins(["log_husbandry"])
    temp_db.execute("INSERT INTO enclosure (name) VALUES ('Snake Rack 3')")
    temp_db.commit()
    enclosure_id = temp_db.execute("SELECT id FROM enclosure WHERE name = 'Snake Rack 3'").fetchone()["id"]

    # 1. log_husbandry reports a Care Event Plugin Event the same way a Plugin reports any other
    #    kind — enclosure_id already resolved from its own Registry export, not a raw name.
    write_event("log_husbandry", f"enclosure:{enclosure_id}", "care_event",
                {"enclosure_id": enclosure_id, "care_kind": "watering"})

    # 2. Ingest drains the Inbox and writes a real care_event row.
    _drain_inbox(_load_validator())

    row = temp_db.execute(
        "SELECT kind, animal_id FROM care_event WHERE enclosure_id = ?", (enclosure_id,)
    ).fetchone()
    assert row is not None
    assert row["kind"] == "watering"
    assert row["animal_id"] is None
