"""Query layer behind the Graphs page (see CONTEXT.md: Graphs, Overlay, Sparkline; ADR 0022).

Builds the same rows View Data (web/view_data_queries.py) shows, as time series instead of a
day-bucketed table. Strictly read-only — unlike view_data_queries.py there are no set_*_cell
functions here; corrections to the underlying data still happen on View Data's own grid.

Granularity split (see ADR 0022): a Smart Sensor's dedupe window is only 5 seconds (see
plugins/govee_ble/plugin.py), so it can write a new sensor_reading row every 5-30 seconds
continuously — tens of thousands of rows a day. Raw-rendering that for every range View Data
already offers (Week through Year) isn't viable in a browser, so Week and Month plot raw points for
auto-collected series (Smart Sensor Readings, Plug Data Capture) while 90 Days/180 Days/Year switch
those two to server-side aggregated buckets (min/avg/max per bucket — hourly through 180 Days, daily
for Year). A Manual Sensor's Readings, Care Events, and Animal Log entries are never high-volume
enough to need this and always plot raw, regardless of range.

Each row is a dict: {key, label, chart_type, unit, series, shape/decimals (line rows only)}.
- chart_type "line": a numeric series. shape "raw" -> series is [[epoch_ms, value], ...];
  shape "band" -> series is [[epoch_ms, min, avg, max], ...]. decimals is the tooltip's display
  precision — a Sensor Reading row uses its own TargetRangeMetric.decimals (Specific Gravity needs
  all 3 to mean anything; a flat 2 everywhere used to clip it), everything else defaults to 2.
- chart_type "marker": series is [[epoch_ms, label_text], ...] — a Care Event, a Plug Status
  change, or an Animal Log Condition has a moment but no Y-value of its own (see CONTEXT.md: Graphs).

Two different timestamp conventions are in play, matching view_data_queries.py's own split (see its
module docstring, ADR 0021): sensor_reading/plug_state_transition/plug_command_log/plug_reading/
animal_log are true UTC with no backdating path, so they're converted before use; care_event.occurred_at
is already local wall-clock (the Enclosure page's Today/Yesterday/N-days-ago buttons compute and
store it that way directly), so it's treated as local time as-is, never converted.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.db import get_connection
from schemas import enclosure_types as et
from web.queries import ANIMAL_CONDITION_LABELS, CARE_EVENT_KINDS
from web.view_data_queries import _metric_shown

_PLUG_TELEMETRY_FIELDS = (("watts", "W"), ("volts", "V"), ("amps", "A"))
_ANIMAL_METRIC_FIELDS = (("weight_g", "Weight", "g"), ("length_cm", "Length", "cm"), ("count", "Count", ""))

# Week=7 and Month=30 (see view_data_queries.py's RANGE_OPTIONS) stay raw for auto-collected series;
# everything longer (90/180/365 days) aggregates them instead — see ADR 0022.
_RAW_TIER_MAX_DAYS = 30
# Bucket size for an aggregated series: hourly through 180 Days, daily only once a window is long
# enough (Year) that even hourly buckets would be more detail than the chart can usefully show.
_HOURLY_BUCKET_MAX_DAYS = 180


def _c_to_f(celsius: float | None) -> float | None:
    return None if celsius is None else celsius * 9 / 5 + 32


def _epoch_ms_utc(ts: str) -> int:
    """ts is a true-UTC 'YYYY-MM-DD HH:MM:SS' (or 'YYYY-MM-DD') stamp -> epoch milliseconds."""
    if len(ts) <= 10:
        ts = f"{ts} 00:00:00"
    utc = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return int(utc.timestamp() * 1000)


def _epoch_ms_local(ts: str) -> int:
    """ts is already local wall-clock (care_event.occurred_at — see module docstring) ->
    epoch milliseconds, treating the naive stamp as this machine's own local time."""
    local = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").astimezone()
    return int(local.timestamp() * 1000)


def _utc_bounds(start: date, end: date) -> tuple[str, str]:
    """A generously padded UTC range guaranteed to cover every row that could land, once converted
    to local time, within [start, end] — same one-day-padding precedent as
    view_data_queries.py's _utc_query_bounds. A chart can tolerate a little slop at its edges (unlike
    a day-bucketed table cell, which needs an exact local day), so there's no need to trim it back
    down afterward."""
    start_dt = datetime.combine(start, datetime.min.time()) - timedelta(days=1)
    end_dt = datetime.combine(end, datetime.min.time()) + timedelta(days=2)
    return start_dt.strftime("%Y-%m-%d %H:%M:%S"), end_dt.strftime("%Y-%m-%d %H:%M:%S")


