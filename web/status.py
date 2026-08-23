"""Color-status logic shared by every panel on the dashboard.

Two distinct rules live here — see CONTEXT.md for the terms:

- Target Range (Sensor readings): simple in-range/out-of-range. No yellow tier yet — the original
  spec only defined green/yellow/red for Care Interval staleness, not for how far out-of-range a
  reading has to be to escalate from yellow to red. Binary for now; add a tolerance band later if
  a plain in/out signal turns out to be too coarse.

- Care Interval (days since last Feeding/Watering/Spot-clean/Deep-clean): the ORIGINAL spec gave
  two concrete examples with different cadences —
      feeding (interval=7): green days 1-5, yellow 6-7, red 8+
      watering (interval=3): green days 1-2, yellow 3, red 4+
  Neither is a fixed day-count once intervals are per-enclosure configurable. The formula below
  (yellow starts at ceil(0.8 * interval), red starts at interval + 1) was derived to fit BOTH
  examples exactly. It's a generalization, not something the user specified directly — revisit if
  it doesn't feel right in practice.
"""
from __future__ import annotations

import math
from enum import Enum


class Status(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    UNKNOWN = "unknown"  # no data yet — distinct from red; nothing to judge, not a violation


def target_range_status(value: float | None, min_value: float | None, max_value: float | None) -> Status:
    if value is None:
        return Status.UNKNOWN
    if min_value is None and max_value is None:
        return Status.UNKNOWN  # no Target Range configured for this Sensor yet
    if min_value is not None and value < min_value:
        return Status.RED
    if max_value is not None and value > max_value:
        return Status.RED
    return Status.GREEN


def care_interval_status(days_since_last: int | None, interval_days: int) -> Status:
    """days_since_last is None when the Care Event has never been logged for this Enclosure."""
    if days_since_last is None:
        return Status.RED  # never logged — treated as overdue, not "no data"
    yellow_start = math.ceil(0.8 * interval_days)
    red_start = interval_days + 1
    if days_since_last >= red_start:
        return Status.RED
    if days_since_last >= yellow_start:
        return Status.YELLOW
    return Status.GREEN
