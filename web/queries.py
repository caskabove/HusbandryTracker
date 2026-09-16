"""Read-only DB access for the dashboard. Opens a short-lived connection per call (same pattern
as the collectors) rather than holding one open — deliberately, since this SQLite file is also
being written by a host-process collector; short-lived connections keep cross-process WAL
behavior simple instead of holding a long-lived handle open across a bind-mounted volume.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.db import get_connection

CARE_EVENT_KINDS = ["feeding", "watering", "spot_clean", "deep_clean"]


def days_since(occurred_at: str | None) -> int | None:
    if occurred_at is None:
        return None
    then = datetime.fromisoformat(occurred_at)
    return (datetime.now() - then).days


def _normalize_datetime_local(value: str | None) -> str | None:
    """Browser <input type="datetime-local"> submits "YYYY-MM-DDTHH:MM" — normalize to the
    "YYYY-MM-DD HH:MM:SS" shape every other timestamp in the DB uses, so backdated rows sort/compare
    consistently with auto-generated ones. Returns None for a blank value (meaning: log as now)."""
    if not value:
        return None
    return value.replace("T", " ") + ":00"


def _latest_reading(conn, sensor_id: int) -> dict | None:
    # SELECT * rather than naming columns: a Reading can carry any of the Target Range metrics
    # (see CONTEXT.md: Reading; schemas/enclosure_types.py's TARGET_RANGE_METRICS), and the
    # Dashboard's reading_row() macro looks up whichever ones are populated by column name.
    row = conn.execute(
        "SELECT * FROM sensor_reading WHERE sensor_id = ? ORDER BY recorded_at DESC LIMIT 1",
        (sensor_id,),
    ).fetchone()
    return dict(row) if row else None


def _current_plug_status(conn, plug: dict) -> dict:
    """What's actually happening with a Plug right now, for its Dashboard status pill — mirrors
    web/admin_queries.py's own _current_plug_status() (see its docstring for the full reasoning),
    kept as a separate, leaner read here since the Dashboard only ever needs on/off + Unreachable,
    never the full Command-confirmation bookkeeping the Admin pages also show. {"unreachable":
    bool, "is_on": bool | None} — is_on is None when there's nothing to report yet."""
    if plug["tracking_mode"] != "smart":
        last = conn.execute(
            "SELECT is_on FROM plug_command_log WHERE plug_id = ? ORDER BY requested_at DESC, id DESC LIMIT 1",
            (plug["id"],),
        ).fetchone()
        return {"unreachable": False, "is_on": bool(last["is_on"]) if last else None}

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


