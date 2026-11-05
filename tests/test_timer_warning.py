"""Timer Warning acknowledgement (see CONTEXT.md: Timer Warning; db/schema.sql's plug.timer_ack_*).

Covers the pure drift check with a cleared warning applied, and the two query-layer rules around
clearing it: clear_timer_warning() stores the current Detected Schedule, and update_plug() re-arms
the warning by resetting that stored value when the Target Schedule changes.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from web import admin_queries as q
from web.status import Status, acknowledged_drift_status, nearest_target_time, schedule_drift_status


# --- pure drift check -----------------------------------------------------------------------------

def test_drift_at_the_threshold_is_yellow_and_beyond_an_hour_is_red():
    assert acknowledged_drift_status("08:00", "08:15", None, 15) is Status.YELLOW
    assert acknowledged_drift_status("08:00", "08:45", None, 15) is Status.YELLOW
    assert acknowledged_drift_status("08:00", "09:00", None, 15) is Status.YELLOW
    assert acknowledged_drift_status("08:00", "09:01", None, 15) is Status.RED


def test_drifting_red_time_acknowledged_at_the_same_detected_time_is_unknown():
    assert acknowledged_drift_status("08:00", "09:30", "09:30", 15) is Status.UNKNOWN


def test_acknowledgement_for_a_different_detected_time_does_not_suppress():
    assert acknowledged_drift_status("08:00", "10:30", "09:30", 15) is Status.RED
    assert acknowledged_drift_status("08:00", "08:45", "08:30", 15) is Status.YELLOW


def test_drifting_yellow_time_acknowledged_at_the_same_detected_time_is_unknown():
    assert acknowledged_drift_status("08:00", "08:45", "08:45", 15) is Status.UNKNOWN


def test_within_threshold_stays_green_regardless_of_acknowledgement():
    assert acknowledged_drift_status("08:00", "08:10", "08:10", 15) is Status.GREEN
    assert acknowledged_drift_status("08:00", "08:10", None, 15) is Status.GREEN


def test_no_target_or_no_detection_is_unknown_regardless_of_acknowledgement():
    assert acknowledged_drift_status(None, "08:45", "08:45", 15) is Status.UNKNOWN
    assert acknowledged_drift_status("08:00", None, None, 15) is Status.UNKNOWN


def test_acknowledged_check_agrees_with_unacknowledged_check_when_nothing_is_cleared():
    for target, detected in [("08:00", "08:05"), ("08:00", "09:00"), ("23:50", "00:05")]:
        assert acknowledged_drift_status(target, detected, None, 15) == schedule_drift_status(target, detected, 15)


def test_stored_utc_time_is_shown_in_local_time():
    # 18:00 local, written the way Ingest writes it (UTC). Passes on any machine's timezone.
    assert q.utc_clock_to_local(_local_to_utc_stamp("2026-10-03 18:00:00")) == "18:00"
    assert q.utc_clock_to_local(_local_to_utc_stamp("2026-10-03 09:05:00")) == "09:05"


# --- multiple Target Schedule cycles (ADR 0057) ---------------------------------------------------

def test_nearest_target_time_picks_the_closest_cycle():
    assert nearest_target_time("21:05", ["08:00", "21:00", None]) == "21:00"
    assert nearest_target_time("08:10", ["08:00", "21:00", None]) == "08:00"


def test_nearest_target_time_is_wraparound_aware():
    # 23:55 is 10 minutes from 00:05 (wraparound) but 11h05m from 12:00 — nearest is 00:05.
    assert nearest_target_time("23:55", ["00:05", "12:00"]) == "00:05"


def test_nearest_target_time_is_none_without_something_to_compare():
    assert nearest_target_time(None, ["08:00", "21:00"]) is None
    assert nearest_target_time("08:00", [None, None]) is None


# --- query layer ----------------------------------------------------------------------------------

def _insert_smart_plug(conn: sqlite3.Connection, target_on: str | None, target_off: str | None,
                        target_on_2: str | None = None, target_off_2: str | None = None) -> int:
    cur = conn.execute(
        """INSERT INTO plug (label, purpose, tracking_mode, plugin, external_id, controller_kind,
                              target_on_time, target_off_time, target_on_time_2, target_off_time_2)
           VALUES ('UTH', 'heat', 'smart', 'tuya_lan', 'dev-1', 'timer', ?, ?, ?, ?)""",
        (target_on, target_off, target_on_2, target_off_2),
    )
    conn.commit()
    return cur.lastrowid


def _local_to_utc_stamp(local_stamp: str) -> str:
    """Stores a transition the way the app does: plugins/common.py writes observed_at in UTC. Takes
    a local "YYYY-MM-DD HH:MM:SS" so each test reads in the time it's about."""
    local = datetime.strptime(local_stamp, "%Y-%m-%d %H:%M:%S").astimezone()
    return local.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _record_transition(conn: sqlite3.Connection, plug_id: int, local_stamp: str, is_on: int) -> None:
    conn.execute(
        "INSERT INTO plug_state_transition (plug_id, recorded_at, is_on) VALUES (?, ?, ?)",
        (plug_id, _local_to_utc_stamp(local_stamp), is_on),
    )
    conn.commit()


