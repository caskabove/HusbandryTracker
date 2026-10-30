# Sparkline's window shrinks from a month to a week

**Context**: ADR 0023 set Sparkline's window at one month, later carried forward unchanged by
ADR 0024. In practice a month of daily buckets, even after the 3-day trailing average, reads as
too flat/compressed at Sparkline's few-dozen-pixels-tall size to show the recent trend a keeper
actually glances at it for — a request asked for a tighter, more immediately readable window.

**Decision — window**: Sparkline's window changes from one month to one week (`_SPARKLINE_DAYS`
in `web/queries.py`, `_sparkline`). Nothing else about Sparkline's data changes — the daily
min/avg/max bucketing and 3-day trailing average for a Smart Sensor, the raw unsmoothed points for
a Manual Sensor, the Target Range band, and the click-through to Graphs (ADR 0023, ADR 0024) all
carry forward unchanged, just over fewer buckets. Every static "- last 30 days" hover title on a
Sparkline canvas (Dashboard, Admin Enclosure/Room, Room header) is updated to "- last 7 days" to
match.

**Decision — x-axis labels**: the x-axis no longer shows Chart.js's own auto-picked "nice" tick
values (up to 3 of them); it shows exactly two labels, the window's start and end date (one if a
Sensor has only a single point), forced via a Chart.js `afterBuildTicks` hook
(`web/static/graphs.js`, `initSparklines`) rather than `ticks.maxTicksLimit`. At a one-week window
there's little room for more, and a plain start/end pair is more legible than whatever dates
Chart.js happened to round to.

**Why**: A month-long trend, smoothed, is the wrong grain for a glance-level preview meant to sit
under a live Reading pill — a week keeps enough history to show direction without flattening it
past usefulness. The full month-or-longer view is still available on Graphs, which Sparkline links
to.

**Consequences**: Supersedes ADR 0023's "one month" window decision and ADR 0024's `maxTicksLimit`
x-axis tick approach; every other part of ADR 0023 and ADR 0024 stands unchanged. A Smart Sensor's
Sparkline now smooths over at most 7 daily buckets instead of 30, so the 3-day trailing average
covers a larger fraction of the visible window than before — still judged acceptable, since the
smoothing's purpose (damping day-to-day noise) applies the same regardless of window length.
