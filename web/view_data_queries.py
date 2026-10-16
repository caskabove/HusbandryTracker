"""Query/mutation layer behind the View Data page (see CONTEXT.md: View Data; ADR 0021).

Builds a day-columned grid per Room/Enclosure: one row per Sensor+metric Reading, one row per Care
Event kind (Enclosure only), and one Status row plus one row per Data Capture metric per Plug. Each
cell holds that day's *last* value, matching the "latest wins" precedent already used for same-day
data elsewhere in this app (see web/queries.py's _latest_reading/_current_plug_status). Only a
Reading or a Care Event is ever mutated here — a Smart Sensor's Reading, a Plug's Status, and a
Plug's Data Capture are shown read-only, since they're auto-collected from a real device.

Bucketing-by-day policy, worked out against this app's real data rather than assumed (see ADR
0021): sensor_reading.recorded_at is converted from UTC before bucketing, same as
plug_state_transition/plug_command_log/plug_reading — confirmed live that a Smart Sensor's
auto-collected Readings (by far the largest source of rows in this table) and a Manual Sensor's
"log as now" Readings are both true UTC with no backdating path on that branch, so bucketing by the
raw string would silently shift most of a day's Smart-Sensor Readings into the wrong local calendar
column. care_event.occurred_at, by contrast, is bucketed with NO conversion: its dominant real path
is the Enclosure page's own Today/Yesterday/N-days-ago buttons, which compute local wall-clock time
and store it as-is (web/admin.py's admin_create_care_event) — converting those from a false "UTC"
assumption would shift the common case instead of fixing it. Either way, a Manual Sensor's
explicitly-backdated-with-a-custom-time Reading (the Enclosure page's blank-unless-filled-in
datetime-local field) is the one input shape this can't disambiguate from a true "now" — rare
enough, and only off by a fixed UTC-offset amount, to accept rather than block on.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.db import get_connection
from schemas import enclosure_types as et
from web.queries import ANIMAL_CONDITIONS, CARE_EVENT_KINDS

# (key, title, number of days) — see ADR 0021. Order matches the Range <select> in view_data.html.
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
# Doubles as the column whitelist set_animal_metric_cell() validates `field` against before it ever
# reaches an f-string SQL fragment.
_ANIMAL_METRIC_FIELDS: tuple[tuple[str, str, str, int, str], ...] = (
    ("weight_g", "Weight", "g", 1, "0.1"),
    ("length_cm", "Length", "cm", 1, "0.1"),
    ("count", "Count", "", 0, "1"),
)
_ANIMAL_LOG_VALUE_COLUMNS = ("weight_g", "length_cm", "count", "condition")


def _f_to_c(fahrenheit: float | None) -> float | None:
    return None if fahrenheit is None else (fahrenheit - 32) * 5 / 9


def compute_window(range_key: str, end_str: str | None) -> tuple[date, date, int]:
    """The [start, end] window a GET to the View Data page should show — end never goes past today
    (there's nothing to show for the future), range_key falls back to the default on anything
    unrecognized rather than erroring on a hand-edited URL."""
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
    here it would mean a permanently empty row, every day, forever, for e.g. a water-chemistry-only
    "Ca"/"Mg"/"pH" Manual Sensor that was never meant to report ambient temperature (confirmed
    against real data — see ADR 0021 discussion). So temperature/humidity only earn a row if this
    Sensor actually has at least one Reading for it somewhere in its history, same as any other
    metric would need a Target Range to show at all."""
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


def _bucket_last_by_raw_day(rows: list[sqlite3.Row], ts_column: str) -> dict[str, sqlite3.Row]:
    """rows must already be ORDER BY <ts_column> ASC. Buckets by the stored string's own date
    prefix (no tz conversion — see module docstring), last row per day wins."""
    buckets: dict[str, sqlite3.Row] = {}
    for row in rows:
        buckets[row[ts_column][:10]] = row
    return buckets


def _bucket_last_by_local_day(rows: list[sqlite3.Row], ts_column: str) -> dict[date, sqlite3.Row]:
    """rows must already be ORDER BY <ts_column> ASC, and <ts_column> must be a UTC
    "YYYY-MM-DD HH:MM:SS" stamp with no backdating path (see module docstring) — converted to local
    time before bucketing, last row per local calendar day wins."""
    buckets: dict[date, sqlite3.Row] = {}
    for row in rows:
        utc = datetime.strptime(row[ts_column], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        buckets[utc.astimezone().date()] = row
    return buckets


def _utc_query_bounds(dates: list[date]) -> tuple[str, str]:
    """A generously padded UTC range guaranteed to cover every row that could land, once converted
    to local time, on any day in `dates` — avoids scanning a Smart Sensor/Plug's entire history on
    every page view. One day of padding on each side covers every real-world UTC offset."""
    start = datetime.combine(dates[0], time.min) - timedelta(days=1)
    end = datetime.combine(dates[-1], time.min) + timedelta(days=2)
    return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")


def _reading_row(conn: sqlite3.Connection, sensor: dict, metric: et.TargetRangeMetric, dates: list[date]) -> dict:
    column = metric.reading_column
    start_s, end_s = _utc_query_bounds(dates)
    rows = conn.execute(
        f"SELECT recorded_at, {column} AS value FROM sensor_reading "
        f"WHERE sensor_id = ? AND {column} IS NOT NULL AND recorded_at BETWEEN ? AND ? "
        f"ORDER BY recorded_at ASC",
        (sensor["id"], start_s, end_s),
    ).fetchall()
    by_day = _bucket_last_by_local_day(rows, "recorded_at")
    editable = sensor["tracking_mode"] == "manual"
    cells = {}
    for d in dates:
        row = by_day.get(d)
        cells[d.isoformat()] = {"value": row["value"] if row else None}
    label_suffix = metric.label or metric.key.replace("_", " ").title()
    return {
        "type": "reading",
        "key": f"reading-{sensor['id']}-{metric.key}",
        "label": f"{sensor['label']} — {label_suffix}",
        "editable": editable,
        "sensor_id": sensor["id"],
        "metric_key": metric.key,
        "metric": metric,
        "cells": cells,
    }


def _care_event_row(conn: sqlite3.Connection, enclosure_id: int, kind: str, dates: list[date]) -> dict:
    start_s, end_s = dates[0].isoformat(), dates[-1].isoformat()
    rows = conn.execute(
        """SELECT ce.occurred_at, ce.note, ce.animal_id, a.name AS animal_name
           FROM care_event ce LEFT JOIN animal a ON a.id = ce.animal_id
           WHERE ce.enclosure_id = ? AND ce.kind = ? AND substr(ce.occurred_at, 1, 10) BETWEEN ? AND ?
           ORDER BY ce.occurred_at ASC""",
        (enclosure_id, kind, start_s, end_s),
    ).fetchall()
    by_day = _bucket_last_by_raw_day(rows, "occurred_at")
    cells = {}
    for d in dates:
        key = d.isoformat()
        row = by_day.get(key)
        if row is None:
            cells[key] = {"time": "", "note": "", "animal_id": None, "animal_name": None}
        else:
            cells[key] = {
                "time": row["occurred_at"][11:16],
                "note": row["note"] or "",
                "animal_id": row["animal_id"],
                "animal_name": row["animal_name"],
            }
    return {
        "type": "care",
        "key": f"care-{enclosure_id}-{kind}",
        "label": kind.replace("_", " ").capitalize(),
        "editable": True,
        "enclosure_id": enclosure_id,
        "kind": kind,
        "cells": cells,
    }


def _plug_status_row(conn: sqlite3.Connection, plug: dict, dates: list[date]) -> dict:
    start_s, end_s = _utc_query_bounds(dates)
    if plug["tracking_mode"] == "smart":
        rows = conn.execute(
            "SELECT recorded_at, is_on FROM plug_state_transition "
            "WHERE plug_id = ? AND recorded_at BETWEEN ? AND ? ORDER BY recorded_at ASC",
            (plug["id"], start_s, end_s),
        ).fetchall()
    else:
        # A Manual Plug's status is its own self-reported Command log — see CONTEXT.md: Command.
        rows = conn.execute(
            "SELECT requested_at AS recorded_at, is_on FROM plug_command_log "
            "WHERE plug_id = ? AND requested_at BETWEEN ? AND ? ORDER BY requested_at ASC",
            (plug["id"], start_s, end_s),
        ).fetchall()
    by_day = _bucket_last_by_local_day(rows, "recorded_at")
    cells = {}
    for d in dates:
        row = by_day.get(d)
        cells[d.isoformat()] = {"is_on": bool(row["is_on"]) if row else None}
    return {
        "type": "plug_status",
        "key": f"plug-status-{plug['id']}",
        "label": f"{plug['label']} — Status",
        "editable": False,
        "cells": cells,
    }


def _plug_telemetry_row(conn: sqlite3.Connection, plug: dict, field: str, unit: str, dates: list[date]) -> dict:
    start_s, end_s = _utc_query_bounds(dates)
    rows = conn.execute(
        f"SELECT recorded_at, {field} AS value FROM plug_reading "
        f"WHERE plug_id = ? AND recorded_at BETWEEN ? AND ? ORDER BY recorded_at ASC",
        (plug["id"], start_s, end_s),
    ).fetchall()
    by_day = _bucket_last_by_local_day(rows, "recorded_at")
    cells = {}
    for d in dates:
        row = by_day.get(d)
        cells[d.isoformat()] = {"value": row["value"] if row else None}
    return {
        "type": "plug_telemetry",
        "key": f"plug-telemetry-{plug['id']}-{field}",
        "label": f"{plug['label']} — {field.capitalize()}",
        "editable": False,
        "unit": unit,
        "cells": cells,
    }


def _plug_rows(conn: sqlite3.Connection, plug: dict, dates: list[date]) -> list[dict]:
    rows = [_plug_status_row(conn, plug, dates)]
    if plug["tracking_mode"] == "smart":
        # Data Capture (see CONTEXT.md) only ever exists for a Smart Plug — a Manual Plug has no
        # device to pull wattage/volts/amps from.
        rows += [_plug_telemetry_row(conn, plug, field, unit, dates) for field, unit in _PLUG_TELEMETRY_FIELDS]
    return rows


def _animal_metric_row(conn: sqlite3.Connection, animal: dict, field: str, label: str, unit: str,
                        decimals: int, step: str, dates: list[date]) -> dict:
    """One Animal Log numeric metric (Weight/Length/Count — see CONTEXT.md: Animal Log) for one
    Animal. Bucketed with UTC->local conversion like sensor_reading, not raw-string like
    care_event: an Animal Log row's dominant real path (leave "When" blank) hits animal_log's own
    datetime('now') DEFAULT, which is UTC — unlike Care Event, whose dominant path already computes
    and stores local wall-clock time itself (see this module's docstring, ADR 0021). A backdated
    entry made via a local datetime-local picker is the one input shape this can't disambiguate,
    same accepted rare edge case as a backdated Manual Sensor Reading."""
    start_s, end_s = _utc_query_bounds(dates)
    rows = conn.execute(
        f"SELECT occurred_at, {field} AS value FROM animal_log "
        f"WHERE animal_id = ? AND {field} IS NOT NULL AND occurred_at BETWEEN ? AND ? "
        f"ORDER BY occurred_at ASC",
        (animal["id"], start_s, end_s),
    ).fetchall()
    by_day = _bucket_last_by_local_day(rows, "occurred_at")
    cells = {}
    for d in dates:
        row = by_day.get(d)
        cells[d.isoformat()] = {"value": row["value"] if row else None}
    return {
        "type": "animal_metric",
        "key": f"animal-{animal['id']}-{field}",
        "label": f"{animal['name']} — {label}",
        "editable": True,
        "animal_id": animal["id"],
        "field": field,
        "unit": unit,
        "decimals": decimals,
        "step": step,
        "cells": cells,
    }


def _animal_condition_row(conn: sqlite3.Connection, animal: dict, dates: list[date]) -> dict:
    start_s, end_s = _utc_query_bounds(dates)
    rows = conn.execute(
        "SELECT occurred_at, condition, note FROM animal_log "
        "WHERE animal_id = ? AND condition IS NOT NULL AND occurred_at BETWEEN ? AND ? "
        "ORDER BY occurred_at ASC",
        (animal["id"], start_s, end_s),
    ).fetchall()
    by_day = _bucket_last_by_local_day(rows, "occurred_at")
    cells = {}
    for d in dates:
        row = by_day.get(d)
        cells[d.isoformat()] = {
            "condition": row["condition"] if row else None,
            "note": (row["note"] if row else None) or "",
        }
    return {
        "type": "animal_condition",
        "key": f"animal-{animal['id']}-condition",
        "label": f"{animal['name']} — Condition",
        "editable": True,
        "animal_id": animal["id"],
        "cells": cells,
    }


def _animal_log_rows(conn: sqlite3.Connection, animal: dict, dates: list[date]) -> list[dict]:
    rows = [
        _animal_metric_row(conn, animal, field, label, unit, decimals, step, dates)
        for field, label, unit, decimals, step in _ANIMAL_METRIC_FIELDS
    ]
    rows.append(_animal_condition_row(conn, animal, dates))
    return rows


def build_room_sections(room_id: int, dates: list[date]) -> list[dict]:
    """Room's own Sensors/Plugs only — never rolls up its Enclosures' own data, same boundary
    Refresh already draws (see CONTEXT.md: Refresh; ADR 0021)."""
    with get_connection() as conn:
        sensors = [dict(r) for r in conn.execute("SELECT * FROM sensor WHERE room_id = ? ORDER BY label", (room_id,))]
        plugs = [dict(r) for r in conn.execute("SELECT * FROM plug WHERE room_id = ? ORDER BY label", (room_id,))]

        reading_rows = [
            _reading_row(conn, sensor, metric, dates)
            for sensor in sensors
            for metric in et.TARGET_RANGE_METRICS
            if _metric_shown(conn, sensor, metric)
        ]
        plug_rows = [row for plug in plugs for row in _plug_rows(conn, plug, dates)]

    sections = []
    if reading_rows:
        sections.append({"title": "Sensor Readings", "rows": reading_rows})
    if plug_rows:
        sections.append({"title": "Plugs", "rows": plug_rows})
    return sections


def build_enclosure_sections(enclosure_id: int, dates: list[date]) -> list[dict]:
    with get_connection() as conn:
        sensors = [dict(r) for r in conn.execute("SELECT * FROM sensor WHERE enclosure_id = ? ORDER BY label", (enclosure_id,))]
        plugs = [dict(r) for r in conn.execute(
            """SELECT p.* FROM plug p JOIN plug_enclosure pe ON pe.plug_id = p.id
               WHERE pe.enclosure_id = ? ORDER BY p.label""",
            (enclosure_id,),
        )]
        animals = [dict(r) for r in conn.execute("SELECT * FROM animal WHERE enclosure_id = ? ORDER BY name", (enclosure_id,))]

        reading_rows = [
            _reading_row(conn, sensor, metric, dates)
            for sensor in sensors
            for metric in et.TARGET_RANGE_METRICS
            if _metric_shown(conn, sensor, metric)
        ]
        # All four Care Event kinds always show, even with nothing logged yet — same precedent as
        # the Enclosure page's own Care section (see CONTEXT.md: Care Interval).
        care_rows = [_care_event_row(conn, enclosure_id, kind, dates) for kind in CARE_EVENT_KINDS]
        plug_rows = [row for plug in plugs for row in _plug_rows(conn, plug, dates)]
        # Unlike Care Events, only shown when there's actually an Animal to log against — an
        # Enclosure with no Animals has nothing here, same "skip if empty" rule as Sensor Readings.
        animal_rows = [row for animal in animals for row in _animal_log_rows(conn, animal, dates)]

    sections = []
    if reading_rows:
        sections.append({"title": "Sensor Readings", "rows": reading_rows})
    sections.append({"title": "Care Events", "rows": care_rows})
    if animal_rows:
        sections.append({"title": "Animal Log", "rows": animal_rows})
    if plug_rows:
        sections.append({"title": "Plugs", "rows": plug_rows})
    return sections


def _local_noon_utc_stamp(day: str) -> str:
    """A new Reading created via an empty View Data cell (see CONTEXT.md: View Data; ADR 0021) is
    stored as noon *local* time on `day`, converted to UTC — so it buckets back to the same local
    day it was entered for, consistent with how every other sensor_reading row is now bucketed (see
    this module's docstring)."""
    local_noon = datetime.combine(date.fromisoformat(day), time(12, 0))
    return local_noon.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _find_reading_for_local_day(conn: sqlite3.Connection, sensor_id: int, column: str, day: str) -> sqlite3.Row | None:
    """The most recent sensor_reading row, for this metric, whose UTC recorded_at converts to local
    day `day` — the exact row View Data's cell for that day is showing (see this module's docstring
    on why sensor_reading needs a real UTC->local conversion, unlike care_event)."""
    day_date = date.fromisoformat(day)
    start_s, end_s = _utc_query_bounds([day_date])
    candidates = conn.execute(
        f"SELECT * FROM sensor_reading WHERE sensor_id = ? AND {column} IS NOT NULL "
        f"AND recorded_at BETWEEN ? AND ? ORDER BY recorded_at DESC",
        (sensor_id, start_s, end_s),
    ).fetchall()
    for row in candidates:
        utc = datetime.strptime(row["recorded_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        if utc.astimezone().date() == day_date:
            return row
    return None


def set_reading_cell(sensor_id: int, metric_key: str, day: str, value: float | None) -> None:
    """Create/update/clear a Manual Sensor's Reading for one day (see CONTEXT.md: View Data; ADR
    0021) — value already in storage units (Celsius for temperature). value=None clears the cell:
    NULLs just this metric's column if the row still holds another metric's value (a single
    sensor_reading row can carry several metrics from one log action — see db/schema.sql), else
    deletes the row outright so no all-NULL husk is left behind. Only ever touches the most recent
    same-day row for this metric, matching what the cell displays when a day already has more than
    one (see ADR 0021's Consequences)."""
    metric = et.metric_by_key(metric_key)
    column = metric.reading_column
    with get_connection() as conn:
        sensor = conn.execute("SELECT tracking_mode FROM sensor WHERE id = ?", (sensor_id,)).fetchone()
        if sensor is None:
            raise ValueError("Sensor not found.")
        if sensor["tracking_mode"] != "manual":
            raise ValueError("Only a Manual Sensor's Reading can be edited here.")
        existing = _find_reading_for_local_day(conn, sensor_id, column, day)
        if value is None:
            if existing is None:
                return
            other_metrics_set = any(
                existing[m.reading_column] is not None
                for m in et.TARGET_RANGE_METRICS if m.reading_column != column
            )
            if other_metrics_set:
                conn.execute(f"UPDATE sensor_reading SET {column} = NULL WHERE id = ?", (existing["id"],))
            else:
                conn.execute("DELETE FROM sensor_reading WHERE id = ?", (existing["id"],))
            return
        if existing is not None:
            conn.execute(f"UPDATE sensor_reading SET {column} = ? WHERE id = ?", (value, existing["id"]))
        else:
            conn.execute(
                f"INSERT INTO sensor_reading (sensor_id, recorded_at, {column}) VALUES (?, ?, ?)",
                (sensor_id, _local_noon_utc_stamp(day), value),
            )


def set_care_event_cell(enclosure_id: int, kind: str, day: str, time_str: str | None,
                         note: str | None, animal_id: int | None) -> None:
    """Create/update a Care Event for one day (see CONTEXT.md: View Data; ADR 0021) — only ever
    touches the most recent same-day row for this kind, same rule as set_reading_cell above."""
    if kind not in CARE_EVENT_KINDS:
        raise ValueError(f"Unknown care event kind: {kind!r}")
    if animal_id is not None and kind != "feeding":
        raise ValueError("Spot-feed (picking one Animal) only applies to Feeding.")
    occurred_at = f"{day} {time_str or '12:00'}:00"
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM care_event WHERE enclosure_id = ? AND kind = ? AND substr(occurred_at, 1, 10) = ? "
            "ORDER BY occurred_at DESC, id DESC LIMIT 1",
            (enclosure_id, kind, day),
        ).fetchone()
        if existing is not None:
            conn.execute(
                "UPDATE care_event SET occurred_at = ?, note = ?, animal_id = ? WHERE id = ?",
                (occurred_at, note or None, animal_id, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO care_event (enclosure_id, animal_id, kind, occurred_at, note) VALUES (?, ?, ?, ?, ?)",
                (enclosure_id, animal_id, kind, occurred_at, note or None),
            )


def delete_care_event_cell(enclosure_id: int, kind: str, day: str) -> None:
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM care_event WHERE enclosure_id = ? AND kind = ? AND substr(occurred_at, 1, 10) = ? "
            "ORDER BY occurred_at DESC, id DESC LIMIT 1",
            (enclosure_id, kind, day),
        ).fetchone()
        if existing is not None:
            conn.execute("DELETE FROM care_event WHERE id = ?", (existing["id"],))


def _find_animal_log_for_local_day(conn: sqlite3.Connection, animal_id: int, column: str, day: str) -> sqlite3.Row | None:
    """Same shape as _find_reading_for_local_day above, for animal_log — see CONTEXT.md: Animal
    Log. column must already be a validated column name (never raw form input) before it reaches
    this f-string."""
    day_date = date.fromisoformat(day)
    start_s, end_s = _utc_query_bounds([day_date])
    candidates = conn.execute(
        f"SELECT * FROM animal_log WHERE animal_id = ? AND {column} IS NOT NULL "
        f"AND occurred_at BETWEEN ? AND ? ORDER BY occurred_at DESC",
        (animal_id, start_s, end_s),
    ).fetchall()
    for row in candidates:
        utc = datetime.strptime(row["occurred_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        if utc.astimezone().date() == day_date:
            return row
    return None


def set_animal_metric_cell(animal_id: int, field: str, day: str, value: float | None) -> None:
    """Create/update/clear one Animal Log numeric metric (Weight/Length/Count) for one day — same
    "null the column, else delete the row" rule as set_reading_cell, since one animal_log row can
    likewise carry more than one of these fields (see CONTEXT.md: Animal Log; ADR 0021)."""
    valid_fields = {f[0] for f in _ANIMAL_METRIC_FIELDS}
    if field not in valid_fields:
        raise ValueError(f"Unknown Animal Log field: {field!r}")
    with get_connection() as conn:
        animal = conn.execute("SELECT id FROM animal WHERE id = ?", (animal_id,)).fetchone()
        if animal is None:
            raise ValueError("Animal not found.")
        existing = _find_animal_log_for_local_day(conn, animal_id, field, day)
        if value is None:
            if existing is None:
                return
            other_fields_set = any(
                existing[c] is not None for c in _ANIMAL_LOG_VALUE_COLUMNS if c != field
            )
            if other_fields_set:
                conn.execute(f"UPDATE animal_log SET {field} = NULL WHERE id = ?", (existing["id"],))
            else:
                conn.execute("DELETE FROM animal_log WHERE id = ?", (existing["id"],))
            return
        if existing is not None:
            conn.execute(f"UPDATE animal_log SET {field} = ? WHERE id = ?", (value, existing["id"]))
        else:
            conn.execute(
                f"INSERT INTO animal_log (animal_id, occurred_at, {field}) VALUES (?, ?, ?)",
                (animal_id, _local_noon_utc_stamp(day), value),
            )


def set_animal_condition_cell(animal_id: int, day: str, condition: str, note: str | None) -> None:
    """Create/update one day's Condition (+ optional note) — condition and note are always written
    together as a pair, unlike Weight/Length/Count which are independent of each other and of
    Condition (see CONTEXT.md: Animal Log)."""
    if condition not in ANIMAL_CONDITIONS:
        raise ValueError(f"Unknown Condition: {condition!r}")
    with get_connection() as conn:
        existing = _find_animal_log_for_local_day(conn, animal_id, "condition", day)
        if existing is not None:
            conn.execute(
                "UPDATE animal_log SET condition = ?, note = ? WHERE id = ?",
                (condition, note or None, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO animal_log (animal_id, occurred_at, condition, note) VALUES (?, ?, ?, ?)",
                (animal_id, _local_noon_utc_stamp(day), condition, note or None),
            )


def delete_animal_condition_cell(animal_id: int, day: str) -> None:
    with get_connection() as conn:
        existing = _find_animal_log_for_local_day(conn, animal_id, "condition", day)
        if existing is None:
            return
        other_fields_set = any(existing[c] is not None for c in ("weight_g", "length_cm", "count"))
        if other_fields_set:
            conn.execute("UPDATE animal_log SET condition = NULL, note = NULL WHERE id = ?", (existing["id"],))
        else:
            conn.execute("DELETE FROM animal_log WHERE id = ?", (existing["id"],))
