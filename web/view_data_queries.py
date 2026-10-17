"""Query/mutation layer behind the View Data page (see CONTEXT.md: View Data; ADR 0021, ADR 0027).

Two levels: an index per Room/Enclosure listing one row *title* per Sensor+metric Reading, Care
Event kind (Enclosure only), Animal Log metric/Condition, and Plug Status/Data Capture metric — no
per-day data at all (see ADR 0027, which replaced the original day-columned grid with this). Clicking
a title opens that row's own detail page: every real row for that one Sensor+metric/kind/Animal
field, newest first, with Add/Edit/Delete for whichever of those is actually editable. Only a Manual
Sensor's Reading, a Care Event, and an Animal Log entry are ever mutated here — a Smart Sensor's
Reading and a Plug's Status/Data Capture are shown read-only, since they're auto-collected from a
real device.

UTC-vs-local policy (see ADR 0021, carried over unchanged by ADR 0027): sensor_reading.recorded_at
and animal_log.occurred_at are true UTC and need conversion before showing/filtering by local
calendar day — confirmed live that a Smart Sensor's auto-collected Readings (by far the largest
source of rows in that table) and a Manual Sensor's "log as now" Readings are both true UTC with no
backdating path on that branch. care_event.occurred_at, by contrast, is stored with NO conversion:
its dominant real path is the Enclosure page's own Today/Yesterday/N-days-ago buttons, which compute
local wall-clock time and store it as-is (web/admin.py's admin_create_care_event) — converting those
from a false "UTC" assumption would shift the common case instead of fixing it.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.db import get_connection
from schemas import enclosure_types as et
from web.queries import ANIMAL_CONDITIONS, CARE_EVENT_KINDS, PERIOD_SLOT_HHMM, PERIOD_SLOTS

# (key, title, number of days) — used only by Graphs now (see CONTEXT.md: Graphs; ADR 0022), which
# still shows a day-windowed chart. View Data itself dropped its own Range picker under ADR 0027.
RANGE_OPTIONS: tuple[tuple[str, str, int], ...] = (
    ("week", "Week", 7),
    ("month", "Month", 30),
    ("90d", "90 Days", 90),
    ("180d", "180 Days", 180),
    ("year", "Year", 365),
)
DEFAULT_RANGE_KEY = "week"
_RANGE_DAYS = {key: days for key, _, days in RANGE_OPTIONS}

_PLUG_TELEMETRY_FIELDS = (("watts", "W"), ("volts", "V"), ("amps", "A"))

# animal_log's numeric fields (see CONTEXT.md: Animal Log) — (column, label, unit, decimals, step).
# Doubles as the column whitelist the animal-metric entry functions validate `field` against before
# it ever reaches an f-string SQL fragment.
_ANIMAL_METRIC_FIELDS: tuple[tuple[str, str, str, int, str], ...] = (
    ("weight_g", "Weight", "g", 1, "0.1"),
    ("length_cm", "Length", "cm", 1, "0.1"),
    ("count", "Count", "", 0, "1"),
)
_ANIMAL_LOG_VALUE_COLUMNS = ("weight_g", "length_cm", "count", "condition")

# "Basic" table (see CONTEXT.md: View Data; ADR 0027) — no pagination yet. A recent-first cap keeps
# a Smart Sensor's auto-collected history (one row every few minutes, for months) from rendering
# thousands of entries on one page.
_DETAIL_ENTRY_LIMIT = 300


def _f_to_c(fahrenheit: float | None) -> float | None:
    return None if fahrenheit is None else (fahrenheit - 32) * 5 / 9


def compute_window(range_key: str, end_str: str | None) -> tuple[date, date, int]:
    """The [start, end] window a GET to Graphs should show — end never goes past today (there's
    nothing to show for the future), range_key falls back to the default on anything unrecognized
    rather than erroring on a hand-edited URL."""
    days = _RANGE_DAYS.get(range_key, _RANGE_DAYS[DEFAULT_RANGE_KEY])
    today = datetime.now().date()
    try:
        end = date.fromisoformat(end_str) if end_str else today
    except ValueError:
        end = today
    end = min(end, today)
    start = end - timedelta(days=days - 1)
    return start, end, days


def date_list(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _metric_shown(conn: sqlite3.Connection, sensor: dict, metric: et.TargetRangeMetric) -> bool:
    """Whether this metric gets its own row for this Sensor at all. Deliberately NOT the same
    "temperature/humidity always, else only if tracked" rule web/queries.py's _latest_reading uses
    for the Dashboard pill — that rule is harmless there (an untracked pill just never renders), but
    here it would mean a permanently empty row, forever, for e.g. a water-chemistry-only "Ca"/"Mg"/
    "pH" Manual Sensor that was never meant to report ambient temperature (confirmed against real
    data — see ADR 0021 discussion). So temperature/humidity only earn a row if this Sensor actually
    has at least one Reading for it somewhere in its history, same as any other metric would need a
    Target Range to show at all."""
    tracked = sensor.get(metric.min_column) is not None or sensor.get(metric.max_column) is not None
    if tracked:
        return True
    if metric.reading_column not in ("temperature_c", "humidity_pct"):
        return False
    (ever_logged,) = conn.execute(
        f"SELECT EXISTS(SELECT 1 FROM sensor_reading WHERE sensor_id = ? AND {metric.reading_column} IS NOT NULL)",
        (sensor["id"],),
    ).fetchone()
    return bool(ever_logged)


# ---------------------------------------------------------------------------------------------
# Index: titles only (see CONTEXT.md: View Data; ADR 0027) — no per-day data, so no date range
# needed at all here.
# ---------------------------------------------------------------------------------------------

def _reading_row(sensor: dict, metric: et.TargetRangeMetric) -> dict:
    label_suffix = metric.label or metric.key.replace("_", " ").title()
    return {
        "type": "reading",
        "label": f"{sensor['label']} — {label_suffix}",
        "editable": sensor["tracking_mode"] == "manual",
        "sensor_id": sensor["id"],
        "metric_key": metric.key,
    }


def _care_event_row(enclosure_id: int, kind: str) -> dict:
    return {
        "type": "care",
        "label": kind.replace("_", " ").capitalize(),
        "editable": True,
        "enclosure_id": enclosure_id,
        "kind": kind,
    }


def _plug_status_row(plug: dict) -> dict:
    return {
        "type": "plug_status",
        "label": f"{plug['label']} — Status",
        "editable": False,
        "plug_id": plug["id"],
    }


def _plug_telemetry_row(plug: dict, field: str, unit: str) -> dict:
    return {
        "type": "plug_telemetry",
        "label": f"{plug['label']} — {field.capitalize()}",
        "editable": False,
        "plug_id": plug["id"],
        "field": field,
        "unit": unit,
    }


def _plug_rows(plug: dict) -> list[dict]:
    rows = [_plug_status_row(plug)]
    if plug["tracking_mode"] == "smart":
        # Data Capture (see CONTEXT.md) only ever exists for a Smart Plug — a Manual Plug has no
        # device to pull wattage/volts/amps from.
        rows += [_plug_telemetry_row(plug, field, unit) for field, unit in _PLUG_TELEMETRY_FIELDS]
    return rows


def _animal_metric_row(animal: dict, field: str, label: str, unit: str, decimals: int, step: str) -> dict:
    return {
        "type": "animal_metric",
        "label": f"{animal['name']} — {label}",
        "editable": True,
        "animal_id": animal["id"],
        "field": field,
        "unit": unit,
        "decimals": decimals,
        "step": step,
    }


def _animal_condition_row(animal: dict) -> dict:
    return {
        "type": "animal_condition",
        "label": f"{animal['name']} — Condition",
        "editable": True,
        "animal_id": animal["id"],
    }


def _animal_log_rows(animal: dict) -> list[dict]:
    rows = [
        _animal_metric_row(animal, field, label, unit, decimals, step)
        for field, label, unit, decimals, step in _ANIMAL_METRIC_FIELDS
    ]
    rows.append(_animal_condition_row(animal))
    return rows


def build_room_sections(room_id: int) -> list[dict]:
    """Room's own Sensors/Plugs only — never rolls up its Enclosures' own data, same boundary
    Refresh already draws (see CONTEXT.md: Refresh; ADR 0021)."""
    with get_connection() as conn:
        sensors = [dict(r) for r in conn.execute("SELECT * FROM sensor WHERE room_id = ? ORDER BY label", (room_id,))]
        plugs = [dict(r) for r in conn.execute("SELECT * FROM plug WHERE room_id = ? ORDER BY label", (room_id,))]

        reading_rows = [
            _reading_row(sensor, metric)
            for sensor in sensors
            for metric in et.TARGET_RANGE_METRICS
            if _metric_shown(conn, sensor, metric)
        ]
    plug_rows = [row for plug in plugs for row in _plug_rows(plug)]

    sections = []
    if reading_rows:
        sections.append({"title": "Sensor Readings", "rows": reading_rows})
    if plug_rows:
        sections.append({"title": "Plugs", "rows": plug_rows})
    return sections


def build_enclosure_sections(enclosure_id: int) -> list[dict]:
    with get_connection() as conn:
        sensors = [dict(r) for r in conn.execute("SELECT * FROM sensor WHERE enclosure_id = ? ORDER BY label", (enclosure_id,))]
        plugs = [dict(r) for r in conn.execute(
            """SELECT p.* FROM plug p JOIN plug_enclosure pe ON pe.plug_id = p.id
               WHERE pe.enclosure_id = ? ORDER BY p.label""",
            (enclosure_id,),
        )]
        animals = [dict(r) for r in conn.execute("SELECT * FROM animal WHERE enclosure_id = ? ORDER BY name", (enclosure_id,))]

        reading_rows = [
            _reading_row(sensor, metric)
            for sensor in sensors
            for metric in et.TARGET_RANGE_METRICS
            if _metric_shown(conn, sensor, metric)
        ]
    # All four Care Event kinds always show, even with nothing logged yet — same precedent as the
    # Enclosure page's own Care section (see CONTEXT.md: Care Interval).
    care_rows = [_care_event_row(enclosure_id, kind) for kind in CARE_EVENT_KINDS]
    plug_rows = [row for plug in plugs for row in _plug_rows(plug)]
    # Unlike Care Events, only shown when there's actually an Animal to log against — an Enclosure
    # with no Animals has nothing here, same "skip if empty" rule as Sensor Readings.
    animal_rows = [row for animal in animals for row in _animal_log_rows(animal)]

    sections = []
    if reading_rows:
        sections.append({"title": "Sensor Readings", "rows": reading_rows})
    sections.append({"title": "Care Events", "rows": care_rows})
    if animal_rows:
        sections.append({"title": "Animal Log", "rows": animal_rows})
    if plug_rows:
        sections.append({"title": "Plugs", "rows": plug_rows})
    return sections


def animal_metric_field_info(field: str) -> tuple[str, str, int, str]:
    """(label, unit, decimals, step) for one Animal Log numeric field — also the one place
    web/admin.py needs to validate a `field` path param before it reaches this module's entry
    functions."""
    for column, label, unit, decimals, step in _ANIMAL_METRIC_FIELDS:
        if column == field:
            return label, unit, decimals, step
    raise ValueError(f"Unknown Animal Log field: {field!r}")


def plug_telemetry_unit(field: str) -> str:
    for column, unit in _PLUG_TELEMETRY_FIELDS:
        if column == field:
            return unit
    raise ValueError(f"Unknown telemetry field: {field!r}")


# ---------------------------------------------------------------------------------------------
# Detail: every real row for one Sensor+metric/kind/Animal field (see CONTEXT.md: View Data; ADR
# 0027), newest first.
# ---------------------------------------------------------------------------------------------

_PERIOD_SLOT_HOURS = dict(PERIOD_SLOTS)


def _period_slot_utc_stamp(day: str, slot: str) -> str:
    """A new Reading/Animal Log/Care Event entry (see CONTEXT.md: View Data, Period Slot; ADR 0026,
    ADR 0027) is stored at its chosen Period Slot's anchor hour, *local* time on `day`, converted to
    UTC. An unrecognized slot name falls back to Afternoon, same lenient-default style as this
    module's own Range picker."""
    hour = _PERIOD_SLOT_HOURS.get(slot, _PERIOD_SLOT_HOURS["afternoon"])
    local = datetime.combine(date.fromisoformat(day), time(hour, 0))
    return local.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _utc_to_local_parts(stamp: str) -> tuple[str, str]:
    """A UTC "YYYY-MM-DD HH:MM:SS" stamp -> (local date ISO, local "HH:MM") — for display, and for
    pre-filling an Edit form's date input."""
    utc = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    local = utc.astimezone()
    return local.date().isoformat(), local.strftime("%H:%M")


