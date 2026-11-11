"""Lineage: Sire/Dam as linked Animals or described parents, nested ancestors (see CONTEXT.md:
Lineage; RHA-106)."""
from __future__ import annotations

import pytest
from starlette.requests import Request

from web import admin as admin_routes
from web import admin_queries as q
from web import gene_catalog_queries as gcq
from web import genetics_queries as genq
from web import lineage_queries as linq


def _request(path: str) -> Request:
    from web.main import app
    return Request({"type": "http", "method": "GET", "path": path, "query_string": b"",
                    "headers": [], "app": app, "root_path": "", "state": {"user": None}})


def _html(response) -> str:
    return response.body.decode("utf-8")


@pytest.fixture()
def enclosure(temp_db) -> int:
    return q.create_enclosure("Rack", "basic", False, 7, 3, 7, 30)


def _animal(conn, enclosure: int, name: str, sex: str = "unknown", species: str | None = "ball_python") -> int:
    q.create_animal(enclosure, name, None, None, None, species, sex)
    return conn.execute("SELECT id FROM animal WHERE name = ?", (name,)).fetchone()["id"]


def _gene(conn, name: str) -> int:
    return conn.execute("SELECT id FROM gene WHERE species_key = 'ball_python' AND name = ?", (name,)).fetchone()["id"]


def _names(nodes) -> list[tuple[str, str]]:
    return [(n["role"], n["name"]) for n in nodes]


# --- linked and described parents ------------------------------------------------------------------

def test_linked_parent_shows_its_live_morph_genetics_and_lineage(temp_db, enclosure):
    bob = _animal(temp_db, enclosure, "Bob", "male")
    grandsire = _animal(temp_db, enclosure, "Old Bob", "male")
    baby = _animal(temp_db, enclosure, "Baby")
    linq.link_parent(bob, None, "sire", grandsire)
    linq.link_parent(baby, None, "sire", bob)

    genq.add_animal_gene(bob, _gene(temp_db, "Clown"), "visual")  # changed after linking: shown live
    (sire,) = linq.lineage_tree(baby)
    assert (sire["kind"], sire["name"], sire["line"]) == ("linked", "Bob", "Clown")
    assert _names(sire["parents"]) == [("sire", "Old Bob")]
    assert temp_db.execute("SELECT name, morph FROM lineage_entry WHERE linked_animal_id = ?", (bob,)).fetchone()[:] == (None, None)


def test_described_parents_nest_without_limit_and_carry_genetics(temp_db, enclosure):
    baby = _animal(temp_db, enclosure, "Baby")
    dam = linq.describe_parent(baby, None, "dam", "Breeder Female", "Banana")
    linq.add_entry_gene(baby, dam, _gene(temp_db, "Piebald"), "het", evidence="proven")
    owner = dam
    for generation in range(2, 7):  # five more generations of Dams
        owner = linq.describe_parent(baby, owner, "dam", f"Gen {generation}", None)

    (node,) = linq.lineage_tree(baby)
    assert (node["kind"], node["line"]) == ("described", "Banana · 100% het Piebald (proven)")
    depth = 1
    while node["parents"]:
        (node,) = node["parents"]
        depth += 1
        assert node["open"] == (depth <= linq.OPEN_GENERATIONS)
    assert depth == 6 and node["name"] == "Gen 6"


def test_any_node_may_be_missing_and_unnamed(temp_db, enclosure):
    baby = _animal(temp_db, enclosure, "Baby")
    assert linq.lineage_tree(baby) == []
    linq.describe_parent(baby, None, "dam", "", "")
    (dam,) = linq.lineage_tree(baby)
    assert (dam["name"], dam["line"]) == ("Unnamed Dam", "Normal")


def test_one_sire_and_one_dam_per_slot_and_linked_entries_have_no_own_parents(temp_db, enclosure):
    baby = _animal(temp_db, enclosure, "Baby")
    bob = _animal(temp_db, enclosure, "Bob", "male")
    entry = linq.link_parent(baby, None, "sire", bob)
    with pytest.raises(ValueError, match="already a Sire"):
        linq.describe_parent(baby, None, "sire", "Other", None)
    with pytest.raises(ValueError, match="edited on that Animal's page"):
        linq.describe_parent(baby, entry, "dam", "X", None)
    with pytest.raises(ValueError, match="Sire or Dam"):
        linq.describe_parent(baby, None, "father", "X", None)


