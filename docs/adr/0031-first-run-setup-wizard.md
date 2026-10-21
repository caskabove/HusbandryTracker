# First-run Setup Wizard: zero-data trigger, Manual-only scope

**Status**: accepted

A new install landed on an empty dashboard with no guidance toward Admin's various create-forms
(Room, Enclosure, Animal, Sensor, Plug), each shaped by multiple interlocking rules — Enclosure
Type gating which Target Range metrics apply (ADR 0011), Manual Sensor's mandatory Target Range
(ADR 0003), Room-XOR-Enclosure(s) parentage for Sensor and Plug (ADR 0004, ADR 0006), Bioactive
gating Plant. A guided Setup Wizard (see `CONTEXT.md`) walks a brand-new install through Room →
Enclosure → Animal/Plant → Sensor → Plug in a fixed order, reusing the existing Admin create logic
rather than new schema.

**Trigger**: the wizard launches automatically only when the database has zero Room rows and zero
Enclosure rows — no new `setup_complete`-style flag on `app_setting`. Rejected a persistent flag as
an unnecessary new persistent concept purely for onboarding; the zero-data check needs no
migration and is self-correcting — an upgrade from a pre-wizard install with existing data never
sees it, a truly empty install always does. Accepted trade-off: a user who deliberately deletes
every Room and Enclosure later will see the wizard again rather than it staying "dismissed"
forever — judged a harmless, rare edge case against the cost of a new column that exists purely to
remember a one-time event.

**Scope, this version**:
- Room stays optional, matching its existing definition — the wizard offers a skip rather than
  forcing a Room into existence for a single-tank setup.
- Sensor and Plug are Manual-only: no Tracking Mode choice, no Discover Devices button (ADR 0029,
  ADR 0030). A Smart device is registered afterward from the Enclosure's own Admin page, the same
  place Device Registration already lives.
- Plug Group is out of scope entirely. Every Plug Group Template (ADR 0017) is built from
  Smart/Tuya relay outlets; there's no all-manual equivalent in the model today, and inventing a
  wizard-only one would diverge from the real Plug Group concept rather than simplify it.
- Where the Enclosure's Room already has its own Sensor, the wizard offers using it as the
  Enclosure's Fallback Sensor as the easy alternative to registering a redundant Enclosure-owned
  Manual Sensor.
- Plant is only offered when Bioactive is checked on the Enclosure, matching Plant's existing hard
  requirement.
- Animal, Plant, and Sensor entry are all skippable with zero rows; each supports "add another" for
  a pair/colony or a multi-point gradient sensor setup.
- After one Enclosure is fully set up, the wizard offers adding another Enclosure (same Room or a
  new one) before finishing, covering a multi-tank first install in one pass.
- An always-visible "skip for now" exit is available on every screen, dropping straight to the
  dashboard and leaving whatever was already saved.

Two alternatives rejected:
- **Forcing a Room to always exist** — rejected; contradicts Room's existing optional-parent
  definition for no real benefit.
- **Letting the wizard register Smart devices** (reusing the Discover Devices flow) — deferred, not
  rejected outright. This version intentionally ships Manual-only to keep the first-run flow short;
  a Smart-device wizard path can layer on later without changing this scope's trigger or step order.

**Consequences**: no schema change. The wizard's routes/templates reuse the existing
`web/admin_queries.py` create functions (`create_room`, `create_enclosure`, `create_room_sensor`,
and the Sensor/Plug/Animal/Plant creation functions) rather than duplicating validation — it is a
different front door onto the same writes Admin already performs, with friendlier copy and a fixed
order, not a parallel implementation.
