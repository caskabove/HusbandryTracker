# Plugs gain a one-shot Core-to-Plugin Command channel for direct on/off control

**Status**: accepted — extends ADR 0013

ADR 0013 made every Plugin observation-only: the Inbox is Plugin-to-Core, the Registry is
Core-to-Plugin, and neither carries an instruction to actuate anything — Core "never touches SQLite"
was mirrored by Core never touching a relay either. `Reptile_App_Technical_Requirements.md` §9.14
flagged "decide observation-only vs. control" as an explicit open question at the time. This ADR
answers it: yes, but narrowly — a direct, one-shot on/off Command, not a standing automation loop.
(Sensor-triggered automation — a Plug reacting to a *different* Sensor's readings — is a deliberate
phase 2, not decided here; see Consequences.)

The trigger is a concrete gap: today, nothing in Core ever writes to a Plug's relay. A Smart Plug's
on/off state is driven entirely outside this app — its own onboard/cloud schedule, a downstream
Thermostat-/Hydrostat-Controlled unit, or a person flipping it by hand. Target Schedule and
Controller Kind's setpoints are both **display-only** today (confirmed by reading every
`controller_kind`/`target_temp_c`/`target_humidity_pct` reference in `web/` — they only ever render
a "Target: 85°F (thermostat)" pill, nothing compares them against a live Reading to decide anything).
Two real needs motivated closing that gap: reacting to an Alert ("something's not working, let me
turn this off right now") and giving Manual Plugs — which have no hardware at all — a way to log
"I turned this on/off just now" the same place Smart Plugs get their control.

**Shape, mirroring the Inbox/Registry pattern:**

- A new **Outbox** (`data/outbox/<plugin>/`) — the Core-to-Plugin half of a second, narrower
  filesystem contract, alongside Registry. One JSON file per pending Command, validated against a
  new `schemas/plug_command.schema.json`, named by External ID so a later click on the same Plug
  supersedes an unprocessed earlier one rather than queuing behind it — only the latest desired
  state matters. Only `tuya_lan` reads it; `govee_ble` is BLE sensors with nothing to actuate and
  never implements it.
- **One-shot, not persistent.** A Command is a single direct write to the relay right now — the
  same as flipping a physical switch by hand — not a state Core continues to re-assert. If the Plug
  has its own onboard schedule or a downstream Thermostat-/Hydrostat-Controlled unit, that keeps
  doing its own thing afterward; Core never fights it. There is no held "override" state on the
  `plug` row.
- **Interruption**, a new distinction: a Command sent to a Plug with a *determined setting*
  (`controller_kind != 'none'`, or a Target Schedule is set) is logically different from a plain
  manual toggle on a Plug with neither — it doesn't change the setting, it's a deliberate, temporary
  departure the Plug is expected to return from on its own. Only an Interruption prompts for an
  optional, skippable note; a plain toggle never does.
- A new plug-scoped `plug_command_log` table (`plug_id, requested_at, is_on, is_interruption, note`)
  records every Command — Smart or Manual, plain or Interruption — in one place. Plug-scoped rather
  than reusing `care_event` (which is `enclosure_id NOT NULL`) because a Plug can be Room-owned
  instead of belonging to any Enclosure.
- **Manual Plugs get the same control**, but synchronously: a self-reported `plug_command_log` row
  written directly, no Outbox file, no Plugin round-trip, since there's no hardware behind it.
  Deliberately **not** written into `plug_state_transition` — Detected Schedule and Timer Warning
  stay Smart-only. A self-reported log is a different trust level than an actually-observed
  transition (a missed log entry would otherwise look identical to "it didn't turn on"), so this
  doesn't retroactively grant Manual Plugs a Detected Schedule.
- Sending a Command on a Smart Plug whose Auto-Update is currently paused **resumes Auto-Update** as
  a side effect, rather than the confirming `plug_state` event silently vanishing into Ingest's
  existing `auto_update_enabled = 1` gate (`ingest/ingest.py::_apply_event`) or forcing the user to
  separately unpause first. Asking Core to act on a Plug and then ignore what happens to it next
  would be a worse default than the small surprise of Auto-Update coming back on.
- **No synchronous confirmation.** The web route returns immediately after writing the Outbox file;
  the Plugin executes on its own poll cadence (5s for `tuya_lan` today) and reports back through the
  ordinary `plug_state` → Ingest path, same as any other observation. The UI computes a "Commanded
  ON at 3:42pm — confirming..." label at render time by comparing the `plug_command_log` row against
  `plug_last_seen`/`plug_state_transition`, flipping to a visible failure state if nothing confirms
  within roughly 2× the Ingest scan interval plus the Plugin's poll cadence (~15-20s with current
  defaults) — a command silently dropped because the device was unreachable must not read as
  "still confirming" forever.

