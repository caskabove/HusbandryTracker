"""Room entity schema (Pydantic v2) — fifth slice of the Entity Schema Layer, see
Reptile_App_Technical_Requirements.md §9.15 (tracked as Jira RHA-14). Follows the same pattern as
schemas/sensor.py / schemas/plug.py / schemas/care_event.py / schemas/enclosure.py.

`room` has ZERO CHECK constraints in db/schema.sql (only `name`'s UNIQUE, DB-level and not
modeled here — same as Sensor/Plug's `(plugin, external_id)` UNIQUE, Enclosure's `name` UNIQUE).
So unlike every other entity so far, `RoomBase` needs no model validator at all — there is
genuinely nothing to mirror.

The Light Schedule both-or-neither rule (`light_on_time`/`light_off_time`) is NOT a schema.sql
CHECK — confirmed by reading db/schema.sql's `room` table directly, no CHECK block exists there at
all. It's enforced purely in `web/admin_queries.py::_validate_light_schedule()` (called from
`update_room()`), the exact same shape as Plug's Target Schedule both-or-neither rule in
schemas/plug.py — stays there, per the established boundary rule.

`RoomCreate` includes `light_on_time`/`light_off_time`/`light_notes` (all defaulted `None`) even
though the real `create_room()` only accepts `name` — Light Schedule is set via a follow-up edit
(`update_room()`), same UI-flow-simplification pattern as Enclosure's `room_id`/
`fallback_sensor_id` on `EnclosureCreate`. Documented rather than silently diverging.
"""
from __future__ import annotations

from pydantic import BaseModel


class RoomBase(BaseModel):
    name: str                          # UNIQUE at the DB level — not re-checked here, same as other entities' UNIQUE columns
    light_on_time: str | None = None   # "HH:MM" — see CONTEXT.md: Light Schedule; both-or-neither with light_off_time, NOT a CHECK (see module docstring)
    light_off_time: str | None = None  # "HH:MM"
    light_notes: str | None = None     # free text, independent of whether a time is set


class RoomCreate(RoomBase):
    """Body for inserting a new room row — see module docstring re: light fields."""


class RoomUpdate(RoomCreate):
    """Mirrors RoomCreate's shape: web/admin_queries.py's update_room() replaces the whole row
    (light fields included, unlike create_room()), same forward-compatibility reasoning as every
    other entity's Update class so far."""


class RoomRead(RoomBase):
    """Full row as stored — adds the DB-assigned id/created_at on top of RoomBase."""
    id: int
    created_at: str
