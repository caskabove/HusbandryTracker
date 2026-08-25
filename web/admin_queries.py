"""Write/CRUD access backing the admin UI — the browser-based counterpart to tools/register_device.py.
Both talk to the same tables; nothing here changes the schema or the CLI tool, which stays useful
for scripting/bulk setup.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.db import get_connection
from schemas import enclosure_types as et
from web.queries import CARE_EVENT_KINDS, _normalize_datetime_local, days_since


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
        enclosure["plugs"] = [dict(r) for r in conn.execute(
            """SELECT p.* FROM plug p JOIN plug_enclosure pe ON pe.plug_id = p.id
               WHERE pe.enclosure_id = ? ORDER BY p.label""",
            (enclosure_id,),
        )]
        for plug in enclosure["plugs"]:
            # Detected Schedule (see CONTEXT.md, ADR 0012) only means anything for a Smart,
            # non-Controller-Kind Plug.
            detected = _detect_schedule(conn, plug["id"]) if (
                plug["tracking_mode"] == "smart" and plug["controller_kind"] == "none"
            ) else {"on_time": None, "off_time": None}
            plug["detected_on_time"] = detected["on_time"]
            plug["detected_off_time"] = detected["off_time"]
            # "everything on one switch" — see CONTEXT.md: Plug, ADR 0006. Names the *other*
            # Enclosures sharing this Plug, so it's obvious here it's not exclusive to this one.
            plug["shared_with"] = [r["name"] for r in conn.execute(
                """SELECT e.name FROM enclosure e JOIN plug_enclosure pe ON pe.enclosure_id = e.id
                   WHERE pe.plug_id = ? AND pe.enclosure_id != ? ORDER BY e.name""",
                (plug["id"], enclosure_id),
            )]

        enclosure["care"] = {}
        for kind in CARE_EVENT_KINDS:
            latest = conn.execute(
                """SELECT occurred_at FROM care_event
                   WHERE enclosure_id = ? AND kind = ? ORDER BY occurred_at DESC LIMIT 1""",
                (enclosure_id, kind),
            ).fetchone()
            occurred_at = latest["occurred_at"] if latest else None
            enclosure["care"][kind] = {"occurred_at": occurred_at, "days_since": days_since(occurred_at)}

        # Plant / Plant Health (see CONTEXT.md: Plant, Plant Health) — only ever populated for a
        # Bioactive Enclosure in practice (create_plant enforces it), but harmless to fetch
        # regardless so a page just shows empty lists rather than needing a special case here.
        enclosure["plants"] = [dict(r) for r in conn.execute(
            "SELECT * FROM plant WHERE enclosure_id = ? ORDER BY name", (enclosure_id,)
        )]
        enclosure["plant_health_log"] = [dict(r) for r in conn.execute(
            """SELECT phl.*, p.name AS plant_name FROM plant_health_log phl
               LEFT JOIN plant p ON p.id = phl.plant_id
               WHERE phl.enclosure_id = ? ORDER BY phl.occurred_at DESC LIMIT 10""",
            (enclosure_id,),
        )]

        return enclosure


def create_plant(enclosure_id: int, name: str, species: str | None) -> None:
    """See CONTEXT.md: Plant. Only meaningful on a Bioactive Enclosure — enforced here, not in the
    schema, same pattern as this file's other cross-row invariants (e.g. Manual Sensor's Target
    Range requirement)."""
    with get_connection() as conn:
        row = conn.execute("SELECT bioactive FROM enclosure WHERE id = ?", (enclosure_id,)).fetchone()
        if row is None or not row["bioactive"]:
            raise ValueError("Only a Bioactive Enclosure can have Plants — check Bioactive in Enclosure Settings first.")
        conn.execute(
            "INSERT INTO plant (enclosure_id, name, species) VALUES (?, ?, ?)",
            (enclosure_id, name, species or None),
        )


def delete_plant(plant_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM plant WHERE id = ?", (plant_id,))


def log_plant_health(enclosure_id: int, note: str, plant_id: int | None = None,
                      occurred_at: str | None = None) -> None:
    """See CONTEXT.md: Plant Health. plant_id None means an Enclosure-wide observation rather than
    one specific Plant — backdatable like a Care Event, but kept in its own table (see
    db/schema.sql's comment on plant_health_log for why)."""
    if not note or not note.strip():
        raise ValueError("Enter a note describing what you observed.")
    occurred_at = _normalize_datetime_local(occurred_at)
    with get_connection() as conn:
        if occurred_at:
            conn.execute(
                "INSERT INTO plant_health_log (enclosure_id, plant_id, note, occurred_at) VALUES (?, ?, ?, ?)",
                (enclosure_id, plant_id, note, occurred_at),
            )
        else:
            conn.execute(
                "INSERT INTO plant_health_log (enclosure_id, plant_id, note) VALUES (?, ?, ?)",
                (enclosure_id, plant_id, note),
            )


def _validate_enclosure_type(enclosure_type: str) -> None:
    if enclosure_type not in et.ENCLOSURE_TYPES:
        raise ValueError(f"Unknown Enclosure Type: {enclosure_type!r}")


def create_enclosure(name: str, enclosure_type: str, bioactive: bool, feeding: int, watering: int,
                      spot: int, deep: int) -> int:
    # Room assignment happens as a follow-up edit (see update_enclosure), not at creation — keeps
    # this quick-create form minimal, matching how Sensor/Plug reassignment already works.
    _validate_enclosure_type(enclosure_type)
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO enclosure (name, enclosure_type, bioactive, feeding_interval_days, watering_interval_days,
                                       spot_clean_interval_days, deep_clean_interval_days)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, enclosure_type, int(bioactive), feeding, watering, spot, deep),
        )
        return cur.lastrowid


