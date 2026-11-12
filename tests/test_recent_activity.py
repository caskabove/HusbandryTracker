"""Recent Activity (see CONTEXT.md: Recent Activity; grill-me decision) — the Enclosure's Animals
card's quick-view strip (list_enclosure_activity) and the Animal page's full paginated history
(list_animal_activity), plus the Animal page route and the 3-way Quick Log redirect it adds a
branch to (_quick_log_redirect).
"""
from __future__ import annotations

from db.db import get_connection
from web import admin as admin_routes
from web import admin_queries as q
from web.queries import log_care_event


def _make_enclosure(name: str = "Test Enclosure") -> int:
    return q.create_enclosure(name, "basic", False, 7, 3, 7, 30)


def _make_animal(enclosure_id: int, name: str = "Rex") -> int:
    with get_connection() as conn:
        cur = conn.execute("INSERT INTO animal (enclosure_id, name) VALUES (?, ?)", (enclosure_id, name))
        return cur.lastrowid


def _request(path: str, query: str = ""):
    from starlette.requests import Request
    from web.main import app
    scope = {"type": "http", "method": "GET", "path": path, "query_string": query.encode(),
             "headers": [], "app": app, "root_path": ""}
    return Request(scope)


def _html(response) -> str:
    return response.body.decode("utf-8")


# --- list_enclosure_activity ---------------------------------------------------------------------

def test_merges_and_sorts_all_three_sources_newest_first(temp_db):
    enclosure_id = _make_enclosure()
    animal_id = _make_animal(enclosure_id, "Rex")
    log_care_event(enclosure_id, "deep_clean", occurred_at="2026-10-01T08:00")
    q.log_animal_weight(animal_id, 100.0, occurred_at="2026-10-03T08:00")
    q.create_shed_log(animal_id, "full", occurred_at="2026-10-02T08:00")

    activity = q.list_enclosure_activity(enclosure_id)

    assert [e["occurred_at"][:10] for e in activity] == ["2026-10-03", "2026-10-02", "2026-10-01"]
    assert activity[0]["label"] == "Weight logged"
    assert activity[1]["label"] == "Shed (full)"
    assert activity[2]["label"] == "Deep clean"


def test_whole_enclosure_event_has_no_animal_id_and_is_labeled_enclosure(temp_db):
    enclosure_id = _make_enclosure()
    log_care_event(enclosure_id, "watering")

    activity = q.list_enclosure_activity(enclosure_id)

    assert activity[0]["animal_id"] is None
    assert activity[0]["animal_name"] == "Enclosure"


def test_spot_fed_event_is_attributed_to_its_animal(temp_db):
    enclosure_id = _make_enclosure()
    animal_id = _make_animal(enclosure_id, "Rex")
    log_care_event(enclosure_id, "feeding", animal_id=animal_id)

    activity = q.list_enclosure_activity(enclosure_id)

    assert activity[0]["animal_id"] == animal_id
    assert activity[0]["animal_name"] == "Rex"
    assert activity[0]["label"] == "Feeding"


def test_animal_log_label_lists_only_the_fields_present_on_that_row(temp_db):
    enclosure_id = _make_enclosure()
    animal_id = _make_animal(enclosure_id)
    q.log_animal_condition(animal_id, "good")

    activity = q.list_enclosure_activity(enclosure_id)

    assert activity[0]["label"] == "Condition logged"


def test_is_capped_at_limit_even_with_more_entries_available(temp_db):
    enclosure_id = _make_enclosure()
    animal_id = _make_animal(enclosure_id)
    for day in range(1, 8):
        q.log_animal_weight(animal_id, 100.0 + day, occurred_at=f"2026-10-{day:02d}T08:00")

    activity = q.list_enclosure_activity(enclosure_id, limit=5)

    assert len(activity) == 5
    assert activity[0]["occurred_at"][:10] == "2026-10-07"


def test_only_includes_activity_from_its_own_enclosure(temp_db):
    enclosure_a = _make_enclosure("A")
    enclosure_b = _make_enclosure("B")
    log_care_event(enclosure_b, "deep_clean")

    assert q.list_enclosure_activity(enclosure_a) == []


