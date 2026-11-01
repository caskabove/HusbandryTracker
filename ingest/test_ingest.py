"""Covers ingest/ingest.py's two JSON contract functions: exporting each Plugin's Registry from
the sensor/plug tables, and draining the Inbox into the database (including the schema-validation
quarantine path). See CONTEXT.md: Ingest, Registry, Inbox, Plugin Event; ADR 0013.

Run with: pytest ingest/test_ingest.py
"""
from __future__ import annotations

import json
import sqlite3

from ingest.ingest import _drain_inbox, _export_log_husbandry_registry, _export_registry, _load_validator


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


def _make_enclosure(conn: sqlite3.Connection, name: str = "Snake Rack 3") -> int:
    conn.execute("INSERT INTO enclosure (name) VALUES (?)", (name,))
    conn.commit()
    return conn.execute("SELECT id FROM enclosure WHERE name = ?", (name,)).fetchone()["id"]


def _make_animal(conn: sqlite3.Connection, enclosure_id: int, name: str = "Bob") -> int:
    conn.execute("INSERT INTO animal (enclosure_id, name) VALUES (?, ?)", (enclosure_id, name))
    conn.commit()
    return conn.execute("SELECT id FROM animal WHERE enclosure_id = ? AND name = ?",
                         (enclosure_id, name)).fetchone()["id"]


def _care_event(enclosure_id: int, care_kind: str, **payload_extra) -> dict:
    return {
        "schema_version": 1, "plugin": "log_husbandry", "kind": "care_event",
        "external_id": "enclosure:" + str(enclosure_id), "observed_at": "2026-01-01 00:00:00",
        "payload": {"enclosure_id": enclosure_id, "care_kind": care_kind, **payload_extra},
    }


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


def test_drain_inbox_applies_log_event_with_no_registered_device(json_dirs, temp_db) -> None:
    # No sensor/plug/anything registered for "enclosure:3" — a log event needs no Registry match.
    event = {
        "schema_version": 1, "plugin": "feeding_skill", "kind": "log", "external_id": "enclosure:3",
        "observed_at": "2026-01-01 00:00:00",
        "payload": {"level": "info", "message": "Logged feeding via voice command", "data": {"animal_id": 7}},
    }
    _drop_inbox_file(json_dirs, "log", "event1.json", json.dumps(event))

    _drain_inbox(_load_validator())

    row = temp_db.execute(
        "SELECT source, scope, level, message, data FROM event_log WHERE source = 'feeding_skill'"
    ).fetchone()
    assert row is not None
    assert row["scope"] == "enclosure:3"
    assert row["level"] == "info"
    assert row["message"] == "Logged feeding via voice command"
    assert json.loads(row["data"]) == {"animal_id": 7}
    assert not (json_dirs["inbox"] / "log" / "event1.json").exists()


def test_drain_inbox_log_event_defaults_level_and_data(json_dirs, temp_db) -> None:
    event = {
        "schema_version": 1, "plugin": "feeding_skill", "kind": "log", "external_id": "app",
        "observed_at": "2026-01-01 00:00:00", "payload": {"message": "started up"},
    }
    _drop_inbox_file(json_dirs, "log", "event1.json", json.dumps(event))

    _drain_inbox(_load_validator())

    row = temp_db.execute(
        "SELECT level, data FROM event_log WHERE scope = 'app'"
    ).fetchone()
    assert row["level"] == "info"
    assert row["data"] is None


def test_care_event_feeding_with_explicit_fields(json_dirs, temp_db) -> None:
    enclosure_id = _make_enclosure(temp_db)
    animal_id = _make_animal(temp_db, enclosure_id)
    event = _care_event(enclosure_id, "feeding", animal_id=animal_id, food="large mouse",
                         count=1, prey_state="frozen_thawed", result="accepted")
    _drop_inbox_file(json_dirs, "care_event", "event1.json", json.dumps(event))

    _drain_inbox(_load_validator())

    row = temp_db.execute(
        "SELECT ce.animal_id, fd.food, fd.count, fd.prey_state, fd.result FROM care_event ce "
        "JOIN feeding_detail fd ON fd.care_event_id = ce.id WHERE ce.enclosure_id = ?",
        (enclosure_id,),
    ).fetchone()
    assert row is not None
    assert row["animal_id"] == animal_id
    assert row["food"] == "large mouse"
    assert row["count"] == 1
    assert row["prey_state"] == "frozen_thawed"
    assert row["result"] == "accepted"
    assert not (json_dirs["inbox"] / "care_event" / "event1.json").exists()