def _is_raw_tier(days: int) -> bool:
    return days <= _RAW_TIER_MAX_DAYS


def _bucket_expr(ts_column: str, days: int) -> str:
    """SQLite expression bucketing a UTC timestamp column for an aggregated series (see module
    docstring) — bucketed on the raw UTC string, not converted to local time first: a chart's bucket
    boundaries don't need to land on local hour/day lines the way View Data's day columns do, only
    the resulting point's own x-position (computed from the bucket's own stamp) needs to be correct,
    and it is either way."""
    if days <= _HOURLY_BUCKET_MAX_DAYS:
        return f"strftime('%Y-%m-%d %H:00:00', {ts_column})"
    return f"substr({ts_column}, 1, 10)"


def _raw_numeric_series(conn: sqlite3.Connection, table: str, id_column: str, id_value: int,
                         ts_column: str, value_column: str, start: date, end: date) -> list[list]:
    start_s, end_s = _utc_bounds(start, end)
    rows = conn.execute(
        f"SELECT {ts_column} AS ts, {value_column} AS value FROM {table} "
        f"WHERE {id_column} = ? AND {value_column} IS NOT NULL AND {ts_column} BETWEEN ? AND ? "
        f"ORDER BY {ts_column} ASC",
        (id_value, start_s, end_s),
    ).fetchall()
    return [[_epoch_ms_utc(row["ts"]), row["value"]] for row in rows]


def _bucketed_numeric_series(conn: sqlite3.Connection, table: str, id_column: str, id_value: int,
                              ts_column: str, value_column: str, start: date, end: date, days: int) -> list[list]:
    start_s, end_s = _utc_bounds(start, end)
    bucket_expr = _bucket_expr(ts_column, days)
    rows = conn.execute(
        f"SELECT {bucket_expr} AS bucket, MIN({value_column}) AS lo, AVG({value_column}) AS avg, MAX({value_column}) AS hi "
        f"FROM {table} WHERE {id_column} = ? AND {value_column} IS NOT NULL AND {ts_column} BETWEEN ? AND ? "
        f"GROUP BY bucket ORDER BY bucket ASC",
        (id_value, start_s, end_s),
    ).fetchall()
    return [[_epoch_ms_utc(row["bucket"]), row["lo"], row["avg"], row["hi"]] for row in rows]


