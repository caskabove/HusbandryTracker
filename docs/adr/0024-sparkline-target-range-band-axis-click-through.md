# Sparkline becomes a compact Graphs preview: Target Range band, axis, smoothing, click-through

**Context**: ADR 0023 redefined Sparkline as a month-long, daily-banded chart with a hover tooltip,
but kept it deliberately axis-less and explicitly "not a substitute for Graphs." A request to
improve readability asked for three more changes at once: shade the Sensor's Target Range as a
background band so a keeper can see where a reading sits relative to the acceptable zone, add a
minimal time/value axis, smooth the line so day-to-day noise doesn't obscure a real trend, and make
the chart clickable through to its matching Graphs chart. Taken together, these move Sparkline from
"a simplified glance indicator" to "a smaller, smoothed, read-only preview of the same chart Graphs
draws in full" — CONTEXT.md's own definition is updated to say so, replacing ADR 0023's
"glance-level... not a substitute for Graphs" framing.

**Decision — Target Range band**: when a Sensor's Target Range is configured for a metric,
Sparkline shades it as a pale background band (reusing the app's existing green status color)
behind the metric's own data — the existing data-variability band for a Smart Sensor, or a plain
line for a Manual Sensor. A metric with no Target Range set (only possible for a Smart Sensor —
a Manual Sensor is always required to have one on at least one metric) shows no shading at all,
chart otherwise unchanged. This gives a Manual Sensor's Sparkline its first-ever band of any kind.

**Decision — smoothing**: a Smart Sensor's daily min/avg/max buckets (ADR 0023) are passed through
a 3-day trailing average across all three series before drawing. A Manual Sensor's raw, sparse
points are left untouched — averaging a handful of deliberately hand-logged entries would
misrepresent what was actually recorded, the same reasoning ADR 0023 already used to keep Manual
Sensors out of the aggregation path entirely.

**Decision — axis**: a minimal linear x-axis (2-3 date labels) and y-axis (2-3 value labels), no
gridlines — kept sparse on purpose so the chart still reads as a compact preview rather than a
second full chart. The y-axis anchors to the Target Range's own min/max when one is set, tying the
axis directly to the shaded band; it falls back to the data's own min/max otherwise. The scale
always expands to include an actual out-of-range reading rather than clipping it off — hiding
exactly the thing the Out of Target Range Alert Condition exists to catch would defeat the point of
adding the band at all.

**Decision — click-through**: the whole chart is a real link to the full Graphs chart for that
exact Sensor+metric row, reusing graphs_queries.py's existing row key (e.g.
`reading-23-specific_gravity`) as an anchor, on whichever Enclosure or Room page actually owns that
Sensor. A Fallback Sensor's Sparkline — shown on an Enclosure panel but owned by a Room (see
CONTEXT.md: Fallback Sensor) — links to the Room's own Graphs page, never the Enclosure's, which
has no row for a Sensor it doesn't own. Consistent with the Room-never-rolled-into-Enclosure
boundary Refresh and View Data already draw.

**Decision — layout**: per-metric charts (already one per metric, from ADR 0023) now stack
vertically rather than side by side in every one of Sparkline's three locations, including the Room
header's condensed ambient-pill summary, since each chart is noticeably taller once it carries an
axis.

**Consequences**: Supersedes ADR 0023's axis-less, non-clickable framing specifically; ADR 0023's
window, placement, Manual/Smart data split, and tooltip decisions stand unchanged. The Room header's
ambient-pill summary grows taller again.
