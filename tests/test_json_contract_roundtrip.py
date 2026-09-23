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

Run with: pytest tests/test_json_contract_roundtrip.py
"""
from __future__ import annotations

from ingest.ingest import _drain_inbox, _export_registry, _load_validator
from plugins.common import read_registry, take_command, write_event
from web.outbox import write_command


def test_registry_to_inbox_roundtrip(json_dirs, temp_db) -> None:
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