# --- picker rules -----------------------------------------------------------------------------------

def test_candidates_are_same_species_with_matching_or_unknown_sex(temp_db, enclosure):
    baby = _animal(temp_db, enclosure, "Baby")
    _animal(temp_db, enclosure, "Male BP", "male")
    _animal(temp_db, enclosure, "Female BP", "female")
    _animal(temp_db, enclosure, "Unsexed BP", "unknown")
    _animal(temp_db, enclosure, "Male Corn", "male", "corn_snake")
    assert {c["name"] for c in linq.candidate_parents(baby, "sire")} == {"Male BP", "Unsexed BP"}
    assert {c["name"] for c in linq.candidate_parents(baby, "dam")} == {"Female BP", "Unsexed BP"}

    with pytest.raises(ValueError, match="same Knowledge Base species"):
        linq.link_parent(baby, None, "sire", temp_db.execute("SELECT id FROM animal WHERE name = 'Male Corn'").fetchone()[0])
    with pytest.raises(ValueError, match="can't be linked as a Sire"):
        linq.link_parent(baby, None, "sire", temp_db.execute("SELECT id FROM animal WHERE name = 'Female BP'").fetchone()[0])


def test_an_animal_cannot_be_its_own_ancestor(temp_db, enclosure):
    a = _animal(temp_db, enclosure, "A")
    b = _animal(temp_db, enclosure, "B")
    c = _animal(temp_db, enclosure, "C")
    with pytest.raises(ValueError, match="its own ancestor"):
        linq.link_parent(a, None, "sire", a)
    linq.link_parent(b, None, "sire", a)       # A -> B
    described = linq.describe_parent(c, None, "dam", "Breeder dam", None)
    linq.link_parent(c, described, "sire", b)  # B is C's grandsire, through a described entry
    with pytest.raises(ValueError, match="would make A its own ancestor"):
        linq.link_parent(a, None, "dam", c)
    assert "C" not in {x["name"] for x in linq.candidate_parents(a, "dam")}
    assert linq.linked_ancestors(c) == {a, b}


def test_a_resexed_parent_is_flagged_not_unlinked(temp_db, enclosure):
    baby = _animal(temp_db, enclosure, "Baby")
    bob = _animal(temp_db, enclosure, "Bob", "male")
    linq.link_parent(baby, None, "sire", bob)
    q.update_animal(bob, enclosure, "Bob", None, None, None, "female", "ball_python")
    (sire,) = linq.lineage_tree(baby)
    assert sire["kind"] == "linked"
    assert sire["flags"] == ["Sex is Female, but linked as Sire"]
    assert "Sex is Female, but linked as Sire" in _html(admin_routes.admin_animal_detail(_request("/x"), baby))


# --- ownership, gating, deletes -----------------------------------------------------------------------

def test_entries_belong_to_one_animal(temp_db, enclosure):
    baby = _animal(temp_db, enclosure, "Baby")
    other = _animal(temp_db, enclosure, "Other")
    dam = linq.describe_parent(baby, None, "dam", "Breeder Female", None)
    with pytest.raises(ValueError, match="isn't part of this Animal's Lineage"):
        linq.update_described(other, dam, "Hijack", None)
    with pytest.raises(ValueError, match="isn't part of this Animal's Lineage"):
        linq.describe_parent(other, dam, "sire", "X", None)


def test_gated_like_genetics(temp_db, enclosure):
    coral = _animal(temp_db, enclosure, "Coral", species="saltwater_reef")
    with pytest.raises(ValueError, match="specific Knowledge Base species"):
        linq.describe_parent(coral, None, "dam", "X", None)
    assert linq.candidate_parents(coral, "sire") == []
    html = _html(admin_routes.admin_edit_animal(_request("/x"), coral))
    assert 'id="lineage"' not in html


def test_species_change_blocked_with_lineage(temp_db, enclosure):
    baby = _animal(temp_db, enclosure, "Baby")
    linq.describe_parent(baby, None, "dam", "X", None)
    with pytest.raises(ValueError, match="1 parent in its Lineage"):
        q.update_animal(baby, enclosure, "Baby", None, None, None, "unknown", "corn_snake")


