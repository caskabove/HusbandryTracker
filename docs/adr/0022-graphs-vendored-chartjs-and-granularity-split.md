# Graphs: vendored Chart.js, raw/aggregate split by range, sparklines on existing pills

**Context**: Phase 2 shipped as "dashboard + logbook, no charts" (see `web/main.py`'s module
docstring, now stale as of this ADR). View Data (ADR 0021) gave every tracked row a day-bucketed
table; the next ask is to chart that same data, plus a small trend indicator under each Dashboard
Reading pill, plus the ability to overlay unrelated series (e.g. temperature, Feeding events, and
Animal weight) to eyeball relationships between them.

**Decision — scope**: Graphs (see CONTEXT.md) is a new page per Room/Enclosure, reached the same
way as View Data, not a global cross-entity page — it keeps the same "a Room never rolls up its
Enclosures' data" boundary already drawn for Refresh and View Data. It's a sibling to View Data, not
a replacement or a tab: View Data stays the only place these rows are edited, so Graphs can treat
every row as pure read-only display.

**Decision — charting library**: Chart.js is vendored into `web/static/` (no CDN reference) rather
than hand-rolled from inline SVG. This app has no other runtime network dependency — every existing
`<script>` tag already points at `/static/` (see `web/templates/*.html`), consistent with offline
install via PyInstaller/InnoSetup (ADR 0018) — so a charting library has to ship with the app, not
load from a CDN at runtime.

**Decision — granularity**: a Smart Sensor's dedupe window is 5 seconds (see
`plugins/govee_ble/plugin.py`), so a single Sensor can write a new `sensor_reading` row every
5-30 seconds continuously — tens of thousands of rows a day. Raw-rendering that for every range
View Data already offers (Week through Year) isn't viable in a browser. Graphs therefore plots raw
points for Week and Month, and switches to server-side aggregated buckets (min/avg/max per bucket,
drawn as an average line with a shaded min-max band) for 90 Days, 180 Days, and Year. This split
applies only to auto-collected series (Smart Sensor Readings, Plug Data Capture) — Care Events,
Animal Log entries, Manual Sensor Readings, and Plug Status changes are never high-volume enough to
need it, and always plot raw regardless of range.

**Decision — overlay**: the picker is free-form and ad hoc, not a saved/named preset — no new schema
for it. Checking rows draws one additional combined chart alongside the page's existing per-row
default charts (nothing is hidden or replaced). Numeric series sharing a unit share a Y-axis;
a series with a different unit gets its own, assigned automatically rather than through a manual
per-series axis control. A Care Event, Plug Status change, or Animal Log Condition has a moment but
no value, so it never gets a Y-axis at all — it draws as a marker along the x-axis instead, on any
chart it's added to.

**Decision — sparkline**: a small 24-hour, single-metric chart renders under every Reading pill
wherever one already appears — the Dashboard's per-Sensor panel rows, a Room's/Enclosure's own
Sensor rows, and the compact Enclosure card's condensed temperature/humidity pills. This is a
deliberate reversal of the Phase 2 "glance-only, no charts" dashboard scope recorded in
`web/main.py`'s docstring; that docstring gets updated alongside the implementation rather than left
to contradict this decision silently.

*(Superseded by ADR 0023: Sparkline's window, placement, aggregation, and interactivity were all
revised. This paragraph describes the original shape only.)*

**Consequences**: the aggregated-bucket query path (90d/180d/Year) is new query surface distinct
from View Data's day-bucketed "last value" rule (ADR 0021) — the two now diverge on purpose:
View Data's table only ever needs one value per day, Graphs' long-range chart needs a
min/avg/max per bucket instead. A future reader comparing the two shouldn't assume they share a
query layer for auto-collected data, even though they share the same Range picker options and the
same day-bucketing for Care Events/Animal Log.
