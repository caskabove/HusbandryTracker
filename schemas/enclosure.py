"""Enclosure entity schema (Pydantic v2) — fourth slice of the Entity Schema Layer, see
Reptile_App_Technical_Requirements.md §9.15 (tracked as Jira RHA-15). Follows the same pattern as
schemas/sensor.py / schemas/plug.py / schemas/care_event.py.

`enclosure_type` deliberately does NOT get a new enum in schemas/enums.py — `schemas/
enclosure_types.py` is already the established single source of truth for the four Enclosure Type
values (Target Range metrics and Controller Kind gating are both built around its `ENCLOSURE_TYPES`
tuple; see ADR 0011). Duplicating it as e.g. `EnclosureType(str, Enum)` here would create a second
source of truth for the same four strings — enums.py's own module docstring says this explicitly,
and it was called out again as a correction on RHA-15 this same day. The model validator below
mirrors `enclosure`'s CHECK by checking membership against `et.ENCLOSURE_TYPES` directly.

Boundary rule (see schemas/sensor.py's module docstring for the full reasoning): `enclosure` has
exactly one CHECK — `enclosure_type IN (...)` — mirrored below. Two things that look like they
could be entity rules are deliberately NOT modeled, because they belong to a different entity or a
different table's row, not to `enclosure` itself:
  - "A Plant can only be created on a Bioactive Enclosure" — that's a `plant`-table concern (needs
    the Enclosure row's `bioactive` value from the *other* side), stays in
    `web/admin_queries.py::create_plant()`. Will matter when schemas/plant.py is built.
  - `fallback_sensor_id` isn't cross-checked against anything (e.g. "must belong to this
    Enclosure's Room") anywhere in the app, on purpose — see `update_enclosure()`'s own docstring
    in web/admin_queries.py: the Admin UI already scopes the dropdown, and display logic always
    prefers an Enclosure's own Sensors regardless, so a stale value is harmless. Nothing to mirror
    here because there's genuinely no rule, not because it was deferred.

`EnclosureCreate` includes `room_id`/`fallback_sensor_id` (defaulted to `None`) even though the
real `create_enclosure()` function doesn't accept them — Room assignment happens as a deliberate
follow-up edit today, a form-UX simplification, not a domain rule (see its own comment: "keeps
this quick-create form minimal"). Including them here is harmless (they default to `None`, same
as the columns do when omitted from the INSERT) and keeps this model's shape uniform with
Sensor/Plug rather than adding a second near-duplicate class for a UI-flow detail.
"""
from __future__ import annotations

from pydantic import BaseModel, model_validator

from schemas import enclosure_types as et


class EnclosureBase(BaseModel):
    name: str                                  # UNIQUE at the DB level — not re-checked here, same as Sensor/Plug's (plugin, external_id)
    room_id: int | None = None                 # optional — see CONTEXT.md: Room
    fallback_sensor_id: int | None = None       # see CONTEXT.md: Fallback Sensor
    enclosure_type: str = "basic"               # see schemas/enclosure_types.py — ADR 0011
    bioactive: bool = False                     # independent of enclosure_type — see CONTEXT.md: Bioactive
    feeding_interval_days: int = 7
    watering_interval_days: int = 3
    spot_clean_interval_days: int = 7
    deep_clean_interval_days: int = 30
    show_feeding_on_dashboard: bool = True      # see CONTEXT.md: Care Interval
    show_watering_on_dashboard: bool = True
    show_spot_clean_on_dashboard: bool = True
    show_deep_clean_on_dashboard: bool = True

    @model_validator(mode="after")
    def _check_enclosure_type(self) -> EnclosureBase:
        """Mirrors enclosure's CHECK (enclosure_type IN (...)) in db/schema.sql exactly, against
        schemas/enclosure_types.py's ENCLOSURE_TYPES — the single source of truth for the value
        set, not re-listed here."""
        if self.enclosure_type not in et.ENCLOSURE_TYPES:
            raise ValueError(f"Unknown Enclosure Type: {self.enclosure_type!r}")
        return self


class EnclosureCreate(EnclosureBase):
    """Body for inserting a new enclosure row — see module docstring re: room_id/fallback_sensor_id."""


class EnclosureUpdate(EnclosureCreate):
    """Mirrors EnclosureCreate's shape: web/admin_queries.py's update_enclosure() replaces the
    whole row (room_id/fallback_sensor_id included, unlike create_enclosure()), same
    forward-compatibility reasoning as Sensor/Plug's Update classes."""


class EnclosureRead(EnclosureBase):
    """Full row as stored — adds the DB-assigned id/created_at on top of EnclosureBase, plus the
    Care Setup Prompt's nag-tracking columns (see CONTEXT.md: Care Setup Prompt, Care Interval;
    ADR 0040), which are DB-managed bookkeeping (web/admin_queries.py's record_care_nags()), not
    something a caller sets at create/update time — same reasoning as id/created_at itself."""
    id: int
    created_at: str
    feeding_nag_count: int = 0
    feeding_nag_last_date: str | None = None
    watering_nag_count: int = 0
    watering_nag_last_date: str | None = None
    spot_clean_nag_count: int = 0
    spot_clean_nag_last_date: str | None = None
    deep_clean_nag_count: int = 0
    deep_clean_nag_last_date: str | None = None
