"""Sex on every Animal: Male / Female / Unknown, default Unknown (see CONTEXT.md: Animal; RHA-102)."""
from __future__ import annotations

import sqlite3

import pytest
from starlette.requests import Request

from db.migrations import m0027_animal_sex
from web import add_pet as add_pet_routes
from web import admin as admin_routes
from web import admin_queries as q
from web import setup as setup_routes


def _request(path: str) -> Request:
    from web.main import app
    # state.user: Admin's App page reads the signed-in user (RHA-99), normally set by auth middleware.
    return Request({"type": "http", "method": "GET", "path": path, "query_string": b"",
                    "headers": [], "app": app, "root_path": "", "state": {"user": None}})


def _html(response) -> str:
    return response.body.decode("utf-8")


def _enclosure() -> int:
    return q.create_enclosure("Rack A", "basic", False, 7, 3, 7, 30)


def _only_animal(conn: sqlite3.Connection) -> sqlite3.Row:
    (row,) = conn.execute("SELECT * FROM animal").fetchall()
    return row


# --- migration -----------------------------------------------------------------------------------

def test_migration_adds_sex_defaulting_existing_animals_to_unknown():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE animal (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    conn.execute("INSERT INTO animal (name) VALUES ('Ziggy')")

    m0027_animal_sex.migrate(conn)
    m0027_animal_sex.migrate(conn)  # idempotent

    assert conn.execute("SELECT name, sex FROM animal").fetchall() == [("Ziggy", "unknown")]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE animal SET sex = 'hermaphrodite'")


# --- queries -------------------------------------------------------------------------------------

def test_new_animal_defaults_to_unknown(temp_db):
    q.create_animal(_enclosure(), "Rex", None, None, None)
    assert _only_animal(temp_db)["sex"] == "unknown"


def test_create_and_resex_an_animal(temp_db):
    enclosure_id = _enclosure()
    q.create_animal(enclosure_id, "Rex", "Ball Python", None, None, sex="male")
    animal = _only_animal(temp_db)
    assert animal["sex"] == "male"

    q.update_animal(animal["id"], enclosure_id, "Rex", "Ball Python", None, None, "female")

    assert _only_animal(temp_db)["sex"] == "female"


def test_blank_sex_means_unknown_and_garbage_is_rejected(temp_db):
    enclosure_id = _enclosure()
    q.create_animal(enclosure_id, "Rex", None, None, None, sex="")
    assert _only_animal(temp_db)["sex"] == "unknown"
    with pytest.raises(ValueError):
        q.create_animal(enclosure_id, "Bob", None, None, None, sex="hermaphrodite")
    with pytest.raises(ValueError):
        q.update_animal(_only_animal(temp_db)["id"], enclosure_id, "Rex", None, None, None, "x")


# --- routes and pages ----------------------------------------------------------------------------

@pytest.mark.parametrize("create", [
    lambda enc: admin_routes.admin_create_animal_global(enclosure_id=str(enc), name="Rex", common="", scientific="", dob="", sex="female"),
    lambda enc: setup_routes.setup_create_animal(enc, name="Rex", common="", scientific="", dob="", sex="female", species_profile="", life_stage="adult"),
    lambda enc: add_pet_routes.add_pet_create_animal(enc, name="Rex", common="", scientific="", dob="", sex="female", species_profile="", life_stage="adult"),
], ids=["admin", "setup-wizard", "add-new-pet"])
def test_every_add_animal_form_saves_sex(temp_db, create):
    create(_enclosure())
    assert _only_animal(temp_db)["sex"] == "female"


def test_edit_route_saves_sex(temp_db):
    enclosure_id = _enclosure()
    q.create_animal(enclosure_id, "Rex", None, None, None)
    animal_id = _only_animal(temp_db)["id"]

    admin_routes.admin_update_animal(animal_id, enclosure_id=enclosure_id, name="Rex", common="", scientific="", dob="", sex="male")

    assert _only_animal(temp_db)["sex"] == "male"


def test_forms_offer_sex_with_unknown_preselected(temp_db):
    enclosure_id = _enclosure()
    pages = [
        admin_routes.admin_app(_request("/admin/app/")),
        setup_routes.setup_animals(_request(f"/setup/enclosures/{enclosure_id}/animals"), enclosure_id),
        add_pet_routes.add_pet_animals(_request(f"/add-pet/enclosures/{enclosure_id}/animals"), enclosure_id),
    ]
    for page in pages:
        html = _html(page)
        assert '<select name="sex">' in html
        assert '<option value="unknown" selected>Unknown</option>' in html


def test_edit_page_preselects_the_animals_sex_and_animal_page_shows_it(temp_db):
    enclosure_id = _enclosure()
    q.create_animal(enclosure_id, "Rex", None, None, None, sex="female")
    animal_id = _only_animal(temp_db)["id"]

    edit_html = _html(admin_routes.admin_edit_animal(_request(f"/admin/animals/{animal_id}/edit"), animal_id))
    assert '<option value="female" selected>Female</option>' in edit_html
    assert '<option value="unknown" selected>' not in edit_html

    page_html = _html(admin_routes.admin_animal_detail(_request(f"/admin/animals/{animal_id}"), animal_id))
    assert "Sex: Female" in page_html
