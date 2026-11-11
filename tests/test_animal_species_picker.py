"""Knowledge Base species picker on Add/Edit Animal, and which picks count as a linked species for
Genetics (see CONTEXT.md: Species Profile, Gene; RHA-103)."""
from __future__ import annotations

import sqlite3

from starlette.requests import Request

from web import admin as admin_routes
from web import admin_queries as q
from web import species_kb_queries as skq


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


def _options_by_group(groups):
    return {g["label"]: [o["key"] for o in g["options"]] for g in groups}


# --- picker options ------------------------------------------------------------------------------

def test_picker_groups_named_species_by_category_and_puts_catch_alls_last(temp_db):
    groups = skq.animal_species_groups()
    by_group = _options_by_group(groups)

    assert "ball_python" in by_group["Snakes"]
    assert "leopard_gecko" in by_group["Lizards"]
    assert "clownfish" in by_group["Saltwater Fish"]
    assert groups[-1]["label"] == skq.OTHER_GROUP_LABEL
    other = by_group[skq.OTHER_GROUP_LABEL]
    for catch_all in ("snake_other", "lizard_other", "insect", "tortoise", "saltwater_reef", "freshwater_planted"):
        assert catch_all in other
        assert all(catch_all not in keys for label, keys in by_group.items() if label != skq.OTHER_GROUP_LABEL)


def test_named_options_carry_names_to_fill_and_catch_alls_carry_none(temp_db):
    options = {o["key"]: o for g in skq.animal_species_groups() for o in g["options"]}
    assert options["ball_python"]["common"] == "Ball Python"
    assert options["ball_python"]["scientific"] == "Python regius"
    assert options["snake_other"]["common"] is None
    assert options["saltwater_reef"]["common"] is None


def test_picker_reads_the_knowledge_base_live(temp_db):
    skq.create_profile("snake", "Blood Python", "Python brongersmai", None, {})
    assert "blood_python" in _options_by_group(skq.animal_species_groups())["Snakes"]


# --- linked species ------------------------------------------------------------------------------

def test_only_a_specific_named_species_counts_as_linked(temp_db):
    linked = skq.linked_species("ball_python")
    assert linked["category"] == "snake" and linked["common_name"] == "Ball Python"
    assert skq.linked_species("gargoyle_gecko")["category"] == "lizard"

    for not_linked in (None, "", "snake_other", "lizard_other", "insect", "saltwater_reef", "tortoise", "no_such_species"):
        assert skq.linked_species(not_linked) is None, not_linked


def test_linked_species_survives_a_rename_and_ends_on_delete(temp_db):
    linked = skq.linked_species("corn_snake")
    skq.update_profile("snake", linked["id"], "Corn Snake (Okeetee)", "Pantherophis guttatus", None, {})
    assert skq.linked_species("corn_snake")["common_name"] == "Corn Snake (Okeetee)"

    skq.delete_profile("snake", linked["id"])
    assert skq.linked_species("corn_snake") is None


# --- saving --------------------------------------------------------------------------------------

def test_add_animal_saves_the_species_pick(temp_db):
    enclosure_id = _enclosure()
    admin_routes.admin_create_animal_global(
        enclosure_id=str(enclosure_id), name="Rex", common="Ball Python", scientific="Python regius",
        dob="", sex="unknown", species_profile="ball_python",
    )
    animal = _only_animal(temp_db)
    assert animal["species_profile"] == "ball_python"
    assert animal["species_common"] == "Ball Python"


def test_edit_animal_changes_and_clears_the_species_pick(temp_db):
    enclosure_id = _enclosure()
    q.create_animal(enclosure_id, "Rex", None, None, None, "saltwater_reef")
    animal_id = _only_animal(temp_db)["id"]

    admin_routes.admin_update_animal(animal_id, enclosure_id=enclosure_id, name="Rex", common="Leopard Gecko",
                                     scientific="", dob="", sex="unknown", species_profile="leopard_gecko")
    assert _only_animal(temp_db)["species_profile"] == "leopard_gecko"

    admin_routes.admin_update_animal(animal_id, enclosure_id=enclosure_id, name="Rex", common="Leopard Gecko",
                                     scientific="", dob="", sex="unknown", species_profile="")
    assert _only_animal(temp_db)["species_profile"] is None
    assert _only_animal(temp_db)["species_common"] == "Leopard Gecko"  # names are independent of the pick


# --- rendering -----------------------------------------------------------------------------------

def test_add_animal_form_has_the_picker_with_fill_data(temp_db):
    html = _html(admin_routes.admin_app(_request("/admin/app/")))
    assert '<select name="species_profile" onchange="onAnimalSpeciesPick(this)">' in html
    assert '<option value="ball_python" data-common="Ball Python" data-scientific="Python regius">Ball Python</option>' in html
    assert '<option value="snake_other">Snake (other/unlisted)</option>' in html


def test_edit_form_preselects_the_current_species(temp_db):
    enclosure_id = _enclosure()
    q.create_animal(enclosure_id, "Spike", None, None, None, "bearded_dragon")
    animal_id = _only_animal(temp_db)["id"]

    html = _html(admin_routes.admin_edit_animal(_request(f"/admin/animals/{animal_id}/edit"), animal_id))

    assert 'value="bearded_dragon" data-common="Bearded Dragon"' in html
    selected = [line for line in html.splitlines() if "<option" in line and " selected>" in line and "species" not in line]
    assert any('value="bearded_dragon"' in line for line in selected)
    assert "no longer in the Knowledge Base" not in html


def test_edit_form_keeps_a_species_that_was_removed_from_the_knowledge_base(temp_db):
    enclosure_id = _enclosure()
    q.create_animal(enclosure_id, "Ghost", None, None, None, "deleted_species")
    animal_id = _only_animal(temp_db)["id"]

    html = _html(admin_routes.admin_edit_animal(_request(f"/admin/animals/{animal_id}/edit"), animal_id))

    assert '<option value="deleted_species" selected>deleted_species (no longer in the Knowledge Base)</option>' in html
