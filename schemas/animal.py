"""Animal entity schema (Pydantic v2) — sixth slice of the Entity Schema Layer, see
Reptile_App_Technical_Requirements.md §9.15 (tracked as Jira RHA-16). Follows the same pattern as
the rest of schemas/ — see schemas/sensor.py's module docstring for the full boundary-rule
reasoning.

The simplest entity so far: `animal` has zero CHECK constraints and zero UNIQUE constraints in
db/schema.sql, and there's no `_validate_animal`/validation function of any kind in
web/admin_queries.py — `AnimalBase` needs no model validator, same as schemas/room.py. Unlike
Room/Enclosure, `create_animal()` and `update_animal()` take the exact same field set — no
UI-flow simplification to document here; `AnimalCreate`/`AnimalUpdate` genuinely mirror the real
functions one-for-one.

One thing that differs from every other entity built so far: `animal` has NO `created_at` column
at all (confirmed directly against db/schema.sql's CREATE TABLE block) — so `AnimalRead` adds only
`id`, not `id`/`created_at` like Sensor/Plug/CareEvent/Enclosure/Room did. Worth remembering when
building Plant next: check its columns too rather than assuming the `created_at` pattern holds.
"""
from __future__ import annotations

from pydantic import BaseModel


class AnimalBase(BaseModel):
    enclosure_id: int                       # every Animal belongs to exactly one Enclosure — see CONTEXT.md: Animal
    name: str
    species_common: str | None = None
    species_scientific: str | None = None
    dob: str | None = None                  # ISO date, nullable — not always known


class AnimalCreate(AnimalBase):
    """Body for inserting a new animal row — matches create_animal()'s signature exactly."""


class AnimalUpdate(AnimalCreate):
    """Mirrors AnimalCreate's shape: update_animal() takes the identical field set (enclosure_id
    included, so an Animal can be moved between Enclosures on edit), same
    forward-compatibility reasoning as every other entity's Update class so far."""


class AnimalRead(AnimalBase):
    """Full row as stored — adds only the DB-assigned id (no created_at column on this table,
    see module docstring)."""
    id: int
