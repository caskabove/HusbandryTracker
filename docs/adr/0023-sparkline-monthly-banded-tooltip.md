# Sparkline: month-long daily bands under the as-of line, with a tooltip

**Context**: ADR 0022 introduced Sparkline as a 24-hour, axis-less raw-point line sitting beside a
Reading pill — purely a glance indicator, no interaction, no aggregation. A request to add a small
chart under the Admin Enclosure page's Sensors card "as of" line, covering a month, turned out not
to fit as a second element alongside the existing Sparkline: it's the same per-metric, under-a-pill
trend indicator, just with a different window and position. Rather than run two overlapping concepts,
this redefines Sparkline itself.

**Decision**: Sparkline's window changes from 24 hours to one month, and its placement moves from
beside the pill to underneath the shared "as of" line, in all three of its existing locations —
Dashboard panels, the Admin Enclosure/Room pages' Sensors tables, and the Room header's condensed
ambient-pill summary (which previously had no timestamp at all, and gains an "as of" line of its own
for this to sit under). A Smart Sensor's Sparkline now aggregates into daily min/avg/max buckets (a
shaded band plus an average line) instead of plotting raw points — reusing the same raw/aggregated
split Graphs already draws between Smart and Manual Sensors (ADR 0022), rather than inventing a
parallel one. A Manual Sensor's Sparkline stays raw, since at most one Reading a day makes bucketing
a no-op. It gains one piece of interactivity it didn't have before — a hover tooltip showing a
bucket's date and min/avg/max — but stays otherwise axis-less, legend-less, and non-clickable. One
chart is still drawn per metric, unchanged; a multi-metric Sensor (a Govee Temp+Humidity pair) gets
two Sparklines, not one combined Overlay-style chart.

**Why**: A Sparkline, unlike a Graphs chart, renders repeatedly on every single Dashboard load rather
than once per on-demand page visit — so the row-volume concern ADR 0022 raised for Graphs' 90+ day
ranges bites much sooner here, at a single month, for a chart that's only ever drawn at a few dozen
pixels tall. Bucketing bounds that cost regardless of how fast a Smart Sensor polls. The band and
tooltip are a deliberate step up in detail from the original "plainest possible" sparkline, accepted
because a month of data with no way to read a specific day's value was judged more confusing than
useful. The term "Sparkline" is kept despite drifting well past its textbook "tiny word-sized glyph"
meaning — this project already defines it by its own CONTEXT.md entry, not the dictionary one, and
renaming would touch every existing reference for no functional benefit.

**Consequences**: Supersedes ADR 0022's "Decision — sparkline" paragraph for window, placement,
aggregation, and interactivity; ADR 0022's vendored-Chart.js, raw/aggregated granularity split, and
Overlay decisions stand unchanged. The Room header's ambient-pill summary — previously a single
condensed line with no timestamp — is now noticeably taller.