def test_care_event_feeding_falls_back_to_last_feeding_detail(json_dirs, temp_db) -> None:
    enclosure_id = _make_enclosure(temp_db)
    animal_id = _make_animal(temp_db, enclosure_id)
    # A prior Feeding with a real prey_state/result to repeat.
    temp_db.execute(
        "INSERT INTO care_event (enclosure_id, animal_id, kind, occurred_at) VALUES (?, ?, 'feeding', '2026-01-01 00:00:00')",
        (enclosure_id, animal_id),
    )
    care_event_id = temp_db.execute("SELECT last_insert_rowid()").fetchone()[0]
    temp_db.execute(
        "INSERT INTO feeding_detail (care_event_id, food, count, prey_state, result) VALUES (?, 'small rat', 2, 'live', 'refused')",
        (care_event_id,),
    )
    temp_db.commit()

    # This event only states food — count/prey_state/result are left for Ingest to fill in.
    event = _care_event(enclosure_id, "feeding", animal_id=animal_id, food="large mouse")
    _drop_inbox_file(json_dirs, "care_event", "event1.json", json.dumps(event))

    _drain_inbox(_load_validator())

    row = temp_db.execute(
        "SELECT fd.food, fd.count, fd.prey_state, fd.result FROM care_event ce "
        "JOIN feeding_detail fd ON fd.care_event_id = ce.id WHERE ce.id != ? ORDER BY ce.id DESC LIMIT 1",
        (care_event_id,),
    ).fetchone()
    assert row["food"] == "large mouse"  # explicitly stated — not overwritten by the fallback
    assert row["count"] == 2  # repeated from the last Feeding
    assert row["prey_state"] == "live"  # repeated from the last Feeding
    assert row["result"] == "refused"  # repeated from the last Feeding


def test_care_event_feeding_falls_back_to_frozen_thawed_with_no_prior_feeding(json_dirs, temp_db) -> None:
    enclosure_id = _make_enclosure(temp_db)
    animal_id = _make_animal(temp_db, enclosure_id)
    event = _care_event(enclosure_id, "feeding", animal_id=animal_id, food="large mouse")
    _drop_inbox_file(json_dirs, "care_event", "event1.json", json.dumps(event))

    _drain_inbox(_load_validator())

    row = temp_db.execute(
        "SELECT fd.prey_state, fd.result FROM care_event ce "
        "JOIN feeding_detail fd ON fd.care_event_id = ce.id WHERE ce.enclosure_id = ?",
        (enclosure_id,),
    ).fetchone()
    assert row["prey_state"] == "frozen_thawed"  # the documented "or Frozen" fallback
    assert row["result"] == "accepted"


def test_care_event_watering_is_enclosure_scoped(json_dirs, temp_db) -> None:
    enclosure_id = _make_enclosure(temp_db)
    event = _care_event(enclosure_id, "watering")
    _drop_inbox_file(json_dirs, "care_event", "event1.json", json.dumps(event))

    _drain_inbox(_load_validator())

    row = temp_db.execute(
        "SELECT kind, animal_id FROM care_event WHERE enclosure_id = ?", (enclosure_id,)
    ).fetchone()
    assert row["kind"] == "watering"
    assert row["animal_id"] is None


def test_care_event_quarantines_on_nonexistent_enclosure(json_dirs, temp_db) -> None:
    event = _care_event(999, "watering")
    _drop_inbox_file(json_dirs, "care_event", "event1.json", json.dumps(event))

    _drain_inbox(_load_validator())  # must not raise

    assert not (json_dirs["inbox"] / "care_event" / "event1.json").exists()
    assert (json_dirs["rejected"] / "care_event" / "event1.json").exists()


def test_care_event_quarantines_when_animal_belongs_to_different_enclosure(json_dirs, temp_db) -> None:
    # The Skill's own Registry snapshot was stale — the Animal moved Enclosures in the meantime.
    real_enclosure_id = _make_enclosure(temp_db, "Reef Tank")
    other_enclosure_id = _make_enclosure(temp_db, "Snake Rack 3")
    animal_id = _make_animal(temp_db, real_enclosure_id)
    event = _care_event(other_enclosure_id, "feeding", animal_id=animal_id)
    _drop_inbox_file(json_dirs, "care_event", "event1.json", json.dumps(event))

    _drain_inbox(_load_validator())

    assert not (json_dirs["inbox"] / "care_event" / "event1.json").exists()
    assert (json_dirs["rejected"] / "care_event" / "event1.json").exists()


# --- _export_log_husbandry_registry --------------------------------------------------------------

def test_export_log_husbandry_registry_writes_rooms_enclosures_animals(
    json_dirs, temp_db, active_plugins_path
) -> None:
    from active_plugins import write_active_plugins
    write_active_plugins(["log_husbandry"])
    room_id = _make_room(temp_db)
    enclosure_id = _make_enclosure(temp_db)
    temp_db.execute("UPDATE enclosure SET room_id = ? WHERE id = ?", (room_id, enclosure_id))
    temp_db.commit()
    animal_id = _make_animal(temp_db, enclosure_id)

    _export_log_husbandry_registry()

    data = json.loads((json_dirs["registry"] / "log_husbandry.json").read_text(encoding="utf-8"))
    assert data["rooms"] == [{"id": room_id, "name": "Reptile Room"}]
    assert data["enclosures"] == [{"id": enclosure_id, "name": "Snake Rack 3", "room_id": room_id}]
    assert data["animals"] == [{"id": animal_id, "name": "Bob", "enclosure_id": enclosure_id}]


def test_export_log_husbandry_registry_removes_file_when_not_active(
    json_dirs, temp_db, active_plugins_path
) -> None:
    json_dirs["registry"].mkdir(parents=True, exist_ok=True)
    (json_dirs["registry"] / "log_husbandry.json").write_text("{}", encoding="utf-8")

    _export_log_husbandry_registry()  # log_husbandry is not in the (empty) Active Plugin list

    assert not (json_dirs["registry"] / "log_husbandry.json").exists()


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
