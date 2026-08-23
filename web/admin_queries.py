"""Write/CRUD access backing the admin UI — the browser-based counterpart to tools/register_device.py.
Both talk to the same tables; nothing here changes the schema or the CLI tool, which stays useful
for scripting/bulk setup.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.db import get_connection


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
        return enclosure


def create_enclosure(name: str, bioactive: bool, feeding: int, watering: int, spot: int, deep: int) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO enclosure (name, bioactive, feeding_interval_days, watering_interval_days,
                                       spot_clean_interval_days, deep_clean_interval_days)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, int(bioactive), feeding, watering, spot, deep),
        )
        return cur.lastrowid


def update_enclosure(enclosure_id: int, name: str, bioactive: bool, feeding: int, watering: int, spot: int, deep: int) -> None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE enclosure SET name = ?, bioactive = ?, feeding_interval_days = ?, watering_interval_days = ?,
                                     spot_clean_interval_days = ?, deep_clean_interval_days = ? WHERE id = ?""",
            (name, int(bioactive), feeding, watering, spot, deep, enclosure_id),
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