def get_dashboard_data() -> dict:
    """Returns {"rooms": [...], "ungrouped": [...]} — the dashboard groups Enclosure panels by
    Room (see CONTEXT.md: Room), with Room-less Enclosures falling into "ungrouped"."""
    with get_connection() as conn:
        enclosures = [dict(row) for row in conn.execute("SELECT * FROM enclosure ORDER BY name")]

        for enclosure in enclosures:
            eid = enclosure["id"]

            # show_on_dashboard (see CONTEXT.md: Animal) is opt-in per Animal, toggled on the
            # Enclosure's own Admin page — that page still lists every Animal regardless (see
            # web/admin_queries.py's get_enclosure()), only the Dashboard panel filters. animal_count
            # (unfiltered) lets the template tell "nothing registered" apart from "registered but
            # none picked to show here".
            (enclosure["animal_count"],) = conn.execute(
                "SELECT COUNT(*) FROM animal WHERE enclosure_id = ?", (eid,)
            ).fetchone()
            enclosure["animals"] = [
                dict(row) for row in conn.execute(
                    "SELECT * FROM animal WHERE enclosure_id = ? AND show_on_dashboard = 1 ORDER BY name", (eid,)
                )
            ]

            # sensor_count is the *unfiltered* count — used below to decide Fallback Sensor
            # eligibility (must reflect whether this Enclosure truly has no Sensor of its own,
            # regardless of show_on_dashboard) and by the template to tell "no sensors registered"
            # apart from "registered but none picked to show here" (see CONTEXT.md: Sensor).
            sensors = [dict(row) for row in conn.execute("SELECT * FROM sensor WHERE enclosure_id = ?", (eid,))]
            for sensor in sensors:
                sensor["latest_reading"] = _latest_reading(conn, sensor["id"])
            enclosure["sensor_count"] = len(sensors)
            enclosure["sensors"] = [s for s in sensors if s["show_on_dashboard"]]

            # Fallback Sensor (see CONTEXT.md) — only relevant when this Enclosure has none of its
            # own; its Reading is never colored (no Target Range comparison), see ADR 0004.
            enclosure["fallback_sensor"] = None
            enclosure["fallback_reading"] = None
            if not sensors and enclosure["fallback_sensor_id"]:
                fb_row = conn.execute("SELECT * FROM sensor WHERE id = ?", (enclosure["fallback_sensor_id"],)).fetchone()
                if fb_row:
                    enclosure["fallback_sensor"] = dict(fb_row)
                    enclosure["fallback_reading"] = _latest_reading(conn, fb_row["id"])

            # Schedules aren't rendered on the dashboard (glance-only — see web/main.py's module
            # docstring); that stays Admin-only, fetched there via web/admin_queries.py. A Plug's
            # current status (on/off, or Unreachable) is glance-appropriate though, same as a
            # Sensor's Reading — opt-in per Plug (show_on_dashboard), same pattern as Animal/Sensor.
            plugs = [dict(row) for row in conn.execute(
                """SELECT p.* FROM plug p JOIN plug_enclosure pe ON pe.plug_id = p.id
                   WHERE pe.enclosure_id = ? ORDER BY p.label""",
                (eid,),
            )]
            for plug in plugs:
                plug["current_status"] = _current_plug_status(conn, plug)
            enclosure["plug_count"] = len(plugs)
            enclosure["plugs"] = [p for p in plugs if p["show_on_dashboard"]]

            care = {}
            for kind in CARE_EVENT_KINDS:
                latest = conn.execute(
                    """SELECT occurred_at FROM care_event
                       WHERE enclosure_id = ? AND kind = ? ORDER BY occurred_at DESC LIMIT 1""",
                    (eid, kind),
                ).fetchone()
                occurred_at = latest["occurred_at"] if latest else None
                care[kind] = {"occurred_at": occurred_at, "days_since": days_since(occurred_at)}
            enclosure["care"] = care

        rooms = [dict(row) for row in conn.execute("SELECT * FROM room ORDER BY name")]
        for room in rooms:
            room_sensors = [dict(row) for row in conn.execute("SELECT * FROM sensor WHERE room_id = ?", (room["id"],))]
            for sensor in room_sensors:
                sensor["latest_reading"] = _latest_reading(conn, sensor["id"])
            room["sensor_count"] = len(room_sensors)  # unfiltered — see the Enclosure loop above
            room["sensors"] = [s for s in room_sensors if s["show_on_dashboard"]]

            room_plugs = [dict(row) for row in conn.execute("SELECT * FROM plug WHERE room_id = ? ORDER BY label", (room["id"],))]
            for plug in room_plugs:
                plug["current_status"] = _current_plug_status(conn, plug)
            room["plug_count"] = len(room_plugs)
            room["plugs"] = [p for p in room_plugs if p["show_on_dashboard"]]

            room["enclosures"] = [e for e in enclosures if e["room_id"] == room["id"]]

        ungrouped = [e for e in enclosures if e["room_id"] is None]

    return {"rooms": rooms, "ungrouped": ungrouped}


