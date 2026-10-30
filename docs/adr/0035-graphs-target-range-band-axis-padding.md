# Graphs: shade the Target Range on every line chart, padded at least 2 units past it

**Context**: Sparkline already shades a Sensor metric's Target Range as a band behind its data and
anchors its y-scale to it (ADR 0024) — but the full Graphs page's own per-row and Overlay charts
(`graphs.js`'s `buildGraphChart`) never carried any Target Range information at all: `view_data_queries.py`'s row builder (and its `graphs_queries.py` counterpart, `_reading_line_row`) never
read `sensor[metric.min_column]`/`max_column`, so there was nothing to shade and the y-axis was
left to Chart.js's own auto-scale. A user looking at the bigger Graphs chart — not just the
Dashboard's compact Sparkline preview — had no visual sense of what counted as "in range" at all.

**Decision — attach target_min/target_max to every reading line row, reuse Sparkline's band
technique**: `graphs_queries.py`'s `_reading_line_row` now reads the same Target Range columns
Sparkline's own row-builder does, °F-converting them the same way its own series already is, and
carries them on the row dict as `target_min`/`target_max` (None/None when unset — an Animal Metric
row has no Target Range concept and never gets these keys at all, same as a marker row). `graphs.js`
shades the band with the classic invisible-min/filled-max dataset pair, drawn *before* the row's own
data dataset(s) so the real line renders on top — same ordering Sparkline's `renderSparklineChart`
already uses, for the same reason (a `fill: "-1"` dataset must point at its own sibling, not get
reordered in front of some other dataset's fill chain). Unlike Sparkline, the band's fill color is
the row's own series color (from `GRAPH_PALETTE`), not a fixed green — Overlay can combine several
Sensors' metrics sharing one axis, each with its own Target Range, and the band needs to read as
"this row's own accepted range," distinguishable the same way its line already is, not a single
undifferentiated green haze.

**Decision — the axis is padded at least 2 of the metric's own units past the Target Range, never
clipped tighter than the real data**: `scales[axisId].min/max` is only ever set explicitly when at
least one row on that axis has a Target Range (an axis with none keeps today's plain auto-scale,
unchanged). When one does, the axis spans `min(dataMin, targetMin − 2)` to `max(dataMax, targetMax +
2)` — a flat 2-unit floor on the padding, not a percentage, so a tight range (e.g. pH 6.5–7.5) gets
real breathing room around the shaded band instead of hugging its edges; but real data is still
never clipped off-chart to keep that padding exact, same "expand to data, never clip it" rule
Sparkline's own y-scale follows (ADR 0024) — an out-of-range Reading (the one thing the Out of
Target Range Alert Condition exists to catch) stays visible regardless of how far outside the band
it lands. A row with a Target Range but zero Readings yet (freshly configured, nothing logged) falls
back to just the padded Target Range itself, rather than mixing in an undefined data extent.

**Decision — Overlay reuses the exact same per-axis logic, not a special case**: when two rows with
different Target Ranges share one axis (two Sensors both tracking temperature, say), the axis pads
around the *union* of both ranges (`min` of their mins minus 2, `max` of their maxes plus 2) while
each row still draws its own distinct, correctly-colored band — there is no ambiguity to special-case
around, since the bands themselves (not just the axis extent) are what actually show each row's own
range.

**Consequences**: no schema change — this only reads columns that already exist and were already
being read for the identical purpose on Sparkline. `graphs_queries.py`'s row dict gains two keys for
line rows; `graphs.js`'s `buildGraphChart` gains a per-axis extent pass and a short loop applying
`min`/`max` only to axes that earned it. The 2-unit pad is a flat constant
(`TARGET_RANGE_AXIS_PAD`), not configurable per metric — if a specific metric's scale turns out to
need a different flat amount later, that's a follow-up, not implied here.
