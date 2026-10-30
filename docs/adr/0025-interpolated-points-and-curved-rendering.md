# Interpolated Points for sparse Manual Sensor data, plus curved line rendering

**Update (2026-10-17)**: the Interpolated Point decision below was implemented, then reverted after
review — it didn't read as the "smooth line" the original complaint wanted, just a dashed-and-capped
version of the same jumpy real points. The Volatility, Period Slot, and Curved Rendering decisions
below stand; `fill_fast_gaps()`, its Graphs/Sparkline call sites, the dashed-segment/tooltip
rendering, and the Interpolation Gap Cap app setting have all been removed. `sensor.volatility_*`
stays on the schema (and in the Admin UI) as a dormant per-metric classification for whatever
smoothing approach comes next, rather than being ripped out along with the feature it first served.
The jumpy-line complaint that opened this ADR is still open.

**Context**: Graphs/Sparkline charts of Manual Sensor Readings looked jumpy and hard to read.
Two distinct causes were tangled together: (1) inconsistent hand-entry timing — a metric tested in
the afternoon one day and the morning the next leaves an irregular, visually spiky gap even though
the underlying value swings smoothly; (2) plain line-segment rendering looks jagged even when points
are complete and evenly spaced. A request to "smooth" the data conflated these; this ADR separates
them into two independent mechanisms.

**Decision — Interpolated Point (see CONTEXT.md)**: for a `Fast`-Volatility Manual Sensor metric
(temperature, pH, KH — see CONTEXT.md: Volatility) Graphs and Sparkline now fill a gap between two
real Readings with a linearly-interpolated, render-time-only value, snapped to the wall-clock hour,
capped at a 48-hour gap (the Interpolation Gap Cap — beyond that, show a visible break rather than
days of fabricated-looking certainty), and visually marked as such (dashed segment, "Interpolated"
tooltip). It is strictly interpolation, never forecasting — nothing is ever fabricated before the
first or after the most recent real Reading. `Slow`-Volatility metrics (Ca, Mg, salinity) and Animal
Log never get this — their real points are sparse on purpose (weekly testing is the whole point;
and weight/length has no meaningful "value between two weigh-ins") and are only Curved-Rendered.

**Decision — Volatility is a new per-Manual-Sensor-metric attribute**, not inferred from actual entry
cadence and not hard-coded purely by metric name: it defaults by metric name at Device Registration
(temp/pH/KH → Fast, Ca/Mg/salinity/ammonia/nitrite/nitrate → Slow) but is overridable per Sensor,
matching this app's existing Purpose pattern (suggested, not fixed). Rejected inferring it from
observed data cadence — implicit behavior that changes based on a user's own entry habits was judged
more surprising than an explicit, defaulted setting.

**Decision — scope is Manual Sensor only, Week/Month range only**: a Smart Sensor already reports
continuously and never needs this, even across a BLE-outage gap (that's a device-health problem, not
a charting problem). Interpolation is only offered at Week/Month range, matching ADR 0022's existing
raw-vs-aggregated boundary — at 90 Days/180 Days/Year, Manual Sensor Readings keep plotting as real
points only, same as today, since hourly interpolation across a full year (~8,760 points/series)
would both be meaningless at that zoom level and break the "Manual Sensor data is never high-volume"
assumption ADR 0022 relies on to skip aggregation for it entirely.

**Decision — Sparkline reuses Graphs' hourly resolution, not a coarser one**: this is the one
genuinely non-obvious call. Smart Sensor Sparklines already bucket daily rather than hourly
specifically because Sparkline renders on every Dashboard load and is only a few dozen pixels tall
(ADR 0023's own stated reasoning). A `Fast` Manual Sensor's Interpolated Point reuses the same
hourly-resolution algorithm as the full Graphs page instead of a coarser Sparkline-specific one —
chosen deliberately for one shared algorithm and one mental model (same resolution everywhere a
Fast metric appears) over matching Sparkline's own cost-driven daily-bucket precedent. A future
reader should not assume this was an oversight; it was raised and decided knowingly, accepting the
extra per-load computation.

**Decision — Curved Rendering is separate and unconditional**: a pure Chart.js line-tension change
with no data-level effect, applied to every Graphs numeric series regardless of Volatility, Tracking
Mode, or whether a gap existed. Deliberately kept independent of Interpolated Point so "the line
looks smooth" and "the data has synthetic points" are never the same claim. Not applied to Sparkline,
which already has its own smoothing (Smart Sensor's existing 3-day trailing average; Manual Sensor's
existing raw/Interpolated-Point line) and is meant to stay visually minimal.

**Decision — Care Event Period Slot (see CONTEXT.md)**: unrelated to Interpolated Point, bundled into
the same body of work because it came from the same "charts are hard to read" complaint. A Care
Event's marker snaps to a Morning/Afternoon/Night slot at Week/Month range instead of its exact
logged minute, reducing clutter from a precision that doesn't matter for a hand-logged feeding or
cleaning. Scoped to Care Event only — Plug Status (exact and automatic) and Animal Log Condition
(already rare) keep exact time.

**Consequences**: reopens ADR 0023/0024's "a Manual Sensor's sparse, hand-logged points are never
averaged [for Sparkline]" framing — that rule now holds only for `Slow`-Volatility metrics; a `Fast`
one gets Interpolated Point on Sparkline too. ADR 0022's raw/aggregate split, Overlay, and vendored
Chart.js decisions stand unchanged. Introduces one new app-wide Admin setting, the Interpolation Gap
Cap (default 48 hours), following the existing Alert Debounce/Refresh Timeout pattern.
