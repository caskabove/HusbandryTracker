"""Lineage (see CONTEXT.md: Lineage; ADR 0059; RHA-106): an Animal's family tree.

Every parent is a `lineage_entry` row filling one slot, Sire or Dam, of either an Animal
(child_animal_id) or a described entry (child_entry_id). An entry is either:

- linked: linked_animal_id points at a real Animal, whose own live Morph, Genetics and Lineage are
  used; nothing is copied, and a linked entry never has parent rows of its own; or
- described: name/morph on the row and Genetics in `lineage_entry_gene`, with its own parents as
  further entries beneath it.

Each Animal owns the described entries under it; they're never shared. Gated like Genetics: only an
Animal linked to a specific Knowledge Base species has a Lineage.
"""
from __future__ import annotations

from db.db import get_connection
from web import genetics_queries as genq

ROLES = ["sire", "dam"]
ROLE_LABELS = {"sire": "Sire", "dam": "Dam"}
ROLE_SEX = {"sire": "male", "dam": "female"}

# Generations shown expanded on the Animal Page; deeper ones start collapsed.
OPEN_GENERATIONS = 3
# A backstop against walking a corrupt tree forever; real trees are far shallower.
_MAX_DEPTH = 40


def _animal(conn, animal_id: int) -> dict:
    row = conn.execute("SELECT * FROM animal WHERE id = ?", (animal_id,)).fetchone()
    if row is None:
        raise ValueError("That Animal no longer exists.")
    return dict(row)


def _species_or_raise(animal: dict) -> dict:
    species = genq.genetics_species(animal)
    if species is None:
        raise ValueError("Link this Animal to a specific Knowledge Base species before recording its Lineage.")
    return species


def root_animal_id(entry_id: int) -> int | None:
    """The Animal whose tree a (described or linked) entry sits in."""
    with get_connection() as conn:
        row = conn.execute(
            """WITH RECURSIVE up(id, child_animal_id, child_entry_id) AS (
                   SELECT id, child_animal_id, child_entry_id FROM lineage_entry WHERE id = ?
                   UNION
                   SELECT le.id, le.child_animal_id, le.child_entry_id FROM lineage_entry le JOIN up ON le.id = up.child_entry_id
               ) SELECT child_animal_id FROM up WHERE child_animal_id IS NOT NULL""",
            (entry_id,),
        ).fetchone()
    return row["child_animal_id"] if row else None


def get_entry(animal_id: int, entry_id: int) -> dict:
    """An entry of this Animal's tree; ValueError if it isn't one."""
    if root_animal_id(entry_id) != animal_id:
        raise ValueError("That Lineage Entry isn't part of this Animal's Lineage.")
    with get_connection() as conn:
        return dict(conn.execute("SELECT * FROM lineage_entry WHERE id = ?", (entry_id,)).fetchone())


def linked_ancestors(animal_id: int) -> set[int]:
    """Every real Animal anywhere in this Animal's tree, through described entries and through
    linked Animals' own Lineages."""
    with get_connection() as conn:
        rows = conn.execute(
            """WITH RECURSIVE e(id, linked) AS (
                   SELECT id, linked_animal_id FROM lineage_entry WHERE child_animal_id = ?
                   UNION
                   SELECT le.id, le.linked_animal_id FROM lineage_entry le JOIN e
                     ON le.child_entry_id = e.id OR (e.linked IS NOT NULL AND le.child_animal_id = e.linked)
               ) SELECT DISTINCT linked FROM e WHERE linked IS NOT NULL""",
            (animal_id,),
        ).fetchall()
    return {r["linked"] for r in rows}


def _would_cycle(animal_id: int, parent_animal_id: int) -> bool:
    """Linking parent_animal_id anywhere in animal_id's tree makes the Animal its own ancestor iff
    it's the same Animal or the Animal already appears in the parent's tree."""
    return parent_animal_id == animal_id or animal_id in linked_ancestors(parent_animal_id)


def sex_mismatch(role: str, sex: str | None) -> bool:
    """A linked parent's Sex should match its role; Unknown is fine (see CONTEXT.md: Lineage)."""
    return (sex or "unknown") not in (ROLE_SEX[role], "unknown")


def candidate_parents(animal_id: int, role: str) -> list[dict]:
    """Animals that can be linked into this Animal's tree as a Sire or Dam: same Knowledge Base
    species, Sex matching the role or Unknown, and not making the Animal its own ancestor."""
    with get_connection() as conn:
        animal = _animal(conn, animal_id)
        if genq.genetics_species(animal) is None:
            return []
        rows = [dict(r) for r in conn.execute(
            "SELECT id, name, sex, dob FROM animal WHERE species_profile = ? AND id != ? ORDER BY name COLLATE NOCASE",
            (animal["species_profile"], animal_id),
        )]
    return [r for r in rows if not sex_mismatch(role, r["sex"]) and not _would_cycle(animal_id, r["id"])]


