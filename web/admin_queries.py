"""Write/CRUD access backing the admin UI — the browser-based counterpart to tools/register_device.py.
Both talk to the same tables; nothing here changes the schema or the CLI tool, which stays useful
for scripting/bulk setup.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.db import get_connection
from web.queries import CARE_EVENT_KINDS, days_since


def list_enclosures() -> list[dict]:
    with get_connection() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM enclosure ORDER BY name")]


def get_enclosure(enclosure_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM enclosure WHERE id = ?", (enclosure_id,)).fetchone()
        if row is None:
            return None
        enclosure = dict(row)
        enclosure["animals"] = [dict(r) for r in conn.execute("SELECT * FROM animal WHERE enclosure_id = ? ORDER BY name", (enclosure_id,))]
        enclosure["sensors"] = [dict(r) for r in conn.execute("SELECT * FROM sensor WHERE enclosure_id = ? ORDER BY label", (enclosure_id,))]
        enclosure["plugs"] = [dict(r) for r in conn.execute("SELECT * FROM plug WHERE enclosure_id = ? ORDER BY label", (enclosure_id,))]
        for plug in enclosure["plugs"]:
            # Schedule inference isn't built yet — see docs/PHASE1.md "What's NOT built yet". A Manual
            # Plug shows its Declared Schedule instead (declared_on_time/declared_off_time columns).
            plug["inferred_schedule"] = None

        enclosure["care"] = {}
        for kind in CARE_EVENT_KINDS:
            latest = conn.execute(
                """SELECT occurred_at FROM care_event
                   WHERE enclosure_id = ? AND kind = ? ORDER BY occurred_at DESC LIMIT 1""",
                (enclosure_id, kind),
            ).fetchone()
            occurred_at = latest["occurred_at"] if latest else None
            enclosure["care"][kind] = {"occurred_at": occurred_at, "days_since": days_since(occurred_at)}

        return enclosure


def create_enclosure(name: str, bioactive: bool, feeding: int, watering: int, spot: int, deep: int) -> int:
    # Room assignment happens as a follow-up edit (see update_enclosure), not at creation — keeps
    # this quick-create form minimal, matching how Sensor/Plug reassignment already works.
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO enclosure (name, bioactive, feeding_interval_days, watering_interval_days,
                                       spot_clean_interval_days, deep_clean_interval_days)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, int(bioactive), feeding, watering, spot, deep),
        )
        return cur.lastrowid


def update_enclosure(enclosure_id: int, name: str, bioactive: bool, feeding: int, watering: int, spot: int, deep: int,
                      room_id: int | None, fallback_sensor_id: int | None) -> None:
    """room_id and fallback_sensor_id see CONTEXT.md: Room, Fallback Sensor. The Admin UI only ever
    offers a Fallback Sensor dropdown scoped to the chosen Room's own Sensors and only when this
    Enclosure has none of its own, so no extra cross-check is done here — display logic (see
    web/queries.py) also always prefers an Enclosure's own Sensors over its Fallback Sensor
    regardless, so a stale fallback_sensor_id left over after adding a real Sensor is harmless."""
    with get_connection() as conn:
        conn.execute(
            """UPDATE enclosure SET name = ?, bioactive = ?, feeding_interval_days = ?, watering_interval_days = ?,
                                     spot_clean_interval_days = ?, deep_clean_interval_days = ?, room_id = ?,
                                     fallback_sensor_id = ? WHERE id = ?""",
            (name, int(bioactive), feeding, watering, spot, deep, room_id, fallback_sensor_id, enclosure_id),
        )


def delete_enclosure(enclosure_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM enclosure WHERE id = ?", (enclosure_id,))  # cascades via FK


def create_animal(enclosure_id: int, name: str, common: str | None, scientific: str | None, dob: str | None) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO animal (enclosure_id, name, species_common, species_scientific, dob) VALUES (?, ?, ?, ?, ?)",
            (enclosure_id, name, common or None, scientific or None, dob or None),
        )


def delete_animal(animal_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM animal WHERE id = ?", (animal_id,))


def get_animal(animal_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM animal WHERE id = ?", (animal_id,)).fetchone()
        return dict(row) if row else None


def update_animal(animal_id: int, enclosure_id: int, name: str, common: str | None,
                   scientific: str | None, dob: str | None) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE animal SET enclosure_id = ?, name = ?, species_common = ?, species_scientific = ?, dob = ? WHERE id = ?",
            (enclosure_id, name, common or None, scientific or None, dob or None, animal_id),
        )


def _validate_sensor(tracking_mode: str, mac_address: str | None, temp_min: float | None, temp_max: float | None,
                      humidity_min: float | None, humidity_max: float | None) -> None:
    """See CONTEXT.md: Tracking Mode, Target Range. Raised as ValueError so the Admin route can show
    a friendly message instead of a raw SQLite CHECK failure."""
    if tracking_mode not in ("smart", "manual"):
        raise ValueError(f"Unknown Tracking Mode: {tracking_mode!r}")
    if tracking_mode == "smart":
        if not mac_address:
            raise ValueError("A Smart Sensor needs a MAC address.")
    else:
        if mac_address:
            raise ValueError("A Manual Sensor has no physical device — leave the MAC address blank.")
        temp_ranged = temp_min is not None and temp_max is not None
        humidity_ranged = humidity_min is not None and humidity_max is not None
        if not (temp_ranged or humidity_ranged):
            raise ValueError(
                "A Manual Sensor needs a complete Target Range (both min and max) on temperature or "
                "humidity before it can be saved — there's nothing to judge a hand-logged Reading against otherwise."
            )


def create_sensor(enclosure_id: int, label: str, tracking_mode: str, mac_address: str | None, temp_min: float | None,
                   temp_max: float | None, humidity_min: float | None, humidity_max: float | None) -> None:
    _validate_sensor(tracking_mode, mac_address, temp_min, temp_max, humidity_min, humidity_max)
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO sensor (enclosure_id, label, tracking_mode, mac_address, target_temp_min_c,
                                    target_temp_max_c, target_humidity_min, target_humidity_max)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (enclosure_id, label, tracking_mode, mac_address.upper() if mac_address else None,
             temp_min, temp_max, humidity_min, humidity_max),
        )


def delete_sensor(sensor_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM sensor WHERE id = ?", (sensor_id,))


def get_sensor(sensor_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM sensor WHERE id = ?", (sensor_id,)).fetchone()
        return dict(row) if row else None


def update_sensor(sensor_id: int, enclosure_id: int, label: str, tracking_mode: str, mac_address: str | None,
                   temp_min: float | None, temp_max: float | None, humidity_min: float | None,
                   humidity_max: float | None) -> None:
    _validate_sensor(tracking_mode, mac_address, temp_min, temp_max, humidity_min, humidity_max)
    with get_connection() as conn:
        conn.execute(
            """UPDATE sensor SET enclosure_id = ?, label = ?, tracking_mode = ?, mac_address = ?,
                                  target_temp_min_c = ?, target_temp_max_c = ?, target_humidity_min = ?,
                                  target_humidity_max = ? WHERE id = ?""",
            (enclosure_id, label, tracking_mode, mac_address.upper() if mac_address else None,
             temp_min, temp_max, humidity_min, humidity_max, sensor_id),
        )


def create_room_sensor(room_id: int, label: str, tracking_mode: str, mac_address: str | None, temp_min: float | None,
                        temp_max: float | None, humidity_min: float | None, humidity_max: float | None) -> None:
    """A Room's ambient Sensor — same Sensor concept, Room instead of Enclosure as parent. See
    CONTEXT.md: Room, Sensor."""
    _validate_sensor(tracking_mode, mac_address, temp_min, temp_max, humidity_min, humidity_max)
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO sensor (room_id, label, tracking_mode, mac_address, target_temp_min_c,
                                    target_temp_max_c, target_humidity_min, target_humidity_max)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (room_id, label, tracking_mode, mac_address.upper() if mac_address else None,
             temp_min, temp_max, humidity_min, humidity_max),
        )


def update_room_sensor(sensor_id: int, room_id: int, label: str, tracking_mode: str, mac_address: str | None,
                        temp_min: float | None, temp_max: float | None, humidity_min: float | None,
                        humidity_max: float | None) -> None:
    _validate_sensor(tracking_mode, mac_address, temp_min, temp_max, humidity_min, humidity_max)
    with get_connection() as conn:
        conn.execute(
            """UPDATE sensor SET room_id = ?, label = ?, tracking_mode = ?, mac_address = ?,
                                  target_temp_min_c = ?, target_temp_max_c = ?, target_humidity_min = ?,
                                  target_humidity_max = ? WHERE id = ?""",
            (room_id, label, tracking_mode, mac_address.upper() if mac_address else None,
             temp_min, temp_max, humidity_min, humidity_max, sensor_id),
        )


def _validate_plug(tracking_mode: str, tuya_device_id: str | None, tuya_local_key: str | None,
                    declared_on_time: str | None, declared_off_time: str | None) -> None:
    """See CONTEXT.md: Tracking Mode, Schedule (Declared). Raised as ValueError so the Admin route can
    show a friendly message instead of a raw SQLite CHECK failure."""
    if tracking_mode not in ("smart", "manual"):
        raise ValueError(f"Unknown Tracking Mode: {tracking_mode!r}")
    if tracking_mode == "smart":
        if not tuya_device_id or not tuya_local_key:
            raise ValueError("A Smart Plug needs both a Tuya device_id and local_key.")
    else:
        if tuya_device_id or tuya_local_key:
            raise ValueError("A Manual Plug has no device credentials — leave the Tuya fields blank.")
        if bool(declared_on_time) != bool(declared_off_time):
            raise ValueError("Enter both a declared on-time and off-time, or leave both blank.")


def create_plug(enclosure_id: int, label: str, purpose: str, tracking_mode: str, tuya_device_id: str | None,
                 tuya_local_key: str | None, tuya_ip_address: str | None, switch_dps_key: str = "1",
                 declared_on_time: str | None = None, declared_off_time: str | None = None) -> None:
    _validate_plug(tracking_mode, tuya_device_id, tuya_local_key, declared_on_time, declared_off_time)
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO plug (enclosure_id, label, purpose, tracking_mode, tuya_device_id, tuya_local_key,
                                  tuya_ip_address, switch_dps_key, declared_on_time, declared_off_time)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (enclosure_id, label, purpose, tracking_mode, tuya_device_id or None, tuya_local_key or None,
             tuya_ip_address or None, switch_dps_key or "1", declared_on_time or None, declared_off_time or None),
        )


def delete_plug(plug_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM plug WHERE id = ?", (plug_id,))


def get_plug(plug_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM plug WHERE id = ?", (plug_id,)).fetchone()
        return dict(row) if row else None


def update_plug(plug_id: int, enclosure_id: int, label: str, purpose: str, tracking_mode: str, switch_dps_key: str,
                 tuya_device_id: str | None, tuya_local_key: str | None, tuya_ip_address: str | None,
                 declared_on_time: str | None = None, declared_off_time: str | None = None) -> None:
    _validate_plug(tracking_mode, tuya_device_id, tuya_local_key, declared_on_time, declared_off_time)
    with get_connection() as conn:
        conn.execute(
            """UPDATE plug SET enclosure_id = ?, label = ?, purpose = ?, tracking_mode = ?, switch_dps_key = ?,
                                tuya_device_id = ?, tuya_local_key = ?, tuya_ip_address = ?,
                                declared_on_time = ?, declared_off_time = ? WHERE id = ?""",
            (enclosure_id, label, purpose, tracking_mode, switch_dps_key or "1", tuya_device_id or None,
             tuya_local_key or None, tuya_ip_address or None, declared_on_time or None, declared_off_time or None,
             plug_id),
        )


def list_rooms() -> list[dict]:
    with get_connection() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM room ORDER BY name")]


def create_room(name: str) -> int:
    with get_connection() as conn:
        cur = conn.execute("INSERT INTO room (name) VALUES (?)", (name,))
        return cur.lastrowid


def get_room(room_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM room WHERE id = ?", (room_id,)).fetchone()
        if row is None:
            return None
        room = dict(row)
        room["sensors"] = [dict(r) for r in conn.execute("SELECT * FROM sensor WHERE room_id = ? ORDER BY label", (room_id,))]
        for sensor in room["sensors"]:
            latest = conn.execute(
                """SELECT temperature_c, humidity_pct, recorded_at FROM sensor_reading
                   WHERE sensor_id = ? ORDER BY recorded_at DESC LIMIT 1""",
                (sensor["id"],),
            ).fetchone()
            sensor["latest_reading"] = dict(latest) if latest else None
        room["enclosures"] = [dict(r) for r in conn.execute("SELECT * FROM enclosure WHERE room_id = ? ORDER BY name", (room_id,))]
        return room


def _validate_light_schedule(light_on_time: str | None, light_off_time: str | None) -> None:
    """See CONTEXT.md: Light Schedule."""
    if bool(light_on_time) != bool(light_off_time):
        raise ValueError("Enter both a light on-time and off-time, or leave both blank.")


def update_room(room_id: int, name: str, light_on_time: str | None, light_off_time: str | None,
                 light_notes: str | None) -> None:
    _validate_light_schedule(light_on_time, light_off_time)
    with get_connection() as conn:
        conn.execute(
            "UPDATE room SET name = ?, light_on_time = ?, light_off_time = ?, light_notes = ? WHERE id = ?",
            (name, light_on_time or None, light_off_time or None, light_notes or None, room_id),
        )


def delete_room(room_id: int) -> None:
    # Cascades to the Room's own Sensors; Enclosures that belonged to it get room_id set NULL
    # (un-assigned, not deleted) via the FK's ON DELETE SET NULL — see ADR 0004.
    with get_connection() as conn:
        conn.execute("DELETE FROM room WHERE id = ?", (room_id,))


def get_settings() -> dict:
    """App-wide settings — a single row (see CONTEXT.md: Refresh, ADR 0005)."""
    with get_connection() as conn:
        return dict(conn.execute("SELECT * FROM app_setting WHERE id = 1").fetchone())


def update_settings(ble_refresh_timeout_seconds: int) -> None:
    if ble_refresh_timeout_seconds < 1:
        raise ValueError("Refresh Timeout needs to be at least 1 second.")
    with get_connection() as conn:
        conn.execute(
            "UPDATE app_setting SET ble_refresh_timeout_seconds = ? WHERE id = 1",
            (ble_refresh_timeout_seconds,),
        )
