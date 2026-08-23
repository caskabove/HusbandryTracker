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


def _days_since(occurred_at: str | None) -> int | None:
    if occurred_at is None:
        return None
    then = datetime.fromisoformat(occurred_at)
    return (datetime.now() - then).days


def get_dashboard_enclosures() -> list[dict]:
    with get_connection() as conn:
        enclosures = [dict(row) for row in conn.execute("SELECT * FROM enclosure ORDER BY name")]

        for enclosure in enclosures:
            eid = enclosure["id"]

            enclosure["animals"] = [
                dict(row) for row in conn.execute("SELECT * FROM animal WHERE enclosure_id = ?", (eid,))
            ]

            sensors = [dict(row) for row in conn.execute("SELECT * FROM sensor WHERE enclosure_id = ?", (eid,))]
            for sensor in sensors:
                latest = conn.execute(
                    """SELECT temperature_c, humidity_pct, battery_pct, recorded_at FROM sensor_reading
                       WHERE sensor_id = ? ORDER BY recorded_at DESC LIMIT 1""",
                    (sensor["id"],),
                ).fetchone()
                sensor["latest_reading"] = dict(latest) if latest else None
            enclosure["sensors"] = sensors

            plugs = [dict(row) for row in conn.execute("SELECT * FROM plug WHERE enclosure_id = ?", (eid,))]
            for plug in plugs:
                latest = conn.execute(
                    """SELECT is_on, recorded_at FROM plug_state_transition
                       WHERE plug_id = ? ORDER BY recorded_at DESC LIMIT 1""",
                    (plug["id"],),
                ).fetchone()
                plug["latest_transition"] = dict(latest) if latest else None
                # Schedule inference (on-time + duration derived from transition history) isn't
                # built yet — see docs/PHASE1.md "What's NOT built yet". Placeholder for now.
                # A Manual Plug has no transitions to infer from at all — see CONTEXT.md: Schedule —
                # it shows its Declared Schedule instead, entered directly in the Admin UI.
                plug["inferred_schedule"] = None
            enclosure["plugs"] = plugs

            care = {}
            for kind in CARE_EVENT_KINDS:
                latest = conn.execute(
                    """SELECT occurred_at FROM care_event
                       WHERE enclosure_id = ? AND kind = ? ORDER BY occurred_at DESC LIMIT 1""",
                    (eid, kind),
                ).fetchone()
                occurred_at = latest["occurred_at"] if latest else None
                care[kind] = {"occurred_at": occurred_at, "days_since": _days_since(occurred_at)}
            enclosure["care"] = care

    return enclosures


def log_care_event(enclosure_id: int, kind: str, note: str | None = None, occurred_at: str | None = None) -> None:
    """occurred_at lets a Care Event be backdated to when it actually happened instead of always
    being "now" — see CONTEXT.md: Care Event. Pass None (the default) to log it as now."""
    if kind not in CARE_EVENT_KINDS:
        raise ValueError(f"Unknown care event kind: {kind!r}")
    with get_connection() as conn:
        if occurred_at:
            conn.execute(
                "INSERT INTO care_event (enclosure_id, kind, occurred_at, note) VALUES (?, ?, ?, ?)",
                (enclosure_id, kind, occurred_at, note),
            )
        else:
            conn.execute(
                "INSERT INTO care_event (enclosure_id, kind, note) VALUES (?, ?, ?)",
                (enclosure_id, kind, note),
            )


def log_reading(sensor_id: int, temperature_c: float | None, humidity_pct: float | None,
                 recorded_at: str | None = None) -> None:
    """Hand-logs a Reading for a Manual Sensor (see CONTEXT.md: Reading) — reuses the same
    sensor_reading table a Smart Sensor's auto-collected Readings go into, so the dashboard's latest-
    reading and Target Range color-coding work unchanged either way. recorded_at backdates it to when
    the measurement was actually taken; pass None (the default) to log it as now."""
    if temperature_c is None and humidity_pct is None:
        raise ValueError("Enter at least one value (temperature or humidity) to log a Reading.")
    with get_connection() as conn:
        if recorded_at:
            conn.execute(
                "INSERT INTO sensor_reading (sensor_id, recorded_at, temperature_c, humidity_pct) VALUES (?, ?, ?, ?)",
                (sensor_id, recorded_at, temperature_c, humidity_pct),
            )
        else:
            conn.execute(
                "INSERT INTO sensor_reading (sensor_id, temperature_c, humidity_pct) VALUES (?, ?, ?)",
                (sensor_id, temperature_c, humidity_pct),
            )