def _check_slot(conn, animal_id: int, owner_entry_id: int | None, role: str) -> None:
    if role not in ROLES:
        raise ValueError("Pick Sire or Dam.")
    if owner_entry_id:
        owner = get_entry(animal_id, owner_entry_id)
        if owner["linked_animal_id"]:
            raise ValueError("A linked parent's own Lineage is edited on that Animal's page.")
        where, owner_id = "child_entry_id", owner_entry_id
    else:
        where, owner_id = "child_animal_id", animal_id
    taken = conn.execute(f"SELECT 1 FROM lineage_entry WHERE {where} = ? AND role = ?", (owner_id, role)).fetchone()
    if taken:
        raise ValueError(f"There's already a {ROLE_LABELS[role]} here; remove it first.")


def _insert(conn, animal_id: int, owner_entry_id: int | None, role: str, **values) -> int:
    owner = {"child_entry_id": owner_entry_id} if owner_entry_id else {"child_animal_id": animal_id}
    fields = {**owner, "role": role, **values}
    cur = conn.execute(
        f"INSERT INTO lineage_entry ({', '.join(fields)}) VALUES ({', '.join('?' * len(fields))})",
        tuple(fields.values()),
    )
    return cur.lastrowid


def link_parent(animal_id: int, owner_entry_id: int | None, role: str, parent_animal_id: int) -> int:
    """Fills a Sire/Dam slot (of the Animal itself, or of a described entry in its tree) with a
    real Animal."""
    with get_connection() as conn:
        animal = _animal(conn, animal_id)
        _species_or_raise(animal)
        _check_slot(conn, animal_id, owner_entry_id, role)
        parent = _animal(conn, parent_animal_id)
    if parent["species_profile"] != animal["species_profile"]:
        raise ValueError(f"{parent['name']} isn't the same Knowledge Base species as {animal['name']}.")
    if sex_mismatch(role, parent["sex"]):
        raise ValueError(f"{parent['name']} is {parent['sex'].capitalize()}, so it can't be linked as a {ROLE_LABELS[role]}.")
    if _would_cycle(animal_id, parent_animal_id):
        raise ValueError(f"Linking {parent['name']} would make {animal['name']} its own ancestor.")
    with get_connection() as conn:
        return _insert(conn, animal_id, owner_entry_id, role, linked_animal_id=parent_animal_id)


def describe_parent(animal_id: int, owner_entry_id: int | None, role: str, name: str | None, morph: str | None) -> int:
    """Fills a Sire/Dam slot with a described parent: an animal never owned."""
    with get_connection() as conn:
        _species_or_raise(_animal(conn, animal_id))
        _check_slot(conn, animal_id, owner_entry_id, role)
        return _insert(conn, animal_id, owner_entry_id, role,
                       name=(name or "").strip() or None, morph=(morph or "").strip() or None)


def update_described(animal_id: int, entry_id: int, name: str | None, morph: str | None) -> None:
    entry = get_entry(animal_id, entry_id)
    if entry["linked_animal_id"]:
        raise ValueError("A linked parent is edited on its own Animal page.")
    with get_connection() as conn:
        conn.execute("UPDATE lineage_entry SET name = ?, morph = ? WHERE id = ?",
                     ((name or "").strip() or None, (morph or "").strip() or None, entry_id))


def remove_entry(animal_id: int, entry_id: int) -> None:
    """Removes the entry and every described ancestor beneath it."""
    get_entry(animal_id, entry_id)
    with get_connection() as conn:
        conn.execute("DELETE FROM lineage_entry WHERE id = ?", (entry_id,))


def entry_species(animal_id: int) -> dict | None:
    with get_connection() as conn:
        return genq.genetics_species(_animal(conn, animal_id))


def add_entry_gene(animal_id: int, entry_id: int, gene_id: int | None, state: str, percent=None, evidence=None,
                   new_gene_name: str | None = None, new_gene_inheritance: str | None = None) -> int:
    if get_entry(animal_id, entry_id)["linked_animal_id"]:
        raise ValueError("A linked parent's Genetics are edited on its own Animal page.")
    return genq.add_gene("entry", entry_id, entry_species(animal_id), gene_id, state, percent, evidence,
                         new_gene_name, new_gene_inheritance)


def update_entry_gene(animal_id: int, entry_id: int, row_id: int, state: str, percent=None, evidence=None) -> None:
    get_entry(animal_id, entry_id)
    genq.update_gene("entry", entry_id, row_id, state, percent, evidence)


