"""Animal Genetics and Morph (see CONTEXT.md: Genetics, Morph; RHA-105)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from starlette.requests import Request

import db.db as db_module
from db.migrate import run_migrations
from web import admin as admin_routes
from web import admin_queries as q
from web import gene_catalog_queries as gcq
from web import genetics_queries as genq


def _request(path: str) -> Request:
    from web.main import app
    return Request({"type": "http", "method": "GET", "path": path, "query_string": b"",
                    "headers": [], "app": app, "root_path": "", "state": {"user": None}})


def _html(response) -> str:
    return response.body.decode("utf-8")


def _animal(conn, species_profile: str | None = "ball_python", name: str = "Bob") -> dict:
    enclosure_id = q.create_enclosure(f"Tub {name}", "basic", False, 7, 3, 7, 30)
    q.create_animal(enclosure_id, name, "Ball Python", "Python regius", None, species_profile)
    return dict(conn.execute("SELECT * FROM animal WHERE name = ?", (name,)).fetchone())


def _gene(conn, name: str, species_key: str = "ball_python") -> int:
    return conn.execute("SELECT id FROM gene WHERE species_key = ? AND name = ?", (species_key, name)).fetchone()["id"]


def _line(conn, animal_id: int) -> str | None:
    return genq.genetics_line(dict(conn.execute("SELECT * FROM animal WHERE id = ?", (animal_id,)).fetchone()))


# --- notation ------------------------------------------------------------------------------------

def test_standard_notation_from_visual_genes_and_hets(temp_db):
    bob = _animal(temp_db)
    genq.add_animal_gene(bob["id"], _gene(temp_db, "Clown"), "visual")
    genq.add_animal_gene(bob["id"], _gene(temp_db, "Banana"), "visual")
    genq.add_animal_gene(bob["id"], _gene(temp_db, "Albino"), "possible_het", "66")
    genq.add_animal_gene(bob["id"], _gene(temp_db, "Piebald"), "het", evidence="proven")
    genq.add_animal_gene(bob["id"], _gene(temp_db, "Axanthic"), "het")  # claimed by default
    assert _line(temp_db, bob["id"]) == "Banana Clown · 100% het Axanthic · 100% het Piebald (proven) · 66% het Albino"


def test_super_and_dominant_genes_and_normal(temp_db):
    bob = _animal(temp_db)
    assert _line(temp_db, bob["id"]) == "Normal"
    genq.add_animal_gene(bob["id"], _gene(temp_db, "Pastel"), "super")
    genq.add_animal_gene(bob["id"], _gene(temp_db, "Spider"), "visual")
    assert _line(temp_db, bob["id"]) == "Super Pastel Spider"


def test_morph_overrides_the_visual_genes_name_and_blank_clears_it(temp_db):
    bob = _animal(temp_db)
    genq.add_animal_gene(bob["id"], _gene(temp_db, "Clown"), "visual")
    genq.add_animal_gene(bob["id"], _gene(temp_db, "Albino"), "possible_het", "50")
    genq.set_morph(bob["id"], "  Clown Harlequin  ")
    assert _line(temp_db, bob["id"]) == "Clown Harlequin · 50% het Albino"
    genq.set_morph(bob["id"], "")
    assert _line(temp_db, bob["id"]) == "Clown · 50% het Albino"


def test_absent_for_animals_without_a_specific_species(temp_db):
    for key in (None, "snake_other", "saltwater_reef"):
        animal = _animal(temp_db, key, name=f"A{key}")
        assert _line(temp_db, animal["id"]) is None
        with pytest.raises(ValueError, match="specific Knowledge Base species"):
            genq.add_animal_gene(animal["id"], _gene(temp_db, "Clown"), "visual")
        with pytest.raises(ValueError, match="specific Knowledge Base species"):
            genq.set_morph(animal["id"], "Harlequin")


# --- rules ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("gene, state", [
    ("Pastel", "het"), ("Pastel", "possible_het"),       # co-dominant: no hets
    ("Clown", "super"),                                   # recessive: no super
    ("Spider", "super"), ("Spider", "het"),               # dominant: visual only
])
def test_only_states_valid_for_the_inheritance(temp_db, gene, state):
    bob = _animal(temp_db)
    with pytest.raises(ValueError, match="gene can be"):
        genq.add_animal_gene(bob["id"], _gene(temp_db, gene), state, "50", "claimed")


def test_possible_het_needs_a_percentage_and_is_never_proven(temp_db):
    bob = _animal(temp_db)
    for bad in ("", "0", "100", "abc"):
        with pytest.raises(ValueError, match="(?i)percentage"):
            genq.add_animal_gene(bob["id"], _gene(temp_db, "Clown"), "possible_het", bad)
    row_id = genq.add_animal_gene(bob["id"], _gene(temp_db, "Clown"), "possible_het", "66%", evidence="proven")
    row = temp_db.execute("SELECT percent, evidence FROM animal_gene WHERE id = ?", (row_id,)).fetchone()
    assert (row["percent"], row["evidence"]) == (66, None)


def test_a_gene_from_another_species_is_refused_and_duplicates_too(temp_db):
    bob = _animal(temp_db)
    with pytest.raises(ValueError, match="Ball Python Gene Catalog"):
        genq.add_animal_gene(bob["id"], _gene(temp_db, "Tremper Albino", "leopard_gecko"), "visual")
    genq.add_animal_gene(bob["id"], _gene(temp_db, "Clown"), "visual")
    with pytest.raises(ValueError, match="already in this Animal's Genetics"):
        genq.add_animal_gene(bob["id"], _gene(temp_db, "Clown"), "het")


def test_add_a_new_gene_on_the_spot_or_reuse_a_same_named_one(temp_db):
    bob = _animal(temp_db)
    genq.add_animal_gene(bob["id"], None, "visual", new_gene_name="Leopard", new_gene_inheritance="co_dominant")
    leopard = temp_db.execute("SELECT * FROM gene WHERE species_key = 'ball_python' AND name = 'Leopard'").fetchone()
    assert leopard["inheritance"] == "co_dominant"

    sue = _animal(temp_db, name="Sue")
    genq.add_animal_gene(sue["id"], None, "het", new_gene_name="clown", new_gene_inheritance="recessive")
    assert temp_db.execute("SELECT COUNT(*) FROM gene WHERE species_key = 'ball_python' AND name = 'Clown'").fetchone()[0] == 1
    assert _line(temp_db, sue["id"]) == "Normal · 100% het Clown"


def test_update_row_and_a_used_gene_cannot_leave_the_catalog(temp_db):
    bob = _animal(temp_db)
    row_id = genq.add_animal_gene(bob["id"], _gene(temp_db, "Clown"), "possible_het", "50")
    genq.update_animal_gene(bob["id"], row_id, "het", "50", "proven")
    assert _line(temp_db, bob["id"]) == "Normal · 100% het Clown (proven)"

    with pytest.raises(ValueError, match="used by 1 record"):
        gcq.delete_gene(_gene(temp_db, "Clown"))
    genq.delete_animal_gene(bob["id"], row_id)
    gcq.delete_gene(_gene(temp_db, "Clown"))


def test_species_change_is_blocked_while_genetics_exist_and_animal_delete_cascades(temp_db):
    bob = _animal(temp_db)
    genq.add_animal_gene(bob["id"], _gene(temp_db, "Clown"), "visual")
    with pytest.raises(ValueError, match="Remove them before changing its species"):
        q.update_animal(bob["id"], bob["enclosure_id"], "Bob", "x", "y", None, "male", "corn_snake")
    q.update_animal(bob["id"], bob["enclosure_id"], "Bobby", "x", "y", None, "male", "ball_python")  # same species: fine

    q.delete_animal(bob["id"])
    assert temp_db.execute("SELECT COUNT(*) FROM animal_gene").fetchone()[0] == 0


# --- migration -----------------------------------------------------------------------------------

def test_migration_29_adds_morph_and_animal_gene_to_an_existing_database(tmp_path: Path, monkeypatch):
    path = tmp_path / "husbandrytracker.db"
    monkeypatch.setattr(db_module, "DB_PATH", path)
    run_migrations()
    conn = sqlite3.connect(path)
    conn.execute("DROP TABLE animal_gene")
    conn.execute("ALTER TABLE animal DROP COLUMN morph")
    conn.execute("PRAGMA user_version = 28")
    conn.commit()
    conn.close()

    assert run_migrations() == 1
    conn = sqlite3.connect(path)
    assert "morph" in {r[1] for r in conn.execute("PRAGMA table_info(animal)")}
    assert conn.execute("SELECT COUNT(*) FROM animal_gene").fetchone()[0] == 0
    conn.close()


# --- pages and routes ----------------------------------------------------------------------------

def test_edit_page_shows_the_card_only_for_a_linked_species(temp_db):
    bob = _animal(temp_db)
    genq.add_animal_gene(bob["id"], _gene(temp_db, "Clown"), "visual")
    html = _html(admin_routes.admin_edit_animal(_request(f"/admin/animals/{bob['id']}/edit"), bob["id"]))
    assert 'id="genetics"' in html and "Add to Genetics" in html
    assert 'data-inheritance="recessive">Clown (Recessive)' in html
    assert "+ add a new Ball Python Gene" in html
    assert "Tremper Albino" not in html  # another species' catalog

    rex = _animal(temp_db, "saltwater_reef", name="Rex")
    assert 'id="genetics"' not in _html(admin_routes.admin_edit_animal(_request("/x"), rex["id"]))


def test_animal_page_and_enclosure_card_show_the_notation(temp_db):
    bob = _animal(temp_db)
    genq.add_animal_gene(bob["id"], _gene(temp_db, "Banana"), "visual")
    genq.add_animal_gene(bob["id"], _gene(temp_db, "Piebald"), "het", evidence="proven")
    expected = "Banana · 100% het Piebald (proven)"
    assert expected in _html(admin_routes.admin_animal_detail(_request("/x"), bob["id"]))
    assert q.get_enclosure(bob["enclosure_id"])["animals"][0]["genetics_line"] == expected


def test_routes_add_update_and_report_errors(temp_db):
    bob = _animal(temp_db)
    response = admin_routes.admin_add_animal_gene(bob["id"], gene_id=str(_gene(temp_db, "Clown")), new_gene_name="",
                                                 new_gene_inheritance="", state="possible_het", percent="66", evidence="")
    assert response.headers["location"] == f"/admin/animals/{bob['id']}/edit#genetics"
    response = admin_routes.admin_add_animal_gene(bob["id"], gene_id="new", new_gene_name="Leopard",
                                                 new_gene_inheritance="co_dominant", state="het", percent="", evidence="")
    assert "error=" in response.headers["location"]
    response = admin_routes.admin_set_morph(bob["id"], morph="Harlequin")
    assert "error=" not in response.headers["location"]
    assert _line(temp_db, bob["id"]) == "Harlequin · 66% het Clown"

    response = admin_routes.admin_update_animal(bob["id"], enclosure_id=bob["enclosure_id"], name="Bob", common="",
                                                scientific="", dob="", sex="unknown", species_profile="corn_snake")
    assert response.headers["location"].startswith(f"/admin/animals/{bob['id']}/edit?error=")
