"""Genetics and Morph (see CONTEXT.md: Genetics, Morph, Gene; RHA-105, RHA-106).

Two things carry Genetics: an Animal (`animal_gene`) and a described Lineage Entry
(`lineage_entry_gene`, RHA-106). Each row is one Gene from the species' Gene Catalog, its Gene
State, a percentage (Possible Het only) and Evidence (Het only). They're always hand-entered, never
derived from Lineage. Morph is free text on the owner (`animal.morph`, `lineage_entry.morph`).

Both exist only for an Animal linked to a specific Knowledge Base species
(web/species_kb_queries.py's linked_species()); a Lineage Entry uses its Animal's species. For
every other Animal the feature is absent.
"""
from __future__ import annotations

import sqlite3

from db.db import get_connection
from web import gene_catalog_queries as gcq
from web import species_kb_queries as skq

STATES = ["visual", "super", "het", "possible_het"]
STATE_LABELS = {"visual": "Visual", "super": "Super", "het": "Het", "possible_het": "Possible Het"}
# Which Gene States each Inheritance allows: Het/Possible Het only for Recessive, Super only for
# Co-dominant (see CONTEXT.md: Genetics).
VALID_STATES = {
    "recessive": ["visual", "het", "possible_het"],
    "co_dominant": ["visual", "super"],
    "dominant": ["visual"],
}
EVIDENCE = ["claimed", "proven"]
EVIDENCE_LABELS = {"claimed": "Claimed", "proven": "Proven"}

# Display order inside a Morph built from Visual genes: the hobby writes co-dominant/dominant genes
# before recessive ones ("Banana Clown", "Pastel Pied").
_INHERITANCE_ORDER = {"co_dominant": 0, "dominant": 0, "recessive": 1}

# Genetics owners: kind -> (table, owner column).
_OWNERS = {"animal": ("animal_gene", "animal_id"), "entry": ("lineage_entry_gene", "entry_id")}


def genetics_species(animal: dict) -> dict | None:
    """The Animal's specific Knowledge Base species, or None when Genetics/Morph don't apply."""
    return skq.linked_species(animal.get("species_profile"))


def _validated_state(inheritance: str, state: str, percent, evidence: str | None) -> tuple[str, int | None, str | None]:
    if state not in VALID_STATES.get(inheritance, []):
        allowed = ", ".join(STATE_LABELS[s] for s in VALID_STATES.get(inheritance, []))
        raise ValueError(f"A {gcq.INHERITANCE_LABELS.get(inheritance, inheritance)} gene can be: {allowed}.")
    if state == "possible_het":
        try:
            percent = int(str(percent).strip().rstrip("%"))
        except (TypeError, ValueError):
            raise ValueError("Enter the Possible Het percentage, e.g. 50 or 66.") from None
        if not 1 <= percent <= 99:
            raise ValueError("A Possible Het percentage is between 1 and 99; a certain one is a Het.")
        return state, percent, None  # never Proven: once proven it becomes a Het
    if state == "het":
        evidence = evidence or "claimed"
        if evidence not in EVIDENCE:
            raise ValueError("Pick the Het's evidence: Claimed or Proven.")
        return state, None, evidence
    return state, None, None


# --- generic, per owner kind ---------------------------------------------------------------------

def list_genetics(kind: str, owner_id: int) -> list[dict]:
    """An owner's Genetics joined with each Gene's name and Inheritance, sorted by Gene name."""
    table, column = _OWNERS[kind]
    with get_connection() as conn:
        rows = [dict(r) for r in conn.execute(
            f"""SELECT x.*, g.name AS gene_name, g.inheritance
                FROM {table} x JOIN gene g ON g.id = x.gene_id
                WHERE x.{column} = ? ORDER BY g.name COLLATE NOCASE""",
            (owner_id,),
        )]
    for row in rows:
        row["valid_states"] = VALID_STATES[row["inheritance"]]
    return rows


def catalog_for(species: dict | None) -> list[dict]:
    """The Gene Catalog entries of one species, for a Genetics picker."""
    if species is None:
        return []
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id, name, inheritance FROM gene WHERE species_category = ? AND species_key = ? ORDER BY name COLLATE NOCASE",
            (species["category"], species["profile_key"]),
        )]


def add_gene(kind: str, owner_id: int, species: dict | None, gene_id: int | None, state: str, percent=None,
             evidence: str | None = None, new_gene_name: str | None = None, new_gene_inheritance: str | None = None) -> int:
    """Adds one Gene to an owner's Genetics. With no gene_id, new_gene_name/new_gene_inheritance add
    the Gene to the species' catalog on the spot (or reuse a same-named one already there)."""
    if species is None:
        raise ValueError("Link this Animal to a specific Knowledge Base species before adding Genetics.")
    table, column = _OWNERS[kind]

    if not gene_id:
        name = (new_gene_name or "").strip()
        if new_gene_inheritance in VALID_STATES:  # refuse a bad state before the catalog gains the Gene
            _validated_state(new_gene_inheritance, state, percent, evidence)
        with get_connection() as conn:
            existing = conn.execute(
                "SELECT id FROM gene WHERE species_category = ? AND species_key = ? AND name = ?",
                (species["category"], species["profile_key"], name),
            ).fetchone()
        gene_id = existing["id"] if existing else gcq.create_gene(
            species["category"], species["profile_key"], name, new_gene_inheritance or "")

    with get_connection() as conn:
        gene = conn.execute("SELECT * FROM gene WHERE id = ?", (gene_id,)).fetchone()
        if gene is None or (gene["species_category"], gene["species_key"]) != (species["category"], species["profile_key"]):
            raise ValueError(f"Pick a Gene from the {species['common_name']} Gene Catalog.")
        state, percent, evidence = _validated_state(gene["inheritance"], state, percent, evidence)
        try:
            cur = conn.execute(
                f"INSERT INTO {table} ({column}, gene_id, state, percent, evidence) VALUES (?, ?, ?, ?, ?)",
                (owner_id, gene_id, state, percent, evidence),
            )
        except sqlite3.IntegrityError:
            raise ValueError(f"{gene['name']} is already in these Genetics; edit that row instead.") from None
        return cur.lastrowid


