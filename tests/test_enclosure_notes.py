"""Enclosure Notes (see CONTEXT.md: Enclosure Note; RHA-116)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from starlette.requests import Request

import db.db as db_module
from db.migrate import run_migrations
from db.migrations import LATEST_VERSION
from web import admin as admin_routes
from web import admin_queries as q


def _request(path: str) -> Request:
    from web.main import app
    return Request({"type": "http", "method": "GET", "path": path, "query_string": b"",
                    "headers": [], "app": app, "root_path": "", "state": {"user": None}})


def _make_enclosure(name: str = "Tub", bioactive: bool = False) -> int:
    return q.create_enclosure(name, "basic", bioactive, 7, 3, 7, 30)


def _page(enclosure_id: int) -> str:
    q.record_care_nags(enclosure_id)
    response = admin_routes.admin_enclosure_detail(_request(f"/admin/enclosures/{enclosure_id}"), enclosure_id)
    return response.body.decode("utf-8")


# --- queries -------------------------------------------------------------------------------------

def test_notes_are_listed_newest_first_with_backdating(temp_db):
    enclosure_id = _make_enclosure()
    q.log_enclosure_note(enclosure_id, "rearranged hides", "2026-11-01T09:30")
    q.log_enclosure_note(enclosure_id, "started Baytril", "2026-11-10T18:00")
    q.log_enclosure_note(enclosure_id, "older one", "2026-10-01T08:00")

    notes = q.get_enclosure(enclosure_id)["notes"]

    assert [n["note"] for n in notes] == ["started Baytril", "rearranged hides", "older one"]
    assert notes[0]["occurred_at"].startswith("2026-11-10 18:00")


def test_blank_occurred_at_defaults_to_now(temp_db):
    enclosure_id = _make_enclosure()
    q.log_enclosure_note(enclosure_id, "misted heavily", "")
    (note,) = q.get_enclosure(enclosure_id)["notes"]
    assert note["occurred_at"]


@pytest.mark.parametrize("note", ["", "   ", None])
def test_blank_note_is_rejected(temp_db, note):
    enclosure_id = _make_enclosure()
    with pytest.raises(ValueError):
        q.log_enclosure_note(enclosure_id, note)


def test_delete_only_removes_the_note_from_its_own_enclosure(temp_db):
    a, b = _make_enclosure("A"), _make_enclosure("B")
    q.log_enclosure_note(a, "note on A")
    note_id = q.get_enclosure(a)["notes"][0]["id"]

    q.delete_enclosure_note(note_id, b)  # wrong enclosure: no-op
    assert len(q.get_enclosure(a)["notes"]) == 1

    q.delete_enclosure_note(note_id, a)
    assert q.get_enclosure(a)["notes"] == []


def test_deleting_the_enclosure_cascades_to_its_notes(temp_db):
    enclosure_id = _make_enclosure()
    q.log_enclosure_note(enclosure_id, "note")
    q.delete_enclosure(enclosure_id)
    assert temp_db.execute("SELECT COUNT(*) FROM enclosure_note").fetchone()[0] == 0


# --- page and routes -----------------------------------------------------------------------------

def test_notes_card_shows_on_a_non_bioactive_enclosure_after_care(temp_db):
    enclosure_id = _make_enclosure(bioactive=False)
    html = _page(enclosure_id)
    assert 'id="notes"' in html and "No notes yet" in html
    assert html.index('id="care-section"') < html.index('id="notes"') < html.index("<h2>Animals</h2>")
    assert '<textarea name="note"' in html


def test_page_shows_ten_notes_and_tucks_the_rest_behind_show_all(temp_db):
    enclosure_id = _make_enclosure()
    for day in range(1, 13):
        q.log_enclosure_note(enclosure_id, f"note {day:02d}", f"2026-11-{day:02d}T12:00")

    html = _page(enclosure_id)
    details = html.index("Show all 12 notes")
    assert html.index("note 12") < details  # newest in the main table
    assert html.index("note 03") < details
    assert html.index("note 02") > details  # 11th and 12th newest behind the expander
    assert html.index("note 01") > details


def test_no_show_all_with_ten_or_fewer_notes(temp_db):
    enclosure_id = _make_enclosure()
    for day in range(1, 11):
        q.log_enclosure_note(enclosure_id, f"note {day:02d}", f"2026-11-{day:02d}T12:00")
    assert "Show all" not in _page(enclosure_id)


def test_note_text_is_html_escaped(temp_db):
    enclosure_id = _make_enclosure()
    q.log_enclosure_note(enclosure_id, "<script>alert(1)</script>")
    html = _page(enclosure_id)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_routes_add_and_delete_redirect_back_to_the_notes_card(temp_db):
    enclosure_id = _make_enclosure()
    response = admin_routes.admin_log_enclosure_note(enclosure_id, "gave water bowl a scrub", "")
    assert response.headers["location"] == f"/admin/enclosures/{enclosure_id}#notes"
    note_id = q.get_enclosure(enclosure_id)["notes"][0]["id"]

    response = admin_routes.admin_delete_enclosure_note(enclosure_id, note_id)
    assert response.headers["location"] == f"/admin/enclosures/{enclosure_id}#notes"
    assert q.get_enclosure(enclosure_id)["notes"] == []


def test_route_reports_a_blank_note_as_an_error(temp_db):
    enclosure_id = _make_enclosure()
    response = admin_routes.admin_log_enclosure_note(enclosure_id, "  ", "")
    assert "error=" in response.headers["location"]
    assert response.headers["location"].endswith("#notes")


# --- migration -----------------------------------------------------------------------------------

def test_migration_31_adds_enclosure_note_to_an_existing_database(tmp_path: Path, monkeypatch):
    path = tmp_path / "husbandrytracker.db"
    monkeypatch.setattr(db_module, "DB_PATH", path)
    run_migrations()
    conn = sqlite3.connect(path)
    conn.execute("DROP TABLE enclosure_note")
    conn.execute("PRAGMA user_version = 30")
    conn.commit()
    conn.close()

    assert run_migrations() == LATEST_VERSION - 30
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT COUNT(*) FROM enclosure_note").fetchone()[0] == 0
    conn.close()
