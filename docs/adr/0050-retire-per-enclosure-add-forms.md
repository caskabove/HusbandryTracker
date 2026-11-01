# Retire the Enclosure page's own Add Animal/Add Sensor/Add Plug forms

**Status**: accepted

**Context**: ADR 0049 moved every *global* "+ Add" form onto App Admin, but explicitly left two
more capable forms where they were: the Enclosure's own Add Sensor (supports Manual Sensors with a
full Target Range at creation, a Species Profile picker, and a Warm/Cool/Ambient zone picker — the
global form was Smart-only) and the Enclosure's own Add Plug (functionally a strict subset of the
global form, just pre-scoped to one Enclosure). The Enclosure page also still had its own Add
Animal form, which had never had a global counterpart at all. Each Enclosure's own page was still
carrying three "create a new X" forms the rest of this cleanup had deliberately moved everywhere
else, working against the same "cleaner view" goal.

**Decision**: remove all three from the Enclosure's own page, and make App Admin's forms fully
cover what they did:
- **Add Animal**: new global form (`POST /admin/animals`), identical fields plus its own Enclosure
  picker. No capability lost — the per-Enclosure form had none the global one doesn't now.
- **Add Plug**: no new work needed — the existing global Add Plug form already lets you pick which
  Enclosure(s)/Room a new Plug belongs to, so the per-Enclosure form was already a pure, narrower
  duplicate.
- **Add Sensor**: the global form (`POST /admin/sensors`) gains a Tracking Mode select (Smart/
  Manual) and, when its Belongs-to is set to Enclosure, the same Species Profile picker, Zone
  picker, and per-Enclosure-Type Target Range/Volatility fields the retired form had — now driven
  by *which* Enclosure is picked rather than being fixed to one. `admin_app.html` renders one
  Target Range/Volatility block per Enclosure Type (basic/freshwater/saltwater/amphibian) up front;
  `app.js`'s `onGlobalSensorEnclosureChange` shows and *enables* just the one matching the picked
  Enclosure's own `data-enclosure-type`, leaving the other three hidden and disabled — disabled
  fields are excluded from form submission, so only one value per field name (e.g. `temp_min_f`,
  which several blocks share) is ever actually sent even though the name isn't unique in the DOM.
  Picking Room instead shows the same fixed temperature/humidity fields `admin_room.html`'s own Add
  Sensor form already has, since a Room has no Enclosure Type. The backend side needed no new
  validation — `create_sensor()` already looks up the target Enclosure's own type itself
  (`_get_enclosure_type`), so it was already generic regardless of which route called it; only the
  route's Form fields needed to grow to match.

One real capability is dropped, not carried over: the Enclosure page's Add Sensor form pre-filled
its Species Profile from `known_species_profile` — the single Species Profile every Animal already
in that Enclosure agreed on (RHA-94), so you didn't have to pick it again. That depended on "this
Enclosure" being a well-defined, already-open thing; Admin's form only gets an Enclosure *after*
you pick one from a dropdown, same moment Species Profile itself becomes pickable, so there's no
earlier point to pre-fill from. Reproducing it would mean a new bulk query (today's
`known_species_profile` is computed per-Enclosure, on demand, inside `get_enclosure()`) and more
client-side wiring, for a one-click convenience, not a missing capability — you can still pick the
Species Profile by hand. `get_enclosure()`'s now-unread `known_species_profile` computation was
removed rather than left dead.

**Considered Options**:
- **Reproduce the Species Profile pre-fill on the global form anyway** — rejected per above: real
  engineering cost (a new per-Enclosure-list bulk query, more JS) for a convenience that already
  has a one-click-by-hand fallback, not a capability gap like Manual Sensor creation was.
- **Leave the per-Enclosure Add Sensor/Add Plug backend routes in place, unreachable from any UI**
  — rejected: `admin_create_sensor` (`/enclosures/{id}/sensors`) and `admin_create_enclosure_plug`
  (`/enclosures/{id}/plugs`) would've been pure dead code the moment their only forms were removed,
  fully superseded by the global routes' own enclosure-scoping. Deleted along with the templates.
  (The Setup Wizard's own, separately-routed `/setup/enclosures/{id}/...` endpoints are untouched —
  a different router entirely, not affected by this.)

**Consequences**: an Enclosure's own page now only edits/removes what's already there — every
"create a new X" starts on Admin. Admin's Add Sensor form is noticeably more involved than it was
(it does the job two forms used to split between them), but it's one card, not two pages.
