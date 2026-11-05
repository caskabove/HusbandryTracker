"""Query/mutation layer behind the Backfill Wizard (see CONTEXT.md: Backfill Wizard; ADR 0053).

Seeds a chosen Enclosure's Manual Sensor(s) with a week or month of placeholder Readings drawn
from each Sensor's own Target Range, so a brand-new graph isn't just a single dot. Writes through
view_data_queries.add_reading_entry() — the exact function View Data's own backdated Period-Slot
entry already uses — so every seeded row is, mechanically, an ordinary hand-logged Manual Sensor
Reading; nothing downstream (Graphs, Sparkline, View Data's own edit/delete) needs to know or care
that it came from here. Never overwrites a day that already has a real (or previously-seeded)
value for that Sensor+metric, which is what lets "one real dot already there" fill in around it
correctly.

Every seeded value sits near the *middle* of the Target Range — "ideal," not a wide random scatter
— with only a small jitter so the result reads as a real, slightly-noisy log rather than a
perfectly flat line. Temperature and Humidity specifically get a real Morning/Afternoon/Night
diurnal cycle (see CONTEXT.md: Period Slot) instead of one flat value per day, and the two are
deliberately coupled opposite each other — Afternoon warmest and driest, Night coolest and most
humid, Morning in between — since that's how an enclosure actually behaves (daytime heat drives
humidity down; it recovers overnight as things cool). Every other metric keeps one seeded value per
day (or every 7th day for a "slow"-Volatility one) at the Afternoon slot.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schemas import enclosure_types as et
from web import admin_queries as q
from web import view_data_queries as vdq

# Temperature and Humidity get a real Morning/Afternoon/Night cycle every day regardless of their
# own Volatility setting (see CONTEXT.md: Volatility) — a diurnal swing isn't a "how often do you
# test this" cadence question, it happens every day by nature. Every other metric keeps the
# existing single-point-per-day/week cadence below.
_DIURNAL_METRIC_KEYS = ("temperature", "humidity")

# Fraction of the way from min to max the "ideal" value sits at each Period Slot (see CONTEXT.md:
# Period Slot) — Afternoon is warmest/driest (daytime heat source running), Night is coolest/most
# humid, Morning is in between, rising out of the overnight low toward the afternoon peak. Humidity
# mirrors Temperature exactly (1 - fraction) so the two always move opposite each other.
_DIURNAL_FRACTIONS: dict[str, dict[str, float]] = {
    "temperature": {"night": 0.15, "morning": 0.45, "afternoon": 0.85},
    "humidity": {"night": 0.85, "morning": 0.55, "afternoon": 0.15},
}
# +/- this fraction of the Target Range's span, applied per point — enough that a week/month of
# points doesn't look robotically identical, never enough to cross into an adjacent Period Slot's
# own fraction above (the smallest gap between two slots' fractions is 0.30) or to read as a spike.
_DIURNAL_JITTER = 0.03

# Every non-diurnal metric (pH, water-chemistry, ...) gets one "ideal" point centered on the
# Target Range's midpoint instead — same small-jitter philosophy, no day/night shape to it.
_IDEAL_JITTER = 0.06

# Which Period Slot a non-diurnal metric's single daily/weekly Reading lands on.
_SEED_SLOT = "afternoon"

# How many days apart a "slow"-Volatility metric (see CONTEXT.md: Volatility) gets seeded — a
# water-chemistry test kit's realistic cadence, vs. every day for a "fast" one. Never applies to
# Temperature/Humidity — see _DIURNAL_METRIC_KEYS above.
_SLOW_STEP_DAYS = 7


def _sensor_metrics(sensor: dict, enclosure_type: str) -> list[et.TargetRangeMetric]:
    """The Target Range metrics this Sensor actually has both a min and max set for, restricted to
    whatever its Enclosure Type allows — the same pair of checks View Data's own _metric_shown()
    and admin_queries' save-time validation already apply."""
    return [
        m for m in et.target_range_metrics_for(enclosure_type)
        if sensor.get(m.min_column) is not None and sensor.get(m.max_column) is not None
    ]


def _f_to_c(celsius: float) -> float:
    return celsius * 9 / 5 + 32


