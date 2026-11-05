# Move Add Room/Enclosure back to Rooms and Enclosures, Add Sensor/Plug back to Plugs and Sensors

**Status**: accepted

**Context**: ADR 0049 moved every global "+ Add" form onto App Admin (`/admin/app`), leaving
"Rooms and Enclosures" (`/admin/enclosures`) and "Plugs and Sensors" (`/admin`) as pure browse/
edit/command pages. In practice, that put each Add form a full page navigation away from the
table it adds a row to and the table that confirms the add worked — adding a Room meant leaving
"Rooms and Enclosures" for App Admin, filling out the form, and bouncing back to see it land.
App Admin had also grown into a mixed bag of truly cross-cutting config (Plugins, Settings, Tuya
Cloud Credentials) sitting alongside entity-creation forms that had nothing to do with app-wide
config, just a shared page.

**Decision**: move Add Room and Add Enclosure back onto "Rooms and Enclosures", and Add Sensor and
Add Plug back onto "Plugs and Sensors" — each form now sits directly below the table it creates
rows for, same `<details>`-collapsed-by-default presentation ADR 0049 used on App Admin. Add
Animal and Add Plug Group stay on App Admin: neither has one obvious listing page to sit next to
(Add Animal's Enclosure picker spans every Enclosure; a Plug Group's members aren't listed on
either "Rooms and Enclosures" or "Plugs and Sensors" specifically). App Admin keeps Add New Pet,
Backfill Data, Plugins, Settings, Tuya Cloud Credentials, Add Animal, and Add Plug Group.

ADR 0050's merge of the per-Enclosure/per-Room Add Sensor and Add Plug forms into one global form
each is untouched — Add Sensor still covers Smart and Manual, for either an Enclosure or a Room,
from one form; Add Plug still covers every Belongs-to/Controller Kind combination from one form.
Only the page each global form lives on changed.

Error redirects for Add Room, Add Enclosure, Add Sensor, and Add Plug move back with their forms:
Add Enclosure's now points to `/admin/enclosures`, and Add Sensor's/Add Plug's now point to
`/admin/`, undoing ADR 0049's move of those to `/admin/app/`. Success redirects were never touched
by ADR 0049 and stay as they were — Add Room/Add Enclosure to the new entity's own detail page,
Add Sensor/Add Plug to "Plugs and Sensors" where the new row now shows. Tuya Cloud Credentials
stays on App Admin, so its own redirects and its "Discover Devices" cross-reference text are
unchanged — just reworded in two places to say which page Add Plug's own Discover Devices button
is actually on now, since it's no longer "below" Tuya Cloud Credentials on the same page.

Each list's "no rows yet" empty-state message ("No sensors yet — add one on Admin.", etc.) changes
from linking to App Admin to just saying "add one below", since the form is now on the same page.

**Considered Options**:
- **Leave everything on App Admin** (status quo from ADR 0049) — rejected: the page-navigation
  round trip this ADR removes was the actual complaint; App Admin is otherwise working fine as the
  home for config that has nowhere more specific to live.
- **Move every Add form back, including Add Animal and Add Plug Group** — rejected: neither has a
  single natural listing page the way Room/Enclosure/Sensor/Plug each do, so "which page" has no
  good answer for them; they're exactly the kind of global Add form App Admin exists for.
- **Keep the forms on App Admin but add quick-links from each table to the matching form** —
  rejected: still two page loads per add, just with an extra click saved on one of them; moving the
  form itself removes the round trip entirely.

**Consequences**: "Rooms and Enclosures" and "Plugs and Sensors" are each back to mixing
browse/edit/command with entity creation, same shape they had before ADR 0049 — accepted as the
right trade for removing the page round trip. App Admin shrinks from 8 cards to 6. Any future
global Add form should default to its own table's listing page if it has one, and to App Admin
only if it doesn't.