# --- list_animal_activity -------------------------------------------------------------------------

def test_feeding_detail_is_rendered_with_food_count_and_prey_state(temp_db):
    enclosure_id = _make_enclosure()
    animal_id = _make_animal(enclosure_id)
    q.log_feeding(enclosure_id, animal_id=animal_id, food="mouse", count=2, prey_state="frozen_thawed")

    entries, has_more = q.list_animal_activity(animal_id)

    assert has_more is False
    assert entries[0]["label"] == "Feeding"
    assert "mouse" in entries[0]["detail"] and "×2" in entries[0]["detail"]


def test_refused_feeding_is_called_out_in_the_detail(temp_db):
    enclosure_id = _make_enclosure()
    animal_id = _make_animal(enclosure_id)
    q.log_feeding(enclosure_id, animal_id=animal_id, food="mouse", result="refused")

    entries, _ = q.list_animal_activity(animal_id)

    assert "refused" in entries[0]["detail"].lower()


def test_whole_enclosure_events_dont_leak_into_an_animals_own_history(temp_db):
    enclosure_id = _make_enclosure()
    animal_id = _make_animal(enclosure_id)
    log_care_event(enclosure_id, "deep_clean")  # animal_id is always None for this kind

    entries, _ = q.list_animal_activity(animal_id)

    assert entries == []


def test_growth_log_detail_includes_every_field_present_and_the_note(temp_db):
    enclosure_id = _make_enclosure()
    animal_id = _make_animal(enclosure_id)
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO animal_log (animal_id, weight_g, condition, note) VALUES (?, ?, ?, ?)",
            (animal_id, 150.0, "good", "looking healthy"),
        )

    entries, _ = q.list_animal_activity(animal_id)

    assert "Weight: 150.0 g" in entries[0]["detail"]
    assert "Condition: Good" in entries[0]["detail"]
    assert "looking healthy" in entries[0]["detail"]


def test_shed_log_detail_includes_stuck_locations_and_note(temp_db):
    enclosure_id = _make_enclosure()
    animal_id = _make_animal(enclosure_id)
    q.create_shed_log(animal_id, "partial", ["eye_caps"], note="watching closely")

    entries, _ = q.list_animal_activity(animal_id)

    assert entries[0]["label"] == "Shed"
    assert "Partial" in entries[0]["detail"]
    assert "Eye caps" in entries[0]["detail"]
    assert "watching closely" in entries[0]["detail"]


def test_pagination_splits_history_across_pages_without_losing_or_duplicating_entries(temp_db):
    enclosure_id = _make_enclosure()
    animal_id = _make_animal(enclosure_id)
    for day in range(1, 6):
        q.log_animal_weight(animal_id, 100.0 + day, occurred_at=f"2026-10-{day:02d}T08:00")

    page1, has_more1 = q.list_animal_activity(animal_id, page=1, page_size=2)
    page2, has_more2 = q.list_animal_activity(animal_id, page=2, page_size=2)
    page3, has_more3 = q.list_animal_activity(animal_id, page=3, page_size=2)

    assert [e["occurred_at"][:10] for e in page1] == ["2026-10-05", "2026-10-04"]
    assert [e["occurred_at"][:10] for e in page2] == ["2026-10-03", "2026-10-02"]
    assert [e["occurred_at"][:10] for e in page3] == ["2026-10-01"]
    assert has_more1 is True
    assert has_more2 is True
    assert has_more3 is False


# --- Animal page route -----------------------------------------------------------------------------

def test_animal_page_shows_profile_and_breadcrumb_to_its_enclosure(temp_db):
    enclosure_id = _make_enclosure("Bob Tank")
    animal_id = _make_animal(enclosure_id, "Bob")

    html = _html(admin_routes.admin_animal_detail(_request(f"/admin/animals/{animal_id}"), animal_id))

    assert "Bob" in html
    assert f"/admin/enclosures/{enclosure_id}" in html
    assert "Bob Tank" in html


