"""Write/CRUD access backing the admin UI — the browser-based counterpart to tools/register_device.py.
Both talk to the same tables; nothing here changes the schema or the CLI tool, which stays useful
for scripting/bulk setup.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.db import get_connection
from plugins.govee_ble import identity as govee_identity
from plugins.tuya_lan import identity as tuya_identity
from schemas import enclosure_types as et
from web.outbox import write_command
from web.queries import CARE_EVENT_KINDS, _normalize_datetime_local, days_since


def _decode_sensor(row_dict: dict) -> dict:
    """Backfills the legacy `mac_address` key onto a sensor row dict from its Plugin/External ID
    (see CONTEXT.md: Plugin, External ID; ADR 0013) — every existing template/route keeps reading
    the field name it already expects. Govee is the only Smart Sensor Plugin this build supports,
    so External ID *is* the MAC address for every Smart Sensor row today."""
    row_dict["mac_address"] = row_dict.get("external_id")
    return row_dict


def _decode_plug(row_dict: dict) -> dict:
    """Backfills the legacy tuya_device_id/tuya_local_key/tuya_ip_address/switch_dps_key keys onto
    a plug row dict from its Plugin/External ID/Plugin Config (see CONTEXT.md: Plugin, External ID,
    Plugin Config; ADR 0013) — every existing template/route keeps reading the field names it
    already expects."""
    if row_dict.get("plugin") == tuya_identity.PLUGIN_NAME and row_dict.get("external_id"):
        device_id, dps_key = tuya_identity.decode_external_id(row_dict["external_id"])
        config = tuya_identity.unpack_config(row_dict.get("plugin_config"))
        row_dict["tuya_device_id"] = device_id
        row_dict["switch_dps_key"] = dps_key
        row_dict["tuya_local_key"] = config["local_key"]
        row_dict["tuya_ip_address"] = config["ip_address"]
    else:
        row_dict["tuya_device_id"] = None
        row_dict["tuya_local_key"] = None
        row_dict["tuya_ip_address"] = None
        row_dict["switch_dps_key"] = "1"
    return row_dict


def _encode_sensor_identity(tracking_mode: str, mac_address: str | None) -> tuple[str | None, str | None]:
    """See CONTEXT.md: Plugin, External ID; ADR 0013. Govee is the only Smart Sensor Plugin this
    build supports — a future second Sensor Plugin would need its own Admin form/field, same as
    Tuya and Govee already have distinct ones, but wouldn't need another schema change."""
    if tracking_mode != "smart" or not mac_address:
        return None, None
    return govee_identity.PLUGIN_NAME, govee_identity.encode_external_id(mac_address)


def _encode_plug_identity(tracking_mode: str, tuya_device_id: str | None, tuya_local_key: str | None,
                           tuya_ip_address: str | None, switch_dps_key: str | None) -> tuple[str | None, str | None, str | None]:
    """See CONTEXT.md: Plugin, External ID, Plugin Config; ADR 0013."""
    if tracking_mode != "smart" or not tuya_device_id:
        return None, None, None
    external_id = tuya_identity.encode_external_id(tuya_device_id, switch_dps_key)
    plugin_config = tuya_identity.pack_config(tuya_local_key, tuya_ip_address)
    return tuya_identity.PLUGIN_NAME, external_id, plugin_config


def _check_external_id_available(conn, plugin: str | None, external_id: str | None,
                                  exclude_plug_id: int | None = None) -> None:
    """Raises a friendly ValueError instead of letting plug's UNIQUE(plugin, external_id) constraint
    fail as a raw sqlite3.IntegrityError (500 Internal Server Error) — same device_id/switch_dps_key
    combination can't back two Plug rows at once (see CONTEXT.md: External ID). The common real
    trigger: a multi-outlet strip's DPS key already claimed by an existing standalone Plug — the fix
    is attaching that existing Plug via set_plug_group(), not creating a second row for it."""
    if plugin is None or external_id is None:
        return
    query = "SELECT id, label FROM plug WHERE plugin = ? AND external_id = ?"
    params: tuple = (plugin, external_id)
    if exclude_plug_id is not None:
        query += " AND id != ?"
        params += (exclude_plug_id,)
    existing = conn.execute(query, params).fetchone()
    if existing is not None:
        raise ValueError(
            f"That device_id/DPS key is already registered as Plug {existing['label']!r} "
            f"(id {existing['id']}) — edit that existing Plug instead of creating a new one for it."
        )


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
        enclosure["sensors"] = [_decode_sensor(dict(r)) for r in conn.execute("SELECT * FROM sensor WHERE enclosure_id = ? ORDER BY label", (enclosure_id,))]
        # Current Reading — same "what's actually happening right now" info the Dashboard already
        # shows for this Enclosure's Sensors, and Room Sensors already get on their own Admin page
        # (get_room() below); this page just didn't fetch it before.
        for sensor in enclosure["sensors"]:
            # SELECT * — a Reading can carry any Target Range metric, not just temp/humidity (see
            # CONTEXT.md: Reading; schemas/enclosure_types.py's TARGET_RANGE_METRICS).
            latest = conn.execute(
                "SELECT * FROM sensor_reading WHERE sensor_id = ? ORDER BY recorded_at DESC LIMIT 1",
                (sensor["id"],),
            ).fetchone()
            sensor["latest_reading"] = dict(latest) if latest else None
        enclosure["plugs"] = [_decode_plug(dict(r)) for r in conn.execute(
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
            plug["last_command"] = _command_status(conn, plug)
            plug["current_status"] = _current_plug_status(conn, plug)
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
                      spot: int, deep: int, show_feeding: bool = True, show_watering: bool = True,
                      show_spot_clean: bool = True, show_deep_clean: bool = True) -> int:
    # Room assignment happens as a follow-up edit (see update_enclosure), not at creation — keeps
    # this quick-create form minimal, matching how Sensor/Plug reassignment already works.
    _validate_enclosure_type(enclosure_type)
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO enclosure (name, enclosure_type, bioactive, feeding_interval_days, watering_interval_days,
                                       spot_clean_interval_days, deep_clean_interval_days,
                                       show_feeding_on_dashboard, show_watering_on_dashboard,
                                       show_spot_clean_on_dashboard, show_deep_clean_on_dashboard)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, enclosure_type, int(bioactive), feeding, watering, spot, deep,
             int(show_feeding), int(show_watering), int(show_spot_clean), int(show_deep_clean)),
        )
        return cur.lastrowid


