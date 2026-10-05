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
from web.status import Status, acknowledged_drift_status, schedule_drift_status


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


# --- query layer ----------------------------------------------------------------------------------

def _insert_smart_plug(conn: sqlite3.Connection, target_on: str | None, target_off: str | None) -> int:
    cur = conn.execute(
        """INSERT INTO plug (label, purpose, tracking_mode, plugin, external_id, target_on_time, target_off_time)
           VALUES ('UTH', 'heat', 'smart', 'tuya_lan', 'dev-1', ?, ?)""",
        (target_on, target_off),
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


def _update_plug_targets(plug_id: int, target_on: str, target_off: str) -> None:
    """update_plug() needs the full Smart Plug identity and a parent Room; this keeps the same
    identity the row was inserted with so only the target times are what's being exercised."""
    import db.db as db_module

    with db_module.get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO room (id, name) VALUES (1, 'Room')")
        conn.execute("UPDATE plug SET room_id = 1 WHERE id = ?", (plug_id,))
        conn.commit()
    q.update_plug(
        plug_id, "UTH", "heat", "smart", "1", "dev-1", "local-key", "10.0.0.5",
        target_on, target_off, 1, [], "none", None, None, True, False,
    )
