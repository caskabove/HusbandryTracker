# Feeding gains a Feeding Detail extension table; Shed Log is a new, separate table

**Status**: accepted

**Context**: RHA-91 asked for two things — richer per-occurrence detail on a Feeding (what was
fed, how much, live/frozen-thawed, accepted/refused), and a new log for Sheds (full/partial,
stuck-shed location, notes). Both could in principle have been added as new `care_event` kinds or
folded into `care_event`'s existing bare `(kind, occurred_at, note)` shape, but neither fits that
shape well, for different reasons — discussion on RHA-91 settled both before any code was written.

**Decision — Feeding Detail, a 1:1 extension of `care_event`, not a replacement**: a Feeding
Care Event keeps logging to `care_event(kind='feeding')` exactly as before — Care Interval,
staleness color-coding, and nag escalation (`web/status.py`, `web/admin_queries.py`'s
`record_care_nags()`) all depend on the shared 4-kind `care_event` mechanism Watering/Spot-clean/
Deep-clean also use, and carving Feeding out of that shared mechanism to stand alone would mean
teaching all three of those call sites to special-case Feeding differently from its three
siblings. Instead, a new `feeding_detail` table (`food` free text, `count`, `prey_state`
live/frozen-thawed/dry, `result` accepted/refused) is written alongside every Feeding `care_event` row,
one-to-one, referencing it via a `UNIQUE` `care_event_id` foreign key — `web/admin_queries.py`'s
`log_feeding()` does both inserts together. `note` stays on `care_event` itself rather than being
duplicated onto `feeding_detail`, since it was never Feeding-specific to begin with.

`food` is one free-text field rather than separate "prey type" and "prey size" fields (the
ticket's own suggestion) — real feeding vocabulary fuses the two ("weaned rat," "small rat"), and
a single field serves the "repeat last Feeding" UX below more directly than two fields that would
need recombining.

**Decision — "repeat last Feeding" reuses the existing Today/Yesterday/2-days-ago + Advanced
pattern**: rather than adding a fourth quick-log button, the three existing buttons (which never
submit Feeding Detail fields at all) are treated server-side as "repeat the last Feeding" whenever
`kind == 'feeding'` and no detail fields were submitted — `get_last_feeding_detail()` fills them in
from the most recent `feeding_detail` row for that Enclosure (or, for a Spot-feed, that specific
Animal). The Advanced form gains `food`/`count`/`prey_state`/`result` inputs, pre-filled from that
same lookup so a keeper can change just the one thing that's different (e.g. flip to Refused) and
submit, rather than retyping everything. A Feeding always writes a `feeding_detail` row, even a
bare quick-log repeat, so the next repeat always chains from the real most-recent Feeding rather
than skipping back further each time nothing new was typed.

**Decision — Shed Log is its own table, scoped to one Animal, not a `care_event` kind**: a Shed is
an observation, not an action the keeper performed, and the ticket never asked for interval/
staleness tracking on it the way Feeding/Watering/Cleaning get — so it doesn't belong in
`care_event` at all. Same reasoning and shape `animal_log`/`plant_health_log` already established
(see their own `db/schema.sql` comments): a new `shed_log` table, `animal_id NOT NULL` (always
scoped to one Animal — a Shed is never a whole-Enclosure event the way Watering is), with
`completeness` (full/partial), `stuck_locations` (Partial only — a comma-joined list of a small
fixed vocabulary plus free text, not a join table, matching the flat-TEXT simplicity every other
small multi-value field in this schema already uses), `note`, and the same backdatable
`occurred_at` every other log already has.

**Decision — photo deferred to RHA-97**: a photo field was in RHA-91's own open questions for Shed
Log, but there is no file-upload capability anywhere in this app yet (no multipart handling, no
on-disk storage location, no image serving) — that's new infrastructure, not a form field, so it
was split into its own ticket (RHA-97), which also covers a "main photo" for Animal/Enclosure/
Plant that came up in the same discussion.

**Consequences**: `db/schema.sql` gains `feeding_detail` and `shed_log`, both purely additive — no
existing table changes, so `tools/migrate_2026_10_30_feeding_detail_and_shed_log.py` just re-runs
the schema file (same shape as `tools/migrate_2026_09_21_plug_group.py`). `web/queries.py`'s
`log_care_event()` now returns the new row's id, needed by `log_feeding()` to attach its
`feeding_detail` row. RHA-58 (Text-to-Log event vocabulary, not yet built) currently assumes every
event type including feeding and shed maps onto `care_event` — it will need to route those two to
the new tables instead when it's picked up. Neither `feeding_detail` nor `shed_log` gained an
Entity Schema Layer (§9.15/RHA-25) Pydantic model — `animal_log` and `plant_health_log`, their
closest architectural siblings, don't have one either, so this follows that existing gap rather
than introducing inconsistent extra coverage.