def update_enclosure(enclosure_id: int, name: str, enclosure_type: str, bioactive: bool, feeding: int,
                      watering: int, spot: int, deep: int,
                      room_id: int | None, fallback_sensor_id: int | None,
                      show_feeding: bool = True, show_watering: bool = True,
                      show_spot_clean: bool = True, show_deep_clean: bool = True) -> None:
    """room_id and fallback_sensor_id see CONTEXT.md: Room, Fallback Sensor. The Admin UI only ever
    offers a Fallback Sensor dropdown scoped to the chosen Room's own Sensors and only when this
    Enclosure has none of its own, so no extra cross-check is done here — display logic (see
    web/queries.py) also always prefers an Enclosure's own Sensors over its Fallback Sensor
    regardless, so a stale fallback_sensor_id left over after adding a real Sensor is harmless.

    Changing enclosure_type doesn't retroactively clear any of this Enclosure's Sensors' now-
    inapplicable Target Range values (e.g. Saltwater -> Basic leaves salinity values sitting
    unused) — see CONTEXT.md: Enclosure Type. They're just hidden/unvalidated going forward, not
    wiped; a deliberate scope cut, not an oversight.

    show_feeding/watering/spot_clean/deep_clean are each Care kind's Dashboard visibility (see
    CONTEXT.md: Care Interval) — unlike Animal/Sensor/Plug's show_on_dashboard there's no per-row
    edit page for these, so they're saved together with the rest of this same Enclosure Settings
    form instead of through a standalone toggle endpoint."""
    _validate_enclosure_type(enclosure_type)
    with get_connection() as conn:
        conn.execute(
            """UPDATE enclosure SET name = ?, enclosure_type = ?, bioactive = ?, feeding_interval_days = ?,
                                     watering_interval_days = ?, spot_clean_interval_days = ?,
                                     deep_clean_interval_days = ?, room_id = ?, fallback_sensor_id = ?,
                                     show_feeding_on_dashboard = ?, show_watering_on_dashboard = ?,
                                     show_spot_clean_on_dashboard = ?, show_deep_clean_on_dashboard = ?
                                     WHERE id = ?""",
            (name, enclosure_type, int(bioactive), feeding, watering, spot, deep, room_id, fallback_sensor_id,
             int(show_feeding), int(show_watering), int(show_spot_clean), int(show_deep_clean), enclosure_id),
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
    """show_on_dashboard (see CONTEXT.md: Animal) defaults on for only the first 3 Animals in an
    Enclosure — counting those already shown, not total Animals, so an Enclosure that's had some
    hidden by hand doesn't have that count "used up" by them. Past 3, a new Animal defaults off
    until picked from the Enclosure's Admin page; the user can always flip any Animal's flag
    either way regardless of this default."""
    with get_connection() as conn:
        (shown_count,) = conn.execute(
            "SELECT COUNT(*) FROM animal WHERE enclosure_id = ? AND show_on_dashboard = 1", (enclosure_id,)
        ).fetchone()
        conn.execute(
            "INSERT INTO animal (enclosure_id, name, species_common, species_scientific, dob, show_on_dashboard) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (enclosure_id, name, common or None, scientific or None, dob or None, 1 if shown_count < 3 else 0),
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


def set_animal_dashboard_visibility(animal_id: int, show_on_dashboard: bool) -> None:
    """Toggled from a checkbox on the Enclosure's Admin page (see CONTEXT.md: Animal) — independent
    of update_animal() since this is a one-field, checkbox-driven action rather than part of the
    full Animal edit form."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE animal SET show_on_dashboard = ? WHERE id = ?",
            (1 if show_on_dashboard else 0, animal_id),
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


def _next_show_on_dashboard(conn, parent_column: str, parent_id: int) -> int:
    """show_on_dashboard (see CONTEXT.md: Sensor) defaults on for only the first 3 Sensors under
    the same parent (Enclosure or Room) — counting those already shown, not total Sensors, same
    "top 3" reasoning as create_animal()'s show_on_dashboard default."""
    (shown_count,) = conn.execute(
        f"SELECT COUNT(*) FROM sensor WHERE {parent_column} = ? AND show_on_dashboard = 1", (parent_id,)
    ).fetchone()
    return 1 if shown_count < 3 else 0


def create_sensor(enclosure_id: int, label: str, tracking_mode: str, mac_address: str | None,
                   target_ranges: TargetRanges) -> None:
    _validate_sensor(tracking_mode, mac_address, target_ranges, _get_enclosure_type(enclosure_id))
    plugin, external_id = _encode_sensor_identity(tracking_mode, mac_address)
    columns, values = _target_range_sql(target_ranges)
    with get_connection() as conn:
        show_on_dashboard = _next_show_on_dashboard(conn, "enclosure_id", enclosure_id)
        conn.execute(
            f"""INSERT INTO sensor (enclosure_id, label, tracking_mode, plugin, external_id, show_on_dashboard,
                                     {", ".join(columns)})
                VALUES (?, ?, ?, ?, ?, ?, {", ".join("?" for _ in columns)})""",
            (enclosure_id, label, tracking_mode, plugin, external_id, show_on_dashboard, *values),
        )


def delete_sensor(sensor_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM sensor WHERE id = ?", (sensor_id,))


def get_sensor(sensor_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM sensor WHERE id = ?", (sensor_id,)).fetchone()
        return _decode_sensor(dict(row)) if row else None


def set_sensor_dashboard_visibility(sensor_id: int, show_on_dashboard: bool) -> None:
    """Toggled from a checkbox on the Sensor's parent (Enclosure or Room) Admin page — see
    CONTEXT.md: Sensor. Independent of update_sensor()/update_room_sensor() for the same reason as
    set_animal_dashboard_visibility(): a one-field, checkbox-driven action, not part of the full
    edit form."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE sensor SET show_on_dashboard = ? WHERE id = ?",
            (1 if show_on_dashboard else 0, sensor_id),
        )


def update_sensor(sensor_id: int, enclosure_id: int, label: str, tracking_mode: str, mac_address: str | None,
                   target_ranges: TargetRanges, auto_update_enabled: bool = True) -> None:
    """auto_update_enabled: see CONTEXT.md: Auto-Update. Pausing has no effect on a Manual Sensor
    (there's no background collection to pause), but the column and toggle stay uniform regardless."""
    _validate_sensor(tracking_mode, mac_address, target_ranges, _get_enclosure_type(enclosure_id))
    plugin, external_id = _encode_sensor_identity(tracking_mode, mac_address)
    columns, values = _target_range_sql(target_ranges)
    set_clause = ", ".join(f"{c} = ?" for c in columns)
    with get_connection() as conn:
        conn.execute(
            f"""UPDATE sensor SET enclosure_id = ?, label = ?, tracking_mode = ?, plugin = ?, external_id = ?,
                                   auto_update_enabled = ?, {set_clause} WHERE id = ?""",
            (enclosure_id, label, tracking_mode, plugin, external_id,
             int(auto_update_enabled), *values, sensor_id),
        )


def create_room_sensor(room_id: int, label: str, tracking_mode: str, mac_address: str | None, temp_min: float | None,
                        temp_max: float | None, humidity_min: float | None, humidity_max: float | None) -> None:
    """A Room's ambient Sensor — same Sensor concept, Room instead of Enclosure as parent. See
    CONTEXT.md: Room, Sensor. Room Sensors aren't gated by Enclosure Type (a Room has none) — only
    temperature/humidity are ever offered here, matching what ambient room comfort needs."""
    target_ranges: TargetRanges = {"temperature": (temp_min, temp_max), "humidity": (humidity_min, humidity_max)}
    _validate_sensor(tracking_mode, mac_address, target_ranges, enclosure_type=None)
    plugin, external_id = _encode_sensor_identity(tracking_mode, mac_address)
    with get_connection() as conn:
        show_on_dashboard = _next_show_on_dashboard(conn, "room_id", room_id)
        conn.execute(
            """INSERT INTO sensor (room_id, label, tracking_mode, plugin, external_id, show_on_dashboard,
                                    target_temp_min_c, target_temp_max_c, target_humidity_min, target_humidity_max)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (room_id, label, tracking_mode, plugin, external_id, show_on_dashboard,
             temp_min, temp_max, humidity_min, humidity_max),
        )


def update_room_sensor(sensor_id: int, room_id: int, label: str, tracking_mode: str, mac_address: str | None,
                        temp_min: float | None, temp_max: float | None, humidity_min: float | None,
                        humidity_max: float | None, auto_update_enabled: bool = True) -> None:
    target_ranges: TargetRanges = {"temperature": (temp_min, temp_max), "humidity": (humidity_min, humidity_max)}
    _validate_sensor(tracking_mode, mac_address, target_ranges, enclosure_type=None)
    plugin, external_id = _encode_sensor_identity(tracking_mode, mac_address)
    with get_connection() as conn:
        conn.execute(
            """UPDATE sensor SET room_id = ?, label = ?, tracking_mode = ?, plugin = ?, external_id = ?,
                                  auto_update_enabled = ?,
                                  target_temp_min_c = ?, target_temp_max_c = ?, target_humidity_min = ?,
                                  target_humidity_max = ? WHERE id = ?""",
            (room_id, label, tracking_mode, plugin, external_id,
             int(auto_update_enabled), temp_min, temp_max, humidity_min, humidity_max, sensor_id),
        )


def _validate_plug(tracking_mode: str, tuya_device_id: str | None, tuya_local_key: str | None,
                    target_on_time: str | None, target_off_time: str | None,
                    room_id: int | None, enclosure_ids: list[int],
                    controller_kind: str, target_temp_c: float | None,
                    target_humidity_pct: float | None, always_on: bool = False) -> None:
    """See CONTEXT.md: Tracking Mode, Target Schedule, Plug, Controller Kind, Always On. Raised as
    ValueError so the Admin route can show a friendly message instead of a raw SQLite CHECK failure
    (the Room-XOR-Enclosure-set rule can't be a CHECK at all — it depends on plug_enclosure row
    counts, a different table)."""
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
    # Schedule and a Smart Plug had no way to set one at all). Always On (see CONTEXT.md) is the
    # third, mutually exclusive option in that same "none" case.
    if controller_kind == "none" and not always_on and bool(target_on_time) != bool(target_off_time):
        raise ValueError("Enter both a target on-time and off-time, or leave both blank.")
    if controller_kind == "none" and always_on and (target_on_time or target_off_time):
        raise ValueError("A Plug can't be both Always On and have a Target Schedule — pick one.")
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
                 target_humidity_pct: float | None = None, always_on: bool = False,
                 plug_group_id: int | None = None) -> int:
    enclosure_ids = enclosure_ids or []
    # Always On only means anything alongside controller_kind = 'none' — see CONTEXT.md: Always On.
    # Normalized (not an error) the same way a stray Target Schedule alongside a Controller Kind is
    # silently cleared below, rather than rejecting the request over a field the UI already hides.
    if controller_kind != "none":
        always_on = False
    _validate_plug(tracking_mode, tuya_device_id, tuya_local_key, target_on_time, target_off_time,
                   room_id, enclosure_ids, controller_kind, target_temp_c, target_humidity_pct, always_on)
    if controller_kind != "none" or always_on:
        # Schedule isn't meaningful for a Thermostat-/Hydrostat-Controlled Plug (see ADR 0008) or
        # an Always On one (see CONTEXT.md: Always On) — mutually exclusive either way.
        target_on_time = target_off_time = None
    if controller_kind != "thermostat":
        target_temp_c = None
    if controller_kind != "hydrostat":
        target_humidity_pct = None
    plugin, external_id, plugin_config = _encode_plug_identity(
        tracking_mode, tuya_device_id, tuya_local_key, tuya_ip_address, switch_dps_key
    )
    with get_connection() as conn:
        _check_external_id_available(conn, plugin, external_id)
        show_on_dashboard = _next_plug_show_on_dashboard(conn, room_id, enclosure_ids)
        cur = conn.execute(
            """INSERT INTO plug (room_id, plug_group_id, label, purpose, tracking_mode, plugin, external_id,
                                  plugin_config, show_on_dashboard, target_on_time, target_off_time, always_on,
                                  controller_kind, target_temp_c, target_humidity_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (room_id, plug_group_id, label, purpose, tracking_mode, plugin, external_id, plugin_config,
             show_on_dashboard, target_on_time or None, target_off_time or None, int(always_on),
             controller_kind, target_temp_c, target_humidity_pct),
        )
        plug_id = cur.lastrowid
        for eid in enclosure_ids:
            conn.execute("INSERT INTO plug_enclosure (plug_id, enclosure_id) VALUES (?, ?)", (plug_id, eid))
        return plug_id


def _next_plug_show_on_dashboard(conn, room_id: int | None, enclosure_ids: list[int]) -> int:
    """show_on_dashboard (see CONTEXT.md: Plug) defaults on for only the first 3 Plugs under the
    same parent — same "top 3" reasoning as create_animal()/create_sensor()'s own default, just
    scoped differently: a Plug's parent is either one Room (room_id, same as Sensor) or one-or-more
    Enclosures via plug_enclosure (see CONTEXT.md: Plug, ADR 0006) — there's no plug.enclosure_id
    column to count against directly. For an Enclosure-linked Plug (almost always exactly one
    Enclosure; "everything on one switch" is the rare case), it's shown only if EVERY Enclosure it's
    attached to still has room for another — a shared Plug shouldn't get a more generous default
    just because it touches more than one Enclosure's count."""
    if room_id is not None:
        (shown_count,) = conn.execute(
            "SELECT COUNT(*) FROM plug WHERE room_id = ? AND show_on_dashboard = 1", (room_id,)
        ).fetchone()
        return 1 if shown_count < 3 else 0
    for enclosure_id in enclosure_ids:
        (shown_count,) = conn.execute(
            """SELECT COUNT(*) FROM plug p JOIN plug_enclosure pe ON pe.plug_id = p.id
               WHERE pe.enclosure_id = ? AND p.show_on_dashboard = 1""",
            (enclosure_id,),
        ).fetchone()
        if shown_count >= 3:
            return 0
    return 1


def delete_plug(plug_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM plug WHERE id = ?", (plug_id,))


def set_plug_dashboard_visibility(plug_id: int, show_on_dashboard: bool) -> None:
    """Toggled from a checkbox on the Plug's parent (Enclosure or Room) Admin page — see
    CONTEXT.md: Plug. Independent of update_plug() for the same reason as
    set_animal_dashboard_visibility()/set_sensor_dashboard_visibility(): a one-field,
    checkbox-driven action, not part of the full edit form."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE plug SET show_on_dashboard = ? WHERE id = ?",
            (1 if show_on_dashboard else 0, plug_id),
        )


def get_plug(plug_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM plug WHERE id = ?", (plug_id,)).fetchone()
        if row is None:
            return None
        plug = _decode_plug(dict(row))
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
        plug["last_command"] = _command_status(conn, plug)
        # Data Capture (see CONTEXT.md, ADR 0009) only ever exists for a Smart Plug.
        plug["latest_reading"] = _latest_plug_reading(conn, plug_id) if plug["tracking_mode"] == "smart" else None
        return plug


def _latest_plug_reading(conn, plug_id: int) -> dict | None:
    """Data Capture's most recently stored value for this Plug (see CONTEXT.md: Data Capture) — the
    first place web/ ever reads plug_reading; every other admin view shows only the on/off Command
    state, never telemetry. None if nothing's ever been captured — a Smart Plug that's never
    reported a non-empty telemetry Plugin Event (see plugins/tuya_lan/plugin.py's
    _extract_telemetry — still empty for every device model in this collection as of ADR 0009's
    landing), or one whose Auto-Update has always been paused."""
    row = conn.execute(
        "SELECT watts, volts, amps, countdown_seconds, recorded_at FROM plug_reading "
        "WHERE plug_id = ? ORDER BY recorded_at DESC LIMIT 1", (plug_id,)
    ).fetchone()
    return dict(row) if row else None


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


_TUYA_POLL_INTERVAL_SECONDS = 5  # matches plugins/tuya_lan/plugin.py's own POLL_INTERVAL_SECONDS —
                                  # duplicated rather than imported, same isolation reasoning as
                                  # web/outbox.py's module docstring; see ADR 0014


def _command_timed_out(requested_at: str, ingest_scan_interval_seconds: int) -> bool:
    """True once roughly 2x the Ingest scan interval plus the Plugin's own poll cadence has passed
    since a Command was requested with nothing confirming it — see ADR 0014 (~15-20s with current
    defaults). Comfortably longer than a normal round trip, short enough not to leave the UI saying
    "confirming..." forever when the device was actually unreachable."""
    requested = datetime.strptime(requested_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    timeout = 2 * ingest_scan_interval_seconds + _TUYA_POLL_INTERVAL_SECONDS
    return (datetime.now(timezone.utc) - requested).total_seconds() > timeout


def _current_plug_status(conn, plug: dict) -> dict:
    """What's actually happening with this Plug right now, for the Plugs table's Status column —
    distinct from last_command (what Core last *told* it to do, which a Controller Kind or
    Schedule may have long since overridden) and from the Schedules section's target/detected
    pills. {"unreachable": bool, "is_on": bool | None} — is_on is None when there's nothing to
    report yet (a Smart Plug that's never polled, or a Manual Plug never Commanded).

    Smart Plug: the latest observed relay state (plug_state_transition), plus whether it's
    currently flagged Unreachable — reusing the exact state ingest/alerts.py's
    evaluate_plug_unreachable() already maintains (see CONTEXT.md: Unreachable), not a fresh
    live poll.
    Manual Plug: no device to observe, so its Command log entry IS the state (see CONTEXT.md:
    Command) — never Unreachable, since there's nothing to lose contact with.
    """
    if plug["tracking_mode"] != "smart":
        last = plug.get("last_command") or _command_status(conn, plug)
        return {"unreachable": False, "is_on": last["is_on"] if last else None}

    alert = conn.execute(
        "SELECT state FROM plug_alert_state WHERE plug_id = ? AND condition_kind = 'unreachable'",
        (plug["id"],),
    ).fetchone()
    unreachable = alert is not None and alert["state"] == "alerting"

    transition = conn.execute(
        "SELECT is_on FROM plug_state_transition WHERE plug_id = ? ORDER BY recorded_at DESC LIMIT 1",
        (plug["id"],),
    ).fetchone()
    return {"unreachable": unreachable, "is_on": bool(transition["is_on"]) if transition else None}


def _command_status(conn, plug: dict) -> dict | None:
    """What to show next to a Plug's on/off control — see CONTEXT.md: Command, Interruption;
    ADR 0014. None if no Command has ever been sent for this Plug.

    A Manual Plug's Command IS the fact — no relay, no round trip — so it's always "confirmed".
    A Smart Plug's Command is "confirmed" once a poll has happened since it was requested
    (plug_last_seen advanced past requested_at) and the most recently observed relay state matches
    what was commanded; "failed" once _command_timed_out with no such poll; otherwise "confirming"."""
    last = conn.execute(
        "SELECT * FROM plug_command_log WHERE plug_id = ? ORDER BY requested_at DESC, id DESC LIMIT 1",
        (plug["id"],),
    ).fetchone()
    if last is None:
        return None
    last = dict(last)

    if plug["tracking_mode"] != "smart":
        return {**last, "status": "confirmed"}

    seen = conn.execute(
        "SELECT last_seen_at FROM plug_last_seen WHERE plug_id = ?", (plug["id"],)
    ).fetchone()
    current = conn.execute(
        "SELECT is_on FROM plug_state_transition WHERE plug_id = ? ORDER BY recorded_at DESC LIMIT 1",
        (plug["id"],),
    ).fetchone()
    confirmed = (
        seen is not None and seen["last_seen_at"] >= last["requested_at"]
        and current is not None and bool(current["is_on"]) == bool(last["is_on"])
    )
    if confirmed:
        status = "confirmed"
    else:
        scan_interval = conn.execute(
            "SELECT ingest_scan_interval_seconds FROM app_setting WHERE id = 1"
        ).fetchone()["ingest_scan_interval_seconds"]
        status = "failed" if _command_timed_out(last["requested_at"], scan_interval) else "confirming"
    return {**last, "status": status}


def list_plugs() -> list[dict]:
    """For the top-level Plugs admin list — each row's parent_label describes where it lives,
    whichever side of the Room/Enclosure-set split it's on. See CONTEXT.md: Plug."""
    with get_connection() as conn:
        plugs = [_decode_plug(dict(r)) for r in conn.execute("SELECT * FROM plug ORDER BY label")]
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
            plug["last_command"] = _command_status(conn, plug)
        return plugs


def update_plug(plug_id: int, label: str, purpose: str, tracking_mode: str, switch_dps_key: str,
                 tuya_device_id: str | None, tuya_local_key: str | None, tuya_ip_address: str | None,
                 target_on_time: str | None = None, target_off_time: str | None = None,
                 room_id: int | None = None, enclosure_ids: list[int] | None = None,
                 controller_kind: str = "none", target_temp_c: float | None = None,
                 target_humidity_pct: float | None = None, auto_update_enabled: bool = True,
                 always_on: bool = False) -> None:
    """auto_update_enabled: see CONTEXT.md: Auto-Update. Pausing has no effect on a Manual Plug
    (there's no background collection to pause), but the column and toggle stay uniform regardless."""
    enclosure_ids = enclosure_ids or []
    if controller_kind != "none":
        always_on = False  # see create_plug's identical normalization, and CONTEXT.md: Always On
    _validate_plug(tracking_mode, tuya_device_id, tuya_local_key, target_on_time, target_off_time,
                   room_id, enclosure_ids, controller_kind, target_temp_c, target_humidity_pct, always_on)
    if controller_kind != "none" or always_on:
        target_on_time = target_off_time = None
    if controller_kind != "thermostat":
        target_temp_c = None
    if controller_kind != "hydrostat":
        target_humidity_pct = None
    plugin, external_id, plugin_config = _encode_plug_identity(
        tracking_mode, tuya_device_id, tuya_local_key, tuya_ip_address, switch_dps_key
    )
    with get_connection() as conn:
        _check_external_id_available(conn, plugin, external_id, exclude_plug_id=plug_id)
        conn.execute(
            """UPDATE plug SET room_id = ?, label = ?, purpose = ?, tracking_mode = ?,
                                plugin = ?, external_id = ?, plugin_config = ?,
                                target_on_time = ?, target_off_time = ?, always_on = ?, auto_update_enabled = ?,
                                controller_kind = ?, target_temp_c = ?, target_humidity_pct = ? WHERE id = ?""",
            (room_id, label, purpose, tracking_mode, plugin, external_id, plugin_config,
             target_on_time or None, target_off_time or None, int(always_on),
             int(auto_update_enabled), controller_kind, target_temp_c, target_humidity_pct,
             plug_id),
        )
        conn.execute("DELETE FROM plug_enclosure WHERE plug_id = ?", (plug_id,))
        for eid in enclosure_ids:
            conn.execute("INSERT INTO plug_enclosure (plug_id, enclosure_id) VALUES (?, ?)", (plug_id, eid))


def list_plug_groups() -> list[dict]:
    """For the top-level Plug Groups admin list — see CONTEXT.md: Plug Group; ADR 0017. Each
    group's member Plugs come back decoded the same way list_plugs() decodes standalone ones, split
    into smart_members/manual_members so the template can render the All On/All Off action against
    only the Smart ones (see CONTEXT.md: All On / All Off — Always-On Outlets never included)."""
    with get_connection() as conn:
        groups = [dict(r) for r in conn.execute("SELECT * FROM plug_group ORDER BY name")]
        room_names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM room")}
        for group in groups:
            if group["room_id"]:
                group["parent_label"] = f"Room: {room_names.get(group['room_id'], '?')}"
            else:
                names = [r["name"] for r in conn.execute(
                    """SELECT e.name FROM enclosure e JOIN plug_group_enclosure pge ON pge.enclosure_id = e.id
                       WHERE pge.plug_group_id = ? ORDER BY e.name""",
                    (group["id"],),
                )]
                group["parent_label"] = ", ".join(names) if names else "—"
            members = [_decode_plug(dict(r)) for r in conn.execute(
                "SELECT * FROM plug WHERE plug_group_id = ? ORDER BY label", (group["id"],)
            )]
            for member in members:
                member["last_command"] = _command_status(conn, member)
            group["members"] = members
            group["smart_members"] = [m for m in members if m["tracking_mode"] == "smart"]
            group["manual_members"] = [m for m in members if m["tracking_mode"] != "smart"]
        return groups


def get_plug_group(plug_group_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM plug_group WHERE id = ?", (plug_group_id,)).fetchone()
        if row is None:
            return None
        group = dict(row)
        group["enclosure_ids"] = [r["enclosure_id"] for r in conn.execute(
            "SELECT enclosure_id FROM plug_group_enclosure WHERE plug_group_id = ?", (plug_group_id,)
        )]
        members = [_decode_plug(dict(r)) for r in conn.execute(
            "SELECT * FROM plug WHERE plug_group_id = ? ORDER BY label", (plug_group_id,)
        )]
        for member in members:
            member["last_command"] = _command_status(conn, member)
        group["members"] = members
        group["smart_members"] = [m for m in members if m["tracking_mode"] == "smart"]
        group["manual_members"] = [m for m in members if m["tracking_mode"] != "smart"]
        return group


def create_plug_group(name: str, room_id: int | None, enclosure_ids: list[int] | None,
                       tuya_device_id: str | None, tuya_local_key: str | None, tuya_ip_address: str | None,
                       smart_members: list[dict], manual_members: list[dict]) -> int:
    """Creates a Plug Group and all of its member Plugs in one shot, from the (currently only)
    Plug Group Template: relay-controlled + USB outlets (smart_members) plus hardwired Always-On
    Outlets (manual_members) — see CONTEXT.md: Plug Group, Plug Group Template, Always-On Outlet;
    ADR 0017.

    smart_members: [{"label", "purpose", "switch_dps_key"}, ...] — share one physical device's
    tuya_device_id/local_key/ip_address, differing only by switch_dps_key (see CONTEXT.md: External
    ID — a multi-outlet strip's outlets already share one device_id today, this just creates all of
    them at once instead of one Add Plug trip per outlet).
    manual_members: [{"label", "purpose"}, ...] — created as ordinary Manual Plugs with
    always_on=True and no device credentials (see CONTEXT.md: Always-On Outlet — reuses the
    existing Plug/Manual/Always On model as-is).

    All members inherit the Group's own room_id/enclosure_ids — there is no per-member override
    (see CONTEXT.md: Plug Group)."""
    enclosure_ids = enclosure_ids or []
    if not name.strip():
        raise ValueError("A Plug Group needs a name.")
    if bool(room_id) == bool(enclosure_ids):
        raise ValueError("A Plug Group needs exactly one parent — pick a Room, or one or more Enclosures, not both or neither.")
    if not smart_members and not manual_members:
        raise ValueError("A Plug Group needs at least one member Plug.")
    if smart_members and (not tuya_device_id or not tuya_local_key):
        raise ValueError("A Plug Group's Smart outlets need a Tuya device_id and local_key.")

    # Check every Smart member's (plugin, external_id) against what's already registered *before*
    # inserting anything — a DPS key already claimed by an existing standalone Plug (e.g. one
    # outlet registered before anyone knew it was part of a bigger strip, same situation
    # set_plug_group() exists for) would otherwise fail on plug's UNIQUE(plugin, external_id)
    # constraint partway through the loop below, leaving the Group and any already-created members
    # committed but incomplete.
    with get_connection() as conn:
        for member in smart_members:
            external_id = tuya_identity.encode_external_id(tuya_device_id, member.get("switch_dps_key", "1"))
            existing = conn.execute(
                "SELECT id, label FROM plug WHERE plugin = ? AND external_id = ?",
                (tuya_identity.PLUGIN_NAME, external_id),
            ).fetchone()
            if existing is not None:
                raise ValueError(
                    f"DPS key {member.get('switch_dps_key', '1')!r} is already registered as Plug "
                    f"{existing['label']!r} (id {existing['id']}) — remove it from this Group's form, "
                    f"then attach that existing Plug to the Group afterward from its own Edit Plug page."
                )

    with get_connection() as conn:
        cur = conn.execute("INSERT INTO plug_group (name, room_id) VALUES (?, ?)", (name.strip(), room_id))
        group_id = cur.lastrowid
        for eid in enclosure_ids:
            conn.execute(
                "INSERT INTO plug_group_enclosure (plug_group_id, enclosure_id) VALUES (?, ?)",
                (group_id, eid),
            )

    for member in smart_members:
        create_plug(
            member["label"], member["purpose"], "smart", tuya_device_id, tuya_local_key, tuya_ip_address,
            member.get("switch_dps_key", "1"), room_id=room_id, enclosure_ids=enclosure_ids,
            plug_group_id=group_id,
        )
    for member in manual_members:
        create_plug(
            member["label"], member["purpose"], "manual", None, None, None,
            room_id=room_id, enclosure_ids=enclosure_ids, always_on=True, plug_group_id=group_id,
        )
    return group_id


def delete_plug_group(plug_group_id: int) -> None:
    """Ungroups member Plugs rather than deleting them — plug.plug_group_id is ON DELETE SET NULL
    (see db/schema.sql, CONTEXT.md: Plug Group — same "never destroy device history over an
    organizational action" precedent as Enclosure deletion falling back to Unassigned). No explicit
    UPDATE needed here; the FK's ON DELETE SET NULL does it as part of this same DELETE."""
    with get_connection() as conn:
        conn.execute("DELETE FROM plug_group WHERE id = ?", (plug_group_id,))


def add_plug_to_group(plug_group_id: int, label: str, purpose: str, tracking_mode: str,
                       switch_dps_key: str = "1") -> int:
    """Adds a brand-new member Plug directly into an existing Plug Group — see CONTEXT.md: Plug
    Group; ADR 0017. The one-step counterpart to create_plug() + set_plug_group(): inherits the
    Group's own Room/Enclosure assignment, and for a Smart outlet, the shared Tuya
    device_id/local_key/ip_address from whichever existing Smart member already has them (a
    Group's outlets are, by definition, one physical device sharing one device_id — see CONTEXT.md:
    External ID) — the caller only ever supplies the new outlet's own switch_dps_key.

    A Manual outlet added this way is always created as an Always-On Outlet (see CONTEXT.md) —
    there's no other kind of Manual Plug Group member in this model, so always_on is forced True
    rather than exposed as a separate choice here."""
    with get_connection() as conn:
        group = conn.execute("SELECT room_id FROM plug_group WHERE id = ?", (plug_group_id,)).fetchone()
        if group is None:
            raise ValueError(f"No such Plug Group: {plug_group_id}")
        room_id = group["room_id"]
        enclosure_ids = [r["enclosure_id"] for r in conn.execute(
            "SELECT enclosure_id FROM plug_group_enclosure WHERE plug_group_id = ?", (plug_group_id,)
        )]
        tuya_device_id = tuya_local_key = tuya_ip_address = None
        if tracking_mode == "smart":
            existing_smart = conn.execute(
                "SELECT external_id, plugin_config FROM plug WHERE plug_group_id = ? AND tracking_mode = 'smart' LIMIT 1",
                (plug_group_id,),
            ).fetchone()
            if existing_smart is None:
                raise ValueError(
                    "This Plug Group has no Smart outlet yet to inherit Tuya credentials from — add "
                    "its first Smart outlet the ordinary way (device_id/local_key filled in), then "
                    "attach it to the Group from its own Edit Plug page."
                )
            tuya_device_id, _ = tuya_identity.decode_external_id(existing_smart["external_id"])
            config = tuya_identity.unpack_config(existing_smart["plugin_config"])
            tuya_local_key = config["local_key"]
            tuya_ip_address = config["ip_address"]

    return create_plug(
        label, purpose, tracking_mode, tuya_device_id, tuya_local_key, tuya_ip_address,
        switch_dps_key, room_id=room_id, enclosure_ids=enclosure_ids,
        always_on=(tracking_mode != "smart"), plug_group_id=plug_group_id,
    )


def set_plug_group(plug_id: int, plug_group_id: int | None) -> None:
    """Attaches an existing standalone Plug to a Plug Group, or detaches it (plug_group_id=None) —
    see CONTEXT.md: Plug Group; ADR 0017. Covers the case create_plug_group() doesn't: a Plug
    registered before its Group existed (e.g. the first outlet found on a multi-outlet device,
    added the ordinary one-at-a-time way before anyone knew it was part of a bigger strip).

    Attaching copies the Group's own room_id/enclosure_ids onto the Plug — the Group is the source
    of truth for a member's parent, same as every member created directly by create_plug_group()
    already gets (see CONTEXT.md: Plug Group — no per-member override). Detaching leaves the Plug's
    current parent alone; only its Group membership clears."""
    with get_connection() as conn:
        if plug_group_id is None:
            conn.execute("UPDATE plug SET plug_group_id = NULL WHERE id = ?", (plug_id,))
            return
        group = conn.execute("SELECT room_id FROM plug_group WHERE id = ?", (plug_group_id,)).fetchone()
        if group is None:
            raise ValueError(f"No such Plug Group: {plug_group_id}")
        enclosure_ids = [r["enclosure_id"] for r in conn.execute(
            "SELECT enclosure_id FROM plug_group_enclosure WHERE plug_group_id = ?", (plug_group_id,)
        )]
        conn.execute(
            "UPDATE plug SET plug_group_id = ?, room_id = ? WHERE id = ?",
            (plug_group_id, group["room_id"], plug_id),
        )
        conn.execute("DELETE FROM plug_enclosure WHERE plug_id = ?", (plug_id,))
        for eid in enclosure_ids:
            conn.execute("INSERT INTO plug_enclosure (plug_id, enclosure_id) VALUES (?, ?)", (plug_id, eid))


def send_plug_group_command(plug_group_id: int, is_on: bool) -> list[dict]:
    """The Plug Group's All On/All Off action (see CONTEXT.md: All On / All Off; ADR 0017) — fans
    out an ordinary send_plug_command() to every Smart member (the relay-controlled and USB
    outlets), mirroring the strip's physical master button. Always-On Outlets are never included —
    they have no relay to command. Not a new Outbox/Plugin-level concept, just N existing Commands."""
    with get_connection() as conn:
        member_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM plug WHERE plug_group_id = ? AND tracking_mode = 'smart'", (plug_group_id,)
        )]
    return [send_plug_command(plug_id, is_on) for plug_id in member_ids]


def send_plug_command(plug_id: int, is_on: bool, note: str | None = None) -> dict:
    """Sends a Command to one Plug, Smart or Manual alike — see CONTEXT.md: Command, Interruption;
    ADR 0014. Always logs one plug_command_log row; a Smart Plug additionally gets an Outbox file
    dropped for its own Plugin to execute on its next poll (a Manual Plug's row IS the whole
    action — there's no hardware behind it to actually command).

    A Command counts as an Interruption iff the Plug has a determined setting at the moment it's
    sent — a Controller Kind other than 'none', or a Target Schedule set (checking target_on_time
    alone is enough: both-or-neither is already enforced by _validate_plug). Only an Interruption's
    `note` is meaningful; a plain toggle's is ignored even if one was passed.

    Sending a Command to a Smart Plug whose Auto-Update is currently paused resumes Auto-Update as
    a side effect (see CONTEXT.md: Auto-Update) — otherwise the confirming plug_state event would
    be silently dropped by Ingest's own auto_update_enabled = 1 gate."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM plug WHERE id = ?", (plug_id,)).fetchone()
        if row is None:
            raise ValueError(f"No such Plug: {plug_id}")
        plug = dict(row)
        is_interruption = plug["controller_kind"] != "none" or bool(plug["target_on_time"])
        cur = conn.execute(
            "INSERT INTO plug_command_log (plug_id, is_on, is_interruption, note) VALUES (?, ?, ?, ?)",
            (plug_id, int(is_on), int(is_interruption), note if is_interruption else None),
        )
        log_id = cur.lastrowid
        if plug["tracking_mode"] == "smart" and not plug["auto_update_enabled"]:
            conn.execute("UPDATE plug SET auto_update_enabled = 1 WHERE id = ?", (plug_id,))
    # Outbox write happens after the connection above closes — same reasoning as
    # ingest/ingest.py::_apply_event calling alerts.* only once its own connection is closed
    # (this app's non-WAL journal mode means a same-process connection can't stay open while
    # another one writes without risking "database is locked").
    if plug["tracking_mode"] == "smart":
        write_command(plug["plugin"], plug["external_id"], is_on, request_id=log_id)
    return {"id": log_id, "is_interruption": is_interruption}


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
        room["sensors"] = [_decode_sensor(dict(r)) for r in conn.execute("SELECT * FROM sensor WHERE room_id = ? ORDER BY label", (room_id,))]
        for sensor in room["sensors"]:
            # SELECT * — see get_enclosure()'s identical comment above; a Room Sensor only ever
            # tracks temp/humidity in practice (create_room_sensor() never writes the others), but
            # reading this generically keeps the two Admin pages' fetch logic uniform.
            latest = conn.execute(
                "SELECT * FROM sensor_reading WHERE sensor_id = ? ORDER BY recorded_at DESC LIMIT 1",
                (sensor["id"],),
            ).fetchone()
            sensor["latest_reading"] = dict(latest) if latest else None
        room["plugs"] = [_decode_plug(dict(r)) for r in conn.execute("SELECT * FROM plug WHERE room_id = ? ORDER BY label", (room_id,))]
        for plug in room["plugs"]:
            # Detected Schedule (see CONTEXT.md, ADR 0012) only means anything for a Smart,
            # non-Controller-Kind Plug.
            detected = _detect_schedule(conn, plug["id"]) if (
                plug["tracking_mode"] == "smart" and plug["controller_kind"] == "none"
            ) else {"on_time": None, "off_time": None}
            plug["detected_on_time"] = detected["on_time"]
            plug["detected_off_time"] = detected["off_time"]
            plug["last_command"] = _command_status(conn, plug)
            plug["current_status"] = _current_plug_status(conn, plug)
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
    ingest/alerts.py, which just logs to the console instead of sending in that case."""
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
