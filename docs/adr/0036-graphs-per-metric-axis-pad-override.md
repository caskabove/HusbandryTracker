# Graphs: let a metric override the flat Target Range axis pad/ticks

**Context**: ADR 0035 pads a Graphs axis at least 2 of the metric's own units past its Target
Range. That's sane for °F, pH, ppm, dKH — but Specific Gravity's values sit around 1.02–1.03, so a
flat 2-unit pad ran the axis from roughly -1 to 3, squashing the real 0.01-wide band and data down
to a flat line. Sparkline (ADR 0024) never had this problem — it pads by a percentage of the
on-screen range, not a flat unit count — but Graphs' own `buildGraphChart` does, and converting it
to a percentage too would've reopened ADR 0035's own `pH 6.5–7.5` case, which explicitly wanted a
flat 2 **pH** units of breathing room, not 8% of a half-point span. The two charts solve the same
problem differently on purpose; this fixes the one case neither approach actually covers.

**Decision — `TargetRangeMetric` gets an `axis_pad` override (schemas/enclosure_types.py), None by
default**: `None` means ADR 0035's flat 2-unit pad, unchanged for every existing metric (temperature,
humidity, UVI, pH, ammonia, nitrite, nitrate, alkalinity, calcium, magnesium). Specific Gravity sets
`axis_pad=0.002` — 2 of its own `step` (0.001) — so a 1.020–1.028 Target Range pads out to exactly
1.018–1.030, the same "2 steps of real-world resolution" shape ADR 0035's flat pad already was for
every other metric, just scaled to a metric whose whole working range is a fraction of a point
rather than tens of units.

**Decision — the same override also forces exact tick steps, instead of leaving it to Chart.js's
auto-picked "nice" numbers**: `graphs_queries.py`'s `_reading_line_row` carries `target_pad`/
`tick_step` (both None unless `axis_pad` is set) alongside `target_min`/`target_max`; `graphs.js`'s
`buildGraphChart` uses `row.target_pad` in place of the flat `TARGET_RANGE_AXIS_PAD` when present,
and sets `scales[axisId].ticks.stepSize` from `row.tick_step` — so Specific Gravity's axis reads
1.018, 1.019, 1.020, … 1.030 instead of whatever round-looking numbers Chart.js would otherwise
land on for a 0.012-wide range. No other metric's ticks change — the override only fires when
`axis_pad` is set.

**Consequences**: no schema change — `axis_pad` lives on the Python dataclass, not the database.
`graphs_queries.py`'s row dict gains two more line-row keys (`target_pad`, `tick_step`, both
None/None for every metric except Specific Gravity); `graphs.js`'s per-axis extent tracking gains
`pad`/`tickStep` fields that default to the existing flat behavior when a row doesn't set them. If
another metric later turns out to need the same treatment (its own `axis_pad`), it's a one-line
addition to its `TargetRangeMetric` entry, not another code path.