def log_care_event(enclosure_id: int, kind: str, note: str | None = None, occurred_at: str | None = None,
                    animal_id: int | None = None) -> None:
    """occurred_at lets a Care Event be backdated to when it actually happened instead of always
    being "now" — see CONTEXT.md: Care Event. Pass None (the default) to log it as now.

    animal_id is Spot-feed only (see CONTEXT.md: Spot-feed) — scopes a Feeding to one Animal in the
    Enclosure instead of the whole Enclosure. Only valid alongside kind == "feeding"; a non-None
    value for any other kind is a friendly ValueError rather than a silently-ignored form field."""
    if kind not in CARE_EVENT_KINDS:
        raise ValueError(f"Unknown care event kind: {kind!r}")
    if animal_id is not None and kind != "feeding":
        raise ValueError("Spot-feed (picking one Animal) only applies to Feeding.")
    occurred_at = _normalize_datetime_local(occurred_at)
    with get_connection() as conn:
        if occurred_at:
            conn.execute(
                "INSERT INTO care_event (enclosure_id, animal_id, kind, occurred_at, note) VALUES (?, ?, ?, ?, ?)",
                (enclosure_id, animal_id, kind, occurred_at, note),
            )
        else:
            conn.execute(
                "INSERT INTO care_event (enclosure_id, animal_id, kind, note) VALUES (?, ?, ?, ?)",
                (enclosure_id, animal_id, kind, note),
            )


def log_reading(sensor_id: int, values: dict[str, float | None], recorded_at: str | None = None) -> None:
    """Hand-logs a Reading for a Manual Sensor (see CONTEXT.md: Reading) — reuses the same
    sensor_reading table a Smart Sensor's auto-collected Readings go into, so the dashboard's latest-
    reading and Target Range color-coding work unchanged either way. recorded_at backdates it to when
    the measurement was actually taken; pass None (the default) to log it as now.

    values maps a sensor_reading column name (e.g. "temperature_c", "ph", "ammonia_ppm" — see
    schemas/enclosure_types.py's TARGET_RANGE_METRICS.reading_column, the fixed set of names this
    can ever be) to the value to log, already in storage units — web/main.py's create_reading()
    does the one unit conversion needed (Fahrenheit input -> Celsius) before calling this, same as
    before this was generalized past temperature/humidity. Only non-None entries are written; a
    dict with nothing set is a friendly error rather than a Reading row with every column NULL."""
    provided = {column: value for column, value in values.items() if value is not None}
    if not provided:
        raise ValueError("Enter at least one value to log a Reading.")
    recorded_at = _normalize_datetime_local(recorded_at)
    columns = list(provided.keys())
    column_list = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)
    with get_connection() as conn:
        if recorded_at:
            conn.execute(
                f"INSERT INTO sensor_reading (sensor_id, recorded_at, {column_list}) VALUES (?, ?, {placeholders})",
                (sensor_id, recorded_at, *provided.values()),
            )
        else:
            conn.execute(
                f"INSERT INTO sensor_reading (sensor_id, {column_list}) VALUES (?, {placeholders})",
                (sensor_id, *provided.values()),
            )


def assign_enclosure_room(enclosure_id: int, room_id: int | None) -> None:
    """Drag-and-drop Room reassignment from the dashboard (see CONTEXT.md: Room) — room_id None
    moves the Enclosure to Ungrouped. Clears fallback_sensor_id (see CONTEXT.md: Fallback Sensor)
    whenever room_id actually changes: a Fallback Sensor is scoped to a specific Room's own
    Sensors, so whatever was picked (if anything) is stale the instant the Room changes, or goes
    away entirely. A no-op drop back onto the Enclosure's current Room leaves it untouched instead
    of pointlessly clearing a Fallback Sensor selection that's still perfectly valid."""
    with get_connection() as conn:
        current = conn.execute("SELECT room_id FROM enclosure WHERE id = ?", (enclosure_id,)).fetchone()
        if current is None or current["room_id"] == room_id:
            return
        conn.execute(
            "UPDATE enclosure SET room_id = ?, fallback_sensor_id = NULL WHERE id = ?",
            (room_id, enclosure_id),
        )
