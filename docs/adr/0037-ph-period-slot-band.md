# pH: show it as a daily Morning/Afternoon/Night band, not a raw/statistical line

**Context**: pH genuinely swings over the course of a day (photosynthesis draws CO₂ down during
the day, respiration pushes it back up overnight), but most keepers test it once or twice a day at
most — never continuously. Every other metric's Graphs/Sparkline band (ADR 0022, ADR 0024) exists
to tame a Smart Sensor's *data volume* (hourly/daily min-avg-max buckets over thousands of raw
rows); that's the wrong lens for pH, where the swing itself, not sensor noise, is the thing worth
seeing, and a Manual Sensor's sparse points never triggered banding at all before now. Plotting
pH's Morning/Afternoon/Night readings as a raw zigzag line buries that pattern; plotting it as a
band shaped by the day's own three checks surfaces it directly.

**Decision — a new `TargetRangeMetric.period_slot_band` flag, True only for pH**: every other
metric is unaffected — Temperature/Humidity/Specific Gravity etc. keep today's raw-at-Week/Month,
statistically-bucketed-at-90-Days+ split (ADR 0022). pH instead always renders as one point per
local calendar day, every Range (Week through Year), Manual or Smart Sensor alike — there's no
row-volume reason to ever show it raw, and the day/night framing is the better view even at Week
range.

**Decision — a day's point is built from Period Slot identity, not sorted statistics**:
`web/queries.py`'s new `period_slot_daily_series()` groups a Sensor's readings by local calendar
day, classifies each by `PERIOD_SLOT_HOUR_RANGES` (the same Morning 0-11/Afternoon 12-17/Night
18-23 local-hour windows Graphs' Care Event marker snapping already used — now centralized here
instead of living only in graphs_queries.py), and averages whatever falls in each slot's window
that day — collapsing a Manual Sensor's single exact-anchor-hour reading to itself, same as always
averaging a Smart Sensor's many readings in that window down to one. The result is reused, as-is,
as the existing `[epoch_ms, lo, avg, hi]` band shape — Morning is the band's bottom, Night is its
top, Afternoon is the center line — but it's an *identity* mapping, not `min()`/`max()`: on an
unusual day where Night actually comes back lower than Morning, the band visually inverts for that
one day rather than silently re-sorting itself into a normal-looking band. That inversion is itself
useful information.

**Decision — a day with fewer than 3 slots logged still gets a point, never skipped, never
invented**: the premise is that most keepers don't test 3x/day, so requiring all three would gut
the feature. Afternoon is the center value when logged; if Afternoon itself is missing, center
falls back to the average of whatever slot(s) are present. Morning/Night only pull the band away
from center when they're actually logged — a day with just one reading renders as a single flat
point (top = center = bottom), not a gap. A day with nothing logged at all is the only thing
skipped.

**Decision — never smoothed**: unlike a Smart Sensor's existing band (3-day trailing average,
`_sparkline_smoothed`), pH's day points are always the literal values for that exact day. Smoothing
exists elsewhere to tame genuine sensor noise; averaging across days here would blur or erase the
exact Morning→Afternoon→Night pattern this whole feature exists to show.

**Decision — the Target Range band (ADR 0035) still shows underneath, layered**: a pH Sensor's
accepted-range shading isn't replaced by this — it draws first/behind (unchanged ordering), the
new Morning–Night spread band draws on top of it in the row's own color, and the Afternoon line
draws on top of everything, matching the existing precedent that two Target-Range-adjacent shaded
regions can coexist (Sparkline already shows both an accepted-range band and a data band at once).
A pH Sensor with no Target Range configured just skips that bottom layer, as before.

**Decision — the tooltip names each slot explicitly, everywhere this renders**: Graphs' band
datasets normally all share one label (`row.label`); when `row.slot_labels` is set (`("Morning",
"Afternoon", "Night")` for pH, `None` for every other band row), each of the three gets its own
suffixed label instead, so hovering near the band's edges reads "— Morning"/"— Night" rather than
a bare repeated value. Sparkline's combined-tooltip wording (`"avg X (range Y–Z)"`) gets an
equivalent `"Afternoon X (Morning Y – Night Z)"` form, gated on a new `data-slot-band="1"` canvas
attribute set only for a metric with `period_slot_band` — every other metric's Sparkline tooltip
wording is unchanged.

**Decision — applies to Sparkline too, not just the full Graphs page**: both call the same
`period_slot_daily_series()`; Sparkline's `_sparkline_points` branches to it before its existing
Manual-raw/Smart-bucketed split whenever `metric.period_slot_band` is set, so the Dashboard's
compact pH preview shows the identical day/night shape as the full chart, not a simplified line.

**Consequences**: no schema change. `schemas/enclosure_types.py` gains one boolean field (default
`False`, so every existing metric is untouched) plus pH's existing entry setting it. The Period
Slot hour-range table used for display-snap classification now lives once in `web/queries.py`
(`PERIOD_SLOT_HOUR_RANGES`/`period_slot_for_hour`) instead of only inside `graphs_queries.py`'s
Care-Event-only `_PERIOD_SLOT_ANCHORS`, which now sources its two boundary hours from there.
`web/graphs_queries.py`'s row dict gains `slot_labels` (`None` for every row except pH's);
`web/static/graphs.js` gains per-dataset label overrides in the band branch and a `slotBand` flag
in Sparkline's tooltip callback, both no-ops unless a row/canvas actually sets them. If another
metric later turns out to need the same day/night framing, it's a one-line `period_slot_band=True`
on its own `TargetRangeMetric` entry, not a new code path.
