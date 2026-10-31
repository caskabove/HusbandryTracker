"""Feeding Detail and Shed Log (see CONTEXT.md: Feeding Detail, Shed Log; ADR 0042; RHA-91).

Covers the dual-write (a Feeding still logs its care_event row, plus a new feeding_detail row),
get_last_feeding_detail()'s Spot-feed scoping, the quick-log "repeat last Feeding" path through the
admin route, and Shed Log's stuck_locations round-trip (including a free-text "other" entry).
"""
from __future__ import annotations

from db.db import get_connection
from web import admin as admin_routes
from web import admin_queries as q


def _make_enclosure(name: str = "Test Enclosure") -> int:
    return q.create_enclosure(name, "basic", False, 7, 3, 7, 30)


def _make_animal(enclosure_id: int, name: str = "Rex") -> int:
    with get_connection() as conn:
        cur = conn.execute("INSERT INTO animal (enclosure_id, name) VALUES (?, ?)", (enclosure_id, name))
        return cur.lastrowid


# --- Feeding Detail ---------------------------------------------------------------------------

def test_log_feeding_writes_both_a_care_event_and_a_feeding_detail_row(temp_db):
    enclosure_id = _make_enclosure()

    q.log_feeding(enclosure_id, food="frozen-thawed rat - small", count=1, prey_state="frozen_thawed", result="accepted")

    assert temp_db.execute("SELECT COUNT(*) c FROM care_event WHERE enclosure_id = ? AND kind = 'feeding'",
                            (enclosure_id,)).fetchone()["c"] == 1
    detail = temp_db.execute("SELECT * FROM feeding_detail").fetchone()
    assert detail["food"] == "frozen-thawed rat - small"
    assert detail["count"] == 1
    assert detail["prey_state"] == "frozen_thawed"
    assert detail["result"] == "accepted"


def test_log_feeding_rejects_unknown_prey_state_and_result(temp_db):
    enclosure_id = _make_enclosure()
    try:
        q.log_feeding(enclosure_id, prey_state="frozen")
        assert False, "expected ValueError"
    except ValueError:
        pass
    try:
        q.log_feeding(enclosure_id, result="maybe")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_get_last_feeding_detail_returns_the_most_recent_whole_enclosure_feeding(temp_db):
    enclosure_id = _make_enclosure()
    q.log_feeding(enclosure_id, food="mouse", occurred_at="2026-10-01T08:00")
    q.log_feeding(enclosure_id, food="rat", occurred_at="2026-10-08T08:00")

    last = q.get_last_feeding_detail(enclosure_id)

    assert last["food"] == "rat"


def test_get_last_feeding_detail_is_scoped_per_spot_fed_animal(temp_db):
    enclosure_id = _make_enclosure()
    animal_id = _make_animal(enclosure_id)
    q.log_feeding(enclosure_id, food="whole enclosure food")
    q.log_feeding(enclosure_id, animal_id=animal_id, food="spot-fed extra pellet")

    assert q.get_last_feeding_detail(enclosure_id)["food"] == "whole enclosure food"
    assert q.get_last_feeding_detail(enclosure_id, animal_id)["food"] == "spot-fed extra pellet"


def test_list_recent_foods_is_newest_first_and_distinct(temp_db):
    enclosure_id = _make_enclosure()
    q.log_feeding(enclosure_id, food="mouse", occurred_at="2026-10-01T08:00")
    q.log_feeding(enclosure_id, food="rat", occurred_at="2026-10-05T08:00")
    q.log_feeding(enclosure_id, food="mouse", occurred_at="2026-10-08T08:00")

    assert q.list_recent_foods(enclosure_id) == ["mouse", "rat"]


def test_quick_log_button_through_the_admin_route_repeats_the_last_feeding(temp_db):
    """The Today/Yesterday/2-days-ago forms never submit food/count/prey_state/result (see
    admin_enclosure.html) — admin_create_care_event() should fill them in from the last Feeding
    rather than logging a blank one."""
    enclosure_id = _make_enclosure()
    q.log_feeding(enclosure_id, food="rat", count=1, prey_state="frozen_thawed", result="accepted")

    admin_routes.admin_create_care_event(
        enclosure_id, "feeding", note=None, occurred_at="", days_ago="0", animal_id="",
        food="", count="", prey_state="", result="",
    )

    rows = temp_db.execute(
        """SELECT fd.food, fd.count, fd.prey_state, fd.result FROM feeding_detail fd
           JOIN care_event ce ON ce.id = fd.care_event_id
           WHERE ce.enclosure_id = ? ORDER BY ce.occurred_at DESC""",
        (enclosure_id,),
    ).fetchall()
    assert len(rows) == 2  # the seeded one above, plus this quick-log repeat
    assert rows[0]["food"] == "rat" and rows[0]["count"] == 1 and rows[0]["prey_state"] == "frozen_thawed"


def test_quick_log_button_with_no_prior_feeding_logs_cleanly_with_nothing_fed(temp_db):
    enclosure_id = _make_enclosure()

    admin_routes.admin_create_care_event(
        enclosure_id, "feeding", note=None, occurred_at="", days_ago="0", animal_id="",
        food="", count="", prey_state="", result="",
    )

    detail = temp_db.execute("SELECT * FROM feeding_detail").fetchone()
    assert detail["food"] is None
    assert detail["result"] == "accepted"  # schema default, since none was submitted


def test_advanced_form_with_explicit_fields_overrides_the_last_feeding(temp_db):
    enclosure_id = _make_enclosure()
    q.log_feeding(enclosure_id, food="rat", result="accepted")

    admin_routes.admin_create_care_event(
        enclosure_id, "feeding", note=None, occurred_at="", days_ago="", animal_id="",
        food="", count="", prey_state="", result="refused",
    )

    last = q.get_last_feeding_detail(enclosure_id)
    assert last["result"] == "refused"


# --- Shed Log ----------------------------------------------------------------------------------

def test_create_and_list_shed_log_round_trips_fixed_and_free_text_locations(temp_db):
    enclosure_id = _make_enclosure()
    animal_id = _make_animal(enclosure_id)

    q.create_shed_log(animal_id, "partial", ["eye_caps", "belly scales"], note="watched closely")

    entries = q.list_shed_logs(animal_id)
    assert len(entries) == 1
    assert entries[0]["completeness"] == "partial"
    assert entries[0]["stuck_location_labels"] == ["Eye caps", "belly scales"]
    assert entries[0]["note"] == "watched closely"


def test_full_shed_clears_stuck_locations_even_if_submitted(temp_db):
    enclosure_id = _make_enclosure()
    animal_id = _make_animal(enclosure_id)

    q.create_shed_log(animal_id, "full", ["toes"])

    entries = q.list_shed_logs(animal_id)
    assert entries[0]["stuck_location_labels"] == []


def test_create_shed_log_rejects_unknown_completeness(temp_db):
    enclosure_id = _make_enclosure()
    animal_id = _make_animal(enclosure_id)
    try:
        q.create_shed_log(animal_id, "half", [])
        assert False, "expected ValueError"
    except ValueError:
        pass
