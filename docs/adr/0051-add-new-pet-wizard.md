# Add New Pet Wizard: a second, always-available front door with existing-entity pickers

**Status**: accepted

**Context**: The Setup Wizard (ADR 0031) only ever triggers once, on a database with zero Rooms
and zero Enclosures — by design, since it exists to get a brand-new install off an empty
dashboard. It never comes back once that's no longer true, so an established install getting one
more animal is back to App Admin's stack of separate Add Room / Add Enclosure / Add Animal / Add
Sensor / Add Plug forms, each its own `<details>` card, with no guidance connecting them into one
pass the way the Setup Wizard does. That's the exact case a new pet needs: a Room (maybe already
there), an Enclosure (maybe already there, maybe brand new), an Animal, and usually a Sensor and a
Plug, in that order, all for one animal.

**Decision**: add a second wizard, `/add-pet/` (`web/add_pet.py`), reached from a new "Add New
Pet" button at the top of App Admin. It reuses the Setup Wizard's step order and the same
`web/admin_queries.py` writes — a third front door onto the same create functions, not a parallel
implementation, same as ADR 0031 already established for the Setup Wizard's relationship to
ordinary Admin forms. Shared pure helpers (Target Range parsing, the Species Profile query-param
carry-through, Purpose suggestions) move out of `web/setup.py` into `web/wizard_shared.py` so both
wizards call the same code instead of two copies drifting apart.

Two differences from the Setup Wizard, both because this one runs against an install that
presumably already has data:
- **No zero-data gate.** It's reachable any time, as many times as needed, rather than
  auto-triggering once.
- **Room and Enclosure each offer "use an existing one"** alongside "create a new one" — an
  established install usually already has the Room (and often the Enclosure, e.g. a quarantine
  tank set up ahead of time) the new pet is going into. Picking an existing Enclosure skips
  straight to the Animal step; picking an existing Room carries its id into a fresh Enclosure the
  same way the Setup Wizard already carries one forward for a second tank.

Two scope cuts from the Setup Wizard, both because they're not about the new pet specifically:
- **No Room-level Sensor/Plug step.** The Setup Wizard's Room step offers a room-wide
  thermometer/light; that's a property of the Room, not of the animal moving into it, so it's left
  to App Admin's own Add Sensor/Add Plug forms (or a future Room-focused wizard) instead of
  growing this one's scope.
- **"Done" offers Admin and the Dashboard**, not "set up a different Room" — this wizard isn't
  trying to walk a whole collection into existence in one sitting, just get one animal fully
  set up.

**Considered Options**:
- **Extend the Setup Wizard itself to also run post-first-run** — rejected: its zero-data trigger,
  Step-N-of-5 headings, and "Welcome! Let's get set up" framing are all first-run-specific, and its
  routes/templates have no existing-entity picker at all; bolting both modes onto one router would
  mean threading a mode flag through every one of its ~15 routes and redirects for a UI that reads
  differently in each mode anyway.
- **An inline, non-wizard shortcut on App Admin itself** (e.g. one big combined form) — rejected:
  Room, Enclosure, Animal, Sensor, and Plug each have their own interlocking validation (Enclosure
  Type gating Target Range metrics, Manual Sensor's mandatory Target Range, Bioactive gating
  Plant); one page trying to hold all of them collapses into the same complexity App Admin already
  has, just relabeled, without the step-by-step guidance that's the actual point of a wizard.

**Consequences**: `web/wizard_shared.py` is new; `web/setup.py` imports from it instead of
defining its own copies (no behavior change there — confirmed by re-running the Setup Wizard's
existing flow end to end). `web/add_pet.py` and six `add_pet_*.html` templates are new. App Admin
(`admin_app.html`) gains one new card, above Plugins. See CONTEXT.md: Add New Pet Wizard.