**Considered Options**:
- **A persistent, continuously-re-asserted override** (a `plug` column Core's Plugin loop keeps
  fighting the device to maintain) — rejected: there is no existing automatic governance loop in
  Core today to override (Target Schedule/Controller Kind are both display-only, confirmed above),
  so phase 1 has nothing to hold state against. Meaningfully more machinery (a state column plus
  continuous enforcement) for a need that reads, in practice, as a one-time corrective click, not a
  standing policy — better served later if phase 2's automation rules ever need it.
- **Reusing `care_event`** for the note/log — rejected: `enclosure_id` is `NOT NULL` there, but a
  Plug can be Room-owned; a plug-scoped table avoids that mismatch and keeps a device-command log
  conceptually distinct from a husbandry-action log.
- **Synchronous command execution** (the web process blocks waiting for the Plugin's result) —
  rejected: breaks the filesystem-only decoupling ADR 0013 established in favor of a request/
  response channel; the whole point of Inbox/Registry/Outbox is that Core and a Plugin never need to
  be reachable from each other in real time.
- **Live client-side polling for instant confirmation** — rejected for now: every action in this app
  is a plain POST → redirect → reload (the one exception, dashboard drag-and-drop, uses a small
  `fetch()` + `location.reload()`); an explicit textual "confirming..."/"failed" state gets most of
  the practical benefit without introducing a new interaction pattern just for this feature.
- **No confirmation dialog before an OFF command** — considered and rejected as unnecessary friction:
  the driving use case is reacting quickly to an Alert, which a confirm dialog works directly
  against; the optional note on Interruptions already provides a moment's pause for the case more
  likely to need one.

**Consequences**: new `data/outbox/<plugin>/` directory and `schemas/plug_command.schema.json`; new
`plug_command_log` table (and its own `schemas/plug_command_log.py`, per the Entity Schema Layer
convention §9.15 established); a `write_command`-equivalent helper alongside
`plugins/common.py::write_event`; `plugins/tuya_lan/plugin.py`'s existing 5s poll loop gains an
Outbox check per watched External ID; new command-handling route(s) in `web/admin.py`; the plug
pill markup in `admin_index.html`/`admin_room.html`/`admin_enclosure.html` gains an on/off control
and a commanded/confirming/failed status label. Resolves the "observation-only vs. control" half of
reqs-alignment-review's §9.14 punch-list item; the rest of that item (a `plugins/<name>/
manifest.json`, secrets-on-disk policy, schema-version policy, third-party-author docs) stays open.
Explicitly **out of scope**: sensor-triggered automation (a Plug's state driven by a *different*
Sensor's readings, e.g. a fan Plug reacting to an over-temp reading elsewhere) — no rules engine is
built here. Deliberately left for a phase 2 ADR, which would sit on top of the Command/Outbox
mechanism this ADR adds (the same channel that executes a manual Command is what an automation rule
would use to actually flip the relay) rather than needing a third filesystem contract of its own.
