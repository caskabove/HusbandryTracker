# View Data: auto-advance date + "Add Another Day" to close the catch-up-entry deferral

**Context**: ADR 0026 and ADR 0027 both raised and then deliberately deferred "bulk/multi-day
entry" — entering a backlog of missed days without opening one cell/row at a time. The underlying
pain was never a missing bulk-entry UI as such; it was that the Add form always starts from a blank
date, so backfilling N missed days means picking the same N dates by hand, one click-through-the-
calendar at a time, even though each one is just "the day after the last one I added." This closes
that deferral with the lightweight fix that actually addresses it, not a full multi-row grid.

**Decision — derive the next date from the entries already on the page, every load, not from
redirect-only state**: View Data's detail page (ADR 0027) always loads every real entry for a row,
newest first. On every `GET` — a fresh navigation or the `303` redirect after a successful Add —
`view_data_queries.entry_prefill()` looks at `entries[0]` (the most recent real row) and suggests
`that date + 1 day` as the next Add's date, capped at today. This was chosen over carrying the
"next date" purely through the add-redirect's query params: deriving it from the data itself means
the catch-up flow survives closing the tab and coming back tomorrow, for free, with no extra state
to go stale. The button reads "Add Another Day" whenever the derived date is still before today
(there's a real gap left to close) and plain "Add" once the most recent entry is today or later, or
there are no entries yet — so the suggestion is self-capping: each successful Add moves "the most
recent entry" forward by one day, and clicking through a backlog naturally lands on today, at which
point the UI quietly reverts to normal. A Reading/Animal Log/Care Event is never pre-filled into a
future date.

**Decision — Period Slot (see CONTEXT.md; ADR 0026) carries forward too, inferred from the last
entry's stored time**: matched back against the three anchor hours (8am/2pm/8pm); Care Event's
4th option, Exact time, also carries forward with its literal time value, since Care Event's
selector can represent it and Reading/Animal Metric/Animal Condition's can't (an unmatched time
there falls back to the Afternoon default instead of selecting an option that isn't offered). A
user backfilling a week of morning measurements doesn't have to re-pick "Morning" on every single
day.

**Decision — Value/Note/Animal/Condition never carry forward**: only date and Period Slot are about
*which day/time this is*; the actual measurement almost always differs day to day, and auto-filling
it risks silently duplicating a stale value into a new day. These fields always clear, matching
existing behavior.

**Decision — a failed Add's attempted date/period-slot/time ride back through the error redirect's
query params**: this is the one place state still travels through the redirect rather than being
derived, because a failed Add saved nothing — there's no new `entries[0]` to read it back from. The
existing `?error=` query param on these four POST routes gained siblings (`date`, `period_slot`,
`time`) for this case only, built with `urlencode` instead of the old single `quote(error)`
f-string. A typo'd value no longer loses the user's place mid-streak.

**Decision — the main data-entry field autofocuses on load**: Value for Reading/Animal Metric, Note
for Care Event, Condition for Animal Condition. Combined with the date already being right, the
fast loop is reload → type → Enter → reload, with no mouse needed between rows.

**Decision — scope is all four editable row types sharing `view_data_detail.html`**, not just
Reading: Care Event, Animal Metric, and Animal Condition have the identical backfill shape and
share the same template and the same `action=add` POST pattern, so implementing this once in
`view_data_queries.entry_prefill()` covers all four for the cost of one.

**Consequences**: no schema change — this only changes what the Add form is pre-filled with and
what its button says, derived from data that was already being loaded. `web/admin.py`'s four
`.../entries` POST handlers build their redirect query string with `urlencode` on a dict instead of
a bare `quote(error)` f-string, only when the failed action was `add`. Bulk/multi-day entry in the
sense of a dedicated multi-row grid remains undone, but the actual complaint behind both prior
deferrals — picking the same handful of consecutive dates by hand — is resolved.
