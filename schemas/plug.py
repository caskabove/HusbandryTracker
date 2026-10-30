"""Plug entity schema (Pydantic v2) — second slice of the Entity Schema Layer, see
Reptile_App_Technical_Requirements.md §9.15. Follows the pattern schemas/sensor.py set: field/
shape validation mirrors `plug`'s own single-table CHECK constraints in db/schema.sql exactly;
everything else that web/admin_queries.py::_validate_plug() currently enforces stays there, on
purpose, per §9.15's boundary list — all of it needs data beyond a single `plug` row:
  - **Room-XOR-Enclosure-set.** `plug` only has a `room_id` column; the Enclosure side is rows in
    the separate `plug_enclosure` join table (0, 1, or many), not a column this model can see —
    can't be a single-table CHECK in schema.sql either, for the same reason (see its comment).
    `enclosure_ids` below is carried on Create/Update only as the write-time input for populating
    that join table — deliberately NOT validated against `room_id` here.
  - **Controller Kind needs a matching setpoint** (thermostat → target_temp_c, hydrostat →
    target_humidity_pct) — an app-level rule, not a schema.sql CHECK (there's only the one CHECK
    block below); §9.15 lists this explicitly as a service-layer concern.
  - **Target Schedule both-or-neither** (target_on_time/target_off_time) when controller_kind is
    'none' — same story: real rule, not a schema.sql CHECK, stays in _validate_plug.
  - **Always On excludes Target Schedule** (see CONTEXT.md: Always On) — technically a single-table
    rule (both live on `plug`), but kept out of schema.sql for the same "all Plug business rules
    stay in _validate_plug" consistency the other two already established here, not because it
    couldn't be a CHECK.

Not yet wired into web/admin_queries.py or tools/register_device.py — see schemas/sensor.py's
module docstring for why (still the pattern to react to, not a replacement).
"""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from schemas.enums import ControllerKind, TrackingMode


class PlugBase(BaseModel):
    room_id: int | None = None        # the Room this Plug belongs to; NULL if Enclosure-owned instead — see CONTEXT.md: Plug
    label: str                        # e.g. "basking bulb", "UTH"
    purpose: str = Field(min_length=1)  # free text; mirrors plug's CHECK (length(purpose) > 0)
    tracking_mode: TrackingMode = TrackingMode.SMART
    plugin: str | None = None         # e.g. "tuya_lan"; required (with external_id) iff Smart — see CONTEXT.md: Plugin
    external_id: str | None = None    # opaque per-Plugin device id — see CONTEXT.md: External ID
    plugin_config: str | None = None  # opaque JSON credentials (Tuya local_key/ip_address) — see CONTEXT.md: Plugin Config
    auto_update_enabled: bool = True  # Smart Plug only — see CONTEXT.md: Auto-Update
    show_on_dashboard: bool = True    # see CONTEXT.md: Plug — set via set_plug_dashboard_visibility(), not create/update
    target_on_time: str | None = None   # "HH:MM" — see CONTEXT.md: Target Schedule
    target_off_time: str | None = None  # "HH:MM"
    timer_ack_on_time: str | None = None   # "HH:MM" — Timer Warning cleared against this Detected on-time; see CONTEXT.md: Timer Warning
    timer_ack_off_time: str | None = None  # "HH:MM" — same, for off-time
    always_on: bool = False  # mutually exclusive with target_on_time/target_off_time — see CONTEXT.md: Always On
    controller_kind: ControllerKind = ControllerKind.NONE
    target_temp_c: float | None = None        # paired with controller_kind = thermostat
    target_humidity_pct: float | None = None  # paired with controller_kind = hydrostat
    plug_group_id: int | None = None  # NULL if standalone — see CONTEXT.md: Plug Group

    @model_validator(mode="after")
    def _check_tracking_mode_identity(self) -> PlugBase:
        """Mirrors plug's CHECK (tracking_mode = 'smart' AND plugin/external_id NOT NULL) OR
        (tracking_mode = 'manual' AND both NULL) in db/schema.sql exactly — same rule as
        schemas/sensor.py's SensorBase, on a different table."""
        if self.tracking_mode == TrackingMode.SMART:
            if self.plugin is None or self.external_id is None:
                raise ValueError("A Smart Plug needs both plugin and external_id set.")
        else:
            if self.plugin is not None or self.external_id is not None:
                raise ValueError("A Manual Plug has no device credentials — plugin and external_id must be unset.")
        return self


class PlugCreate(PlugBase):
    """Body for inserting a new plug row. `enclosure_ids` isn't a plug column — it's the Enclosure
    side of the Room-XOR-Enclosure-set choice, written into plug_enclosure alongside this row (see
    module docstring for why it isn't cross-validated against room_id here)."""
    enclosure_ids: list[int] = Field(default_factory=list)


class PlugUpdate(PlugCreate):
    """Mirrors PlugCreate's shape — web/admin_queries.py's update_plug() replaces the whole row
    (room_id/enclosure_ids included) rather than patching individual fields, same as
    schemas/sensor.py's SensorUpdate. Split out on its own for the same forward-compatibility
    reason as there."""


class PlugRead(PlugBase):
    """Full row as stored — adds the DB-assigned id/created_at on top of PlugBase. No
    enclosure_ids here: that's plug_enclosure rows, not a plug column, so it stays out of the
    model this model's PRAGMA table_info(plug) test checks against (see
    schemas/test_entity_schema.py) — a caller wanting a Plug's Enclosures reads plug_enclosure
    separately, same as today's web/admin_queries.py does."""
    id: int
    created_at: str
