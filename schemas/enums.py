"""Consolidated string-literal enums for entity fields that are `CHECK`-constrained in
db/schema.sql — see Reptile_App_Technical_Requirements.md §9.15. Each enum's values MUST match
its corresponding CHECK constraint exactly; grep db/schema.sql for the literal list when adding
or renaming a value on either side (schemas/test_entity_schema.py only checks that Pydantic
models agree with `PRAGMA table_info()` on column names/nullability, not on CHECK value sets —
SQLite doesn't expose CHECK bodies via a pragma, so this file staying in sync is on the honor
system, same as _METRICS_BY_KEY below already was before this module existed).

`str, Enum` (not `enum.StrEnum`) throughout — StrEnum needs Python 3.11+; this repo's local dev
environment is still 3.10 (Docker is 3.11-slim, see Dockerfile), and web/status.py already
established this exact pattern for the same reason.

Enclosure Type stays in schemas/enclosure_types.py, NOT here — it's already the established
single source of truth for Enclosure Type, with Target Range / Controller Kind lookups built
around its `ENCLOSURE_TYPES` tuple (see ADR 0011). Duplicating it as an enum here would just
create a second source of truth for the same four strings; import it from there instead.
"""
from __future__ import annotations

from enum import Enum


class TrackingMode(str, Enum):
    """sensor.tracking_mode, plug.tracking_mode — see CONTEXT.md: Tracking Mode."""
    SMART = "smart"
    MANUAL = "manual"


class ControllerKind(str, Enum):
    """plug.controller_kind — see CONTEXT.md: Controller Kind, ADR 0008 (supersedes ADR 0007's
    is_thermostat_controlled)."""
    NONE = "none"
    THERMOSTAT = "thermostat"
    HYDROSTAT = "hydrostat"


class AlertState(str, Enum):
    """sensor_alert_state.state, plug_alert_state.state — see CONTEXT.md: Alert; ADR 0010."""
    NORMAL = "normal"
    PENDING = "pending"
    ALERTING = "alerting"
    RESOLVED = "resolved"


class SensorAlertCondition(str, Enum):
    """sensor_alert_state.condition_kind — see CONTEXT.md: Alert Condition."""
    OUT_OF_RANGE = "out_of_range"
    UNREACHABLE = "unreachable"


class PlugAlertCondition(str, Enum):
    """plug_alert_state.condition_kind — see CONTEXT.md: Alert Condition."""
    ZERO_POWER_WHILE_ON = "zero_power_while_on"
    UNREACHABLE = "unreachable"


class CareEventKind(str, Enum):
    """care_event.kind. Supersedes the CARE_EVENT_KINDS list literal in web/queries.py — that
    module still defines its own for now (see §9.14-style "finish the migration" note; not
    touched in this slice to keep this change additive, see §9.15 session log)."""
    FEEDING = "feeding"
    WATERING = "watering"
    SPOT_CLEAN = "spot_clean"
    DEEP_CLEAN = "deep_clean"
