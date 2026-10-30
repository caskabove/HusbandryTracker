# Move Rooms to the Enclosures page; rename both admin pages

**Status**: accepted

The Rooms card (its table plus "+ Add Room") lived on the Control Panel (`/admin`) alongside
unrelated cards — Settings, Tuya Cloud Credentials, Sensors, Plug Groups, Plugs. Room was the odd
one out there: every other card on that page is about a Plug or a Sensor, while Room is a
container for Enclosures, and the All Enclosures page (`/admin/enclosures`) already existed one
click away. Keeping Rooms on Control Panel meant assigning an Enclosure to a Room required
bouncing between the two pages, and the Control Panel's name ("Control Panel") never described
what was actually on it once Rooms is excluded — it's a Plugs/Sensors settings page.

**Decision**: the Rooms card moves to the Enclosures page, and both pages are renamed to describe
what they actually hold:

- `/admin/enclosures` becomes **"Rooms and Enclosures"**: a Rooms card (table + a separate "+ Add
  Room" card, matching this page's existing Enclosures/"+ Add Enclosure" split) sits above the
  Enclosures card, since Room is the container.
- `/admin` becomes **"Plugs and Sensors"**: Settings, Tuya Cloud Credentials, Sensors, Plug Groups
  and Plugs stay, unchanged.
- URL paths are unchanged (`/admin`, `/admin/enclosures`, `/admin/rooms/...`) — only the nav
  labels and each page's own `<h1>`/`<title>` change. Renaming paths would touch dozens of
  existing redirects for no user-facing benefit, since paths never appear in the UI.
- The four "Room not found" redirects that pointed at `/admin` (`admin_room_detail`,
  `admin_delete_room`, `admin_room_data`, `admin_room_graphs`) now point at `/admin/enclosures`,
  matching the equivalent Enclosure routes, which already redirected to `/admin/enclosures`.
- Unrelated admin pages (Room edit, Animal edit, Sensor edit, Plug edit, Room Sensor edit) had
  borrowed "Husbandry Tracker Control Panel" as a generic `<title>` prefix even though they aren't
  the Control Panel page. Those are fixed to a plain `Husbandry Tracker - {{ page }}` while this
  rename is already touching that string, rather than leaving a stale page name in place.

**Consequences**: no schema or route changes — this is a template/nav-only move. `admin_index()`
no longer computes `enclosure_count_by_room` (only the Rooms card used it); `admin_enclosures()`
now does. Setup Wizard copy that pointed at "the Control Panel" for adding a Room-level
Sensor/Plug now says "Plugs and Sensors" (still precise); the one generic "come back to it later"
line on the final setup step no longer names a specific page, since what you'd come back to add
could now be on either page.
