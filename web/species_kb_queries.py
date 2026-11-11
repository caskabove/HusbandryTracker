"""Query/CRUD layer for the Species Profile Knowledge Base (see CONTEXT.md: Knowledge Base,
Species Profile; ADR 0054; schemas/species_profile_kb.py) — the 7 editable reference tables that
replaced the old hardcoded SPECIES_PROFILES/SPECIES_PROFILE_GROUPS literal in web/static/app.js.

Two jobs:
  - Generic CRUD for the Knowledge Base Admin page (list/create/update/delete a row in any of the
    7 categories), driven entirely by schemas/species_profile_kb.py's field registry so adding a
    column there is the only code change a new field needs.
  - species_profile_js_context(): rebuilds the exact SPECIES_PROFILES/SPECIES_PROFILE_GROUPS shape
    the retired app.js literal had, from live DB rows, for the Setup/Add-Pet Wizard and Admin
    templates that still consume those two globals unchanged (see web/static/app.js's
    populateSpeciesProfileSelect and friends) — only *where the data comes from* changed.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.db import get_connection
from schemas import enclosure_types as et
from schemas.species_profile_kb import (
    CATCH_ALL_PROFILE_KEYS,
    GENERIC_PROFILE_OPTIONS,
    PROFILE_CATEGORIES,
    ProfileCategory,
    categories_for_enclosure_type,
    category_by_key,
)

_COMMON_COLUMNS = ("id", "profile_key", "common_name", "scientific_name", "notes", "sort_order")


def _slugify(common_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", common_name.strip().lower()).strip("_")
    return slug or "profile"


def _unique_profile_key(conn, table: str, base_slug: str, skip_id: int | None = None) -> str:
    """Appends -2, -3, ... only if base_slug collides within this category's own table — collision
    across categories is accepted (see schemas/species_profile_kb.py's comment on profile_key)."""
    candidate = base_slug
    suffix = 2
    while True:
        query = f"SELECT id FROM {table} WHERE profile_key = ?"
        params: tuple = (candidate,)
        if skip_id is not None:
            query += " AND id != ?"
            params = (candidate, skip_id)
        if conn.execute(query, params).fetchone() is None:
            return candidate
        candidate = f"{base_slug}_{suffix}"
        suffix += 1


def list_profiles(category_key: str) -> list[dict]:
    category = category_by_key(category_key)
    with get_connection() as conn:
        rows = conn.execute(f"SELECT * FROM {category.table} ORDER BY sort_order").fetchall()
        return [dict(r) for r in rows]


def all_profiles_by_category() -> dict[str, list[dict]]:
    return {c.key: list_profiles(c.key) for c in PROFILE_CATEGORIES}


def _field_value(raw: str | None, kind: str) -> float | str | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    return raw if kind == "text" else float(raw)


def create_profile(category_key: str, common_name: str, scientific_name: str | None, notes: str | None,
                    field_values: dict[str, str | None]) -> int:
    category = category_by_key(category_key)
    common_name = common_name.strip()
    if not common_name:
        raise ValueError("Enter a common name.")
    with get_connection() as conn:
        profile_key = _unique_profile_key(conn, category.table, _slugify(common_name))
        (next_order,) = conn.execute(f"SELECT COALESCE(MAX(sort_order), -1) + 1 FROM {category.table}").fetchone()
        columns = ["profile_key", "common_name", "scientific_name", "notes", "sort_order"]
        values: list = [profile_key, common_name, scientific_name or None, notes or None, next_order]
        for field in category.fields:
            columns.append(field.column)
            values.append(_field_value(field_values.get(field.column), field.kind))
        placeholders = ", ".join("?" for _ in columns)
        cur = conn.execute(
            f"INSERT INTO {category.table} ({', '.join(columns)}) VALUES ({placeholders})", values
        )
        return cur.lastrowid


def update_profile(category_key: str, profile_id: int, common_name: str, scientific_name: str | None,
                    notes: str | None, field_values: dict[str, str | None]) -> None:
    category = category_by_key(category_key)
    common_name = common_name.strip()
    if not common_name:
        raise ValueError("Enter a common name.")
    with get_connection() as conn:
        columns = ["common_name", "scientific_name", "notes"]
        values: list = [common_name, scientific_name or None, notes or None]
        for field in category.fields:
            columns.append(field.column)
            values.append(_field_value(field_values.get(field.column), field.kind))
        set_clause = ", ".join(f"{col} = ?" for col in columns)
        conn.execute(f"UPDATE {category.table} SET {set_clause} WHERE id = ?", (*values, profile_id))


def delete_profile(category_key: str, profile_id: int) -> None:
    category = category_by_key(category_key)
    with get_connection() as conn:
        conn.execute(f"DELETE FROM {category.table} WHERE id = ?", (profile_id,))


# ---------------------------------------------------------------------------
# Wizard/Admin pre-fill JS context — see this module's docstring.
# ---------------------------------------------------------------------------

def _js_profile_entry(category: ProfileCategory, row: dict) -> dict:
    """Reshapes one Knowledge Base row into the label/scientific/basking/cool/night/humidity/
    feeding shape web/static/app.js's prefill functions already expect (unchanged by ADR 0054).

    Terrestrial categories (snake/lizard/insect) carry that shape's fields directly. The 4 aquatic
    categories have no basking/cool/night gradient — a tank has one temperature, not a zone — so
    temp_min/temp_max is repeated into basking/cool/night alike, which keeps
    web/static/app.js's _tempRangeForZone() working unchanged for every Target Range zone pick.
    Insects use the same repetition for the same reason (a terrarium's basking/cool/night figures
    don't apply to a non-basking pet insect). `feeding` only exists where a numeric feeding
    interval does (snake_profile/lizard_profile) — diet/lifespan are free text, not something
    `enclosure.feeding_interval_days` can pre-fill from.
    """
    entry: dict = {"label": row["common_name"]}
    if row.get("scientific_name"):
        entry["scientific"] = row["scientific_name"]
    if category.key in ("snake", "lizard"):
        if row["basking_min_f"] is not None:
            entry["basking"] = [row["basking_min_f"], row["basking_max_f"]]
            entry["cool"] = [row["cool_min_f"], row["cool_max_f"]]
            entry["night"] = [row["night_min_f"], row["night_max_f"]]
        if row["humidity_min_pct"] is not None:
            entry["humidity"] = [row["humidity_min_pct"], row["humidity_max_pct"]]
        if row["feeding_baby_interval_days"] is not None:
            entry["feeding"] = {"baby": row["feeding_baby_interval_days"], "adult": row["feeding_adult_interval_days"]}
    elif category.key == "insect":
        if row["temp_min_f"] is not None:
            entry["basking"] = entry["cool"] = entry["night"] = [row["temp_min_f"], row["temp_max_f"]]
        if row["humidity_min_pct"] is not None:
            entry["humidity"] = [row["humidity_min_pct"], row["humidity_max_pct"]]
    else:  # the 4 aquatic categories
        if row["temp_min_f"] is not None:
            entry["basking"] = entry["cool"] = entry["night"] = [row["temp_min_f"], row["temp_max_f"]]
    return entry


def species_profile_js_context() -> dict[str, str]:
    """{"species_profiles_json": ..., "species_profile_groups_json": ...} — pass straight into any
    template context that includes web/templates/_species_profile_data.html (see that file)."""
    profiles: dict[str, dict] = {}
    groups_by_enclosure_type: dict[str, list[dict]] = {t: [] for t in et.ENCLOSURE_TYPES}

    for category in PROFILE_CATEGORIES:
        rows = list_profiles(category.key)
        keys = []
        for row in rows:
            profiles[row["profile_key"]] = _js_profile_entry(category, row)
            keys.append(row["profile_key"])
        if keys:
            groups_by_enclosure_type[category.enclosure_type].append({"label": category.label, "keys": keys})

    # Generic, non-numeric catch-alls (Tortoise, general Freshwater/Saltwater tank types) — grouped
    # under "Other" alongside whichever categories share their Enclosure Type, matching the old
    # SPECIES_PROFILE_GROUPS literal's "basic" -> Other group.
    generic_by_type: dict[str, list[str]] = {t: [] for t in et.ENCLOSURE_TYPES}
    for key, (label, enclosure_type) in GENERIC_PROFILE_OPTIONS.items():
        profiles[key] = {"label": label}
        generic_by_type[enclosure_type].append(key)
    for enclosure_type, keys in generic_by_type.items():
        if keys:
            groups_by_enclosure_type[enclosure_type].append({"label": "Other" if enclosure_type == "basic" else "", "keys": keys})

    return {
        "species_profiles_json": json.dumps(profiles),
        "species_profile_groups_json": json.dumps(groups_by_enclosure_type),
    }


# ---------------------------------------------------------------------------
# Add/Edit Animal species picker (RHA-103; see CONTEXT.md: Species Profile)
# ---------------------------------------------------------------------------

OTHER_GROUP_LABEL = "Other / general"


def animal_species_groups() -> list[dict]:
    """Option groups for the Add/Edit Animal species picker, read live from the Knowledge Base:
    one group per category ({"category", "label", "options"}) holding its specific named species,
    in Knowledge Base order, then one
    "Other / general" group of every catch-all (the "(other/unlisted)" rows and the general tank
    types). Every option is {"key", "label", "common", "scientific"}; catch-alls carry no
    common/scientific, so picking one doesn't overwrite the Animal's names.

    Unlike the Enclosure form's picker this isn't filtered by Enclosure Type: an Animal's species
    is a fact about the Animal, and Add Animal can pick any Enclosure."""
    groups: list[dict] = []
    other: list[dict] = []
    for category in PROFILE_CATEGORIES:
        named = []
        for row in list_profiles(category.key):
            if row["profile_key"] in CATCH_ALL_PROFILE_KEYS:
                other.append({"key": row["profile_key"], "label": row["common_name"], "common": None, "scientific": None})
            else:
                named.append({"key": row["profile_key"], "label": row["common_name"],
                              "common": row["common_name"], "scientific": row["scientific_name"]})
        if named:
            groups.append({"category": category.key, "label": category.label, "options": named})
    other.extend({"key": key, "label": label, "common": None, "scientific": None}
                 for key, (label, _type) in GENERIC_PROFILE_OPTIONS.items())
    groups.append({"category": None, "label": OTHER_GROUP_LABEL, "options": other})
    return groups


def linked_species(profile_key: str | None) -> dict | None:
    """The specific named Knowledge Base species an Animal is linked to, or None. Genes are defined
    per specific species (see CONTEXT.md: Gene), so this is the gate for Genetics and Morph.

    None for: no pick, a catch-all ("Snake (other/unlisted)", "Saltwater — Reef", ...), or a key
    whose Knowledge Base row has since been deleted. Returns {"category", "id", "profile_key",
    "common_name", "scientific_name"}. profile_key is unique within a category's table only; the
    seed data has no cross-category duplicates, and the first category in PROFILE_CATEGORIES
    order wins if a user ever creates one."""
    if not profile_key or profile_key in CATCH_ALL_PROFILE_KEYS or profile_key in GENERIC_PROFILE_OPTIONS:
        return None
    with get_connection() as conn:
        for category in PROFILE_CATEGORIES:
            row = conn.execute(
                f"SELECT id, profile_key, common_name, scientific_name FROM {category.table} WHERE profile_key = ?",
                (profile_key,),
            ).fetchone()
            if row is not None:
                return {"category": category.key, **dict(row)}
    return None
