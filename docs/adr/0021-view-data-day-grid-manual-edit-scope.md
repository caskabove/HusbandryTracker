# View Data: day-aggregated grid, editable only for hand-entered rows

**Context**: Reviewing or correcting a Room's/Enclosure's full history (Readings, Care Events, Plug
Status, Plug Data Capture) had no single place to go, and a Smart Sensor or Plug can produce
hundreds of raw rows a day — too many to show or edit one-for-one.

**Decision**: View Data represents each tracked thing as one row (one per Sensor+metric; one per
Care Event kind, Feeding covering both whole-Enclosure and any Spot-feed; one Status row plus one
per Data Capture metric per Plug) and each calendar day (local time) as one column, with each cell
showing that day's *last* value — same "latest wins" precedent the Dashboard already uses for
same-day data. Only rows with one real hand-entered row behind them — a Manual Sensor's Reading, a
Care Event — are editable in the grid: typing into an empty cell creates a row for that date,
clearing one deletes it, and when a day already holds more than one same-kind row, an edit or clear
only ever touches the most recent one. Smart Sensor Readings, Plug Status, and Plug Data Capture
are shown read-only — editing an aggregate would silently rewrite history a device actually
reported. A Room's own View Data page never rolls up its child Enclosures' data, the same boundary
already drawn for Refresh (see CONTEXT.md: Refresh) — each Enclosure has its own View Data instead.

A metric only earns a row for a given Sensor if it's actually tracked (a Target Range is set) or it
has at least one logged Reading in its history — deliberately *not* the Dashboard pill's own
"temperature/humidity always, else only if tracked" rule (web/queries.py's `_latest_reading`). That
rule is harmless for a pill that just doesn't render when empty; here it would mean a permanently
empty row, every day, forever, for a water-chemistry-only Manual Sensor (confirmed against real
data — several of this collection's Saltwater Enclosure Sensors are named for one test-kit metric
each, e.g. "Ca", "Mg", "pH", and never report ambient temperature at all).

**Consequences**: Clearing or editing a day's cell when an earlier same-day row for that same field
still exists will "resurface" that earlier row as the new last value shown — accepted as consistent
with the app's existing same-day collapsing behavior rather than surfacing every same-day row
individually.

**Timezone correctness (found live, not assumed)**: `sensor_reading.recorded_at` is converted from
UTC before bucketing into a local calendar day, same as the Plug tables — confirmed against real
data that a Smart Sensor's auto-collected Readings (by far the largest source of rows in that
table) are true UTC with no backdating path, so bucketing by the raw string shifted most of a day's
Readings into the wrong local column (a reading timestamped `04:43 UTC` was invisible in "today"'s
column while the local calendar date was still yesterday). `care_event.occurred_at` is bucketed
with *no* conversion instead, because its dominant real path — the Enclosure page's own
Today/Yesterday/N-days-ago buttons — already computes and stores local wall-clock time directly
(`web/admin.py`'s `admin_create_care_event`); converting those from a false "UTC" assumption would
have broken the common case instead of fixing it. Either table's rule is wrong for the one input
shape it can't disambiguate from its dominant case (an explicitly backdated-with-a-custom-time
Manual Sensor Reading, or a Care Event logged with occurred_at genuinely left blank) — accepted
since both are rare and only off by a fixed UTC-offset amount, never a crash or data loss.
