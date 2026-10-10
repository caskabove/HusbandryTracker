"""Main menu and page split (see the Control Panel / All Enclosures change): every page shows the same
four nav items, with the current one marked, and the Enclosures card lives on its own page at
/admin/enclosures rather than on the Control Panel at /admin.
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


def test_all_enclosures_page_lists_enclosures_and_is_marked_current(temp_db):
    q.create_enclosure("Dart", "basic", False, 7, 3, 7, 30)

    html = _html(admin_routes.admin_enclosures(_request("/admin/enclosures")))

    assert "Husbandry Tracker Enclosures" in html
    assert "Dart" in html
    assert "+ Add Enclosure" in html
    assert _current_nav_item(html) == "All Enclosures"


def test_control_panel_no_longer_has_the_enclosures_card(temp_db):
    html = _html(admin_routes.admin_index(_request("/admin/")))

    assert "Husbandry Tracker Control Panel" in html
    assert "+ Add Enclosure" not in html
    assert _current_nav_item(html) == "Control Panel"


def test_dashboard_nav_has_the_four_items_and_marks_dashboard(temp_db):
    html = _html(main_routes.dashboard(_request("/")))

    for label in ("Dashboard", "All Enclosures", "Control Panel", "Guide"):
        assert f">{label}</a>" in html
    assert _current_nav_item(html) == "Dashboard"


def test_deleting_an_enclosure_returns_to_the_all_enclosures_page(temp_db):
    enclosure_id = q.create_enclosure("Dart", "basic", False, 7, 3, 7, 30)

    response = admin_routes.admin_delete_enclosure(enclosure_id)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/enclosures"
