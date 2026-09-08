"""Plug Command Log entity schema (Pydantic v2) — see CONTEXT.md: Command, Interruption; ADR 0014.
Follows the schemas/care_event.py pattern: append-only, one write path
(web/admin_queries.py::send_plug_command(), not built yet as of this file — see ADR 0014's
Consequences), no update/delete anywhere, so only Create/Read exist here, no Update — mirroring
db/schema.sql's own comment that plug_command_log is never updated in place.

`plug_command_log` has no CHECK constraints in db/schema.sql beyond NOT NULL, so — same as
schemas/animal.py/schemas/room.py — this model needs no model_validator.
"""
from __future__ import annotations

from pydantic import BaseModel


class PlugCommandLogBase(BaseModel):
    plug_id: int
    is_on: bool
    is_interruption: bool  # true iff the Plug had a determined setting at request time — see CONTEXT.md: Interruption
    note: str | None = None  # only ever prompted-for on an Interruption; free text otherwise unused


class PlugCommandLogCreate(PlugCommandLogBase):
    """Body for logging a new Command. requested_at is caller-settable (None means "log it as
    now"), same pattern as CareEventCreate.occurred_at — lets a Manual Plug's self-reported entry
    be backdated the same way a Care Event can be."""
    requested_at: str | None = None


class PlugCommandLogRead(PlugCommandLogBase):
    """Full row as stored — adds the DB-assigned id and the always-populated requested_at (NOT
    NULL with a DEFAULT in db/schema.sql, so always a real value once read back, unlike on
    Create)."""
    id: int
    requested_at: str
