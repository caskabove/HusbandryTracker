# Plug Probe: on-demand diagnostic device query, bypassing Outbox

**Status**: accepted

Data Capture (ADR 0009) only ever stores the four DPS values core already knows how to interpret
(`cur_power`/`cur_voltage`/`cur_current`/`countdown_1`) into `plug_reading`, discarding the rest of
`tinytuya`'s `status()` response — the same discard `tools/tuya_probe.py` already works around from
the command line when someone needs to see a device's *full* raw `dps` dict, e.g. to find which key
is the actual switch before registering a plug. There's no way to ask that question from Admin
itself, and no reason to assume the answer stays fixed forever — a firmware update on the physical
device (or swapping in a different model behind the same Plug row) can add or remove DPS keys over
time, so "what can this Plug report" isn't a static manifest core could just look up once and cache.

Decision: add **Probe**, a per-Smart-Plug button on the Edit Plug page that makes one synchronous
local `tinytuya.OutletDevice(...).status()` call — the same construction
`plugins/tuya_lan/plugin.py` already uses — directly from `web`, and renders the full raw response
back on the page, unfiltered and unlabeled. This is a **diagnostic** tool, not a monitoring feature:
it exists purely so a person can ask "what does this plug currently have to say," and is strictly
**read-only** — it only ever calls `.status()`, never a `set_status`/DPS write, so it cannot change
anything about the device. Probe uses whatever device_id/local_key/IP is currently typed into the
Edit Plug form, even if unsaved, so new credentials can be verified before committing them. Nothing
Probe returns is persisted — no new table, no write to `plug_reading` — it's shown once and
discarded, same as the request itself. Never shown for a Manual Plug (no device to query). Its own
short hardcoded timeout (a plain code constant, not the Sensor-scoped Refresh Timeout setting) —
a local LAN call has different failure behavior than a BLE broadcast wait.

This deliberately follows ADR 0005's precedent (Sensor Refresh runs its own short-lived
`BleakScanner` directly from `web`, bypassing the passive collector) rather than ADR 0014's Outbox/
Command channel. The Outbox exists for durable, eventually-executed actuation on the Plugin's own
poll cadence — the right shape when nothing's watching and a Command must survive the Plugin being
mid-cycle. Probe is the opposite: a person is looking at the screen right now, wants an answer
within a few seconds, and the call is read-only, so there is nothing to make durable or retryable.
Routing a diagnostic read through a request/response file pair for that case would only add latency
and a new protocol for no benefit.

**Considered and rejected:**
- **Route Probe through the Outbox** (a request file `tuya_lan` picks up on its poll, writing a
  response file back) — rejected as real inter-process coordination for a problem a direct call
  already solves, the same reasoning ADR 0005 used for Refresh and ADR 0002 used to drop Docker.
- **Persist each Probe response** for historical comparison — rejected; the value is in looking, not
  in warehousing arbitrary undocumented keys. If a specific new DPS key turns out worth tracking
  long-term, that's a deliberate follow-up (extending Data Capture), not something Probe should
  quietly start accumulating.
- **Filter the response down to this Plug's own switch/telemetry keys** — rejected; a shared
  power-strip device (see CONTEXT.md: Plug, multi-outlet setups) may report sibling outlets' keys in
  the same response, and hiding them would defeat the point of a discovery tool.

**Consequences**: `web` gains a second direct-to-device code path alongside Sensor Refresh's BLE
scan — Probe is the first place `web` talks to Tuya hardware synchronously outside the Outbox/
Plugin boundary ADR 0014 built. Because Probe never writes to `plug_command_log` or touches
Auto-Update, it carries none of Command's state-mutation bookkeeping — probing a Plug leaves no
trace anywhere once the page is left. See CONTEXT.md: Probe.
