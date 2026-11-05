# Backfill Wizard: seed starting Readings from each Sensor's own Target Range

**Status**: accepted

**Context**: A brand-new Manual Sensor — just registered through the Setup Wizard, the Add New Pet
Wizard, or App Admin's own Add Sensor form — has no history. Its Graphs page (ADR 0022) is a
single dot, or nothing at all, which doesn't demonstrate what the chart is for and gives a new user
nothing to look at. The ask is a wizard that seeds a Week or a Month of plausible Readings so the
graph is actually readable from day one.

This runs straight into a documented invariant: CONTEXT.md's own Reading entry says a Reading is
"always either auto-collected or hand-logged; never computed," and ADR 0025 explicitly considered
and *rejected* a similar-looking idea — an automatic, display-time "Interpolated Point" to smooth
over gaps — in favor of Curved Rendering alone, specifically because a fabricated point drawn next
to real ones is misleading.

**Decision**: add a third wizard, `/backfill/` (`web/backfill.py`), reached from a new "Backfill
Data" button on App Admin, next to "Add New Pet." Four steps: Time Frame (Week or Month) → Animal
or Enclosure (an Animal pick is just a lookup shortcut to its own Enclosure — Readings are an
Enclosure property, not an Animal one) → Sensors (every Manual Sensor on that Enclosure with a
Target Range set) → Done.

Three choices resolve the tension with Reading's "never computed" rule, each confirmed directly
with the user before implementation:

- **Data source: each Sensor's own Target Range**, not a re-derivation of the species knowledge
  base (`docs/reference/Reptile Care Parameters Knowledge Base.md`, encoded today only as
  client-side `SPECIES_PROFILES` data in `web/static/app.js`). A Target Range already *is* "what we
  expect as ideal conditions" for that specific Sensor+metric — whether it came from a Species
  Profile pick at creation time or was typed by hand — and it exists for every Enclosure Type,
  including Freshwater/Saltwater water-chemistry metrics that have no Species Profile data at all.
  Re-deriving from `SPECIES_PROFILES` directly would mean duplicating JS-only data into Python and
  would only ever cover a named Basic-type species.
- **Manual Sensors only.** A Manual Sensor's Readings are hand-logged by definition (see
  CONTEXT.md: Sensor), so a wizard-assisted bulk hand-log is the same mechanism, just at scale. A
  Smart Sensor's Reading history comes from a real device; mixing fabricated points into it would
  blur exactly the "auto-collected vs. hand-logged" line Reading's own definition draws.
- **No schema flag distinguishing a seeded Reading from a real one.** It's written through
  `view_data_queries.add_reading_entry()` — the same function View Data's own backdated Period-Slot
  entry already uses — so it's mechanically an ordinary hand-logged row from the moment it's
  created. The Done screen discloses plainly that it's a starting point, not a measurement, and it's
  edited or deleted exactly like any other View Data entry afterward. This is less machinery than
  tracking "is this one still a placeholder," and matches Period Slot's own precedent (CONTEXT.md:
  Period Slot) of not distinguishing an attested-coarse entry from an exact one once saved.

This makes the Backfill Wizard a deliberate, disclosed, user-initiated, Manual-only bulk front door
onto the *existing* hand-log path — not the automatic, silent, display-time computation ADR 0025
rejected. Reading's own CONTEXT.md entry is updated with a cross-reference explaining this
distinction rather than being weakened.

Generation detail, revised after first building it with a uniform-random value per point (the user
flagged that as not "ideal" enough, and specifically asked for a real Temperature/Humidity
day/night cycle): every seeded value now lands near the *middle* of the Target Range with only a
small jitter — "ideal," not a wide scatter — except Temperature and Humidity, which are
special-cased onto a real Morning/Afternoon/Night cycle (CONTEXT.md: Period Slot) every day,
regardless of either metric's own Volatility: Afternoon warmest/driest, Night coolest/most humid,
Morning in between, the two metrics' fractions deliberately mirrored opposite each other
(`web/backfill_queries.py`'s `_DIURNAL_FRACTIONS`) so they always move opposite directions, matching
how an enclosure actually behaves. Every other metric keeps cadence driven by the existing
Volatility concept (CONTEXT.md: Volatility) — `fast` fills every day at the Afternoon slot, `slow`
(water-chemistry, test-kit cadence) every 7th day — with its own value centered the same
near-the-middle way. Either way, any day that already has a Reading for that Sensor+metric is left
alone — checked via `view_data_queries.list_reading_entries()`'s existing local-date conversion —
which is what lets a Sensor with one real Reading keep it while the rest of the window fills in
around it.

**Considered Options**:
- **Re-derive from the species knowledge base** (`SPECIES_PROFILES`) instead of Target Range —
  rejected: requires duplicating JS-only data into Python, and covers nothing for an unlisted
  animal, a Tortoise/Insect placeholder, or any Freshwater/Saltwater water-chemistry metric, all of
  which Target Range already handles uniformly.
- **Allow Smart Sensors too**, since a just-paired one has the same "one dot" problem — rejected:
  a Smart Sensor's history is supposed to be exactly what the real device reported; seeding fake
  points into that same table blurs provenance in a way a Manual Sensor's already-hand-logged
  table doesn't.
- **Flag seeded rows** (an `is_backfilled` column) so Graphs/View Data could mark them visually or
  a future feature could bulk-clear/re-run a backfill — rejected for now: no schema change needed,
  and disclosure-plus-ordinary-editability already satisfies the actual requirement ("notify the
  user it's editable"); revisit if a real need for bulk re-seeding or visual distinction shows up.

**Consequences**: `web/backfill.py` and `web/backfill_queries.py` are new, along with four
`backfill_*.html` templates. `web/admin_queries.py` gains `list_animals()` (nothing previously
needed every Animal across the whole install at once). `web/wizard_shared.py` gains
`enclosures_with_room_names()` (lifted out of `web/add_pet.py`'s own private copy, same "shared
pure helpers" move ADR 0051 already made once) and `animals_with_enclosure_names()`. App Admin
(`admin_app.html`) gains one new card, next to "Add New Pet." No database schema changes. See
CONTEXT.md: Backfill Wizard, Reading, App Admin.