def delete_entry_gene(animal_id: int, entry_id: int, row_id: int) -> None:
    get_entry(animal_id, entry_id)
    genq.delete_gene("entry", entry_id, row_id)


# --- the tree ------------------------------------------------------------------------------------

def _slots(conn, column: str, owner_id: int) -> dict[str, dict]:
    return {r["role"]: dict(r) for r in conn.execute(f"SELECT * FROM lineage_entry WHERE {column} = ?", (owner_id,))}


def _node(conn, entry: dict, root: dict, generation: int, path: frozenset[int]) -> dict:
    role = entry["role"]
    node = {"entry_id": entry["id"], "role": role, "role_label": ROLE_LABELS[role], "generation": generation,
            "open": generation <= OPEN_GENERATIONS, "flags": []}
    if entry["linked_animal_id"]:
        animal = dict(conn.execute("SELECT * FROM animal WHERE id = ?", (entry["linked_animal_id"],)).fetchone())
        node.update(kind="linked", animal_id=animal["id"], name=animal["name"], sex=animal["sex"],
                    line=genq.genetics_line(animal) or "")
        if sex_mismatch(role, animal["sex"]):
            node["flags"].append(f"Sex is {animal['sex'].capitalize()}, but linked as {ROLE_LABELS[role]}")
        if animal["species_profile"] != root["species_profile"]:
            node["flags"].append("Not the same Knowledge Base species")
        if animal["id"] in path:  # can't be created through the app; never walk it
            node["flags"].append("Appears in its own Lineage")
            node["parents"] = []
        else:
            node["parents"] = _parents(conn, "child_animal_id", animal["id"], root, generation + 1, path | {animal["id"]})
    else:
        node.update(kind="described", name=entry["name"] or f"Unnamed {ROLE_LABELS[role]}",
                    line=genq.notation(entry["morph"], genq.list_genetics("entry", entry["id"])))
        node["parents"] = _parents(conn, "child_entry_id", entry["id"], root, generation + 1, path)
    return node


def _parents(conn, column: str, owner_id: int, root: dict, generation: int, path: frozenset[int]) -> list[dict]:
    if generation > _MAX_DEPTH:
        return []
    slots = _slots(conn, column, owner_id)
    return [_node(conn, slots[role], root, generation, path) for role in ROLES if role in slots]


def lineage_tree(animal_id: int) -> list[dict]:
    """The Animal's parents as nested nodes ({"kind": "linked"|"described", "name", "line", "flags",
    "parents": [...], ...}), Sire before Dam. Linked parents bring their own live Lineage."""
    with get_connection() as conn:
        root = _animal(conn, animal_id)
        return _parents(conn, "child_animal_id", animal_id, root, 1, frozenset({animal_id}))


def slots_for(animal_id: int, owner_entry_id: int | None) -> list[dict]:
    """The Sire and Dam slots of the Animal itself (owner_entry_id None) or of one described entry,
    for the editing UI: {"role", "label", "node" (or None when empty), "candidates"}."""
    with get_connection() as conn:
        root = _animal(conn, animal_id)
        column, owner_id = ("child_entry_id", owner_entry_id) if owner_entry_id else ("child_animal_id", animal_id)
        generation = 1 if not owner_entry_id else 2
        filled = {n["role"]: n for n in _parents(conn, column, owner_id, root, generation, frozenset({animal_id}))}
    return [{"role": role, "label": ROLE_LABELS[role], "node": filled.get(role),
             "candidates": [] if role in filled else candidate_parents(animal_id, role)} for role in ROLES]


def lineage_entry_count(animal_id: int) -> int:
    """Parents recorded directly on the Animal (described ones bring their ancestors with them)."""
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM lineage_entry WHERE child_animal_id = ?", (animal_id,)).fetchone()[0]


# --- Copy Lineage (RHA-107) ----------------------------------------------------------------------

def copy_sources(animal_id: int) -> list[dict]:
    """Animals whose Lineage can be copied onto this one: same Knowledge Base species, with at least
    one parent recorded, and not making this Animal its own ancestor."""
    with get_connection() as conn:
        animal = _animal(conn, animal_id)
        if genq.genetics_species(animal) is None:
            return []
        rows = [dict(r) for r in conn.execute(
            """SELECT id, name FROM animal a WHERE species_profile = ? AND id != ?
                 AND EXISTS (SELECT 1 FROM lineage_entry WHERE child_animal_id = a.id)
               ORDER BY name COLLATE NOCASE""",
            (animal["species_profile"], animal_id),
        )]
    return [r for r in rows if animal_id not in linked_ancestors(r["id"])]