def test_removing_an_entry_removes_described_ancestors_and_deleting_the_animal_removes_its_tree(temp_db, enclosure):
    baby = _animal(temp_db, enclosure, "Baby")
    dam = linq.describe_parent(baby, None, "dam", "D", None)
    linq.add_entry_gene(baby, dam, _gene(temp_db, "Clown"), "visual")
    linq.describe_parent(baby, dam, "sire", "DS", None)
    linq.remove_entry(baby, dam)
    assert temp_db.execute("SELECT COUNT(*) FROM lineage_entry").fetchone()[0] == 0
    assert temp_db.execute("SELECT COUNT(*) FROM lineage_entry_gene").fetchone()[0] == 0

    linq.describe_parent(baby, None, "dam", "D2", None)
    q.delete_animal(baby)
    assert temp_db.execute("SELECT COUNT(*) FROM lineage_entry").fetchone()[0] == 0


def test_deleting_a_linked_parent_keeps_its_name_in_the_offspring_tree(temp_db, enclosure):
    baby = _animal(temp_db, enclosure, "Baby")
    bob = _animal(temp_db, enclosure, "Bob", "male")
    linq.link_parent(baby, None, "sire", bob)
    q.delete_animal(bob)
    (sire,) = linq.lineage_tree(baby)
    assert (sire["kind"], sire["name"]) == ("described", "Bob")


def test_a_gene_used_by_a_described_parent_stays_in_the_catalog(temp_db, enclosure):
    baby = _animal(temp_db, enclosure, "Baby")
    dam = linq.describe_parent(baby, None, "dam", "D", None)
    linq.add_entry_gene(baby, dam, _gene(temp_db, "Clown"), "visual")
    with pytest.raises(ValueError, match="used by 1 record"):
        gcq.delete_gene(_gene(temp_db, "Clown"))


# --- pages and routes -------------------------------------------------------------------------------

def test_edit_page_animal_page_and_entry_page(temp_db, enclosure):
    baby = _animal(temp_db, enclosure, "Baby")
    bob = _animal(temp_db, enclosure, "Bob", "male")
    response = admin_routes.admin_link_parent(baby, owner_entry_id="", role="sire", parent_animal_id=str(bob))
    assert response.headers["location"] == f"/admin/animals/{baby}/edit#lineage"
    admin_routes.admin_describe_parent(baby, owner_entry_id="", role="dam", name="Breeder Female", morph="Banana")
    dam = temp_db.execute("SELECT id FROM lineage_entry WHERE name = 'Breeder Female'").fetchone()["id"]

    edit = _html(admin_routes.admin_edit_animal(_request("/x"), baby))
    assert 'id="lineage"' in edit and "Family tree" in edit
    assert f"/admin/animals/{baby}/lineage/{dam}" in edit

    page = _html(admin_routes.admin_animal_detail(_request("/x"), baby))
    assert 'class="lineage-tree"' in page and "Breeder Female" in page and f'href="/admin/animals/{bob}"' in page

    entry_page = _html(admin_routes.admin_lineage_entry(_request("/x"), baby, dam))
    assert "Dam in Baby's Lineage" in entry_page and "Add to Genetics" in entry_page
    assert "Link Sire" in entry_page and "Describe Dam" in entry_page

    response = admin_routes.admin_describe_parent(baby, owner_entry_id=str(dam), role="sire", name="DS", morph="")
    assert response.headers["location"] == f"/admin/animals/{baby}/lineage/{dam}#lineage"
    response = admin_routes.admin_link_parent(baby, owner_entry_id="", role="sire", parent_animal_id=str(bob))
    assert "error=" in response.headers["location"]

    response = admin_routes.admin_add_entry_gene(baby, dam, gene_id=str(_gene(temp_db, "Clown")), new_gene_name="",
                                                new_gene_inheritance="", state="het", percent="", evidence="claimed")
    assert response.headers["location"] == f"/admin/animals/{baby}/lineage/{dam}#genetics"
    (_, dam_node) = linq.lineage_tree(baby)
    assert dam_node["line"] == "Banana · 100% het Clown"


# --- Copy Lineage (RHA-107) ------------------------------------------------------------------------

