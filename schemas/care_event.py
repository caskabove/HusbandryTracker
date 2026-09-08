"""Care Event entity schema (Pydantic v2) — third slice of the Entity Schema Layer, see
Reptile_App_Technical_Requirements.md §9.15 (tracked as Jira RHA-25). Follows the same pattern as
schemas/sensor.py / schemas/plug.py, with one real difference explained below.

Boundary rule (see schemas/sensor.py's module docstring for the full reasoning): the model
validates a rule only if it's an actual CHECK constraint on `care_event` in db/schema.sql. That
table has exactly one CHECK — `kind IN (...)` — mirrored below via the `CareEventKind` enum field
type. The Spot-feed rule ("animal_id only valid alongside kind = 'feeding'") is deliberately NOT
a CHECK — db/schema.sql's own comment on this table says so explicitly ("enforced in
web/admin_queries.py rather than a CHECK, same pattern as this file's other cross-column rules")
— so it stays in web/queries.py::log_care_event(), not modeled here, per §9.15's boundary.

No `Update` class, unlike Sensor/Plug: there is no `update_care_event`/`delete_care_event`
anywhere in web/queries.py or web/admin_queries.py — only `log_care_event()` (insert). Care
Events are append-only, matching CONTEXT.md's "capture everything" pattern already established
for `sensor_reading`. Adding an Update class with nothing behind it would be exactly the
speculative machinery §9.15 already decided against for Sensor/Plug's own Update classes.
"""
from __future__ import annotations

from pydantic import BaseModel

from schemas.enums import CareEventKind


class CareEventBase(BaseModel):
    enclosure_id: int          # every Care Event belongs to an Enclosure — see CONTEXT.md: Care Event
    kind: CareEventKind
    animal_id: int | None = None  # Spot-feed only — see CONTEXT.md: Spot-feed; NOT cross-validated
                                   # against kind here, see module docstring
    note: str | None = None


class CareEventCreate(CareEventBase):
    """Body for logging a new care_event row. occurred_at is caller-settable (backdatable — see
    CONTEXT.md: Care Event) unlike Sensor/Plug's created_at: None means "log it as now", matching
    log_care_event()'s own default."""
    occurred_at: str | None = None


class CareEventRead(CareEventBase):
    """Full row as stored — adds the DB-assigned id and the always-populated occurred_at (NOT
    NULL with a DEFAULT in db/schema.sql, so always a real value once read back, unlike on
    Create)."""
    id: int
    occurred_at: str