def _display_range(metric: et.TargetRangeMetric, mn: float, mx: float) -> dict:
    """Target Range min/max in whatever unit the Admin UI already shows them in — Fahrenheit for
    Temperature (stored as Celsius), the metric's own unit otherwise — same conversion
    web/templates/admin_enclosure.html already applies via its c_to_f filter, done here instead so
    the Sensor-picker template stays a plain loop with no Jinja-side unit math."""
    if metric.converts_f_c:
        mn, mx, unit = _f_to_c(mn), _f_to_c(mx), "°F"
    else:
        unit = metric.unit
    return {"min": round(mn, metric.decimals), "max": round(mx, metric.decimals), "unit": unit}


def eligible_sensors_for_enclosure(enclosure: dict) -> list[dict]:
    """The Backfill Wizard's Sensor-picker list (step 3) — every Manual Sensor on this Enclosure
    with at least one Target Range metric set. Smart Sensors are never eligible (see CONTEXT.md:
    Backfill Wizard — their history comes from a real device)."""
    out = []
    for sensor in enclosure["sensors"]:
        if sensor["tracking_mode"] != "manual":
            continue
        metrics = _sensor_metrics(sensor, enclosure["enclosure_type"])
        if not metrics:
            continue
        existing_count = sum(len(vdq.list_reading_entries(sensor["id"], m.key)) for m in metrics)
        out.append({
            "id": sensor["id"],
            "label": sensor["label"],
            "metrics": [
                {
                    "label": m.label or m.key.replace("_", " ").title(),
                    **_display_range(m, sensor[m.min_column], sensor[m.max_column]),
                }
                for m in metrics
            ],
            "existing_reading_count": existing_count,
        })
    return out


def _frac_value(mn: float, mx: float, frac: float, jitter: float) -> float:
    span = mx - mn
    if span <= 0:
        return round(mn, 3)
    frac = frac + random.uniform(-jitter, jitter)
    return round(mn + frac * span, 3)


def run_backfill(enclosure_id: int, sensor_ids: list[int], range_key: str) -> dict:
    """Fills every selected Sensor's eligible metrics across the chosen window (see
    view_data_queries.RANGE_OPTIONS for "week"/"month"). Returns a summary for the Backfill
    Wizard's Done screen: how many Sensors actually got at least one new point, and how many
    points were written in total."""
    enclosure = q.get_enclosure(enclosure_id)
    if enclosure is None:
        raise ValueError("Enclosure not found.")
    start, end, _ = vdq.compute_window(range_key, None)
    days = vdq.date_list(start, end)
    sensors_by_id = {s["id"]: s for s in enclosure["sensors"]}

    sensors_filled = 0
    points_written = 0
    for sensor_id in sensor_ids:
        sensor = sensors_by_id.get(sensor_id)
        if sensor is None or sensor["tracking_mode"] != "manual":
            continue
        metrics = _sensor_metrics(sensor, enclosure["enclosure_type"])
        if not metrics:
            continue
        sensor_points = 0
        for metric in metrics:
            existing_days = {e["date"] for e in vdq.list_reading_entries(sensor_id, metric.key)}
            mn, mx = sensor[metric.min_column], sensor[metric.max_column]
            if metric.key in _DIURNAL_METRIC_KEYS:
                for day in days:
                    day_iso = day.isoformat()
                    if day_iso in existing_days:
                        continue
                    for slot, frac in _DIURNAL_FRACTIONS[metric.key].items():
                        value = _frac_value(mn, mx, frac, _DIURNAL_JITTER)
                        vdq.add_reading_entry(sensor_id, metric.key, day_iso, slot, value)
                        sensor_points += 1
                continue
            step = 1 if et.effective_volatility(sensor, metric) == "fast" else _SLOW_STEP_DAYS
            for i, day in enumerate(days):
                if i % step != 0:
                    continue
                day_iso = day.isoformat()
                if day_iso in existing_days:
                    continue
                value = _frac_value(mn, mx, 0.5, _IDEAL_JITTER)
                vdq.add_reading_entry(sensor_id, metric.key, day_iso, _SEED_SLOT, value)
                sensor_points += 1
        if sensor_points:
            sensors_filled += 1
            points_written += sensor_points

    return {
        "sensors_filled": sensors_filled, "points_written": points_written,
        "days": len(days), "range_key": range_key,
    }