def _clutch(conn, enclosure):
    """Bob (linked Sire) and a described Dam with Genetics and a described grandsire, on Baby."""
    bob = _animal(conn, enclosure, "Bob", "male")
    baby = _animal(conn, enclosure, "Baby")
    linq.link_parent(baby, None, "sire", bob)
    dam = linq.describe_parent(baby, None, "dam", "Breeder Dam", "Pastel")
    linq.add_entry_gene(baby, dam, _gene(conn, "Clown"), "het", 66)
    linq.describe_parent(baby, dam, "sire", "Breeder Grandsire", None)
    return bob, baby, dam


def test_copy_lineage_deep_copies_described_entries_and_keeps_links(temp_db, enclosure):
    bob, baby, dam = _clutch(temp_db, enclosure)
    mate = _animal(temp_db, enclosure, "Clutch-mate")
    linq.copy_lineage(mate, baby)

    tree = linq.lineage_tree(mate)
    assert _names(tree) == [("sire", "Bob"), ("dam", "Breeder Dam")]
    assert tree[0]["kind"] == "linked" and tree[0]["animal_id"] == bob
    assert tree[1]["line"] == linq.lineage_tree(baby)[1]["line"]
    assert _names(tree[1]["parents"]) == [("sire", "Breeder Grandsire")]
    assert tree[1]["entry_id"] != dam  # new rows, owned by the target
    assert linq.root_animal_id(tree[1]["parents"][0]["entry_id"]) == mate


def test_copied_trees_are_independent(temp_db, enclosure):
    _, baby, dam = _clutch(temp_db, enclosure)
    mate = _animal(temp_db, enclosure, "Clutch-mate")
    linq.copy_lineage(mate, baby)
    copied_dam = linq.lineage_tree(mate)[1]["entry_id"]

    linq.update_described(mate, copied_dam, "Renamed Dam", None)
    linq.remove_entry(baby, linq.lineage_tree(baby)[1]["parents"][0]["entry_id"])
    assert linq.lineage_tree(baby)[1]["name"] == "Breeder Dam"
    assert _names(linq.lineage_tree(mate)[1]["parents"]) == [("sire", "Breeder Grandsire")]
    with pytest.raises(ValueError, match="isn't part of this Animal's Lineage"):
        linq.update_described(baby, copied_dam, "x", None)


def test_copy_needs_replace_to_overwrite_an_existing_lineage(temp_db, enclosure):
    _, baby, _ = _clutch(temp_db, enclosure)
    mate = _animal(temp_db, enclosure, "Clutch-mate")
    linq.describe_parent(mate, None, "sire", "Wrong Sire", None)
    with pytest.raises(ValueError, match="already has a Lineage"):
        linq.copy_lineage(mate, baby)
    assert _names(linq.lineage_tree(mate)) == [("sire", "Wrong Sire")]

    linq.copy_lineage(mate, baby, replace=True)
    assert _names(linq.lineage_tree(mate)) == [("sire", "Bob"), ("dam", "Breeder Dam")]
    assert temp_db.execute("SELECT COUNT(*) FROM lineage_entry WHERE name = 'Wrong Sire'").fetchone()[0] == 0


def test_copy_refuses_other_species_empty_sources_and_cycles(temp_db, enclosure):
    bob, baby, _ = _clutch(temp_db, enclosure)
    other = _animal(temp_db, enclosure, "Leo", species="leopard_gecko")
    with pytest.raises(ValueError, match="same Knowledge Base species"):
        linq.copy_lineage(other, baby)
    empty = _animal(temp_db, enclosure, "Empty")
    with pytest.raises(ValueError, match="no Lineage to copy"):
        linq.copy_lineage(baby, empty, replace=True)
    with pytest.raises(ValueError, match="its own ancestor"):  # Bob is Baby's Sire
        linq.copy_lineage(bob, baby)
    assert [s["name"] for s in linq.copy_sources(empty)] == ["Baby"]
    assert linq.copy_sources(bob) == []


