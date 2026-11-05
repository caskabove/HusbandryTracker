# Species Profile Knowledge Base: move it into the app, make it editable, and cover aquatic/insects

**Status**: accepted

**Context**: The species care data backing the Species Profile picker (CONTEXT.md: Species Profile)
lived in two disconnected, uneditable places — `docs/reference/Reptile Care Parameters Knowledge
Base.md`, a hand-written markdown doc (Snakes and Lizards only, with citations), and
`SPECIES_PROFILES`/`SPECIES_PROFILE_GROUPS`, a hardcoded JS literal in `web/static/app.js` that the
browser read directly to pre-fill Enclosure/Sensor form fields. Neither had a write path: fixing a
number or adding a species meant editing a file and redeploying. Every aquatic and insect entry in
the picker (`freshwater`, `saltwater_reef`, `insect`, etc.) was a label-only placeholder with no
numbers behind it at all — CONTEXT.md's own Species Profile entry documented this as a known gap.

The ask: make the Knowledge Base editable from inside the running app — a page with directly
editable fields and a search bar — and extend it to cover 5 categories that had no reference data
at all: Saltwater Fish, Freshwater Fish, Saltwater Inverts, Freshwater Inverts, and Insects.

A `/grill-me` session worked through the forks before any code was written:

- **Storage: a new DB table per category, not a rewritten markdown file.** "Editable" needs a
  write path a markdown file doesn't have without building a parser/writer; the DB + Admin CRUD
  pattern already exists for everything else in this app (Room, Enclosure, Sensor, Plug, ...). The
  markdown doc is left untouched as a historical, uneditable snapshot.
- **Seven separate tables, not one wide table with a category column** — `snake_profile`,
  `lizard_profile`, `insect_profile`, `saltwater_fish_profile`, `freshwater_fish_profile`,
  `saltwater_invert_profile`, `freshwater_invert_profile` — matching this schema's existing
  convention of one typed table per entity kind (room/enclosure/animal/sensor/plug are all separate
  tables already) rather than a polymorphic shape. Water-chemistry columns (pH, salinity, GH/KH,
  alkalinity, calcium) genuinely don't apply to a Snake/Lizard row and vice versa, so a shared wide
  table would carry a dozen always-NULL columns per row either way.
- **The Setup/Add-Pet Wizard and Admin's Species Profile pickers now read live from these tables**,
  replacing `SPECIES_PROFILES`/`SPECIES_PROFILE_GROUPS` entirely — editing the Knowledge Base
  changes what every picker across the app suggests, and the aquatic/insect categories finally
  pre-fill something instead of being inert placeholders.
- **One page, inline-editable cells, not a separate edit-page-per-row.** All 7 tables render on one
  Admin page (`/admin/app/knowledge-base`); every field is a plain `<input>`/`<select>` editable in
  place, no navigating to a dedicated edit page the way `admin_sensor_edit.html` works for a Sensor.
- **Full CRUD — add and delete rows, not just edit a fixed seeded set.**
- **One global search box** filtering all 7 tables at once by common or scientific name, matching
  on either so "python" and "Python regius" both work.
- **The 5 new categories ship pre-seeded** with ~8 researched common species each, same rigor as the
  original Snakes/Lizards research, rather than starting empty.
- **"Insects" means pet insects** (mantids, beetles, roaches, stick insects kept as livestock in
  their own right) — not feeder insects bought to feed something else, which this app has no
  tracking concept for at all. This finally gives the old inert "Insect" Basic-type placeholder real
  numbers, reusing its exact key (`insect`) for backward compatibility.
- **This change gets an ADR and a CONTEXT.md entry**, matching how every other structurally
  significant feature in this app (the three Wizards, Active Plugins) has been documented.

