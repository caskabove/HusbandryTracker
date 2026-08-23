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


def create_sensor(enclosure_id: int, label: str, mac_address: str, temp_min: float | None, temp_max: float | None,
                   humidity_min: float | None, humidity_max: float | None) -> None:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO sensor (enclosure_id, label, mac_address, target_temp_min_c, target_temp_max_c,
                                    target_humidity_min, target_humidity_max)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (enclosure_id, label, mac_address.upper(), temp_min, temp_max, humidity_min, humidity_max),
        )


def delete_sensor(sensor_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM sensor WHERE id = ?", (sensor_id,))


def create_plug(enclosure_id: int, label: str, purpose: str, tuya_device_id: str, tuya_local_key: str,
                 tuya_ip_address: str | None) -> None:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO plug (enclosure_id, label, purpose, tuya_device_id, tuya_local_key, tuya_ip_address)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (enclosure_id, label, purpose, tuya_device_id, tuya_local_key, tuya_ip_address or None),
        )


def delete_plug(plug_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM plug WHERE id = ?", (plug_id,))
