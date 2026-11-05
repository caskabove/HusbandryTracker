# Active Plugin: immediate manual-action enforcement, explicit Admin copy, and success notices

**Status**: accepted

**Context**: ADR 0045/0047 made Active Plugin a real, enforced concept for Ingest — a deactivated
Plugin's Registry export stops and its Inbox events get dropped, so background polling/listening
eventually stops touching the database. But that's the only place it was ever enforced. Three
manual, hardware-touching entry points never checked Active status at all:

- The Dashboard's and Admin's own Refresh buttons (`web/main.py::_refresh_smart_sensors`,
  `web/admin.py::_refresh_one_sensor`) ran a live BLE scan and wrote a real `sensor_reading`
  regardless of whether `govee_ble` was Active.
- `web/admin_queries.py::send_plug_command()` — the Plug on/off control, and the Plug Group
  All On/All Off fan-out built on top of it — logged a Command and dropped a real Outbox file for
  `tuya_lan` to execute, regardless of whether it was Active.
- Admin's own copy claimed a deactivated Plugin's Sensors/Plugs stop updating "the same way
  deregistering their last device would," which wasn't true for any of the above, and the Tuya
  Cloud Credentials card stayed visible/editable even with `tuya_lan` deactivated.

Separately, activating or deactivating any Plugin left the page looking identical to any other
click — no confirmation of what, if anything, actually happened. Only Skill-kind Plugins got any
explanatory text at all (a caption shown before clicking Activate, describing the one-time file
install), and only while inactive.

**Decision**:
- `web/main.py`, `web/admin.py`, and `web/admin_queries.py::send_plug_command()` all now call
  `active_plugins.is_plugin_active()` directly before touching hardware, rather than relying on
  Ingest's own lagged, Registry-file-based gate. A blocked Plug Command raises `ValueError` (same
  as every other invalid-state check that function already makes) rather than logging a Command
  nothing will execute. A Refresh that covers more than one Sensor (an Enclosure's or Room's) skips
  just the ones on a deactivated Plugin and still refreshes the rest, naming what was skipped in
  the result message — not an all-or-nothing block, since today's single-Plugin-per-kind reality
  (only `govee_ble` does Smart Sensors) makes that the common case already, and nothing stops a
  second Smart Sensor Plugin from existing later. Manual Plugs/Sensors have no Plugin to check and
  are never affected.
- Every Refresh control (Dashboard, Admin's Sensor edit pages) and Plug on/off control (Plug edit
  page, Room's inline Plug list, Plug Group's All On/All Off) is disabled client-side whenever
  there's nothing Active left for it to act on, with a title/caption explaining why — not just a
  server-side error after the fact. The Dashboard needed `get_dashboard_data()` to carry this
  through per Enclosure/Room (`can_refresh`), since it has no per-request Jinja global the way
  Admin's pages do.
- Admin's Plugins card copy is now explicit about exactly what Active controls (background
  updates, Refresh, Plug commands — all immediate, not eventual) instead of the vaguer "pauses them
  the same way deregistering their last device would" line, which was also inaccurate until this
  change actually made it true. Each device-kind Plugin row gets its own before-the-click caption
  now too (what Activate/Deactivate is about to do), the same way Skill-kind rows already did.
- Tuya Cloud Credentials is hidden, with a one-line explanation (not silently gone), whenever
  `tuya_lan` isn't Active — already-saved credentials stay in the DB regardless, just not shown or
  editable meanwhile.
- A new green `.notice-banner` (parallel to the existing red `.error-banner`) confirms both
  activation and deactivation, worded per Plugin kind — a Skill's names its actual
  `.claude/skills/<name>/` install/removal, a device Plugin's names the behavior change.

**Considered Options**:
- **Leave manual actions as a deliberate testing escape hatch, only tighten the background-polling
  lag** — rejected: "a plugin should not work if not activated" is the whole point of Active
  Plugin existing; an escape hatch that bypasses it entirely for the two most-used manual controls
  defeats that for no documented reason (unlike Probe, ADR 0016, which is deliberately exempt
  because it predates any Sensor/Plug row, let alone a Plugin association, existing to check).
- **Block a whole multi-Sensor Refresh if any one Sensor it covers is on a deactivated Plugin** —
  rejected: strictly worse for a mixed Enclosure/Room than skipping just the affected Sensor(s),
  for no safety benefit.
- **Hide Tuya Cloud Credentials entirely with no explanation** — rejected in favor of the
  one-line note, consistent with this change's own "explicit, not silent" premise.

**Consequences**: `web/queries.py::get_dashboard_data()` gained a Python-computed `can_refresh`
flag per Enclosure/Room; `web/admin.py` registered `is_plugin_active` as a Jinja global so its own
templates (Plug edit, Room, Plugs-and-Sensors index, Sensor edit, Room Sensor edit) can gate
inline. `web/admin.py::admin_send_plug_group_command` gained the `try`/`except ValueError` every
sibling Plug/Sensor route already had, closing a pre-existing gap where a blocked Command would
have surfaced as an unhandled 500 instead of the usual error banner. See CONTEXT.md: Active Plugin.