def _reading_line_row(conn: sqlite3.Connection, sensor: dict, metric: et.TargetRangeMetric,
                       start: date, end: date, days: int) -> dict:
    """A Manual Sensor's Readings always plot raw (sparse by nature — see module docstring); a Smart
    Sensor's follow the Week/Month-raw, longer-aggregated split."""
    print(f"HEY    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    column = metric.reading_column
    raw = sensor["tracking_mode"] == "manual" or _is_raw_tier(days)
    label_suffix = metric.label or metric.key.replace("_", " ").title()
    unit = "°F" if metric.converts_f_c else metric.unit
    if raw:
        series = _raw_numeric_series(conn, "sensor_reading", "sensor_id", sensor["id"], "recorded_at", column, start, end)
        if metric.converts_f_c:
            series = [[t, _c_to_f(v)] for t, v in series]
        print(f"SERIES RAW----")
        shape = "raw"
    else:
        series = _bucketed_numeric_series(conn, "sensor_reading", "sensor_id", sensor["id"], "recorded_at", column, start, end, days)
        if metric.converts_f_c:
            series = [[t, _c_to_f(lo), _c_to_f(avg), _c_to_f(hi)] for t, lo, avg, hi in series]

        print(f"SERIES BAND----")
        shape = "band"
    return {
        "key": f"reading-{sensor['id']}-{metric.key}",
        "label": f"{sensor['label']} — {label_suffix}",
        "chart_type": "line",
        "shape": shape,
        "unit": unit,
        "series": series,
        "decimals": metric.decimals,
    }


def _plug_telemetry_line_row(conn: sqlite3.Connection, plug: dict, field: str, unit: str,
                              start: date, end: date, days: int) -> dict:
    if _is_raw_tier(days):
        series = _raw_numeric_series(conn, "plug_reading", "plug_id", plug["id"], "recorded_at", field, start, end)
        shape = "raw"
    else:
        series = _bucketed_numeric_series(conn, "plug_reading", "plug_id", plug["id"], "recorded_at", field, start, end, days)
        shape = "band"
    return {
        "key": f"plug-telemetry-{plug['id']}-{field}",
        "label": f"{plug['label']} — {field.capitalize()}",
        "chart_type": "line",
        "shape": shape,
        "unit": unit,
        "series": series,
        "decimals": 2,
    }


def _plug_status_marker_row(conn: sqlite3.Connection, plug: dict, start: date, end: date) -> dict:
    start_s, end_s = _utc_bounds(start, end)
    if plug["tracking_mode"] == "smart":
        rows = conn.execute(
            "SELECT recorded_at AS ts, is_on FROM plug_state_transition "
            "WHERE plug_id = ? AND recorded_at BETWEEN ? AND ? ORDER BY recorded_at ASC",
            (plug["id"], start_s, end_s),
        ).fetchall()
    else:
        # A Manual Plug's status is its own self-reported Command log — see CONTEXT.md: Command.
        rows = conn.execute(
            "SELECT requested_at AS ts, is_on FROM plug_command_log "
            "WHERE plug_id = ? AND requested_at BETWEEN ? AND ? ORDER BY requested_at ASC",
            (plug["id"], start_s, end_s),
        ).fetchall()
    series = [[_epoch_ms_utc(row["ts"]), "On" if row["is_on"] else "Off"] for row in rows]
    return {
        "key": f"plug-status-{plug['id']}",
        "label": f"{plug['label']} — Status",
        "chart_type": "marker",
        "unit": "",
        "series": series,
    }


def _plug_rows(conn: sqlite3.Connection, plug: dict, start: date, end: date, days: int) -> list[dict]:
    rows = [_plug_status_marker_row(conn, plug, start, end)]
    if plug["tracking_mode"] == "smart":
        rows += [_plug_telemetry_line_row(conn, plug, field, unit, start, end, days) for field, unit in _PLUG_TELEMETRY_FIELDS]
    return rows


def _care_event_marker_row(conn: sqlite3.Connection, enclosure_id: int, kind: str, start: date, end: date) -> dict:
    start_s, end_s = start.isoformat(), end.isoformat()
    rows = conn.execute(
        """SELECT ce.occurred_at, ce.note, a.name AS animal_name
           FROM care_event ce LEFT JOIN animal a ON a.id = ce.animal_id
           WHERE ce.enclosure_id = ? AND ce.kind = ? AND substr(ce.occurred_at, 1, 10) BETWEEN ? AND ?
           ORDER BY ce.occurred_at ASC""",
        (enclosure_id, kind, start_s, end_s),
    ).fetchall()
    series = []
    for row in rows:
        text = kind.replace("_", " ").capitalize()
        if row["animal_name"]:
            text += f" — {row['animal_name']}"
        if row["note"]:
            text += f" ({row['note']})"
        series.append([_epoch_ms_local(row["occurred_at"]), text])
    return {
        "key": f"care-{enclosure_id}-{kind}",
        "label": kind.replace("_", " ").capitalize(),
        "chart_type": "marker",
        "unit": "",
        "series": series,
    }


def _animal_metric_line_row(conn: sqlite3.Connection, animal: dict, field: str, label: str, unit: str,
                             start: date, end: date) -> dict:
    """Always raw — an Animal Log entry is self-reported and never high-volume (see module
    docstring)."""
    series = _raw_numeric_series(conn, "animal_log", "animal_id", animal["id"], "occurred_at", field, start, end)
    return {
        "key": f"animal-{animal['id']}-{field}",
        "label": f"{animal['name']} — {label}",
        "chart_type": "line",
        "shape": "raw",
        "unit": unit,
        "series": series,
        "decimals": 2,
    }


def _animal_condition_marker_row(conn: sqlite3.Connection, animal: dict, start: date, end: date) -> dict:
    start_s, end_s = _utc_bounds(start, end)
    rows = conn.execute(
        "SELECT occurred_at AS ts, condition, note FROM animal_log "
        "WHERE animal_id = ? AND condition IS NOT NULL AND occurred_at BETWEEN ? AND ? "
        "ORDER BY occurred_at ASC",
        (animal["id"], start_s, end_s),
    ).fetchall()
    series = []
    for row in rows:
        text = ANIMAL_CONDITION_LABELS[row["condition"]]
        if row["note"]:
            text += f" ({row['note']})"
        series.append([_epoch_ms_utc(row["ts"]), text])
    return {
        "key": f"animal-{animal['id']}-condition",
        "label": f"{animal['name']} — Condition",
        "chart_type": "marker",
        "unit": "",
        "series": series,
    }


def _animal_graph_rows(conn: sqlite3.Connection, animal: dict, start: date, end: date) -> list[dict]:
    rows = [_animal_metric_line_row(conn, animal, field, label, unit, start, end)
            for field, label, unit in _ANIMAL_METRIC_FIELDS]
    rows.append(_animal_condition_marker_row(conn, animal, start, end))
    return rows


def build_room_graph_sections(room_id: int, start: date, end: date, days: int) -> list[dict]:
    """Room's own Sensors/Plugs only — never rolls up its Enclosures' own data, same boundary as
    View Data and Refresh (see CONTEXT.md: Graphs, Refresh; ADR 0021, 0022)."""
    with get_connection() as conn:
        sensors = [dict(r) for r in conn.execute("SELECT * FROM sensor WHERE room_id = ? ORDER BY label", (room_id,))]
        plugs = [dict(r) for r in conn.execute("SELECT * FROM plug WHERE room_id = ? ORDER BY label", (room_id,))]

        reading_rows = [
            _reading_line_row(conn, sensor, metric, start, end, days)
            for sensor in sensors
            for metric in et.TARGET_RANGE_METRICS
            if _metric_shown(conn, sensor, metric)
        ]
        plug_rows = [row for plug in plugs for row in _plug_rows(conn, plug, start, end, days)]

    sections = []
    if reading_rows:
        sections.append({"title": "Sensor Readings", "rows": reading_rows})
    if plug_rows:
        sections.append({"title": "Plugs", "rows": plug_rows})
    return sections


def build_enclosure_graph_sections(enclosure_id: int, start: date, end: date, days: int) -> list[dict]:
    with get_connection() as conn:
        sensors = [dict(r) for r in conn.execute("SELECT * FROM sensor WHERE enclosure_id = ? ORDER BY label", (enclosure_id,))]
        plugs = [dict(r) for r in conn.execute(
            """SELECT p.* FROM plug p JOIN plug_enclosure pe ON pe.plug_id = p.id
               WHERE pe.enclosure_id = ? ORDER BY p.label""",
            (enclosure_id,),
        )]
        animals = [dict(r) for r in conn.execute("SELECT * FROM animal WHERE enclosure_id = ? ORDER BY name", (enclosure_id,))]

        reading_rows = [
            _reading_line_row(conn, sensor, metric, start, end, days)
            for sensor in sensors
            for metric in et.TARGET_RANGE_METRICS
            if _metric_shown(conn, sensor, metric)
        ]
        # All four Care Event kinds always show, even with nothing logged yet — same precedent as
        # View Data's own Care Events section.
        care_rows = [_care_event_marker_row(conn, enclosure_id, kind, start, end) for kind in CARE_EVENT_KINDS]
        plug_rows = [row for plug in plugs for row in _plug_rows(conn, plug, start, end, days)]
        animal_rows = [row for animal in animals for row in _animal_graph_rows(conn, animal, start, end)]

    sections = []
    if reading_rows:
        sections.append({"title": "Sensor Readings", "rows": reading_rows})
    sections.append({"title": "Care Events", "rows": care_rows})
    if animal_rows:
        sections.append({"title": "Animal Log", "rows": animal_rows})
    if plug_rows:
        sections.append({"title": "Plugs", "rows": plug_rows})
    return sections


def rows_by_key(sections: list[dict], keys: list[str]) -> list[dict]:
    """The Overlay picker's checked rows (see CONTEXT.md: Overlay), in section order, for the one
    additional combined chart the Graphs page draws alongside each row's own default chart. An
    unknown/stale key (e.g. a row that no longer exists) is silently skipped rather than erroring."""
    wanted = set(keys)
    if not wanted:
        return []
    return [row for section in sections for row in section["rows"] if row["key"] in wanted]
