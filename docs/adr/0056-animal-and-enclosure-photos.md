# Add Animal Photo and Enclosure Photo, with a per-Enclosure Dashboard Thumbnail

**Status**: accepted

**Context**: Husbandry Tracker had no file-upload capability at all — the Shed Log ADR (0042)
explicitly deferred a per-entry photo attachment for exactly that reason. The request here is
simpler and more general: one photo per Animal, shown large on that Animal's card; one photo per
Enclosure, shown at the top of its own Admin page; and a per-Enclosure choice of which one (never
both) shows as a small thumbnail on that Enclosure's Dashboard panel. Clicking any of the three
pops the image up at full size.

**Decision**:
- **Storage**: photo files live on disk under `data/images/animals/<animal_id>.<ext>` and
  `data/images/enclosures/<enclosure_id>.<ext>` (`web/image_storage.py`), not as database BLOBs —
  keeps the SQLite file small and queries untouched by large binary payloads. `animal` and
  `enclosure` each gain a nullable `image_filename` column holding just the filename. One image per
  row: a new upload deletes whatever was stored for that row before, under any extension — never a
  history/gallery. Accepted types: JPEG/PNG/WebP, 10MB max, validated server-side against the
  upload's content-type rather than a client-supplied filename extension. Stored as uploaded, no
  server-side resize — every display size (card thumbnail, Dashboard thumbnail, lightbox full-size)
  is CSS-scaled from the same file.
- **Backup/Restore**: since photos aren't inside `data/husbandrytracker.db`, Ingest's
  `_perform_backup()` now also best-effort copies `data/images/` into a same-named `-images` folder
  alongside each `.db` backup, and prunes it alongside an aged-out `.db` backup. Supervisor's
  `_restore_backup()` restores that folder too, with the same safety-copy-first treatment the
  database itself gets. Closes the gap against Backup's own documented guarantee ("the single file
  that fully recovers a working system").
- **Animal Photo**: uploaded/replaced/removed only from the Animal's own Edit page
  (`admin_animal_edit.html`) — not inline on its card, and not from either Wizard (Setup Wizard, Add
  New Pet Wizard both stay untouched; a photo is an after-the-fact addition once the Animal already
  exists). Displayed as a large thumbnail by redesigning the Enclosure Admin page's Animals section
  from a plain `<table>` into a card grid — every existing control (On Dashboard toggle, quick log,
  edit, remove) carries over unchanged, just inside a card instead of a row.
- **Enclosure Photo**: uploaded/replaced/removed from a new control inside the existing Enclosure
  Settings form. Rendered full-width at the very top of the Enclosure's own Admin page, above
  everything else, only when one exists.
- **Dashboard Thumbnail**: a new explicit per-Enclosure setting, saved alongside Enclosure
  Settings — `dashboard_thumbnail_source` (`'enclosure'` or `'animal'`, default `'enclosure'`) plus
  `dashboard_thumbnail_animal_id` (`ON DELETE SET NULL`, same pattern as `fallback_sensor_id`). The
  Animal picker lists every Animal in the Enclosure regardless of that Animal's own
  `show_on_dashboard` — the two settings are independent. If the picked source has no photo yet, or
  the picked Animal is later deleted, the Dashboard panel simply shows no thumbnail that visit
  rather than a placeholder graphic or an error.
- **Lightbox**: one shared `#image-lightbox` `<dialog>` per page (Dashboard, Enclosure Admin, Animal
  Edit), reusing the existing Care Setup Prompt/Quick Log modal shell/backdrop-click-to-dismiss
  pattern already in `app.js`/`style.css` rather than a new library.

**Considered Options**:
- **Store images as BLOB columns on `animal`/`enclosure`** — rejected: every plain `SELECT *` on
  either table (used throughout `web/admin_queries.py`/`web/queries.py`) would drag image bytes
  along unless carefully reworked to exclude the column everywhere, and Backup/Restore would stay
  untouched for free but the live `.db` file would grow large fast.
- **Server-side resize into a separate thumbnail file on upload** — rejected for v1: adds a Pillow
  dependency and more code for a local, single-user app where CSS-scaling the original is simple
  and good enough; revisit if a very large upload is ever observed to make the Dashboard noticeably
  slow.
- **Dashboard Thumbnail as a plain toggle ("Enclosure photo" vs "first Animal with a photo"),
  no explicit Animal picker** — rejected: silently picks "whichever" Animal when more than one has
  a photo; an explicit picker has one unambiguous answer even for a colony Enclosure.
- **Let Setup/Add New Pet Wizards upload a photo at creation time** — rejected for v1: keeps this
  feature's surface area to Admin-only; revisit if uploading immediately at creation turns out to
  matter in practice.

**Consequences**: the Enclosure Admin page's Animals section changes shape (table → card grid) for
every existing install the moment this ships, even for an Enclosure with no photos yet — accepted,
since the empty-photo state ("no photo" placeholder) still reads cleanly and the card shape is
needed regardless of whether a photo's been uploaded. `data/images/` is a second on-disk location
(besides `data/husbandrytracker.db`) that now matters for a full backup — anyone with their own
backup tooling outside Supervisor/Ingest needs to know to include it too.
