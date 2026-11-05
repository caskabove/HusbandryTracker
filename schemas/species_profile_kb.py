"""Species Profile Knowledge Base schema — the single source of truth for which columns each of
the 7 editable Knowledge Base tables (db/schema.sql) carries, and their display metadata. See
CONTEXT.md: Knowledge Base, Species Profile; ADR 0054.

Mirrors schemas/enclosure_types.py's shape: pure data + lookups, no DB access. web/species_kb_queries.py
builds its generic CRUD off this registry, and web/admin.py's Knowledge Base page renders its 7
tables from it too, so adding a field here is the only place that's needed — no per-category
query/route/template code to touch.

Every table also carries `profile_key` (TEXT UNIQUE — the dropdown value, carried onto
`animal.species_profile`; see CONTEXT.md: Animal, Species Profile), `common_name`, `scientific_name`,
`notes` (sources/free text), and `sort_order`, handled generically in web/species_kb_queries.py
rather than listed per-category here, since every table has them identically (see db/schema.sql).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProfileField:
    column: str            # db/schema.sql column name
    label: str              # table header / form label
    unit: str = ""           # display suffix, "" if unitless
    kind: str = "number"     # "number" | "text" — which <input> type Admin renders
    step: str = "1"


@dataclass(frozen=True)
class ProfileCategory:
    key: str                          # stable id — URL segment, dropdown group key, Enclosure Type link
    label: str                        # display heading, e.g. "Saltwater Fish"
    table: str                        # db/schema.sql table name
    enclosure_type: str                # which Enclosure Type's Species Profile dropdown offers this category
    fields: tuple[ProfileField, ...]   # category-specific fields, in display order


# Basking/cool/night/humidity/feeding — unchanged shape from the original (pre-Knowledge-Base)
# SPECIES_PROFILES entries for Snakes and Lizards (web/static/app.js, retired by ADR 0054), so
# existing `animal.species_profile` values keep resolving to the same numbers after migration.
_TERRESTRIAL_FIELDS = (
    ProfileField("basking_min_f", "Basking min", "°F"),
    ProfileField("basking_max_f", "Basking max", "°F"),
    ProfileField("cool_min_f", "Cool side min", "°F"),
    ProfileField("cool_max_f", "Cool side max", "°F"),
    ProfileField("night_min_f", "Night low min", "°F"),
    ProfileField("night_max_f", "Night low max", "°F"),
    ProfileField("humidity_min_pct", "Humidity min", "%"),
    ProfileField("humidity_max_pct", "Humidity max", "%"),
    ProfileField("feeding_baby_interval_days", "Feeding, baby", "days"),
    ProfileField("feeding_adult_interval_days", "Feeding, adult", "days"),
)

PROFILE_CATEGORIES: tuple[ProfileCategory, ...] = (
    ProfileCategory("snake", "Snakes", "snake_profile", "basic", _TERRESTRIAL_FIELDS),
    ProfileCategory("lizard", "Lizards", "lizard_profile", "basic", _TERRESTRIAL_FIELDS),
    ProfileCategory("insect", "Insects", "insect_profile", "basic", (
        ProfileField("temp_min_f", "Temp min", "°F"),
        ProfileField("temp_max_f", "Temp max", "°F"),
        ProfileField("humidity_min_pct", "Humidity min", "%"),
        ProfileField("humidity_max_pct", "Humidity max", "%"),
        ProfileField("lifespan", "Lifespan", "", kind="text"),
        ProfileField("diet", "Diet / feeding frequency", "", kind="text"),
    )),
    ProfileCategory("saltwater_fish", "Saltwater Fish", "saltwater_fish_profile", "saltwater", (
        ProfileField("temp_min_f", "Temp min", "°F"),
        ProfileField("temp_max_f", "Temp max", "°F"),
        ProfileField("salinity_sg_min", "Salinity/SG min", "", step="0.001"),
        ProfileField("salinity_sg_max", "Salinity/SG max", "", step="0.001"),
        ProfileField("ph_min", "pH min", "", step="0.1"),
        ProfileField("ph_max", "pH max", "", step="0.1"),
        ProfileField("ammonia_ppm_max", "Ammonia target", "ppm", step="0.1"),
        ProfileField("nitrite_ppm_max", "Nitrite target", "ppm", step="0.1"),
        ProfileField("nitrate_ppm_max", "Nitrate target", "ppm", step="0.1"),
        ProfileField("diet", "Diet / feeding frequency", "", kind="text"),
    )),
    ProfileCategory("freshwater_fish", "Freshwater Fish", "freshwater_fish_profile", "freshwater", (
        ProfileField("temp_min_f", "Temp min", "°F"),
        ProfileField("temp_max_f", "Temp max", "°F"),
        ProfileField("ph_min", "pH min", "", step="0.1"),
        ProfileField("ph_max", "pH max", "", step="0.1"),
        ProfileField("gh_min", "GH min", "dGH"),
        ProfileField("gh_max", "GH max", "dGH"),
        ProfileField("kh_min", "KH min", "dKH"),
        ProfileField("kh_max", "KH max", "dKH"),
        ProfileField("ammonia_ppm_max", "Ammonia target", "ppm", step="0.1"),
        ProfileField("nitrite_ppm_max", "Nitrite target", "ppm", step="0.1"),
        ProfileField("nitrate_ppm_max", "Nitrate target", "ppm", step="0.1"),
        ProfileField("diet", "Diet / feeding frequency", "", kind="text"),
    )),
    ProfileCategory("saltwater_invert", "Saltwater Inverts", "saltwater_invert_profile", "saltwater", (
        ProfileField("temp_min_f", "Temp min", "°F"),
        ProfileField("temp_max_f", "Temp max", "°F"),
        ProfileField("salinity_sg_min", "Salinity/SG min", "", step="0.001"),
        ProfileField("salinity_sg_max", "Salinity/SG max", "", step="0.001"),
        ProfileField("ph_min", "pH min", "", step="0.1"),
        ProfileField("ph_max", "pH max", "", step="0.1"),
        ProfileField("alkalinity_dkh_min", "Alkalinity min", "dKH"),
        ProfileField("alkalinity_dkh_max", "Alkalinity max", "dKH"),
        ProfileField("calcium_ppm_min", "Calcium min", "ppm"),
        ProfileField("calcium_ppm_max", "Calcium max", "ppm"),
        ProfileField("diet", "Diet / feeding frequency", "", kind="text"),
    )),
    ProfileCategory("freshwater_invert", "Freshwater Inverts", "freshwater_invert_profile", "freshwater", (
        ProfileField("temp_min_f", "Temp min", "°F"),
        ProfileField("temp_max_f", "Temp max", "°F"),
        ProfileField("ph_min", "pH min", "", step="0.1"),
        ProfileField("ph_max", "pH max", "", step="0.1"),
        ProfileField("gh_min", "GH min", "dGH"),
        ProfileField("gh_max", "GH max", "dGH"),
        ProfileField("kh_min", "KH min", "dKH"),
        ProfileField("kh_max", "KH max", "dKH"),
        ProfileField("diet", "Diet / feeding frequency", "", kind="text"),
        ProfileField("sensitivity_notes", "Sensitivity notes", "", kind="text"),
    )),
)

_CATEGORIES_BY_KEY = {c.key: c for c in PROFILE_CATEGORIES}


def category_by_key(key: str) -> ProfileCategory:
    category = _CATEGORIES_BY_KEY.get(key)
    if category is None:
        raise ValueError(f"Unknown Knowledge Base category: {key!r}")
    return category


def categories_for_enclosure_type(enclosure_type: str) -> tuple[ProfileCategory, ...]:
    """Which Knowledge Base categories this Enclosure Type's Species Profile dropdown offers —
    e.g. a `saltwater` Enclosure offers both Saltwater Fish and Saltwater Inverts."""
    return tuple(c for c in PROFILE_CATEGORIES if c.enclosure_type == enclosure_type)


# Generic, non-numeric catch-alls offered in the Species Profile dropdown alongside real Knowledge
# Base rows so the dropdown's shape never shrinks for a "no specific species, I'll enter my own
# numbers" pick — not species data, so not part of the editable Knowledge Base itself (see
# CONTEXT.md: Species Profile). Keys/labels unchanged from the pre-Knowledge-Base SPECIES_PROFILES
# literal in web/static/app.js (ADR 0054) other than dropping its old placeholder "Insect" entry,
# now a real category above.
GENERIC_PROFILE_OPTIONS: dict[str, tuple[str, str]] = {
    # key: (label, enclosure_type)
    "tortoise": ("Tortoise", "basic"),
    "freshwater": ("Freshwater", "freshwater"),
    "freshwater_planted": ("Freshwater (planted)", "freshwater"),
    "saltwater_fish_only": ("Saltwater — Fish-Only", "saltwater"),
    "saltwater_mixed": ("Saltwater — Mixed", "saltwater"),
    "saltwater_reef": ("Saltwater — Reef", "saltwater"),
}