def test_copy_route_and_edit_page_offer(temp_db, enclosure):
    _, baby, _ = _clutch(temp_db, enclosure)
    mate = _animal(temp_db, enclosure, "Clutch-mate")
    page = _html(admin_routes.admin_edit_animal(_request(f"/admin/animals/{mate}/edit"), mate))
    assert "Copy Lineage from" in page and "Replace the current Lineage" not in page

    response = admin_routes.admin_copy_lineage(mate, str(baby), "")
    assert response.headers["location"] == f"/admin/animals/{mate}/edit#lineage"
    assert linq.lineage_entry_count(mate) == 2

    response = admin_routes.admin_copy_lineage(mate, str(baby), "")
    assert "error=" in response.headers["location"]
    page = _html(admin_routes.admin_edit_animal(_request(f"/admin/animals/{mate}/edit"), mate))
    assert "Replace the current Lineage" in page


# --- Snapshot on delete (RHA-108) ------------------------------------------------------------------

def test_deleting_a_linked_parent_snapshots_its_morph_genetics_and_lineage(temp_db, enclosure):
    bob = _animal(temp_db, enclosure, "Bob", "male")
    old_bob = _animal(temp_db, enclosure, "Old Bob", "male")
    baby = _animal(temp_db, enclosure, "Baby")
    genq.set_morph(bob, "Killer Clown")
    genq.add_animal_gene(bob, _gene(temp_db, "Clown"), "visual")
    linq.link_parent(bob, None, "sire", old_bob)
    bob_dam = linq.describe_parent(bob, None, "dam", "Breeder Dam", None)
    linq.add_entry_gene(bob, bob_dam, _gene(temp_db, "Clown"), "het")
    linq.link_parent(baby, None, "sire", bob)
    live_line = linq.lineage_tree(baby)[0]["line"]

    q.delete_animal(bob)
    (sire,) = linq.lineage_tree(baby)
    assert (sire["kind"], sire["name"], sire["line"]) == ("described", "Bob", live_line)
    assert _names(sire["parents"]) == [("sire", "Old Bob"), ("dam", "Breeder Dam")]
    assert sire["parents"][0]["kind"] == "linked"  # still-living ancestors stay linked
    assert "het Clown" in sire["parents"][1]["line"]
    assert linq.root_animal_id(sire["parents"][1]["entry_id"]) == baby


def test_each_child_gets_its_own_snapshot(temp_db, enclosure):
    bob = _animal(temp_db, enclosure, "Bob", "male")
    a, b = _animal(temp_db, enclosure, "A"), _animal(temp_db, enclosure, "B")
    linq.describe_parent(bob, None, "dam", "Bob's Dam", None)
    linq.link_parent(a, None, "sire", bob)
    linq.link_parent(b, None, "sire", bob)
    assert linq.lineages_linking(bob) == 2

    q.delete_animal(bob)
    sa, sb = linq.lineage_tree(a)[0], linq.lineage_tree(b)[0]
    assert sa["parents"][0]["entry_id"] != sb["parents"][0]["entry_id"]
    linq.remove_entry(a, sa["parents"][0]["entry_id"])
    assert _names(linq.lineage_tree(b)[0]["parents"]) == [("dam", "Bob's Dam")]


def test_deleting_a_grandparent_linked_through_a_linked_parent_keeps_every_tree(temp_db, enclosure):
    grand = _animal(temp_db, enclosure, "Grand", "male")
    bob = _animal(temp_db, enclosure, "Bob", "male")
    baby = _animal(temp_db, enclosure, "Baby")
    linq.link_parent(bob, None, "sire", grand)
    linq.link_parent(baby, None, "sire", bob)
    dam = linq.describe_parent(baby, None, "dam", "D", None)
    linq.link_parent(baby, dam, "sire", grand)  # Grand also sits under a described entry
    assert linq.lineages_linking(grand) == 2  # Bob's and Baby's

    q.delete_animal(grand)
    assert temp_db.execute("SELECT COUNT(*) FROM lineage_entry WHERE linked_animal_id IS NULL AND name = 'Grand'").fetchone()[0] == 2
    sire, dam_node = linq.lineage_tree(baby)
    assert sire["kind"] == "linked" and _names(sire["parents"]) == [("sire", "Grand")]
    assert sire["parents"][0]["kind"] == "described"
    assert _names(dam_node["parents"]) == [("sire", "Grand")] and dam_node["parents"][0]["kind"] == "described"
    assert linq.lineage_tree(bob)[0]["name"] == "Grand"