**Decision**: `schemas/species_profile_kb.py` is the single source of truth for which columns each
of the 7 categories carries (`ProfileField`/`ProfileCategory` dataclasses, mirroring
`schemas/enclosure_types.py`'s shape) — adding a column there is the only change a new field needs;
`web/species_kb_queries.py` and `web/templates/admin_knowledge_base.html` are both driven generically
off this registry rather than hand-writing CRUD/markup per category.

`profile_key` is kept byte-for-byte identical to the retired `SPECIES_PROFILES` dict keys for every
Snake/Lizard row (`ball_python`, `corn_snake`, ...; `tools/migrate_2026_11_02_species_profile_kb.py`
needs no `animal` backfill as a result — an already-stored `animal.species_profile` value keeps
resolving to the same row). A handful of inert, non-numeric catch-alls that were never species data
to begin with (`tortoise`, `freshwater`, `freshwater_planted`, `saltwater_fish_only`,
`saltwater_mixed`, `saltwater_reef`) stay as a small hardcoded dict
(`GENERIC_PROFILE_OPTIONS`) rather than becoming Knowledge Base rows — they represent "no specific
species, general tank type" picks, a different concept from a species row, and were never editable
before either.

`web/species_kb_queries.py`'s `species_profile_js_context()` rebuilds the exact
`SPECIES_PROFILES`/`SPECIES_PROFILE_GROUPS` shape the retired literal had from live DB rows — same
`label`/`scientific`/`basking`/`cool`/`night`/`humidity`/`feeding` keys — specifically so every
consumer function already in `web/static/app.js` (`populateSpeciesProfileSelect`,
`onEnclosureSpeciesProfileChange`, `onSensorSpeciesProfileChange`, `_tempRangeForZone`, and friends)
keeps working completely unchanged. Only *where the data comes from* changed: a new partial,
`web/templates/_species_profile_data.html`, renders the two globals server-side from that context
dict, included on every page that already included one of those functions
(`setup_enclosure.html`, `setup_animals.html`, `setup_sensor.html`, `add_pet_enclosure.html`,
`add_pet_animals.html`, `add_pet_sensor.html`, `admin_app.html`), right before each page's own
`<script src="/static/app.js">` tag. The 4 aquatic categories and Insects have no basking/cool/night
gradient (one flat temperature range, not a zone-dependent one), so their JS entries repeat
`temp_min_f`/`temp_max_f` into `basking`/`cool`/`night` alike — this keeps `_tempRangeForZone()`
working for them without any changes to its own logic, and is a strict improvement over today
(previously: no numbers at all for any of them).

**Considered Options**:
- **One wide table with a category column** instead of 7 separate tables — rejected: breaks this
  schema's own established convention, and most rows would carry a dozen unused NULL columns.
- **Rewrite the JS prefill functions to read a new Python-shaped data structure directly** instead
  of reusing `SPECIES_PROFILES`'s exact shape — rejected: touches ~10 working functions
  (`populateSpeciesProfileSelect`, `onSensorSpeciesProfileChange`, `onGlobalSensorSpeciesProfileChange`,
  `prefillAnimalSpecies`, ...) for no behavioral gain; reshaping the DB rows into the *same* shape
  server-side keeps 100% of that code, and the risk, untouched.
- **A separate edit page per Knowledge Base row**, mirroring `admin_sensor_edit.html` — rejected in
  favor of inline-editable cells on one page, the explicit ask ("a page with editable fields").
- **Treat `profile_key` as globally unique across all 7 tables** (e.g. a `category:slug` prefix) —
  rejected: would silently orphan any already-stored `animal.species_profile` value using the old,
  unprefixed Snake/Lizard keys. Accepted the small residual cross-category collision risk instead,
  same as the pre-Knowledge-Base literal already implicitly accepted for 20+ keys.

**Consequences**: `db/schema.sql` gains 7 tables, pre-seeded via `INSERT OR IGNORE`
(`tools/migrate_2026_11_02_species_profile_kb.py` is the one-off migration for an already-deployed
install). `schemas/species_profile_kb.py` and `web/species_kb_queries.py` are new.
`web/admin.py` gains the Knowledge Base page route and its create/update/delete routes;
`web/templates/admin_knowledge_base.html` and `web/templates/_species_profile_data.html` are new;
`admin_app.html` gains one new card. `web/setup.py` and `web/add_pet.py`'s Enclosure/Animal/Sensor
step routes, and `web/admin.py`'s own `admin_app` route, now merge `species_profile_js_context()`
into their template context. `web/static/app.js` loses the ~70-line `SPECIES_PROFILES`/
`SPECIES_PROFILE_GROUPS` literal; every function that read those two globals is otherwise unchanged.
`docs/reference/Reptile Care Parameters Knowledge Base.md` is untouched. See CONTEXT.md: Knowledge
Base, Species Profile.