def _copy_children(conn, column: str, source_owner: int, target_animal: int | None, target_entry: int | None) -> None:
    for entry in conn.execute(f"SELECT * FROM lineage_entry WHERE {column} = ?", (source_owner,)).fetchall():
        new_id = conn.execute(
            "INSERT INTO lineage_entry (child_animal_id, child_entry_id, role, linked_animal_id, name, morph) VALUES (?, ?, ?, ?, ?, ?)",
            (target_animal, target_entry, entry["role"], entry["linked_animal_id"], entry["name"], entry["morph"]),
        ).lastrowid
        if entry["linked_animal_id"]:
            continue  # a linked parent brings its own live Lineage; nothing beneath it to copy
        conn.execute(
            """INSERT INTO lineage_entry_gene (entry_id, gene_id, state, percent, evidence)
               SELECT ?, gene_id, state, percent, evidence FROM lineage_entry_gene WHERE entry_id = ?""",
            (new_id, entry["id"]),
        )
        _copy_children(conn, "child_entry_id", entry["id"], None, new_id)


def copy_lineage(animal_id: int, source_animal_id: int, replace: bool = False) -> None:
    """Deep-copies the source Animal's whole Lineage onto this Animal: described entries (and their
    Genetics) become new rows owned by this Animal, linked entries stay linked to the same Animals.
    The two trees are independent afterwards. An existing Lineage is only overwritten with replace."""
    with get_connection() as conn:
        animal = _animal(conn, animal_id)
        _species_or_raise(animal)
        source = _animal(conn, source_animal_id)
    if source_animal_id == animal_id:
        raise ValueError("Pick a different Animal to copy from.")
    if source["species_profile"] != animal["species_profile"]:
        raise ValueError(f"{source['name']} isn't the same Knowledge Base species as {animal['name']}.")
    if not lineage_entry_count(source_animal_id):
        raise ValueError(f"{source['name']} has no Lineage to copy.")
    if animal_id in linked_ancestors(source_animal_id):
        raise ValueError(f"Copying {source['name']}'s Lineage would make {animal['name']} its own ancestor.")
    if lineage_entry_count(animal_id) and not replace:
        raise ValueError(f"{animal['name']} already has a Lineage; tick \"Replace the current Lineage\" to overwrite it.")
    with get_connection() as conn:
        conn.execute("DELETE FROM lineage_entry WHERE child_animal_id = ?", (animal_id,))
        _copy_children(conn, "child_animal_id", source_animal_id, animal_id, None)


# --- Snapshot on delete (RHA-108) ----------------------------------------------------------------

def lineages_linking(animal_id: int) -> int:
    """How many Animals' Lineages link to this Animal anywhere in their tree (directly or through a
    described ancestor), i.e. how many trees deleting it will convert to a snapshot."""
    with get_connection() as conn:
        return conn.execute(
            """WITH RECURSIVE up(id, child_animal_id, child_entry_id) AS (
                   SELECT id, child_animal_id, child_entry_id FROM lineage_entry WHERE linked_animal_id = ?
                   UNION
                   SELECT le.id, le.child_animal_id, le.child_entry_id FROM lineage_entry le JOIN up ON le.id = up.child_entry_id
               ) SELECT COUNT(DISTINCT child_animal_id) FROM up WHERE child_animal_id IS NOT NULL""",
            (animal_id,),
        ).fetchone()[0]


def snapshot_links_to(conn, animal_id: int) -> int:
    """Turns every Lineage Entry linking to this Animal into a described snapshot of it: its name,
    Morph, Genetics and its own Lineage copied beneath (linked ancestors in that Lineage stay
    linked). Each linking entry gets its own copy. Runs on the caller's connection so it shares the
    delete's transaction. Returns the number of entries converted."""
    animal = conn.execute("SELECT * FROM animal WHERE id = ?", (animal_id,)).fetchone()
    if animal is None:
        return 0
    entries = [r["id"] for r in conn.execute("SELECT id FROM lineage_entry WHERE linked_animal_id = ?", (animal_id,))]
    for entry_id in entries:
        conn.execute("UPDATE lineage_entry SET linked_animal_id = NULL, name = ?, morph = ? WHERE id = ?",
                     (animal["name"], animal["morph"], entry_id))
        conn.execute(
            """INSERT INTO lineage_entry_gene (entry_id, gene_id, state, percent, evidence)
               SELECT ?, gene_id, state, percent, evidence FROM animal_gene WHERE animal_id = ?""",
            (entry_id, animal_id),
        )
        _copy_children(conn, "child_animal_id", animal_id, None, entry_id)
    return len(entries)