def test_enclosure_remove_button_warns_about_snapshots(temp_db, enclosure):
    bob = _animal(temp_db, enclosure, "Bob", "male")
    baby = _animal(temp_db, enclosure, "Baby")
    linq.link_parent(baby, None, "sire", bob)
    page = _html(admin_routes.admin_enclosure_detail(_request(f"/admin/enclosures/{enclosure}"), enclosure))
    assert "Bob is a parent in 1 Lineage; it'll keep a snapshot of Bob. Remove Bob?" in page
    assert page.count("data-confirm=") == 1


# --- Offspring (RHA-109) ---------------------------------------------------------------------------

def _born(conn, enclosure: int, name: str, dob: str | None, sex: str = "unknown") -> int:
    q.create_animal(enclosure, name, None, None, dob, "ball_python", sex)
    return conn.execute("SELECT id FROM animal WHERE name = ?", (name,)).fetchone()["id"]


def test_offspring_grouped_by_other_parent_and_sorted_by_dob(temp_db, enclosure):
    bob = _animal(temp_db, enclosure, "Bob", "male")
    sally = _animal(temp_db, enclosure, "Sally", "female")
    late = _born(temp_db, enclosure, "Late", "2026-06-01")
    early = _born(temp_db, enclosure, "Early", "2025-05-01")
    mid = _born(temp_db, enclosure, "Mid", "2025-05-01")
    loner = _born(temp_db, enclosure, "Loner", "2024-01-01")
    nodob = _born(temp_db, enclosure, "No DOB", None)
    for child in (late, early, mid, loner, nodob):
        linq.link_parent(child, None, "sire", bob)
    linq.link_parent(early, None, "dam", sally)
    linq.link_parent(mid, None, "dam", sally)
    linq.describe_parent(late, None, "dam", "Breeder Girl", None)
    linq.describe_parent(nodob, None, "dam", "Breeder Girl", None)
    genq.add_animal_gene(early, _gene(temp_db, "Clown"), "visual")

    groups = linq.offspring(bob)
    assert [(g["other"] and g["other"]["name"], [c["name"] for c in g["children"]]) for g in groups] == [
        (None, ["Loner"]),
        ("Sally", ["Early", "Mid"]),
        ("Breeder Girl", ["Late", "No DOB"]),
    ]
    assert groups[1]["other"]["kind"] == "linked" and groups[1]["other"]["role_label"] == "Dam"
    assert groups[1]["children"][0]["line"] == "Clown"
    assert groups[1]["children"][0]["enclosure_name"] == "Rack"
    assert [c["name"] for g in linq.offspring(sally) for c in g["children"]] == ["Early", "Mid"]


def test_offspring_excludes_grandchildren_and_snapshots(temp_db, enclosure):
    grand = _animal(temp_db, enclosure, "Grand", "male")
    bob = _animal(temp_db, enclosure, "Bob", "male")
    baby = _animal(temp_db, enclosure, "Baby")
    linq.link_parent(bob, None, "sire", grand)
    linq.link_parent(baby, None, "sire", bob)
    dam = linq.describe_parent(baby, None, "dam", "D", None)
    linq.link_parent(baby, dam, "sire", grand)  # Grand is Baby's grandsire, not its parent
    assert [c["name"] for g in linq.offspring(grand) for c in g["children"]] == ["Bob"]

    q.delete_animal(bob)  # Baby now holds a described snapshot of Bob, with Grand linked beneath it
    assert linq.offspring(grand) == []  # snapshots aren't offspring


def test_animal_page_offspring_card_only_when_there_are_some(temp_db, enclosure):
    bob = _animal(temp_db, enclosure, "Bob", "male")
    page = _html(admin_routes.admin_animal_detail(_request(f"/admin/animals/{bob}"), bob))
    assert 'id="offspring"' not in page
    baby = _born(temp_db, enclosure, "Baby", "2026-01-02")
    linq.link_parent(baby, None, "sire", bob)
    page = _html(admin_routes.admin_animal_detail(_request(f"/admin/animals/{bob}"), bob))
    assert 'id="offspring"' in page and f'href="/admin/animals/{baby}">Baby</a>' in page
    assert "Other parent unknown" in page and "2026-01-02" in page
