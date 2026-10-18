"""Sensor entity schema (Pydantic v2) — first slice of the Entity Schema Layer, see
Reptile_App_Technical_Requirements.md §9.15. Reacted-to pattern for the rest of the entities
(room, enclosure, animal, plant, plug, care event, …) once this shape proves out.

Boundary this module holds to (§9.15): field/shape validation lives here, mirroring `sensor`'s
own single-table CHECK constraints in db/schema.sql exactly (tracking_mode/plugin/external_id
coupling, enclosure_id/room_id XOR). Two related rules do NOT live here, on purpose, because
they need another table's data to evaluate and so count as service-layer / cross-row concerns
per §9.15's boundary list:
  - "a Manual Sensor needs a complete Target Range on at least one metric" — stays in
    web/admin_queries.py::_validate_sensor.
  - "a submitted Target Range metric must apply to the parent Enclosure's Enclosure Type" —
    needs the Enclosure row's enclosure_type; stays in
    schemas/enclosure_types.py::validate_target_ranges(), called from web/admin_queries.py.

Not yet wired into web/admin_queries.py, tools/register_device.py, or anywhere else — this slice
is the pattern to react to, not a replacement for the existing dict-based validation. That
migration is a followup once the pattern is confirmed (see §9.15 session log).
"""
from __future__ import annotations

from pydantic import ConfigDict, create_model, model_validator

from schemas import enclosure_types as et
from schemas.enums import TrackingMode

# Every Target Range min/max column pair, generated from schemas/enclosure_types.py's
# TARGET_RANGE_METRICS rather than re-listed by hand — see CONTEXT.md: Target Range; ADR 0011.
# That module is already the single source of truth for these column names (web/admin_queries.py's
# _target_range_sql() builds its INSERT/UPDATE column list from the same tuple), so this is a
# second reader of it, not a second source of truth.
_TargetRangeFields = create_model(
    "_SensorTargetRangeFields",
    **{
        column: (float | None, None)
        for metric in et.TARGET_RANGE_METRICS
        for column in (metric.min_column, metric.max_column)
    },
)

# One nullable "fast"/"slow" override column per metric — see CONTEXT.md: Volatility; ADR 0025.
_VolatilityFields = create_model(
    "_SensorVolatilityFields",
    **{
        metric.volatility_column: (str | None, None)
        for metric in et.TARGET_RANGE_METRICS
    },
)


class SensorBase(_TargetRangeFields, _VolatilityFields):  # type: ignore[misc]
    model_config = ConfigDict(use_enum_values=False)

    label: str
    tracking_mode: TrackingMode = TrackingMode.SMART
    enclosure_id: int | None = None   # exactly one of enclosure_id/room_id — see CONTEXT.md: Sensor
    room_id: int | None = None
    plugin: str | None = None         # e.g. "govee_ble"; required (with external_id) iff Smart — see CONTEXT.md: Plugin
    external_id: str | None = None    # opaque per-Plugin device id, e.g. a MAC address — see CONTEXT.md: External ID
    plugin_config: str | None = None  # opaque JSON credentials; NULL if the Plugin needs none — see CONTEXT.md: Plugin Config
    auto_update_enabled: bool = True  # Smart Sensor only — see CONTEXT.md: Auto-Update
    show_on_dashboard: bool = True    # see CONTEXT.md: Sensor — set via set_sensor_dashboard_visibility(), not create/update

    @model_validator(mode="after")
    def _check_tracking_mode_identity(self) -> SensorBase:
        """Mirrors sensor's CHECK (tracking_mode = 'smart' AND plugin/external_id NOT NULL) OR
        (tracking_mode = 'manual' AND both NULL) in db/schema.sql exactly."""
        if self.tracking_mode == TrackingMode.SMART:
            if self.plugin is None or self.external_id is None:
                raise ValueError("A Smart Sensor needs both plugin and external_id set.")
        else:
            if self.plugin is not None or self.external_id is not None:
                raise ValueError("A Manual Sensor has no physical device — plugin and external_id must be unset.")
        return self

    @model_validator(mode="after")
    def _check_single_parent(self) -> SensorBase:
        """Mirrors sensor's CHECK (enclosure_id XOR room_id) in db/schema.sql exactly."""
        if (self.enclosure_id is None) == (self.room_id is None):
            raise ValueError("A Sensor belongs to exactly one of enclosure_id or room_id, never both or neither.")
        return self


class SensorCreate(SensorBase):
    """Body for inserting a new sensor row — no id/created_at, both DB-assigned."""


class SensorUpdate(SensorBase):
    """Mirrors SensorCreate's shape: web/admin_queries.py's update_sensor() replaces the whole
    row (no partial-field PATCH exists yet), so there's nothing an Update needs beyond Create
    plus the id, which callers already have out-of-band as the row to update. Split out as its
    own class anyway, per §9.15's Base/Create/Update/Read convention, so a future PATCH-style
    endpoint has somewhere to diverge without reshaping SensorCreate underneath it."""


class SensorRead(SensorBase):
    """Full row as stored — adds the DB-assigned id/created_at on top of SensorBase."""
    id: int
    created_at: str
