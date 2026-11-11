"""Gene Catalog queries (see CONTEXT.md: Gene, Gene Catalog; RHA-104): the user-editable list of
Genes per specific Knowledge Base species, so a newly named morph is a data change, never a code
change. The App Admin page web/templates/admin_gene_catalog.html is built on these.

A Gene points at its species by (species_category, species_key): the Knowledge Base category key
and that row's profile_key, which survives a rename. Only a specific named species can own Genes
(web/species_kb_queries.py's linked_species() is the gate).
"""
from __future__ import annotations

import sqlite3

from db.db import get_connection
from schemas.species_profile_kb import PROFILE_CATEGORIES
from web import species_kb_queries as skq

INHERITANCES = ["recessive", "co_dominant", "dominant"]
INHERITANCE_LABELS = {"recessive": "Recessive", "co_dominant": "Co-dominant", "dominant": "Dominant"}

# (table, column) pairs that reference gene.id. Deleting a Gene still in use is blocked with a
# count.
GENE_REFERENCES: list[tuple[str, str]] = [("animal_gene", "gene_id"), ("lineage_entry_gene", "gene_id")]


def _validated(name: str, inheritance: str) -> tuple[str, str]:
    name = (name or "").strip()
    if not name:
        raise ValueError("Enter a gene name.")
    if inheritance not in INHERITANCES:
        raise ValueError(f"Pick an inheritance: {', '.join(INHERITANCE_LABELS.values())}.")
    return name, inheritance


def list_genes_by_species() -> list[dict]:
    """Every species that has Genes, in Knowledge Base order, each as {"category", "key", "label",
    "scientific", "genes": [...]}; Genes sorted by name. Genes whose species has been deleted from
    the Knowledge Base come last, labelled as such, so they can still be edited or removed."""
    with get_connection() as conn:
        genes = [dict(r) for r in conn.execute("SELECT * FROM gene ORDER BY name COLLATE NOCASE")]
        by_species: dict[tuple[str, str], list[dict]] = {}
        for gene in genes:
            by_species.setdefault((gene["species_category"], gene["species_key"]), []).append(gene)

        groups = []
        for category in PROFILE_CATEGORIES:
            for row in conn.execute(f"SELECT profile_key, common_name, scientific_name FROM {category.table} ORDER BY sort_order"):
                species_genes = by_species.pop((category.key, row["profile_key"]), None)
                if species_genes:
                    groups.append({"category": category.key, "key": row["profile_key"], "label": row["common_name"],
                                   "scientific": row["scientific_name"], "genes": species_genes})
    for (category_key, species_key), species_genes in sorted(by_species.items()):
        groups.append({"category": category_key, "key": species_key, "scientific": None, "genes": species_genes,
                       "label": f"{species_key} (no longer in the Knowledge Base)"})
    return groups


def species_choices() -> list[dict]:
    """The specific named species a new Gene can belong to, grouped like the Animal species picker
    (catch-alls excluded: they can't have Genes)."""
    return [g for g in skq.animal_species_groups() if g["label"] != skq.OTHER_GROUP_LABEL]


def create_gene(species_category: str, species_key: str, name: str, inheritance: str, notes: str | None = None) -> int:
    name, inheritance = _validated(name, inheritance)
    linked = skq.linked_species(species_key)
    if linked is None or linked["category"] != species_category:
        raise ValueError("Pick a specific Knowledge Base species; catch-alls can't have Genes.")
    try:
        with get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO gene (species_category, species_key, name, inheritance, notes) VALUES (?, ?, ?, ?, ?)",
                (species_category, species_key, name, inheritance, (notes or "").strip() or None),
            )
            return cur.lastrowid
    except sqlite3.IntegrityError:
        raise ValueError(f"{linked['common_name']} already has a Gene called {name!r}.") from None


def update_gene(gene_id: int, name: str, inheritance: str, notes: str | None = None) -> None:
    """A Gene's species never changes: the same name in another species is a different Gene."""
    name, inheritance = _validated(name, inheritance)
    try:
        with get_connection() as conn:
            conn.execute("UPDATE gene SET name = ?, inheritance = ?, notes = ? WHERE id = ?",
                         (name, inheritance, (notes or "").strip() or None, gene_id))
    except sqlite3.IntegrityError:
        raise ValueError(f"This species already has a Gene called {name!r}.") from None


def gene_usage_count(gene_id: int) -> int:
    with get_connection() as conn:
        return sum(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (gene_id,)).fetchone()[0]
                   for table, column in GENE_REFERENCES)


def delete_gene(gene_id: int) -> None:
    """Raises ValueError, naming how many records use it, if anything still references the Gene."""
    used = gene_usage_count(gene_id)
    if used:
        raise ValueError(f"This Gene is used by {used} record{'s' if used != 1 else ''} "
                         "(Animal Genetics or Lineage Entries), so it can't be removed.")
    with get_connection() as conn:
        conn.execute("DELETE FROM gene WHERE id = ?", (gene_id,))
