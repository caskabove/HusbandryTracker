"""Plant entity schema (Pydantic v2) — seventh and last-scoped slice of the Entity Schema Layer,
see Reptile_App_Technical_Requirements.md §9.15 (tracked as Jira RHA-17). Follows the same pattern
as the rest of schemas/ — see schemas/sensor.py's module docstring for the full boundary-rule
reasoning.

`plant` has zero CHECK constraints in db/schema.sql — no model validator needed, same as
schemas/room.py and schemas/animal.py.

No `Update` class, same reasoning as schemas/care_event.py: there is no `update_plant()` anywhere
in web/admin_queries.py, only `create_plant()` and `delete_plant()`. An unused Update class would
be exactly the speculative machinery this design avoids.

The Bioactive gate ("only a Bioactive Enclosure can have Plants") is deliberately NOT modeled
here — it needs the *Enclosure* row's `bioactive` value, a different table, so it's a cross-row
rule per §9.15's boundary. Confirmed still true by reading `create_plant()` directly: it queries
`enclosure.bioactive` itself before inserting. Stays exactly there.

NOT in scope here: `plant_health_log` (Plant Health observations — see CONTEXT.md: Plant Health)
is a related but separate table with no Jira ticket of its own as of this slice. Deliberately not
built alongside this file — flag for a follow-up ticket rather than scope-creeping it in.
"""
from __future__ import annotations

from pydantic import BaseModel


class PlantBase(BaseModel):
    enclosure_id: int          # only meaningful on a Bioactive Enclosure — NOT cross-validated here, see module docstring
    name: str
    species: str | None = None


class PlantCreate(PlantBase):
    """Body for inserting a new plant row — matches create_plant()'s signature exactly."""


class PlantRead(PlantBase):
    """Full row as stored — adds the DB-assigned id/created_at on top of PlantBase."""
    id: int
    created_at: str
