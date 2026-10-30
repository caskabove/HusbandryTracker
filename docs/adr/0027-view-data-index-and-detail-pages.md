# View Data: replace the single day-grid page with an index of titles + a per-row detail page

**Context**: View Data's original shape (ADR 0021) was one page per Room/Enclosure: a table with one
row per Sensor+metric/Care Event kind/Animal Log field/Plug metric, columned by calendar day, each
cell showing that day's *last* value. Feedback after using it for real backfilling was that it shows
too much at once — a wide, mostly-empty day-grid — when what's actually wanted is: see the list of
things that can be logged, pick one, and get a simple editable table of its actual entries. The
day-grid's "last value per day wins" rule was also actively in the way for the three backfill
scenarios ADR 0026 was written for (catching up history, transcribing a week of notes, filling a
forgotten gap) — it hides same-day multiple entries and makes correcting or removing a specific past
entry (rather than "today's cell") awkward.

**Decision — two levels, not one**: the index (still per Room/Enclosure) now shows *only* row
titles — no dates, no values, nothing computed per day. Clicking a title opens that row's own detail
page: every real row behind it (e.g. every `sensor_reading` for one Sensor+metric), newest first,
with its own Add/Edit/Delete. This replaces the grid outright rather than adding the detail page
alongside it — the day-grid's view is now redundant with Graphs (which already charts the same rows
over a date range) plus this detail list, so keeping a third way to see the same data wasn't worth
the upkeep.

**Decision — the index drops its Range picker/date window entirely**: since the index no longer
computes anything per day, it no longer needs `week`/`month`/`90d`/... or a Prev/Next window either —
it's a flat, cheap list of Sensors/kinds/Animals/Plugs this Room/Enclosure has. Graphs keeps its own
Range picker (`view_data_queries.compute_window`/`date_list`/`RANGE_OPTIONS` are retained for that
one caller) — Graphs' use case (chart a window of time) is unrelated to View Data's new one (manage
a row's own entries).

**Decision — a detail page shows at most 300 entries, newest first, no pagination yet**: a Manual
Sensor/Animal Log/Care Event row is sparse (at most a few a day) and 300 comfortably covers a year+
of real use. A Smart Sensor's auto-collected Reading row could otherwise be thousands of rows; the
same cap applies there too rather than special-casing it, since that row is read-only anyway and the
cap is just about not rendering an unreasonably long read-only list.

**Decision — Reading/Animal Log entries keep ADR 0026's "edit never moves time" rule; Care Event
entries are now fully editable (date, time, note, spot-fed Animal) on every save**: unchanged from
ADR 0026 for the first two — editing a Reading/Animal Log entry's value only ever touches its value
column. Care Event already re-derived its full `occurred_at` (and note/Animal) on every save under
ADR 0026; this carries that forward to the per-row detail table rather than only allowing it on
"today's cell" as the grid did. Fixing a wrong date/time/value on a Reading or Animal Log entry now
means delete-and-re-add rather than in-place correction — no worse than the grid, which never
exposed per-entry date editing either.

**Consequences**: `view_data_queries.py`'s per-day cell functions (`set_reading_cell`,
`set_care_event_cell`, etc., all keyed by `(owner, day)`) are replaced by per-entry CRUD functions
keyed by row id (`add_reading_entry`/`update_reading_entry`/`delete_reading_entry`, and the
equivalent trio for Care Event/Animal metric/Animal Condition); `web/admin.py`'s four `.../cell` POST
routes are replaced by GET detail routes plus `.../entries` POST routes taking an `action` of
add/update/delete. No schema change. Bulk/multi-day entry is still deferred, as it was under ADR
0026.
