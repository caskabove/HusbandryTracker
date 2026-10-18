# Sensor Discover: a clickable "Discover Devices" button, not a Command Prompt detour

**Status**: accepted — Phase 1 of GitHub issue
[caskabove/HusbandryTracker#3](https://github.com/caskabove/HusbandryTracker/issues/3)

Adding a Smart Sensor currently requires a trip to a Command Prompt to run
`tools/govee_discover.py`, a standalone script that was never frozen into the PyInstaller build (see
ADR 0018) — a beta tester who only ran `HusbandryTrackerSetup.exe` has no `python` on PATH at all, so
this step is currently a dead end for them, not just an inconvenience. Issue #3 also covers
`tuya_lan`'s device-ID/local-key lookup (`python -m tinytuya wizard`), but that's a multi-step
interactive flow against Tuya's own cloud (account linking, a phone QR-code scan) — turning *that*
into a web form is a materially bigger job, out of scope here. This ADR covers Phase 1 only: Govee.

**Decision**: add a **"Discover Devices"** button next to the MAC address field on every Add Sensor
form (Enclosure's own, Room's own, the Control Panel's global one), backed by a new
`discover_govee()` in `web/govee_refresh.py` — an unfiltered sibling of that same module's
`refresh_sensors()` (see CONTEXT.md: Refresh; ADR 0005): a short-lived `BleakScanner`, run directly
from `web`, this time listening for *any* Govee-looking advertisement for a fixed 20s rather than a
specific known set of MACs, decoding each with the same `plugins/govee_ble/protocol.py` DECODERS
`tools/govee_discover.py` already uses. Results are never written to the database — purely
diagnostic, same as Probe (ADR 0016), not a second source of sensor_reading rows. This replaces
`tools/govee_discover.py`'s job for every user, installer or from-source alike; the script itself
is left in place for anyone debugging decode issues from a terminal, per its own docstring's second
purpose.

**Why `web` talks to the BLE radio directly, again**: this is the third time this exact shape shows
up (Refresh, ADR 0005; Probe, ADR 0016; now Discover) — a person looking at the screen right now,
wanting an answer in seconds, with nothing to make durable or retryable. Routing it through the
Plugin/Registry/Inbox contract (ADR 0013) would mean teaching `govee_ble/plugin.py` a second mode,
plus a request/response file pair to get the answer back to `web` — real inter-process coordination
for a problem a direct call already solves. Reuses `govee_refresh.py`'s existing `_lock` so Discover
and Refresh (two BLE scans that could otherwise overlap within this one process) take turns instead
of running concurrently — see that module's own docstring for why two *processes* each scanning
(this one and the always-on Govee Plugin) is fine, but two scanners *within* `web` are not.

**Why this is a JSON endpoint instead of the usual redirect-and-redisplay**: every other admin
action in this app (including the dashboard's drag-and-drop Room reassignment — see
`web/static/app.js`) ends in a full page reload, deliberately, for consistency. Discover breaks that
on purpose: the button sits inside an *in-progress* Add Sensor form — Label, Target Range, Volatility
may already be half-filled-in — and a full-page round trip would either discard all of that or
require threading a `discovered_devices` list through three separate render functions
(`admin_enclosure.html`'s, `admin_room.html`'s, and the Control Panel's own) for a result that's
only ever used once, immediately, to fill in one field. `POST /admin/sensors/discover` is this app's
first plain JSON API route for exactly this reason; `web/static/app.js`'s new
`onDiscoverGoveeClick()` fetches it and injects a small list of clickable MAC buttons next to the
field — a deliberate, narrow exception to the full-reload convention, not a first step toward a
broader SPA-style rewrite.

**Why no new Plugin-declared "tool manifest" concept**: the request that prompted this (issue #3)
was framed as "whenever someone writes a new Plugin, it should get a button for free" — rejected as
the actual mechanism, because this app's Plugin contract (ADR 0013) deliberately keeps a Plugin
language-agnostic and reachable by Core only through the filesystem (Inbox/Registry/Outbox); letting
Core launch a Plugin's own process on demand for a UI button would be a second, inconsistent channel
alongside that contract, and ADR 0016 already rejected routing a read-only diagnostic back through
Outbox for the same reason Probe gave. What *is* generic here: `discover_govee()` lives in `web`
next to `refresh_sensors()`, and the three Add Sensor templates' MAC field markup is the one place a
future Smart-Sensor-type Plugin's own discovery call would plug in the same way — a future author
adds their own `discover_<plugin>()` bypass function and wires one more button, following this same
shape, rather than Core gaining a generic subprocess-launcher.

**Consequences**: `web/govee_refresh.py` gains `discover_govee()` alongside `refresh_sensors()`;
`web/admin.py` gains `POST /admin/sensors/discover` (JSON); `web/static/app.js` gains
`onDiscoverGoveeClick()`; the three Add Sensor forms gain a button and a small results list next to
the MAC field. `docs/USER_GUIDE.md` and `docs/HOWTO_ADD_GOVEE_SENSOR.md`'s "one-time technical step"
sections are superseded for Govee and updated accordingly; Tuya's equivalent (issue #3, Phase 2)
stays a Command Prompt detour until that separate, larger piece of work happens.
