"""Gene Catalog: per-species editable Genes with Inheritance, seeded once (see CONTEXT.md: Gene,
Gene Catalog; RHA-104)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from starlette.requests import Request

import db.db as db_module
from db.migrate import run_migrations
from db.migrations import LATEST_VERSION
from db.migrations import m0028_gene_catalog
from web import admin as admin_routes
from web import gene_catalog_queries as gcq
from web import species_kb_queries as skq


def _request(path: str, query: str = "") -> Request:
    from web.main import app
    return Request({"type": "http", "method": "GET", "path": path, "query_string": query.encode(),
                    "headers": [], "app": app, "root_path": "", "state": {"user": None}})


def _html(response) -> str:
    return response.body.decode("utf-8")


def _gene_id(conn, species_key: str, name: str) -> int:
    return conn.execute("SELECT id FROM gene WHERE species_key = ? AND name = ?", (species_key, name)).fetchone()["id"]


def _names(conn, species_key: str) -> set[str]:
    return {r["name"] for r in conn.execute("SELECT name FROM gene WHERE species_key = ?", (species_key,))}


# --- seed data -----------------------------------------------------------------------------------

def test_seed_covers_five_species_and_every_seed_species_is_a_linked_kb_species(temp_db):
    counts = dict(temp_db.execute("SELECT species_key, COUNT(*) FROM gene GROUP BY species_key").fetchall())
    assert counts == {"ball_python": 20, "leopard_gecko": 14, "crested_gecko": 4, "bearded_dragon": 6, "corn_snake": 16}
    for category, key, *_ in m0028_gene_catalog.GENES:
        assert skq.linked_species(key)["category"] == category, key
    assert skq.linked_species("gargoyle_gecko") is not None  # in the KB, deliberately seeded with no Genes


def test_seed_has_no_polygenic_looks_and_valid_inheritances():
    names = {name.lower() for _, _, name, _, _ in m0028_gene_catalog.GENES}
    assert names.isdisjoint({"harlequin", "dalmatian", "reticulated", "tangerine", "red stripe", "flame"})
    assert {inh for *_, inh, _ in m0028_gene_catalog.GENES} <= set(gcq.INHERITANCES)
    pairs = [(k, n.lower()) for _, k, n, _, _ in m0028_gene_catalog.GENES]
    assert len(pairs) == len(set(pairs)), "duplicate seed Gene"


def test_fresh_install_is_seeded(temp_db):
    # temp_db builds a brand-new database, which skips migrations; SEEDS must cover it.
    assert "Clown" in _names(temp_db, "ball_python")


def test_existing_database_is_seeded_by_migration_28_and_a_deleted_seed_gene_stays_deleted(tmp_path: Path, monkeypatch):
    path = tmp_path / "husbandrytracker.db"
    monkeypatch.setattr(db_module, "DB_PATH", path)
    run_migrations()
    conn = sqlite3.connect(path)
    conn.execute("DROP TABLE gene")
    conn.execute("PRAGMA user_version = 27")
    conn.commit()
    conn.close()

    assert run_migrations() == LATEST_VERSION - 27
    db_module.init_db()  # schema.sql replays on every startup; it must not re-seed
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT COUNT(*) FROM gene").fetchone()[0] == len(m0028_gene_catalog.GENES)
    conn.execute("DELETE FROM gene WHERE name = 'Clown'")
    conn.commit()
    conn.close()

    db_module.init_db()
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT COUNT(*) FROM gene WHERE name = 'Clown'").fetchone()[0] == 0
    conn.close()


# --- rules ---------------------------------------------------------------------------------------

def test_same_name_in_two_species_is_two_genes_but_unique_within_one(temp_db):
    assert "Albino" in _names(temp_db, "ball_python")
    gcq.create_gene("lizard", "bearded_dragon", "Albino", "recessive")
    assert "Albino" in _names(temp_db, "bearded_dragon")

    with pytest.raises(ValueError, match="already has a Gene called"):
        gcq.create_gene("snake", "ball_python", "albino", "recessive")  # case-insensitive


def test_genes_need_a_specific_species_a_name_and_a_valid_inheritance(temp_db):
    for category, key in (("snake", "snake_other"), (None, "saltwater_reef"), ("snake", "no_such"), ("lizard", "ball_python")):
        with pytest.raises(ValueError, match="specific Knowledge Base species"):
            gcq.create_gene(category, key, "Thing", "recessive")
    with pytest.raises(ValueError, match="gene name"):
        gcq.create_gene("snake", "ball_python", "  ", "recessive")
    with pytest.raises(ValueError, match="inheritance"):
        gcq.create_gene("snake", "ball_python", "Thing", "incomplete")


def test_update_gene_and_rename_collision(temp_db):
    clown = _gene_id(temp_db, "ball_python", "Clown")
    gcq.update_gene(clown, "Clown", "co_dominant", "test note")
    row = temp_db.execute("SELECT inheritance, notes FROM gene WHERE id = ?", (clown,)).fetchone()
    assert (row["inheritance"], row["notes"]) == ("co_dominant", "test note")
    with pytest.raises(ValueError, match="already has a Gene"):
        gcq.update_gene(clown, "Piebald", "recessive")


def test_unused_gene_deletes_but_a_used_one_is_blocked_with_a_count(temp_db, monkeypatch):
    temp_db.execute("CREATE TABLE fake_genetics (gene_id INTEGER)")
    pied = _gene_id(temp_db, "ball_python", "Piebald")
    temp_db.executemany("INSERT INTO fake_genetics VALUES (?)", [(pied,), (pied,)])
    temp_db.commit()
    monkeypatch.setattr(gcq, "GENE_REFERENCES", [("fake_genetics", "gene_id")])

    with pytest.raises(ValueError, match="used by 2 records"):
        gcq.delete_gene(pied)
    assert "Piebald" in _names(temp_db, "ball_python")

    gcq.delete_gene(_gene_id(temp_db, "ball_python", "Clown"))
    assert "Clown" not in _names(temp_db, "ball_python")


def test_genes_of_a_species_deleted_from_the_kb_are_still_listed(temp_db):
    corn = skq.linked_species("corn_snake")
    skq.delete_profile("snake", corn["id"])
    groups = gcq.list_genes_by_species()
    assert groups[-1]["label"] == "corn_snake (no longer in the Knowledge Base)"
    assert len(groups[-1]["genes"]) == 16


# --- page and routes ------------------------------------------------------------------------------

def test_page_lists_species_with_their_genes_and_offers_only_specific_species(temp_db):
    html = _html(admin_routes.admin_gene_catalog(_request("/admin/app/gene-catalog")))
    assert "Ball Python <em>(Python regius)</em>" in html
    assert 'value="Clown"' in html
    assert '<option value="snake:ball_python">Ball Python</option>' in html
    assert "snake_other" not in html and "saltwater_reef" not in html
    assert "Gene Catalog" in _html(admin_routes.admin_app(_request("/admin/app/")))


def test_create_route_adds_a_gene_and_reports_errors(temp_db):
    response = admin_routes.admin_create_gene(species="lizard:gargoyle_gecko", name="Test Gene", inheritance="dominant", notes="")
    assert response.headers["location"] == "/admin/app/gene-catalog#genes-lizard-gargoyle_gecko"
    assert _names(temp_db, "gargoyle_gecko") == {"Test Gene"}

    response = admin_routes.admin_create_gene(species="snake:ball_python", name="Clown", inheritance="recessive", notes="")
    assert "error=" in response.headers["location"]


def test_delete_route_redirects_with_the_block_message(temp_db, monkeypatch):
    monkeypatch.setattr(gcq, "gene_usage_count", lambda gene_id: 3)
    response = admin_routes.admin_delete_gene(_gene_id(temp_db, "ball_python", "Clown"))
    assert "used%20by%203%20records" in response.headers["location"]