def update_enclosure(enclosure_id: int, name: str, enclosure_type: str, bioactive: bool, feeding: int,
                      watering: int, spot: int, deep: int,
                      room_id: int | None, fallback_sensor_id: int | None) -> None:
    """room_id and fallback_sensor_id see CONTEXT.md: Room, Fallback Sensor. The Admin UI only ever
    offers a Fallback Sensor dropdown scoped to the chosen Room's own Sensors and only when this
    Enclosure has none of its own, so no extra cross-check is done here — display logic (see
    web/queries.py) also always prefers an Enclosure's own Sensors over its Fallback Sensor
    regardless, so a stale fallback_sensor_id left over after adding a real Sensor is harmless.

    Changing enclosure_type doesn't retroactively clear any of this Enclosure's Sensors' now-
    inapplicable Target Range values (e.g. Saltwater -> Basic leaves salinity values sitting
    unused) — see CONTEXT.md: Enclosure Type. They're just hidden/unvalidated going forward, not
    wiped; a deliberate scope cut, not an oversight."""
    _validate_enclosure_type(enclosure_type)
    with get_connection() as conn:
        conn.execute(
            """UPDATE enclosure SET name = ?, enclosure_type = ?, bioactive = ?, feeding_interval_days = ?,
                                     watering_interval_days = ?, spot_clean_interval_days = ?,
                                     deep_clean_interval_days = ?, room_id = ?,
                                     fallback_sensor_id = ? WHERE id = ?""",
            (name, enclosure_type, int(bioactive), feeding, watering, spot, deep, room_id, fallback_sensor_id, enclosure_id),
        )


