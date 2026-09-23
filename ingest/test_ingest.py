"""Covers ingest/ingest.py's two JSON contract functions: exporting each Plugin's Registry from
the sensor/plug tables, and draining the Inbox into the database (including the schema-validation
quarantine path). See CONTEXT.md: Ingest, Registry, Inbox, Plugin Event; ADR 0013.

Run with: pytest ingest/test_ingest.py
"""
from __future__ import annotations

import json
import sqlite3

from ingest.ingest import _drain_inbox, _export_registry, _load_validator


def _make_room(conn: sqlite3.Connection, name: str = "Reptile Room") -> int:
    conn.execute("INSERT INTO room (name) VALUES (?)", (name,))
    conn.commit()
    return conn.execute("SELECT id FROM room WHERE name = ?", (name,)).fetchone()["id"]


def _make_smart_sensor(conn: sqlite3.Connection, room_id: int, plugin: str, external_id: str) -> int:
    conn.execute(
        "INSERT INTO sensor (room_id, label, tracking_mode, plugin, external_id, plugin_config, "
        "auto_update_enabled) VALUES (?, 'warm side', 'smart', ?, ?, ?, 1)",
        (room_id, plugin, external_id, json.dumps({"mac": external_id})),
    )
    conn.commit()
    return conn.execute("SELECT id FROM sensor WHERE plugin = ? AND external_id = ?",
                         (plugin, external_id)).fetchone()["id"]


def _make_smart_plug(conn: sqlite3.Connection, plugin: str, external_id: str) -> int:
    conn.execute(
        "INSERT INTO plug (label, purpose, tracking_mode, plugin, external_id, plugin_config, "
        "auto_update_enabled) VALUES ('basking bulb', 'heat', 'smart', ?, ?, ?, 1)",
        (plugin, external_id, json.dumps({"local_key": "k", "ip_address": "10.0.0.5"})),
    )
    conn.commit()
    return conn.execute("SELECT id FROM plug WHERE plugin = ? AND external_id = ?",
                         (plugin, external_id)).fetchone()["id"]


# --- _export_registry --------------------------------------------------------------------------

def test_export_registry_writes_one_file_per_plugin(json_dirs, temp_db) -> None:
    room_id = _make_room(temp_db)
    _make_smart_sensor(temp_db, room_id, "govee_ble", "AA:BB:CC:DD:EE:FF")
    _make_smart_plug(temp_db, "tuya_lan", "dev1:1")

    _export_registry()

    govee_entries = json.loads((json_dirs["registry"] / "govee_ble.json").read_text(encoding="utf-8"))
    assert govee_entries == [{
        "external_id": "AA:BB:CC:DD:EE:FF",
        "plugin_config": {"mac": "AA:BB:CC:DD:EE:FF"},
        "auto_update_enabled": True,
    }]

    tuya_entries = json.loads((json_dirs["registry"] / "tuya_lan.json").read_text(encoding="utf-8"))
    assert tuya_entries == [{
        "external_id": "dev1:1",
        "plugin_config": {"local_key": "k", "ip_address": "10.0.0.5"},
        "auto_update_enabled": True,
    }]


def test_export_registry_removes_stale_plugin_file(json_dirs, temp_db) -> None:
    json_dirs["registry"].mkdir(parents=True, exist_ok=True)
    (json_dirs["registry"] / "some_removed_plugin.json").write_text("[]", encoding="utf-8")

    _export_registry()  # no devices registered at all

    assert not (json_dirs["registry"] / "some_removed_plugin.json").exists()


def test_export_registry_excludes_manual_devices(json_dirs, temp_db) -> None:
    room_id = _make_room(temp_db)
    temp_db.execute(
        "INSERT INTO sensor (room_id, label, tracking_mode) VALUES (?, 'ambient', 'manual')",
        (room_id,),
    )
    temp_db.commit()

    _export_registry()

    assert list(json_dirs["registry"].glob("*.json")) == []


# --- _drain_inbox --------------------------------------------------------------------------------

def _drop_inbox_file(json_dirs, kind: str, name: str, raw: str) -> None:
    kind_dir = json_dirs["inbox"] / kind
    kind_dir.mkdir(parents=True, exist_ok=True)
    (kind_dir / name).write_text(raw, encoding="utf-8")


def test_drain_inbox_applies_valid_plug_state_event(json_dirs, temp_db) -> None:
    plug_id = _make_smart_plug(temp_db, "tuya_lan", "dev1:1")
    event = {
        "schema_version": 1, "plugin": "tuya_lan", "kind": "plug_state", "external_id": "dev1:1",
        "observed_at": "2026-01-01 00:00:00", "payload": {"is_on": True},
    }
    _drop_inbox_file(json_dirs, "plug_state", "event1.json", json.dumps(event))

    _drain_inbox(_load_validator())

    row = temp_db.execute(
        "SELECT is_on FROM plug_state_transition WHERE plug_id = ?", (plug_id,)
    ).fetchone()
    assert row is not None and row["is_on"] == 1
    assert not (json_dirs["inbox"] / "plug_state" / "event1.json").exists()


def test_drain_inbox_quarantines_invalid_json(json_dirs, temp_db) -> None:
    _drop_inbox_file(json_dirs, "plug_state", "bad.json", "{not valid json")

    _drain_inbox(_load_validator())

    assert not (json_dirs["inbox"] / "plug_state" / "bad.json").exists()
    assert (json_dirs["rejected"] / "plug_state" / "bad.json").exists()


def test_drain_inbox_quarantines_schema_violation(json_dirs, temp_db) -> None:
    # plug_state payload requires "is_on" — omitted here.
    bad_event = {
        "schema_version": 1, "plugin": "tuya_lan", "kind": "plug_state", "external_id": "dev1:1",
        "observed_at": "2026-01-01 00:00:00", "payload": {},
    }
    _drop_inbox_file(json_dirs, "plug_state", "bad.json", json.dumps(bad_event))

    _drain_inbox(_load_validator())

    assert not (json_dirs["inbox"] / "plug_state" / "bad.json").exists()
    assert (json_dirs["rejected"] / "plug_state" / "bad.json").exists()


def test_drain_inbox_ignores_event_for_deregistered_device(json_dirs, temp_db) -> None:
    # No plug row registered for "dev1:1" at all.
    event = {
        "schema_version": 1, "plugin": "tuya_lan", "kind": "plug_state", "external_id": "dev1:1",
        "observed_at": "2026-01-01 00:00:00", "payload": {"is_on": True},
    }
    _drop_inbox_file(json_dirs, "plug_state", "event1.json", json.dumps(event))

    _drain_inbox(_load_validator())  # must not raise

    # Silently consumed, same as Ingest treats a deregistered device — see _apply_event.
    assert not (json_dirs["inbox"] / "plug_state" / "event1.json").exists()
    assert not (json_dirs["rejected"] / "plug_state" / "event1.json").exists()
