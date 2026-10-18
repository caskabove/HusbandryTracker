# View Data: Period Slot as a backdating option for Reading/Animal Log/Care Event entry

**Context**: View Data's day-grid (see CONTEXT.md: View Data; ADR 0021) is meant to make backfilling
past data easy — a new user catching up history, someone transcribing a week of notepad
measurements, or filling in a day they forgot. A Reading or Animal Log cell has no time-of-day
control at all today: a new value is always silently stamped at local noon. A Care Event cell
already has a real `<input type="time">`, but it forces picking (or defaulting to) an exact minute
even when the user genuinely doesn't know or care what time something happened — common for a
notepad-transcribed water test or a backdated feeding.

**Decision — reuse Period Slot (see CONTEXT.md) as the vocabulary, not a new term**: Morning (8am) /
Afternoon (2pm) / Night (8pm) already existed as a *display* concept (Care Event marker snapping on
Graphs). This adds an *entry* use of the exact same three buckets and anchor hours. Rejected
inventing a second term (e.g. "Approximate Time") for the entry side — same three words, same three
hours, same purpose (a coarser substitute for an exact time); two glossary entries for one idea would
be exactly the kind of duplication CONTEXT.md exists to prevent.

**Decision — a Period Slot pick is stored as a real timestamp at the anchor hour, with no separate
"approximate" marker**: picking "Afternoon" for a backfilled pH Reading stores `recorded_at` as
2pm local, converted to UTC, indistinguishable in storage from a hand-typed "2:00pm" entry. This is
deliberate, not an oversight: unlike the Interpolated Point this app tried and then dropped (see ADR
0025) — a *computed*, fabricated value nobody actually attested to — a Period Slot entry is always
something the user is reporting as true ("this happened in the afternoon"), just at coarser
precision. There is nothing here to visually flag as fake, because it isn't.

**Decision — scope**: Reading and Animal Log cells (which have no time control today) get Period
Slot only — Morning/Afternoon/Night, defaulting to Afternoon so a user who doesn't care can still
save in one action, matching today's "just type a number and hit save" speed. Care Event keeps its
existing exact-time field *and* gains Period Slot as an alternative, combined into one `<select>`
(Morning/Afternoon/Night/Exact time…) rather than two separate controls, so there's never ambiguity
about which one wins — exactly one time source is active at a time. Care Event's own default also
moves to Afternoon, for consistency across all three row types.

**Decision — editing an existing Reading/Animal Log cell never moves its stored time**: today,
updating an existing `sensor_reading`/`animal_log` row only ever touches the value column —
`recorded_at` is set once, at insert, and a value-only edit leaves it alone. Adding a Period Slot
selector could have changed that (re-stamping the time to whatever the selector shows on every
save), but the selector has no way to faithfully read back an existing row's actual time if it
doesn't land on one of the three anchors (e.g. a legacy noon-stamped row, or an exact time entered
through the separate Enclosure-page logging flow) — defaulting it to Afternoon regardless would risk
silently moving a real logged time just because someone corrected a typo'd value. Kept the existing
"edit never touches time" rule instead: the Period Slot selector only has any effect when creating a
new row in an empty cell. Care Event is unaffected by this — its time field already reads back and
re-applies the true value on every save, update or insert, so no equivalent risk exists there.

**Consequences**: once a Reading or Animal Log row exists, its time of day can't be changed short of
clearing the cell and re-entering it — not a new limitation, since no time control exists for either
today. No schema change: every column this needs (`recorded_at`, `occurred_at`) already exists.
Scoped to View Data's own cell editor only — the Enclosure page's separate "log now"/backdate flow
(exact `datetime-local` picker) is untouched. Bulk/multi-day entry (entering a week at once without
opening one cell at a time) was raised as a related need but deliberately deferred to its own,
separate round of design rather than bundled in here.