# ---- Reading entries (sensor_reading) ----

def list_reading_entries(sensor_id: int, metric_key: str) -> list[dict]:
    column = et.metric_by_key(metric_key).reading_column
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT id, recorded_at, {column} AS value FROM sensor_reading "
            f"WHERE sensor_id = ? AND {column} IS NOT NULL ORDER BY recorded_at DESC LIMIT ?",
            (sensor_id, _DETAIL_ENTRY_LIMIT),
        ).fetchall()
    entries = []
    for row in rows:
        local_date, local_time = _utc_to_local_parts(row["recorded_at"])
        entries.append({"id": row["id"], "date": local_date, "time": local_time, "value": row["value"]})
    return entries


def add_reading_entry(sensor_id: int, metric_key: str, day: str, slot: str, value: float) -> None:
    """Only a Manual Sensor's Reading can be logged here — see module docstring."""
    column = et.metric_by_key(metric_key).reading_column
    with get_connection() as conn:
        sensor = conn.execute("SELECT tracking_mode FROM sensor WHERE id = ?", (sensor_id,)).fetchone()
        if sensor is None:
            raise ValueError("Sensor not found.")
        if sensor["tracking_mode"] != "manual":
            raise ValueError("Only a Manual Sensor's Reading can be logged here.")
        conn.execute(
            f"INSERT INTO sensor_reading (sensor_id, recorded_at, {column}) VALUES (?, ?, ?)",
            (sensor_id, _period_slot_utc_stamp(day, slot), value),
        )