def _get_or_create_unassigned_enclosure(conn, exclude_id: int | None = None) -> int:
    """See CONTEXT.md: Unassigned. exclude_id skips a row by that id — used when the Enclosure
    literally named "Unassigned" is itself the one being deleted, so a fresh one gets created
    instead of pointing back at the row that's about to disappear."""
    row = conn.execute("SELECT id FROM enclosure WHERE name = 'Unassigned' AND id != ?", (exclude_id or -1,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO enclosure (name) VALUES ('Unassigned')")
    return cur.lastrowid


def delete_enclosure(enclosure_id: int) -> None:
    # A Plug whose ONLY Enclosure link is this one would otherwise lose its last parent (and its
    # Tuya credentials/history with it) — move it to Unassigned first instead. See ADR 0006.
    with get_connection() as conn:
        orphaned = conn.execute(
            """SELECT plug_id FROM plug_enclosure WHERE enclosure_id = ?
               AND plug_id NOT IN (SELECT plug_id FROM plug_enclosure WHERE enclosure_id != ?)""",
            (enclosure_id, enclosure_id),
        ).fetchall()
        if orphaned:
            unassigned_id = _get_or_create_unassigned_enclosure(conn, exclude_id=enclosure_id)
            for row in orphaned:
                conn.execute(
                    "INSERT OR IGNORE INTO plug_enclosure (plug_id, enclosure_id) VALUES (?, ?)",
                    (row["plug_id"], unassigned_id),
                )
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


TargetRanges = dict[str, tuple[float | None, float | None]]


def _validate_sensor(tracking_mode: str, mac_address: str | None, target_ranges: TargetRanges,
                      enclosure_type: str | None) -> None:
    """See CONTEXT.md: Tracking Mode, Target Range, Enclosure Type. Raised as ValueError so the
    Admin route can show a friendly message instead of a raw SQLite CHECK failure.

    target_ranges maps a schemas.enclosure_types metric key (e.g. "temperature", "ph") to its
    submitted (min, max) pair — see schemas/enclosure_types.py. enclosure_type is None for a
    Room-owned Sensor: a Room has no Enclosure Type (see CONTEXT.md: Room), so only
    temperature/humidity are ever offered there and the et.validate_target_ranges() check below is
    skipped entirely rather than gated against a type that doesn't apply.
    """
    if tracking_mode not in ("smart", "manual"):
        raise ValueError(f"Unknown Tracking Mode: {tracking_mode!r}")
    if tracking_mode == "smart":
        if not mac_address:
            raise ValueError("A Smart Sensor needs a MAC address.")
    else:
        if mac_address:
            raise ValueError("A Manual Sensor has no physical device — leave the MAC address blank.")
        if not any(mn is not None and mx is not None for mn, mx in target_ranges.values()):
            raise ValueError(
                "A Manual Sensor needs a complete Target Range (both min and max) on at least one "
                "metric before it can be saved — there's nothing to judge a hand-logged Reading against otherwise."
            )
    if enclosure_type is not None:
        provided = [key for key, (mn, mx) in target_ranges.items() if mn is not None or mx is not None]
        et.validate_target_ranges(enclosure_type, provided)


def _target_range_sql(target_ranges: TargetRanges) -> tuple[list[str], list[float | None]]:
    """Column names + values for every Target Range metric, in schemas.enclosure_types' fixed
    order — the single source of truth for the column list, so it can't drift from db/schema.sql or
    from the Enclosure Type gating logic. A metric missing from target_ranges (Room Sensor calls
    only ever supply temperature/humidity) is written as NULL, same as if it were left blank."""
    columns: list[str] = []
    values: list[float | None] = []
    for metric in et.TARGET_RANGE_METRICS:
        mn, mx = target_ranges.get(metric.key, (None, None))
        columns += [metric.min_column, metric.max_column]
        values += [mn, mx]
    return columns, values


def _get_enclosure_type(enclosure_id: int) -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT enclosure_type FROM enclosure WHERE id = ?", (enclosure_id,)).fetchone()
    return row["enclosure_type"] if row else "basic"


def create_sensor(enclosure_id: int, label: str, tracking_mode: str, mac_address: str | None,
                   target_ranges: TargetRanges) -> None:
    _validate_sensor(tracking_mode, mac_address, target_ranges, _get_enclosure_type(enclosure_id))
    columns, values = _target_range_sql(target_ranges)
    with get_connection() as conn:
        conn.execute(
            f"""INSERT INTO sensor (enclosure_id, label, tracking_mode, mac_address, {", ".join(columns)})
                VALUES (?, ?, ?, ?, {", ".join("?" for _ in columns)})""",
            (enclosure_id, label, tracking_mode, mac_address.upper() if mac_address else None, *values),
        )


def delete_sensor(sensor_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM sensor WHERE id = ?", (sensor_id,))


def get_sensor(sensor_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM sensor WHERE id = ?", (sensor_id,)).fetchone()
        return dict(row) if row else None


def update_sensor(sensor_id: int, enclosure_id: int, label: str, tracking_mode: str, mac_address: str | None,
                   target_ranges: TargetRanges, auto_update_enabled: bool = True) -> None:
    """auto_update_enabled: see CONTEXT.md: Auto-Update. Pausing has no effect on a Manual Sensor
    (there's no background collection to pause), but the column and toggle stay uniform regardless."""
    _validate_sensor(tracking_mode, mac_address, target_ranges, _get_enclosure_type(enclosure_id))
    columns, values = _target_range_sql(target_ranges)
    set_clause = ", ".join(f"{c} = ?" for c in columns)
    with get_connection() as conn:
        conn.execute(
            f"""UPDATE sensor SET enclosure_id = ?, label = ?, tracking_mode = ?, mac_address = ?,
                                   auto_update_enabled = ?, {set_clause} WHERE id = ?""",
            (enclosure_id, label, tracking_mode, mac_address.upper() if mac_address else None,
             int(auto_update_enabled), *values, sensor_id),
        )


def create_room_sensor(room_id: int, label: str, tracking_mode: str, mac_address: str | None, temp_min: float | None,
                        temp_max: float | None, humidity_min: float | None, humidity_max: float | None) -> None:
    """A Room's ambient Sensor — same Sensor concept, Room instead of Enclosure as parent. See
    CONTEXT.md: Room, Sensor. Room Sensors aren't gated by Enclosure Type (a Room has none) — only
    temperature/humidity are ever offered here, matching what ambient room comfort needs."""
    target_ranges: TargetRanges = {"temperature": (temp_min, temp_max), "humidity": (humidity_min, humidity_max)}
    _validate_sensor(tracking_mode, mac_address, target_ranges, enclosure_type=None)
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
                        humidity_max: float | None, auto_update_enabled: bool = True) -> None:
    target_ranges: TargetRanges = {"temperature": (temp_min, temp_max), "humidity": (humidity_min, humidity_max)}
    _validate_sensor(tracking_mode, mac_address, target_ranges, enclosure_type=None)
    with get_connection() as conn:
        conn.execute(
            """UPDATE sensor SET room_id = ?, label = ?, tracking_mode = ?, mac_address = ?,
                                  auto_update_enabled = ?,
                                  target_temp_min_c = ?, target_temp_max_c = ?, target_humidity_min = ?,
                                  target_humidity_max = ? WHERE id = ?""",
            (room_id, label, tracking_mode, mac_address.upper() if mac_address else None,
             int(auto_update_enabled), temp_min, temp_max, humidity_min, humidity_max, sensor_id),
        )


def _validate_plug(tracking_mode: str, tuya_device_id: str | None, tuya_local_key: str | None,
                    target_on_time: str | None, target_off_time: str | None,
                    room_id: int | None, enclosure_ids: list[int],
                    controller_kind: str, target_temp_c: float | None,
                    target_humidity_pct: float | None) -> None:
    """See CONTEXT.md: Tracking Mode, Target Schedule, Plug, Controller Kind. Raised as ValueError
    so the Admin route can show a friendly message instead of a raw SQLite CHECK failure (the
    Room-XOR-Enclosure-set rule can't be a CHECK at all — it depends on plug_enclosure row counts, a
    different table)."""
    if tracking_mode not in ("smart", "manual"):
        raise ValueError(f"Unknown Tracking Mode: {tracking_mode!r}")
    if controller_kind not in ("none", "thermostat", "hydrostat"):
        raise ValueError(f"Unknown Controller Kind: {controller_kind!r}")
    if tracking_mode == "smart":
        if not tuya_device_id or not tuya_local_key:
            raise ValueError("A Smart Plug needs both a Tuya device_id and local_key.")
    else:
        if tuya_device_id or tuya_local_key:
            raise ValueError("A Manual Plug has no device credentials — leave the Tuya fields blank.")
    # Target Schedule's both-or-neither rule applies to any Plug without a Controller Kind, Smart
    # or Manual alike — see ADR 0012 (this used to be Manual-only, back when it was called Declared
    # Schedule and a Smart Plug had no way to set one at all).
    if controller_kind == "none" and bool(target_on_time) != bool(target_off_time):
        raise ValueError("Enter both a target on-time and off-time, or leave both blank.")
    if bool(room_id) == bool(enclosure_ids):
        raise ValueError("A Plug needs exactly one parent — pick a Room, or one or more Enclosures, not both or neither.")
    if controller_kind == "thermostat" and target_temp_c is None:
        raise ValueError("A Thermostat-Controlled Plug needs a Target Temperature.")
    if controller_kind == "hydrostat" and target_humidity_pct is None:
        raise ValueError("A Hydrostat-Controlled Plug needs a Target Humidity.")


def create_plug(label: str, purpose: str, tracking_mode: str, tuya_device_id: str | None,
                 tuya_local_key: str | None, tuya_ip_address: str | None, switch_dps_key: str = "1",
                 target_on_time: str | None = None, target_off_time: str | None = None,
                 room_id: int | None = None, enclosure_ids: list[int] | None = None,
                 controller_kind: str = "none", target_temp_c: float | None = None,
                 target_humidity_pct: float | None = None) -> int:
    enclosure_ids = enclosure_ids or []
    _validate_plug(tracking_mode, tuya_device_id, tuya_local_key, target_on_time, target_off_time,
                   room_id, enclosure_ids, controller_kind, target_temp_c, target_humidity_pct)
    if controller_kind != "none":
        # Schedule isn't meaningful for a Thermostat-/Hydrostat-Controlled Plug — see ADR 0008.
        target_on_time = target_off_time = None
    if controller_kind != "thermostat":
        target_temp_c = None
    if controller_kind != "hydrostat":
        target_humidity_pct = None
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO plug (room_id, label, purpose, tracking_mode, tuya_device_id, tuya_local_key,
                                  tuya_ip_address, switch_dps_key, target_on_time, target_off_time,
                                  controller_kind, target_temp_c, target_humidity_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (room_id, label, purpose, tracking_mode, tuya_device_id or None, tuya_local_key or None,
             tuya_ip_address or None, switch_dps_key or "1", target_on_time or None, target_off_time or None,
             controller_kind, target_temp_c, target_humidity_pct),
        )
        plug_id = cur.lastrowid
        for eid in enclosure_ids:
            conn.execute("INSERT INTO plug_enclosure (plug_id, enclosure_id) VALUES (?, ?)", (plug_id, eid))
        return plug_id


def delete_plug(plug_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM plug WHERE id = ?", (plug_id,))


def get_plug(plug_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM plug WHERE id = ?", (plug_id,)).fetchone()
        if row is None:
            return None
        plug = dict(row)
        plug["enclosure_ids"] = [r["enclosure_id"] for r in conn.execute(
            "SELECT enclosure_id FROM plug_enclosure WHERE plug_id = ?", (plug_id,)
        )]
        # Detected Schedule (see CONTEXT.md, ADR 0012) only means anything for a Smart,
        # non-Controller-Kind Plug.
        detected = _detect_schedule(conn, plug_id) if (
            plug["tracking_mode"] == "smart" and plug["controller_kind"] == "none"
        ) else {"on_time": None, "off_time": None}
        plug["detected_on_time"] = detected["on_time"]
        plug["detected_off_time"] = detected["off_time"]
        return plug


def _detect_schedule(conn, plug_id: int) -> dict:
    """Detected Schedule (see CONTEXT.md) — the time-of-day of the most recent transition to on,
    and separately to off, for a Smart Plug. Not an average across days, just the latest observed
    instance of each (see ADR 0012). Either/both come back None if that kind of transition has never
    been seen. Computed on demand from plug_state_transition, not stored."""
    on_row = conn.execute(
        """SELECT recorded_at FROM plug_state_transition WHERE plug_id = ? AND is_on = 1
           ORDER BY recorded_at DESC LIMIT 1""",
        (plug_id,),
    ).fetchone()
    off_row = conn.execute(
        """SELECT recorded_at FROM plug_state_transition WHERE plug_id = ? AND is_on = 0
           ORDER BY recorded_at DESC LIMIT 1""",
        (plug_id,),
    ).fetchone()
    return {
        "on_time": on_row["recorded_at"][11:16] if on_row else None,
        "off_time": off_row["recorded_at"][11:16] if off_row else None,
    }


def list_plugs() -> list[dict]:
    """For the top-level Plugs admin list — each row's parent_label describes where it lives,
    whichever side of the Room/Enclosure-set split it's on. See CONTEXT.md: Plug."""
    with get_connection() as conn:
        plugs = [dict(r) for r in conn.execute("SELECT * FROM plug ORDER BY label")]
        room_names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM room")}
        for plug in plugs:
            if plug["room_id"]:
                plug["parent_label"] = f"Room: {room_names.get(plug['room_id'], '?')}"
            else:
                names = [r["name"] for r in conn.execute(
                    """SELECT e.name FROM enclosure e JOIN plug_enclosure pe ON pe.enclosure_id = e.id
                       WHERE pe.plug_id = ? ORDER BY e.name""",
                    (plug["id"],),
                )]
                plug["parent_label"] = ", ".join(names) if names else "—"
            # Detected Schedule only means anything for a Smart, non-Controller-Kind Plug — see
            # CONTEXT.md: Detected Schedule.
            detected = _detect_schedule(conn, plug["id"]) if (
                plug["tracking_mode"] == "smart" and plug["controller_kind"] == "none"
            ) else {"on_time": None, "off_time": None}
            plug["detected_on_time"] = detected["on_time"]
            plug["detected_off_time"] = detected["off_time"]
        return plugs


def update_plug(plug_id: int, label: str, purpose: str, tracking_mode: str, switch_dps_key: str,
                 tuya_device_id: str | None, tuya_local_key: str | None, tuya_ip_address: str | None,
                 target_on_time: str | None = None, target_off_time: str | None = None,
                 room_id: int | None = None, enclosure_ids: list[int] | None = None,
                 controller_kind: str = "none", target_temp_c: float | None = None,
                 target_humidity_pct: float | None = None, auto_update_enabled: bool = True) -> None:
    """auto_update_enabled: see CONTEXT.md: Auto-Update. Pausing has no effect on a Manual Plug
    (there's no background collection to pause), but the column and toggle stay uniform regardless."""
    enclosure_ids = enclosure_ids or []
    _validate_plug(tracking_mode, tuya_device_id, tuya_local_key, target_on_time, target_off_time,
                   room_id, enclosure_ids, controller_kind, target_temp_c, target_humidity_pct)
    if controller_kind != "none":
        target_on_time = target_off_time = None
    if controller_kind != "thermostat":
        target_temp_c = None
    if controller_kind != "hydrostat":
        target_humidity_pct = None
    with get_connection() as conn:
        conn.execute(
            """UPDATE plug SET room_id = ?, label = ?, purpose = ?, tracking_mode = ?, switch_dps_key = ?,
                                tuya_device_id = ?, tuya_local_key = ?, tuya_ip_address = ?,
                                target_on_time = ?, target_off_time = ?, auto_update_enabled = ?,
                                controller_kind = ?, target_temp_c = ?, target_humidity_pct = ? WHERE id = ?""",
            (room_id, label, purpose, tracking_mode, switch_dps_key or "1", tuya_device_id or None,
             tuya_local_key or None, tuya_ip_address or None, target_on_time or None, target_off_time or None,
             int(auto_update_enabled), controller_kind, target_temp_c, target_humidity_pct,
             plug_id),
        )
        conn.execute("DELETE FROM plug_enclosure WHERE plug_id = ?", (plug_id,))
        for eid in enclosure_ids:
            conn.execute("INSERT INTO plug_enclosure (plug_id, enclosure_id) VALUES (?, ?)", (plug_id, eid))


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
        room["plugs"] = [dict(r) for r in conn.execute("SELECT * FROM plug WHERE room_id = ? ORDER BY label", (room_id,))]
        for plug in room["plugs"]:
            # Detected Schedule (see CONTEXT.md, ADR 0012) only means anything for a Smart,
            # non-Controller-Kind Plug.
            detected = _detect_schedule(conn, plug["id"]) if (
                plug["tracking_mode"] == "smart" and plug["controller_kind"] == "none"
            ) else {"on_time": None, "off_time": None}
            plug["detected_on_time"] = detected["on_time"]
            plug["detected_off_time"] = detected["off_time"]
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


def update_settings(ble_refresh_timeout_seconds: int, alert_debounce_minutes: int,
                     ntfy_server_url: str | None, ntfy_topic: str | None,
                     schedule_drift_threshold_minutes: int = 15) -> None:
    """See CONTEXT.md: Refresh (ADR 0005), Alert Debounce (ADR 0010), Timer Warning (ADR 0012).
    ntfy_server_url/ntfy_topic left blank disables Send Alert delivery entirely — see
    collectors/alerts.py, which just logs to the console instead of sending in that case."""
    if ble_refresh_timeout_seconds < 1:
        raise ValueError("Refresh Timeout needs to be at least 1 second.")
    if alert_debounce_minutes < 1:
        raise ValueError("Alert Debounce needs to be at least 1 minute.")
    if schedule_drift_threshold_minutes < 1:
        raise ValueError("Schedule Drift Threshold needs to be at least 1 minute.")
    with get_connection() as conn:
        conn.execute(
            """UPDATE app_setting SET ble_refresh_timeout_seconds = ?, alert_debounce_minutes = ?,
                                       ntfy_server_url = ?, ntfy_topic = ?,
                                       schedule_drift_threshold_minutes = ? WHERE id = 1""",
            (ble_refresh_timeout_seconds, alert_debounce_minutes, ntfy_server_url or None, ntfy_topic or None,
             schedule_drift_threshold_minutes),
        )
