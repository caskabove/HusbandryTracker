# Feeding's quick-log buttons open a confirm-and-adjust dialog instead of repeating silently

**Status**: accepted

**Context**: ADR 0042 gave Feeding its own `feeding_detail` extension table and had
Today/Yesterday/2-days-ago silently repeat the most recent Feeding's Food/Count/Prey State/Result
with zero extra clicks — the Advanced form existed only as the place to change one field without
retyping everything. In practice this traded away too much: a keeper spot-feeding a different
Animal than last time, or logging a different food/outcome than usual, had no visible confirmation
of what was about to be repeated before committing, and the Care Setup Prompt's "Set your own"
hint banner it grew to compensate (see Care Setup Prompt, CONTEXT.md) was its own admission that
the silent-repeat flow needed explaining. This revisits that decision for Feeding specifically —
Watering/Spot-clean/Deep-clean's instant one-click logging (no detail fields to repeat) is
untouched.

**Decision — Today/Yesterday/2-days-ago open the Log Feeding Dialog instead of submitting
immediately**: clicking any of the three buttons opens one shared dialog (see Log Feeding Dialog,
CONTEXT.md) pre-filled with the last matching Feeding's Who/Food/Count/Prey State/Result, Date
locked to that button's offset. Nothing is logged until the user explicitly submits the dialog's
own "Log" button; closing it (backdrop click or X, same convention as the existing Care Setup
Prompt modal) discards it with no confirmation guard and logs nothing.

**Decision — Advanced is repurposed as backdating/catch-up, sharing the same dialog**: rather than
building a second form, Advanced opens the identical Log Feeding Dialog with Date editable
(`datetime-local`) and no day pre-picked, instead of the inline `<details>` it used to be for
Feeding. This keeps "logging a Feeding" one concept with one set of fields/defaulting logic
instead of two forms that must be hand-kept in sync. Advanced for Watering/Spot-clean/Deep-clean is
unchanged — those three never had detail fields to share a dialog over.

**Decision — Who moves into the dialog; the row-level Spot-feed picker and its hint banner are
removed**: the `spot-feed-picker` `<select>` and `syncSpotFeedAnimal()` (`app.js`) existed only to
sync a hidden `animal_id` into whichever of the four old forms got submitted — once the dialog
carries its own visible Who field, that workaround has no job left, and is deleted outright rather
than kept as a redundant pre-set. The `care-advanced-hint` banner ("Pick when it actually happened
for each one below, then click Log.") and `dismissCareAdvancedHint()` are removed entirely along
with it — bad UX per direct feedback, and no longer applicable now that Feeding's Advanced isn't an
inline dropdown a hint needs to explain.

**Decision — per-Who defaulting reuses `get_last_feeding_detail()`, pre-embedded, no new
storage**: switching Who inside the dialog clears the other fields and immediately refills them
from that Who's own last Feeding (blank only when that Who genuinely has none yet) —
`get_last_feeding_detail(enclosure_id, animal_id)` (`web/admin_queries.py`) already scopes
correctly per Animal (Spot-feed) or enclosure-wide and needed no schema change. To make switching
feel instant, the admin page now computes it once per Animal (plus once enclosure-wide) at render
time and embeds the whole set client-side, rather than adding a live-fetch endpoint — Enclosures
here hold few Animals, so the extra per-render computation is cheap. Result defaults to Accepted
when a Who has no history at all (matching the existing fallback in `admin_create_care_event`);
Prey State stays unselected rather than guessing Live/Frozen/Dry with nothing to go on.

**Decision — Prey State gains a third value, `dry`**: covers pelleted/flake food, distinct from
live or frozen-thawed prey — real for an omnivorous lizard's or fish's diet. `PREY_STATES` and the
`feeding_detail.prey_state` `CHECK` constraint grow from two values to three (see ADR 0042, amended
in place since it had not yet been merged).

**Decision — the Care Setup Prompt's "Set your own" no longer touches Feeding**: it still
auto-expands each other unlogged kind's inline Advanced `<details>` exactly as before; an unlogged
Feeding is left alone rather than auto-opening its dialog, since popping a second modal immediately
after dismissing the first would be jarring, and the dialog now carries its own Who-switch state to
absorb on open. The user opens it themselves (any of the four buttons) when ready, same as arriving
at the page with no prompt at all.

**Consequences**: `db/schema.sql`'s `feeding_detail.prey_state` CHECK constraint needs a migration
to add `dry`; `web/queries.py`'s `PREY_STATES`/`PREY_STATE_LABELS` grow to match. The row-level
`spot-feed-picker` markup, `syncSpotFeedAnimal()`, the `care-advanced-hint` markup, and
`dismissCareAdvancedHint()`/`useOwnCareDates()`'s hint-showing line all get deleted rather than
deprecated. `admin_queries.py`'s `get_enclosure()` gains a per-Animal `get_last_feeding_detail()`
pass (plus the existing enclosure-wide one) to embed for the dialog's client-side Who-switch.
`admin_create_care_event` (`web/admin.py`) is unchanged in shape — it already accepts
Who/Food/Count/Prey State/Result together on one POST; only the template changes which UI produces
that POST and when.
