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

- Care Interval, never-logged case: a kind with no Care Event logged at all used to read straight
  Red ("never logged — treated as overdue"). It now reads Unknown ("no data") instead — the Care
  Setup Prompt (see CONTEXT.md) exists to resolve this actively rather than leaving it to the pill
  color alone — but escalates back to Red once it's been nagged about on CARE_NAG_RED_THRESHOLD
  separate calendar days and still has no data, since an unattended Feeding/Watering kind defeats
  the point of tracking it at all. See ADR 0040.
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


SCHEDULE_DRIFT_RED_MINUTES = 60  # drift beyond this is red; between the threshold and this is yellow


def schedule_drift_status(target_time: str | None, detected_time: str | None, threshold_minutes: int) -> Status:
    """Timer Warning (see CONTEXT.md: Target Schedule, Detected Schedule, Timer Warning) — compares
    a Plug's Target Schedule against its Detected Schedule for one of its two times (on or off,
    called separately for each). Both "HH:MM" strings; wraparound-aware (23:50 vs 00:05 is a
    15-minute gap, not a 23-hour one) since a schedule can straddle midnight.

    Green under threshold_minutes, yellow from threshold_minutes up to SCHEDULE_DRIFT_RED_MINUTES,
    red beyond that."""
    if target_time is None or detected_time is None:
        return Status.UNKNOWN  # nothing to compare yet — not a violation
    target_minutes = int(target_time[:2]) * 60 + int(target_time[3:5])
    detected_minutes = int(detected_time[:2]) * 60 + int(detected_time[3:5])
    diff = abs(target_minutes - detected_minutes)
    diff = min(diff, 1440 - diff)
    if diff > SCHEDULE_DRIFT_RED_MINUTES:
        return Status.RED
    if diff >= threshold_minutes:
        return Status.YELLOW
    return Status.GREEN


def acknowledged_drift_status(target_time: str | None, detected_time: str | None,
                              acknowledged_time: str | None, threshold_minutes: int) -> Status:
    """schedule_drift_status() with the user's cleared warning applied (see CONTEXT.md: Timer
    Warning). A drifting detected time the user already cleared — yellow or red — reads UNKNOWN —
    not flagged, but not verified either — until the Detected Schedule moves to a different time."""
    status = schedule_drift_status(target_time, detected_time, threshold_minutes)
    if status in (Status.YELLOW, Status.RED) and detected_time == acknowledged_time:
        return Status.UNKNOWN
    return status


CARE_NAG_RED_THRESHOLD = 3  # separate calendar days the Care Setup Prompt can nag before Red


def care_interval_status(days_since_last: int | None, interval_days: int, nag_count: int = 0) -> Status:
    """days_since_last is None when the Care Event has never been logged for this Enclosure — see
    module docstring above. nag_count (web/admin_queries.py's record_care_nags()) is only consulted
    in that case; once real data exists it's irrelevant."""
    if days_since_last is None:
        return Status.RED if nag_count >= CARE_NAG_RED_THRESHOLD else Status.UNKNOWN
    yellow_start = math.ceil(0.8 * interval_days)
    red_start = interval_days + 1
    if days_since_last >= red_start:
        return Status.RED
    if days_since_last >= yellow_start:
        return Status.YELLOW
    return Status.GREEN
