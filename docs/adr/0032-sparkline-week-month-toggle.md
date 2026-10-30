# Sparkline gains a per-chart Week/Month toggle

**Context**: ADR 0028 shrank Sparkline's window from a month to a week for readability, but kept
it fixed — there was no way back to the longer view short of clicking through to Graphs. A request
asked for a way to pick between week and month right on the Sparkline itself.

**Decision — two embedded windows, client-side toggle**: `web/queries.py`'s `_sparkline` now fetches
both a week and a month of each metric's data up front (`_SPARKLINE_RANGES`), and every Sparkline
chart ships both, embedded on its `<canvas>` as `data-points-week`/`data-points-month`. A small
Week/Month button pair (`.sparkline-range-toggle`, `web/static/graphs.js`'s `setSparklineRange`)
sits beside each chart; clicking one just redraws that chart from whichever window is already on
the page — no new request, no new route. This mirrors how Sparkline already ships fully baked into
the page rather than fetching on demand (ADR 0022's offline-install constraint: nothing here adds a
network round-trip the app didn't already avoid). The month window reuses the exact same
raw/bucket/smooth split per Tracking Mode that the week window already used (ADR 0023, ADR 0024) —
a Smart Sensor's month is still only ~30 daily buckets, not a raw row dump — so embedding both costs
little extra payload.

**Decision — scope**: the toggle applies everywhere Sparkline already appears — Dashboard panels,
Admin Enclosure/Room Sensor tables, and the Room header's condensed ambient-pill summary — not just
the Admin Enclosure page the request started from, so every Sparkline location keeps behaving the
same way (the precedent ADR 0024 and ADR 0028 each already followed).

**Decision — per-chart, not per-group**: each metric's chart gets its own independent toggle rather
than one toggle governing every chart under a Sensor (e.g. a Govee Sensor's Temp and Humidity
charts can show different windows at once). Simpler to wire — no group-level state to keep in sync
— and the Room header's Govee-specific layout splits Temp/Humidity into separate markup blocks with
no shared wrapper to hang a group toggle on anyway.

**Decision — defaults, bug fix in passing**: every chart defaults to Week, matching ADR 0028's
existing default. While touching every Sparkline call site, `admin_room.html` was found to be
missing the `chart.min.js`/`graphs.js` `<script>` tags every other Sparkline-rendering template
already has — its Sparklines were rendering as blank canvases. Added alongside this change, since
the new toggle would otherwise have had nothing to toggle on that page either.

**Why**: Embedding both windows keeps Sparkline's "fully baked into the page, no live dependency"
shape (ADR 0022) intact rather than introducing a JSON endpoint and a loading state for what's a
small, bounded amount of data either way. A per-chart toggle is simpler to reason about and
implement than keeping multiple charts in a group synchronized, at the cost of a little visual
repetition when a Sensor has more than one metric.

**Consequences**: `_sparkline`'s return shape changes from `{"points": [...], "target_min": ...,
"target_max": ...}` to `{"ranges": {"week": [...], "month": [...]}, "target_min": ...,
"target_max": ...}` — every template reading `spark.points` now reads `spark.ranges.week`/
`spark.ranges.month`. `_SPARKLINE_DAYS` is replaced by `_SPARKLINE_RANGES`, a week/month pair; a
third window would extend that tuple plus each template's two-button toggle markup. A Sensor with
data only outside the default Week window (e.g. a Manual Sensor last logged three weeks ago) shows
an empty Week chart until the viewer clicks Month — no auto-selection of "whichever window actually
has data," kept simple since Week is still the common case ADR 0028 optimized for.
