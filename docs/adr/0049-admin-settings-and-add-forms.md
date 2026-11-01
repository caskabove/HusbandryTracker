# Move Settings, Tuya Cloud Credentials, and every global "Add" form onto App Admin

**Status**: accepted

**Context**: ADR 0048 introduced App Admin (`/admin/app`) as the entity-independent home for
cross-cutting app config, moving Plugins there first and explicitly deferring Settings and Tuya
Cloud Credentials as "later, separate work." Separately, "Rooms and Enclosures"
(`/admin/enclosures`) and "Plugs and Sensors" (`/admin`) are two of the most-visited pages in the
app, and each mixes two different jobs in one place: browsing/editing what already exists (the
Rooms/Enclosures tables; the Sensors/Plug Groups/Plugs tables), and creating something new (the
"+ Add Room"/"+ Add Enclosure"/"+ Add Sensor"/"+ Add Plug"/"+ Add Plug Group" forms). That made
both pages longer and busier than the "what's going on right now" job they're mostly used for.

**Decision**: finish ADR 0048's deferred move (Settings, Tuya Cloud Credentials) and additionally
move every *global* "+ Add" form onto App Admin: Add Room and Add Enclosure (from "Rooms and
Enclosures"), Add Sensor and Add Plug and Add Plug Group (from "Plugs and Sensors"). "Rooms and
Enclosures" and "Plugs and Sensors" keep their tables — listing, editing, deleting, commanding
(All On/All Off) — unchanged. App Admin's final card order: Plugins, Settings, Tuya Cloud
Credentials, Add Room, Add Enclosure, Add Sensor, Add Plug, Add Plug Group — a flat list of
admin-cards, no subheadings, matching the existing Plugins card's style.

Only the *global* Add Sensor and Add Plug forms move. Two more specific forms stay exactly where
they are, since they're not interchangeable with the global ones:
- The per-Enclosure/per-Room Add Sensor form (on `admin_enclosure.html`/`admin_room.html`)
  supports Manual Sensors and takes a full Target Range at creation — the global form is Smart
  (Govee BLE) only, since a Manual Sensor's Target Range depends on its parent's Enclosure Type,
  which isn't known generically on Admin.
- The per-Enclosure Add Plug form (on `admin_enclosure.html`) is scoped to that one already-open
  Enclosure.

Every Add form's success redirect is unchanged — Add Room/Add Enclosure still jump to the new
entity's own detail page, and Add Sensor/Add Plug/Add Plug Group still jump to "Plugs and Sensors"
where the new row now shows, confirming the action worked. Only the *error* redirects move, from
`/admin/` or `/admin/enclosures` to `/admin/app/`, since that's where the form the error belongs to
now lives. The Tuya-discovery JSON error (`/admin/plugs/discover-tuya`) and its credentials-missing
message are updated the same way, from `/admin#tuya-cloud-credentials` to
`/admin/app#tuya-cloud-credentials`.

Nav also drops the "Guide" link — `/guide` itself, and the two existing inline links to it (the
Tuya Cloud Credentials card's walkthrough link, and Help's "Looking for setup steps instead?"
line), are untouched; it's just no longer in the top-level nav bar.

**Considered Options**:
- **Move whole sections (table + Add form together)** — rejected: Sensors/Plugs/Plug Groups tables
  are what "Plugs and Sensors" is actually used for day to day (its name says so); moving them too
  would leave that page empty and need its own nav removal, well beyond what was asked.
- **Group App Admin's cards under subheadings** (e.g. "Rooms & Enclosures", "Plugs & Sensors")
  — rejected for now: adds new markup/CSS for a page that's still a flat, scannable length (8
  cards); revisit if more cards get added later.
- **Redirect every Add form back to App Admin on success** (instead of to the new item/list)
  — rejected: loses the "go see what you made" confirmation Add Room/Enclosure/Sensor/Plug/Plug
  Group already gave before this change.

**Consequences**: "Rooms and Enclosures" and "Plugs and Sensors" are shorter, purely
browse/edit/command pages. App Admin now has 8 cards. Any future global "Add" form (a new entity
kind, or a promoted per-entity form) should default to landing here rather than on the entity's own
list page.