def test_animal_page_hides_the_activity_section_entirely_when_theres_no_history_yet(temp_db):
    enclosure_id = _make_enclosure()
    animal_id = _make_animal(enclosure_id)

    html = _html(admin_routes.admin_animal_detail(_request(f"/admin/animals/{animal_id}"), animal_id))

    assert "Recent Activity" not in html


def test_animal_page_shows_the_activity_section_once_there_is_history(temp_db):
    enclosure_id = _make_enclosure()
    animal_id = _make_animal(enclosure_id)
    q.log_animal_weight(animal_id, 100.0)

    html = _html(admin_routes.admin_animal_detail(_request(f"/admin/animals/{animal_id}"), animal_id))

    assert "Recent Activity" in html


def test_a_missing_animal_redirects_to_admin(temp_db):
    response = admin_routes.admin_animal_detail(_request("/admin/animals/999999"), 999999)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin"


def test_enclosure_page_links_each_animals_name_to_its_own_animal_page(temp_db):
    enclosure_id = _make_enclosure()
    animal_id = _make_animal(enclosure_id, "Bob")
    q.record_care_nags(enclosure_id)

    html = _html(admin_routes.admin_enclosure_detail(_request(f"/admin/enclosures/{enclosure_id}"), enclosure_id))

    assert f'<a href="/admin/animals/{animal_id}" class="animal-card-name">Bob</a>' in html


def test_enclosure_page_hides_the_activity_strip_when_theres_no_activity_yet(temp_db):
    enclosure_id = _make_enclosure()
    _make_animal(enclosure_id, "Bob")
    q.record_care_nags(enclosure_id)

    html = _html(admin_routes.admin_enclosure_detail(_request(f"/admin/enclosures/{enclosure_id}"), enclosure_id))

    assert "activity-feed" not in html


def test_edit_animal_page_links_back_to_its_enclosure_and_animal_page(temp_db):
    enclosure_id = _make_enclosure("Bob Tank")
    animal_id = _make_animal(enclosure_id, "Bob")

    html = _html(admin_routes.admin_edit_animal(_request(f"/admin/animals/{animal_id}/edit"), animal_id))

    assert f'<a href="/admin/enclosures/{enclosure_id}">&larr; Back to Bob Tank</a>' in html
    assert f'<a href="/admin/animals/{animal_id}">' in html


def test_enclosure_and_animal_pages_are_never_served_stale_on_back(temp_db):
    enclosure_id = _make_enclosure()
    animal_id = _make_animal(enclosure_id, "Bob")

    enclosure = admin_routes.admin_enclosure_detail(_request(f"/admin/enclosures/{enclosure_id}"), enclosure_id)
    animal = admin_routes.admin_animal_detail(_request(f"/admin/animals/{animal_id}"), animal_id)

    for response in (enclosure, animal):
        assert response.headers["cache-control"] == "no-store"
        assert "e.persisted" in _html(response)


# --- _quick_log_redirect's 3-way branch -------------------------------------------------------------

def test_quick_log_redirect_prefers_enclosure_over_animal_page_flag():
    url = admin_routes._quick_log_redirect(5, "2", from_animal_page="1")
    assert url == "/admin/enclosures/2#animal-row-5"


def test_quick_log_redirect_goes_to_the_animal_page_when_flagged():
    url = admin_routes._quick_log_redirect(5, "", from_animal_page="1")
    assert url == "/admin/animals/5"


def test_quick_log_redirect_falls_back_to_the_edit_page_otherwise():
    url = admin_routes._quick_log_redirect(5, "", edit_anchor="shed-log")
    assert url == "/admin/animals/5/edit#shed-log"


def test_quick_log_redirect_carries_the_error_onto_the_animal_page():
    url = admin_routes._quick_log_redirect(5, "", error="Weight must be greater than zero.", from_animal_page="1")
    assert url == "/admin/animals/5?error=Weight%20must%20be%20greater%20than%20zero."
