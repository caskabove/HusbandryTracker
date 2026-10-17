"""Read-only DB access for the dashboard. Opens a short-lived connection per call (same pattern
as the collectors) rather than holding one open — deliberately, since this SQLite file is also
being written by a host-process collector; short-lived connections keep cross-process WAL
behavior simple instead of holding a long-lived handle open across a bind-mounted volume.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.db import get_connection
from schemas import enclosure_types as et

CARE_EVENT_KINDS = ["feeding", "watering", "spot_clean", "deep_clean"]

# animal_log.condition's allowed values — see CONTEXT.md: Animal Log. Must match the CHECK
# constraint in db/schema.sql.
ANIMAL_CONDITIONS = ["poor", "ok", "good", "really_good"]
ANIMAL_CONDITION_LABELS = {
    "poor": "Poor", "ok": "OK", "good": "Good", "really_good": "Really Good",
}

# Morning/Afternoon/Night anchor hours — see CONTEXT.md: Period Slot; ADR 0026. Shared by both this
# concept's uses: View Data's cell editors (entry — see web/view_data_queries.py) and Graphs' Care
# Event marker snapping (display — see web/graphs_queries.py's _PERIOD_SLOT_ANCHORS), so the three
# hours only ever live in one place.
PERIOD_SLOTS: tuple[tuple[str, int], ...] = (("morning", 8), ("afternoon", 14), ("night", 20))
PERIOD_SLOT_HHMM: dict[str, str] = {name: f"{hour:02d}:00" for name, hour in PERIOD_SLOTS}


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


def _latest_reading(conn, sensor: dict) -> dict | None:
    """The Sensor's current Reading — each metric's own newest value, not the newest row's. A hand-
    logged Reading only fills in the metrics entered in it, so a later temperature-only log used to
    blank out this Sensor's SG/salinity/etc. pills until the next SG-bearing log. recorded_at stays
    the newest row's time (the "as of" the page shows).

    Only metrics this Sensor can actually show get their own lookup: temperature/humidity (the
    dashboard always checks those) plus any metric with a Target Range set. Looking up every column
    would scan a Sensor's entire history for each metric it never reports. Every metric column is
    still present in the returned dict (None where skipped), since the dashboard's reading_row()
    reads them by name."""
    newest = conn.execute(
        "SELECT * FROM sensor_reading WHERE sensor_id = ? ORDER BY recorded_at DESC LIMIT 1",
        (sensor["id"],),
    ).fetchone()
    if newest is None:
        return None
    reading = dict(newest)
    for metric in et.TARGET_RANGE_METRICS:
        column = metric.reading_column
        tracked = sensor.get(metric.min_column) is not None or sensor.get(metric.max_column) is not None
        if not (tracked or column in ("temperature_c", "humidity_pct")):
            continue
        row = conn.execute(
            f"SELECT {column} FROM sensor_reading WHERE sensor_id = ? AND {column} IS NOT NULL "
            f"ORDER BY recorded_at DESC LIMIT 1",
            (sensor["id"],),
        ).fetchone()
        reading[column] = row[column] if row else None
    return reading


_SPARKLINE_DAYS = 7
# Trailing buckets averaged into each smoothed point (see CONTEXT.md: Sparkline; ADR 0024) — a
# Smart Sensor's daily min/avg/max buckets get this before drawing, so a Sparkline reads as a trend
# rather than a day-to-day zigzag. Index-based, not calendar-based: a bucket only exists for a day
# that actually had a Reading, so this is "the last 3 buckets", not "the last 3 calendar days".
_SPARKLINE_SMOOTHING_WINDOW = 3


def _sparkline_c_to_f(celsius: float | None) -> float | None:
    return None if celsius is None else celsius * 9 / 5 + 32


def _sparkline_epoch_ms(ts: str, fmt: str = "%Y-%m-%d %H:%M:%S") -> int:
    return int(datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc).timestamp() * 1000)


def _sparkline_smoothed(points: list[list]) -> list[list]:
    """A trailing _SPARKLINE_SMOOTHING_WINDOW-bucket moving average over every numeric column but
    the leading epoch_ms one, applied to a Smart Sensor's bucketed [epoch_ms, min, avg, max] rows
    (see CONTEXT.md: Sparkline; ADR 0024) — min/avg/max all get the same treatment so the band's
    edges stay consistent with the line drawn inside it."""
    smoothed = []
    for i, point in enumerate(points):
        window = points[max(0, i - _SPARKLINE_SMOOTHING_WINDOW + 1):i + 1]
        smoothed.append([point[0]] + [sum(p[c] for p in window) / len(window) for c in range(1, len(point))])
    return smoothed


def _sparkline(conn, sensor: dict, metric) -> dict:
    """A Sparkline's points for one metric, covering the last week, plus the Sensor's own Target
    Range for that metric (see CONTEXT.md: Sparkline; ADR 0023, ADR 0024, ADR 0028) — {"points":
    [...], "target_min": float | None, "target_max": float | None}, all already in the metric's
    display unit (Fahrenheit for Temperature, same as every pill), since the Target Range is stored
    in the same unit as the Reading it judges (Celsius for Temperature).

    A Smart Sensor's dedupe window is only 5 seconds (see plugins/govee_ble/plugin.py), so it can
    write a new sensor_reading row every 5-30 seconds continuously — even a week of that raw would be
    thousands of points for a chart this small, repeated on every Dashboard load. Its Sparkline
    instead aggregates into daily min/avg/max buckets, then smooths those with a trailing moving
    average (_sparkline_smoothed) so the line reads as a trend rather than a zigzag — both as
    [epoch_ms, min, avg, max] rows, oldest first. A Manual Sensor's Readings are hand-logged and
    sparse (at most one a day), so bucketing and smoothing them would misrepresent what was
    actually recorded — its Sparkline stays raw and unsmoothed, as [epoch_ms, value] pairs.
    sensor_reading.recorded_at is true UTC with no backdating path (see view_data_queries.py's
    module docstring) — converted here so epoch_ms lines up with the viewer's actual wall-clock,
    same as every other chart in this app."""
    column = metric.reading_column
    cutoff = (datetime.now(timezone.utc) - timedelta(days=_SPARKLINE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    if sensor["tracking_mode"] == "manual":
        rows = conn.execute(
            f"SELECT recorded_at, {column} AS value FROM sensor_reading "
            f"WHERE sensor_id = ? AND {column} IS NOT NULL AND recorded_at >= ? ORDER BY recorded_at ASC",
            (sensor["id"], cutoff),
        ).fetchall()
        points = [[_sparkline_epoch_ms(row["recorded_at"]), row["value"]] for row in rows]
    else:
        rows = conn.execute(
            f"SELECT strftime('%Y-%m-%d', recorded_at) AS bucket, "
            f"MIN({column}) AS lo, AVG({column}) AS avg, MAX({column}) AS hi FROM sensor_reading "
            f"WHERE sensor_id = ? AND {column} IS NOT NULL AND recorded_at >= ? "
            f"GROUP BY bucket ORDER BY bucket ASC",
            (sensor["id"], cutoff),
        ).fetchall()
        points = [
            [_sparkline_epoch_ms(row["bucket"], "%Y-%m-%d"), row["lo"], row["avg"], row["hi"]]
            for row in rows
        ]
        points = _sparkline_smoothed(points)
    target_min = sensor[metric.min_column]
    target_max = sensor[metric.max_column]
    if metric.converts_f_c:
        points = [[p[0]] + [_sparkline_c_to_f(v) for v in p[1:]] for p in points]
        target_min = _sparkline_c_to_f(target_min)
        target_max = _sparkline_c_to_f(target_max)
    return {"points": points, "target_min": target_min, "target_max": target_max}


def _sparklines(conn, sensor: dict, reading: dict | None) -> dict[str, dict]:
    """Only fetches a Sparkline for a metric this Sensor's Reading pill is actually showing right
    now (reading[column] is not None) — same restriction _latest_reading already applies to which
    metrics it looks up at all, so this never scans a column this Sensor has never reported."""
    if reading is None:
        return {}
    return {
        metric.reading_column: _sparkline(conn, sensor, metric)
        for metric in et.TARGET_RANGE_METRICS
        if reading.get(metric.reading_column) is not None
    }


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
                sensor["latest_reading"] = _latest_reading(conn, sensor)
                sensor["sparklines"] = _sparklines(conn, sensor, sensor["latest_reading"])
            enclosure["sensor_count"] = len(sensors)
            enclosure["sensors"] = [s for s in sensors if s["show_on_dashboard"]]

            # Fallback Sensor (see CONTEXT.md) — only relevant when this Enclosure has none of its
            # own; its Reading is never colored (no Target Range comparison), see ADR 0004.
            enclosure["fallback_sensor"] = None
            enclosure["fallback_reading"] = None
            enclosure["fallback_sparklines"] = {}
            if not sensors and enclosure["fallback_sensor_id"]:
                fb_row = conn.execute("SELECT * FROM sensor WHERE id = ?", (enclosure["fallback_sensor_id"],)).fetchone()
                if fb_row:
                    enclosure["fallback_sensor"] = dict(fb_row)
                    enclosure["fallback_reading"] = _latest_reading(conn, dict(fb_row))
                    enclosure["fallback_sparklines"] = _sparklines(conn, fb_row, enclosure["fallback_reading"])

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
                sensor["latest_reading"] = _latest_reading(conn, sensor)
                sensor["sparklines"] = _sparklines(conn, sensor, sensor["latest_reading"])
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