def update_gene(kind: str, owner_id: int, row_id: int, state: str, percent=None, evidence: str | None = None) -> None:
    table, column = _OWNERS[kind]
    with get_connection() as conn:
        row = conn.execute(
            f"""SELECT g.inheritance FROM {table} x JOIN gene g ON g.id = x.gene_id
                WHERE x.id = ? AND x.{column} = ?""",
            (row_id, owner_id),
        ).fetchone()
        if row is None:
            raise ValueError("That Genetics row no longer exists.")
        state, percent, evidence = _validated_state(row["inheritance"], state, percent, evidence)
        conn.execute(f"UPDATE {table} SET state = ?, percent = ?, evidence = ? WHERE id = ?",
                     (state, percent, evidence, row_id))


def delete_gene(kind: str, owner_id: int, row_id: int) -> None:
    table, column = _OWNERS[kind]
    with get_connection() as conn:
        conn.execute(f"DELETE FROM {table} WHERE id = ? AND {column} = ?", (row_id, owner_id))


# --- Animals -------------------------------------------------------------------------------------

def _animal_or_raise(animal_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM animal WHERE id = ?", (animal_id,)).fetchone()
    if row is None:
        raise ValueError("That Animal no longer exists.")
    return dict(row)


def list_animal_genetics(animal_id: int) -> list[dict]:
    return list_genetics("animal", animal_id)


def species_genes(animal: dict) -> list[dict]:
    """The Gene Catalog entries the Animal's Genetics can be picked from (its own species only)."""
    return catalog_for(genetics_species(animal))


def add_animal_gene(animal_id: int, gene_id: int | None, state: str, percent=None, evidence: str | None = None,
                    new_gene_name: str | None = None, new_gene_inheritance: str | None = None) -> int:
    species = genetics_species(_animal_or_raise(animal_id))
    return add_gene("animal", animal_id, species, gene_id, state, percent, evidence, new_gene_name, new_gene_inheritance)


def update_animal_gene(animal_id: int, row_id: int, state: str, percent=None, evidence: str | None = None) -> None:
    update_gene("animal", animal_id, row_id, state, percent, evidence)


def delete_animal_gene(animal_id: int, row_id: int) -> None:
    delete_gene("animal", animal_id, row_id)


def set_morph(animal_id: int, morph: str | None) -> None:
    """Blank clears it, so the Visual genes serve as the name again."""
    if genetics_species(_animal_or_raise(animal_id)) is None:
        raise ValueError("Link this Animal to a specific Knowledge Base species before giving it a Morph.")
    with get_connection() as conn:
        conn.execute("UPDATE animal SET morph = ? WHERE id = ?", ((morph or "").strip() or None, animal_id))


# --- notation ------------------------------------------------------------------------------------

def morph_name(morph: str | None, genetics: list[dict]) -> str:
    """The Morph if given; else the Visual/Super genes joined ("Super Pastel Clown"); else Normal."""
    if morph and morph.strip():
        return morph.strip()
    shown = sorted((g for g in genetics if g["state"] in ("visual", "super")),
                   key=lambda g: (_INHERITANCE_ORDER[g["inheritance"]], g["gene_name"].lower()))
    names = [f"Super {g['gene_name']}" if g["state"] == "super" else g["gene_name"] for g in shown]
    return " ".join(names) or "Normal"


def het_notation(gene: dict) -> str:
    if gene["state"] == "possible_het":
        return f"{gene['percent']}% het {gene['gene_name']}"
    return f"100% het {gene['gene_name']}" + (" (proven)" if gene["evidence"] == "proven" else "")


def notation(morph: str | None, genetics: list[dict]) -> str:
    """Standard notation, e.g. "Banana Clown · 66% het Albino · 100% het Pied (proven)"."""
    hets = sorted((g for g in genetics if g["state"] in ("het", "possible_het")),
                  key=lambda g: (-(g["percent"] or 100), g["gene_name"].lower()))
    return " · ".join([morph_name(morph, genetics), *(het_notation(g) for g in hets)])


def genetics_line(animal: dict, genetics: list[dict] | None = None) -> str | None:
    """An Animal's standard notation, or None for an Animal Genetics/Morph don't apply to."""
    if genetics_species(animal) is None:
        return None
    if genetics is None:
        genetics = list_animal_genetics(animal["id"])
    return notation(animal.get("morph"), genetics)
