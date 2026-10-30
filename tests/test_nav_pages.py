"""Main menu and page split (see ADR 0033): every page shows the same four nav items, with the
current one marked. The Enclosures card lives on its own page at /admin/enclosures rather than on
Plugs and Sensors at /admin, and (per ADR 0033) the Rooms card lives there too, not on /admin.
"""
from __future__ import annotations

from starlette.requests import Request

from web import admin_queries as q
from web import admin as admin_routes
from web import main as main_routes


def _request(path: str, query: str = "") -> Request:
    """A bare GET request for calling a route function directly — no HTTP client needed."""
    from web.main import app
    scope = {"type": "http", "method": "GET", "path": path, "query_string": query.encode(),
             "headers": [], "app": app, "root_path": ""}
    return Request(scope)


def _html(response) -> str:
    return response.body.decode("utf-8")


def _current_nav_item(html: str) -> str | None:
    """The label of the nav link marked aria-current="page", or None."""
    marker = 'aria-current="page"'
    if marker not in html:
        return None
    line = next(l for l in html.splitlines() if marker in l)
    return line.split(">")[1].split("<")[0]


def test_rooms_and_enclosures_page_lists_rooms_and_enclosures_and_is_marked_current(temp_db):
    q.create_enclosure("Dart", "basic", False, 7, 3, 7, 30)
    q.create_room("Living Room")

    html = _html(admin_routes.admin_enclosures(_request("/admin/enclosures")))

    assert "Husbandry Tracker Rooms and Enclosures" in html
    assert "Dart" in html
    assert "+ Add Enclosure" in html
    assert "Living Room" in html
    assert "+ Add Room" in html
    assert _current_nav_item(html) == "Rooms and Enclosures"


def test_plugs_and_sensors_page_has_neither_the_enclosures_card_nor_the_rooms_card(temp_db):
    html = _html(admin_routes.admin_index(_request("/admin/")))

    assert "Husbandry Tracker Plugs and Sensors" in html
    assert "+ Add Enclosure" not in html
    assert "+ Add Room" not in html
    assert _current_nav_item(html) == "Plugs and Sensors"


def test_dashboard_nav_has_the_four_items_and_marks_dashboard(temp_db):
    html = _html(main_routes.dashboard(_request("/")))

    for label in ("Dashboard", "Rooms and Enclosures", "Plugs and Sensors", "Guide"):
        assert f">{label}</a>" in html
    assert _current_nav_item(html) == "Dashboard"


def test_deleting_an_enclosure_returns_to_the_rooms_and_enclosures_page(temp_db):
    enclosure_id = q.create_enclosure("Dart", "basic", False, 7, 3, 7, 30)

    response = admin_routes.admin_delete_enclosure(enclosure_id)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/enclosures"


def test_deleting_a_room_returns_to_the_rooms_and_enclosures_page(temp_db):
    room_id = q.create_room("Living Room")

    response = admin_routes.admin_delete_room(room_id)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/enclosures"


def test_a_missing_room_redirects_to_the_rooms_and_enclosures_page(temp_db):
    response = admin_routes.admin_room_detail(_request("/admin/rooms/999999"), 999999)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/enclosures"
