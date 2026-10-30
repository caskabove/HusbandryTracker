# Plug's Controller Kind gains a fourth value, `timer`, splitting Target Schedule out of `none`

**Status**: accepted

**Supersedes part of ADR 0008/ADR 0012.** Until now, `controller_kind = 'none'` meant two different
things at once: "switched purely by hand, nothing to compare against" and "plugged into a separate
timer device, with a Target Schedule worth tracking and comparing against a Smart Plug's Detected
Schedule" (see CONTEXT.md: Target Schedule, Timer Warning). Always On lived in that same `none`
bucket too, as a third, mutually-exclusive option. RHA-95 asked for "Timer" as an explicit option
in the Controller Kind picker (Add/Edit Plug, and the Setup Wizard's own Plug step, which had no
Controller Kind concept at all before this) — discussion settled the two genuinely open questions
the ticket itself flagged:

- Target Schedule moves out of `none` and onto `timer` exclusively, rather than staying available
  under `none` too (which would have made `timer` a pure relabel with no behavior change).
- Always On stays under `none` — it isn't really "timed" in the way `timer`'s whole point is,
  closer to "no automation device at all."

Replaced `controller_kind`'s CHECK with `none | timer | thermostat | hydrostat`. `none` now carries
no Target Schedule at all (Always On is its one remaining optional attribute); `timer` is the only
Controller Kind with a Target Schedule, compared against Detected Schedule for a Timer Warning the
same way `none` used to. `thermostat`/`hydrostat` are unchanged.

**Consequences**: `web/admin_queries.py`'s `_validate_plug()`/`create_plug()`/`update_plug()` gate
Target Schedule's both-or-neither rule and field-clearing on `controller_kind == 'timer'` instead of
`'none'`; the four Detected-Schedule-gating call sites (`get_enclosure()`, `get_plug()`,
`list_plugs()`, `get_room()`) do the same. `send_plug_command()`'s `is_interruption` simplifies to
`controller_kind != 'none'` (a Target Schedule can no longer exist under `'none'` to check
separately). `db/schema.sql`'s `plug.controller_kind` CHECK widens accordingly;
`tools/migrate_2026_10_29_plug_timer_controller_kind.py` rebuilds the live table (SQLite can't
ALTER a CHECK in place) following SQLite's documented 12-step procedure, since several other
tables hold a foreign key onto `plug(id)`.

Every Controller-Kind-gated Plug form (`admin_plug_edit.html`, `admin_enclosure.html`'s and
`admin_index.html`'s own Add Plug, and the Setup Wizard's `setup_plug.html`, newly given the full
picker) splits what used to be one shared "Always On / Target Schedule" block into two separate
blocks, toggled by `web/static/app.js`'s `updatePlugFieldVisibility()` (now also takes an
`alwaysOnBlockId`, and tolerates a null Tracking Mode select/block for the Setup Wizard's simpler,
Manual-only Plug form — see ADR 0031). The Setup Wizard's own Room-step Plug form
(`setup_room_devices.html`) still has no Controller Kind picker at all, by design — its backend
route (`web/setup.py`'s `setup_create_room_plug`) infers `timer` for itself whenever an actual
on/off time was entered, `none` otherwise, so that simpler form keeps working unmodified.

Every Admin display table that shows a Plug's Schedule column already branched on
`plug["target_on_time"]`/`always_on` directly rather than re-checking `controller_kind == 'none'`
itself (`admin_enclosure.html`, `admin_index.html`, `admin_room.html`, `dashboard.html`) — those
needed no change at all, since a `'none'` Plug now simply never has `target_on_time` set.