def _ack(conn: sqlite3.Connection, plug_id: int) -> tuple[str | None, str | None]:
    row = conn.execute("SELECT timer_ack_on_time, timer_ack_off_time FROM plug WHERE id = ?", (plug_id,)).fetchone()
    return row["timer_ack_on_time"], row["timer_ack_off_time"]


def test_clear_timer_warning_stores_the_current_detected_times(temp_db):
    plug_id = _insert_smart_plug(temp_db, "08:00", "20:00")
    _record_transition(temp_db, plug_id, "2026-10-03 08:45:00", 1)
    _record_transition(temp_db, plug_id, "2026-10-03 20:30:00", 0)

    q.clear_timer_warning(plug_id)

    assert _ack(temp_db, plug_id) == ("08:45", "20:30")


def test_clear_timer_warning_with_no_detection_stores_nothing(temp_db):
    plug_id = _insert_smart_plug(temp_db, "08:00", "20:00")

    q.clear_timer_warning(plug_id)

    assert _ack(temp_db, plug_id) == (None, None)


def test_changing_the_target_schedule_re_arms_a_cleared_warning(temp_db, monkeypatch):
    plug_id = _insert_smart_plug(temp_db, "08:00", "20:00")
    _record_transition(temp_db, plug_id, "2026-10-03 08:45:00", 1)
    q.clear_timer_warning(plug_id)
    assert _ack(temp_db, plug_id)[0] == "08:45"

    _update_plug_targets(plug_id, "08:00", "20:00")  # unchanged target: acknowledgement kept
    assert _ack(temp_db, plug_id)[0] == "08:45"

    _update_plug_targets(plug_id, "08:30", "20:00")  # changed target: acknowledgement reset
    assert _ack(temp_db, plug_id) == (None, None)


def test_changing_only_cycle_2_also_re_arms_a_cleared_warning(temp_db):
    # Cycle 1 unchanged across both update_plug() calls — only Cycle 2 moves — still re-arms
    # (ADR 0057: the re-arm check now covers all 3 cycles, not just Cycle 1).
    plug_id = _insert_smart_plug(temp_db, "08:00", "20:00", "21:00", "23:00")
    _record_transition(temp_db, plug_id, "2026-10-03 21:05:00", 1)
    q.clear_timer_warning(plug_id)
    assert _ack(temp_db, plug_id)[0] == "21:05"

    _update_plug_targets(plug_id, "08:00", "20:00", "21:00", "23:00")  # unchanged: ack kept
    assert _ack(temp_db, plug_id)[0] == "21:05"

    _update_plug_targets(plug_id, "08:00", "20:00", "21:15", "23:00")  # Cycle 2 on-time moved
    assert _ack(temp_db, plug_id) == (None, None)


def test_drift_is_checked_against_the_nearest_configured_cycle(temp_db):
    # Cycle 1 is 08:00-20:00, Cycle 2 is 21:00-23:00. A transition near 21:05 should be matched
    # against Cycle 2's on-time (21:00), not Cycle 1's (08:00) — see ADR 0057.
    plug_id = _insert_smart_plug(temp_db, "08:00", "20:00", "21:00", "23:00")
    _record_transition(temp_db, plug_id, "2026-10-03 21:05:00", 1)

    plug = q.get_plug(plug_id)

    assert plug["detected_on_time"] == "21:05"
    assert plug["matched_target_on_time"] == "21:00"
    assert acknowledged_drift_status(plug["matched_target_on_time"], plug["detected_on_time"],
                                      plug["timer_ack_on_time"], 15) is Status.GREEN


def _update_plug_targets(plug_id: int, target_on: str, target_off: str,
                          target_on_2: str | None = None, target_off_2: str | None = None) -> None:
    """update_plug() needs the full Smart Plug identity and a parent Room; this keeps the same
    identity the row was inserted with so only the target times are what's being exercised.
    controller_kind='timer' (not 'none') — Target Schedule only means anything for a Timer-
    Controlled Plug (ADR 0041); passing 'none' here would always null the targets out."""
    import db.db as db_module

    with db_module.get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO room (id, name) VALUES (1, 'Room')")
        conn.execute("UPDATE plug SET room_id = 1 WHERE id = ?", (plug_id,))
        conn.commit()
    q.update_plug(
        plug_id, "UTH", "heat", "smart", "1", "dev-1", "local-key", "10.0.0.5",
        target_on, target_off, 1, [], "timer", None, None, True, False,
        target_on_time_2=target_on_2, target_off_time_2=target_off_2,
    )
