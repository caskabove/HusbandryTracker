# Room grouping, with a per-Enclosure Fallback Sensor

**Status**: accepted

The dashboard organized Enclosures as a flat grid. That stopped matching reality once Enclosures
needed grouping by physical space (which ones share a room), a room-level ambient reading distinct
from any Enclosure's own microclimate, and a way for an Enclosure with no Sensor of its own to show
*something* useful rather than "no data yet".

A new `room` table holds this: a name, its own Sensor(s) (reusing Tracking Mode/Target Range/
Reading unchanged — a Room's Sensor is the same kind of thing as an Enclosure's, just with a
different parent), and a Light Schedule (on-time/off-time plus a free-text note — see
`CONTEXT.md`). `sensor`'s parent becomes polymorphic: `enclosure_id` or `room_id`, exactly one, not
both. `enclosure.room_id` is optional, so none of the 12 existing Enclosures need reassignment for
this to ship. The dashboard groups panels into a section per Room (each section heading showing
that Room's own Sensor readings and Light Schedule), with an "Ungrouped" section for the rest.

An Enclosure with zero Sensors of its own, belonging to a Room, gets a **Fallback Sensor** picker —
a dropdown of that Room's Sensors, so the specific one nearest that Enclosure can be chosen rather
than assuming one Room-wide default. Its Reading is shown raw and uncolored: a Room's Target Range
means "comfortable for a person standing in the room," and coloring an Enclosure's panel green
against that would misrepresent whether the actual animal's environment is fine.

Three alternatives were rejected:
- **Modeling Room as a special Enclosure** (a parent_room_id self-reference) — rejected because a
  Room has no Animals, Bioactive flag, or Care Events; every Enclosure-shaped query would need a
  permanent "but not if it's secretly a Room" filter.
- **A single Room-wide primary Sensor** for all of that Room's zero-Sensor Enclosures — rejected
  because different Enclosures in the same Room can sit nearer different Sensors (a window vs. a
  door), and forcing them all to the same one throws that distinction away.
- **Coloring a Fallback Sensor's Reading against the Room's Target Range** — rejected as
  misleading; see above.

**Consequences**: `sensor.enclosure_id` becomes nullable, with a CHECK ensuring exactly one of
`enclosure_id`/`room_id` is set. `enclosure` gains a nullable `room_id` and a nullable
`fallback_sensor_id` (`ON DELETE SET NULL`, so deleting a Room's Sensor — directly or via deleting
the Room itself, which cascades to its Sensors — just clears the pointer rather than blocking the
delete or erroring). Deleting a Room un-assigns its Enclosures (`room_id` set NULL) rather than
deleting them. Admin gains a full Rooms list + per-Room detail page mirroring Enclosure's existing
treatment, plus a Room-assignment dropdown and (when applicable) a Fallback Sensor dropdown on the
Enclosure settings form.