def update_reading_entry(entry_id: int, metric_key: str, value: float) -> None:
    column = et.metric_by_key(metric_key).reading_column
    with get_connection() as conn:
        conn.execute(f"UPDATE sensor_reading SET {column} = ? WHERE id = ?", (value, entry_id))


def delete_reading_entry(entry_id: int, metric_key: str) -> None:
    """NULLs just this metric's column if the row still holds another metric's value (a single
    sensor_reading row can carry several metrics from one log action — see db/schema.sql), else
    deletes the row outright so no all-NULL husk is left behind."""
    column = et.metric_by_key(metric_key).reading_column
    with get_connection() as conn:
        existing = conn.execute("SELECT * FROM sensor_reading WHERE id = ?", (entry_id,)).fetchone()
        if existing is None:
            return
        other_metrics_set = any(
            existing[m.reading_column] is not None for m in et.TARGET_RANGE_METRICS if m.reading_column != column
        )
        if other_metrics_set:
            conn.execute(f"UPDATE sensor_reading SET {column} = NULL WHERE id = ?", (entry_id,))
        else:
            conn.execute("DELETE FROM sensor_reading WHERE id = ?", (entry_id,))


# ---- Care Event entries ----

def list_care_event_entries(enclosure_id: int, kind: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT ce.id, ce.occurred_at, ce.note, ce.animal_id, a.name AS animal_name
               FROM care_event ce LEFT JOIN animal a ON a.id = ce.animal_id
               WHERE ce.enclosure_id = ? AND ce.kind = ? ORDER BY ce.occurred_at DESC LIMIT ?""",
            (enclosure_id, kind, _DETAIL_ENTRY_LIMIT),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "date": row["occurred_at"][:10],
            "time": row["occurred_at"][11:16],
            "note": row["note"] or "",
            "animal_id": row["animal_id"],
            "animal_name": row["animal_name"],
        }
        for row in rows
    ]


def add_care_event_entry(enclosure_id: int, kind: str, day: str, time_str: str | None,
                          note: str | None, animal_id: int | None) -> None:
    if kind not in CARE_EVENT_KINDS:
        raise ValueError(f"Unknown care event kind: {kind!r}")
    if animal_id is not None and kind != "feeding":
        raise ValueError("Spot-feed (picking one Animal) only applies to Feeding.")
    occurred_at = f"{day} {time_str or PERIOD_SLOT_HHMM['afternoon']}:00"
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO care_event (enclosure_id, animal_id, kind, occurred_at, note) VALUES (?, ?, ?, ?, ?)",
            (enclosure_id, animal_id, kind, occurred_at, note or None),
        )


def update_care_event_entry(entry_id: int, day: str, time_str: str | None,
                             note: str | None, animal_id: int | None) -> None:
    """Unlike Reading/Animal Log entries, a Care Event entry's date/time is fully editable in
    place — same "always re-derive occurred_at" rule the day-grid cell editor used under ADR 0026,
    carried over to this per-row table by ADR 0027."""
    occurred_at = f"{day} {time_str or PERIOD_SLOT_HHMM['afternoon']}:00"
    with get_connection() as conn:
        conn.execute(
            "UPDATE care_event SET occurred_at = ?, note = ?, animal_id = ? WHERE id = ?",
            (occurred_at, note or None, animal_id, entry_id),
        )


def delete_care_event_entry(entry_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM care_event WHERE id = ?", (entry_id,))


# ---- Animal Log metric entries (Weight/Length/Count) ----

def list_animal_metric_entries(animal_id: int, field: str) -> list[dict]:
    animal_metric_field_info(field)  # validates `field` before the f-string below
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT id, occurred_at, {field} AS value FROM animal_log "
            f"WHERE animal_id = ? AND {field} IS NOT NULL ORDER BY occurred_at DESC LIMIT ?",
            (animal_id, _DETAIL_ENTRY_LIMIT),
        ).fetchall()
    entries = []
    for row in rows:
        local_date, local_time = _utc_to_local_parts(row["occurred_at"])
        entries.append({"id": row["id"], "date": local_date, "time": local_time, "value": row["value"]})
    return entries


def add_animal_metric_entry(animal_id: int, field: str, day: str, slot: str, value: float) -> None:
    animal_metric_field_info(field)
    with get_connection() as conn:
        animal = conn.execute("SELECT id FROM animal WHERE id = ?", (animal_id,)).fetchone()
        if animal is None:
            raise ValueError("Animal not found.")
        conn.execute(
            f"INSERT INTO animal_log (animal_id, occurred_at, {field}) VALUES (?, ?, ?)",
            (animal_id, _period_slot_utc_stamp(day, slot), value),
        )


def update_animal_metric_entry(entry_id: int, field: str, value: float) -> None:
    animal_metric_field_info(field)
    with get_connection() as conn:
        conn.execute(f"UPDATE animal_log SET {field} = ? WHERE id = ?", (value, entry_id))


def delete_animal_metric_entry(entry_id: int, field: str) -> None:
    animal_metric_field_info(field)
    with get_connection() as conn:
        existing = conn.execute("SELECT * FROM animal_log WHERE id = ?", (entry_id,)).fetchone()
        if existing is None:
            return
        other_fields_set = any(existing[c] is not None for c in _ANIMAL_LOG_VALUE_COLUMNS if c != field)
        if other_fields_set:
            conn.execute(f"UPDATE animal_log SET {field} = NULL WHERE id = ?", (entry_id,))
        else:
            conn.execute("DELETE FROM animal_log WHERE id = ?", (entry_id,))


# ---- Animal Log Condition entries ----

def list_animal_condition_entries(animal_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, occurred_at, condition, note FROM animal_log "
            "WHERE animal_id = ? AND condition IS NOT NULL ORDER BY occurred_at DESC LIMIT ?",
            (animal_id, _DETAIL_ENTRY_LIMIT),
        ).fetchall()
    entries = []
    for row in rows:
        local_date, local_time = _utc_to_local_parts(row["occurred_at"])
        entries.append({
            "id": row["id"], "date": local_date, "time": local_time,
            "condition": row["condition"], "note": row["note"] or "",
        })
    return entries


def add_animal_condition_entry(animal_id: int, day: str, slot: str, condition: str, note: str | None) -> None:
    if condition not in ANIMAL_CONDITIONS:
        raise ValueError(f"Unknown Condition: {condition!r}")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO animal_log (animal_id, occurred_at, condition, note) VALUES (?, ?, ?, ?)",
            (animal_id, _period_slot_utc_stamp(day, slot), condition, note or None),
        )


def update_animal_condition_entry(entry_id: int, condition: str, note: str | None) -> None:
    if condition not in ANIMAL_CONDITIONS:
        raise ValueError(f"Unknown Condition: {condition!r}")
    with get_connection() as conn:
        conn.execute("UPDATE animal_log SET condition = ?, note = ? WHERE id = ?", (condition, note or None, entry_id))


def delete_animal_condition_entry(entry_id: int) -> None:
    with get_connection() as conn:
        existing = conn.execute("SELECT * FROM animal_log WHERE id = ?", (entry_id,)).fetchone()
        if existing is None:
            return
        other_fields_set = any(existing[c] is not None for c in ("weight_g", "length_cm", "count"))
        if other_fields_set:
            conn.execute("UPDATE animal_log SET condition = NULL, note = NULL WHERE id = ?", (entry_id,))
        else:
            conn.execute("DELETE FROM animal_log WHERE id = ?", (entry_id,))


# ---- Plug Status/Data Capture entries (read-only) ----

def list_plug_status_entries(plug_id: int) -> list[dict]:
    with get_connection() as conn:
        plug = conn.execute("SELECT tracking_mode FROM plug WHERE id = ?", (plug_id,)).fetchone()
        if plug is None:
            return []
        if plug["tracking_mode"] == "smart":
            rows = conn.execute(
                "SELECT recorded_at, is_on FROM plug_state_transition WHERE plug_id = ? "
                "ORDER BY recorded_at DESC LIMIT ?",
                (plug_id, _DETAIL_ENTRY_LIMIT),
            ).fetchall()
        else:
            # A Manual Plug's status is its own self-reported Command log — see CONTEXT.md: Command.
            rows = conn.execute(
                "SELECT requested_at AS recorded_at, is_on FROM plug_command_log WHERE plug_id = ? "
                "ORDER BY requested_at DESC LIMIT ?",
                (plug_id, _DETAIL_ENTRY_LIMIT),
            ).fetchall()
    entries = []
    for row in rows:
        local_date, local_time = _utc_to_local_parts(row["recorded_at"])
        entries.append({"date": local_date, "time": local_time, "is_on": bool(row["is_on"])})
    return entries


def list_plug_telemetry_entries(plug_id: int, field: str) -> list[dict]:
    plug_telemetry_unit(field)  # validates `field` before the f-string below
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT recorded_at, {field} AS value FROM plug_reading "
            f"WHERE plug_id = ? AND {field} IS NOT NULL ORDER BY recorded_at DESC LIMIT ?",
            (plug_id, _DETAIL_ENTRY_LIMIT),
        ).fetchall()
    entries = []
    for row in rows:
        local_date, local_time = _utc_to_local_parts(row["recorded_at"])
        entries.append({"date": local_date, "time": local_time, "value": row["value"]})
    return entries
