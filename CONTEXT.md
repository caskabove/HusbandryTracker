# Husbandry Tracker

A local-only monitoring and husbandry-tracking system for a reptile collection: environmental readings (temperature, humidity), device schedules (light, heat, cooling), and care events (feeding, watering, cleaning). A CaskAbove product — CaskAbove is the publisher (installer, LICENSE, GitHub org), not part of the in-app name; the running app refers to itself only as "Husbandry Tracker".
_Formerly_: HerpMonitor (renamed before first release — see ADR 0020). Historical ADRs written before the rename still say "HerpMonitor" in their prose; that's original wording, not a typo — see ADR 0020.

## Language

**Enclosure**:
The physical housing unit (tank, tub, rack tray) that an environmental sensor and control devices belong to. The unit of monitoring — temp, humidity, and schedules are properties of the Enclosure, not of any single Animal inside it. May contain one Animal, a pair, or a colony. May optionally belong to a Room (see Room, Fallback Sensor).
_Avoid_: Tank, cage, habitat (use only when quoting a specific product/UI)

**Room**:
A named grouping of Enclosures sharing a physical space (e.g. "Living Room", "Reptile Rack"), with its own ambient Sensor(s) and Light Schedule. Optional — an Enclosure need not belong to one. Unlike an Enclosure, a Room has no Animals, no Bioactive flag, and no Care Events; it exists purely to group Enclosures on the dashboard and to monitor/schedule the shared space around them.

**Animal**:
An individual reptile with a name, species (common + scientific name), and DOB. Belongs to exactly one Enclosure. Whether an Animal's card shows on the Dashboard's Enclosure panel is its own per-Animal flag (`show_on_dashboard`), toggled from a checkbox on the Enclosure's Admin page — the Admin page itself always lists every Animal regardless. Defaults on for the first 3 Animals registered to an Enclosure, off after that; the user can flip any Animal's flag either way at any time.
_Avoid_: Pet, specimen

**Plant**:
An individual live plant tracked within a Bioactive Enclosure, with a name and species (optional) — analogous to Animal, but only creatable on an Enclosure with Bioactive set. Not required: a Bioactive Enclosure's plants can be logged purely at the Enclosure level (see Plant Health) without ever naming an individual Plant.

**Plant Health**:
A manually-logged, backdatable observation about a Bioactive Enclosure's plants (e.g. "pothos yellowing, moved out of direct light") — scoped to either the Enclosure as a whole or one specific Plant, at the logger's choice. Not a Care Event: it's a status observation, not an action performed, and lives in its own table rather than stacking a second conditionally-valid entity reference onto `care_event` alongside Spot-feed's `animal_id`.

**Sensor**:
An environmental monitor assigned to either an Enclosure or a Room (never both), in one of two Tracking Modes: a `Smart Sensor` is a Govee H5074 BLE temp/humidity device, polled automatically; a `Manual Sensor` has no physical device behind it — its Readings are logged by hand, and it must have a complete Target Range set on at least one metric (there's nothing to judge a hand-entered value against otherwise). An Enclosure or a Room may have more than one Sensor (e.g. an Enclosure's warm-side/cool-side gradient, or a Room with one Sensor near a window and one near a door). Whether a Sensor's Reading shows on the Dashboard is its own per-Sensor flag (`show_on_dashboard`), toggled from a checkbox on its parent Enclosure's or Room's Admin page — the Admin page itself always lists every Sensor regardless. Defaults on for the first 3 Sensors registered under the same parent, off after that; the user can flip any Sensor's flag either way at any time (same pattern as Animal's own `show_on_dashboard`).
_Avoid_: Hygrometer, thermometer (use Sensor as the umbrella term)

**Fallback Sensor**:
The specific Sensor an Enclosure with no Sensor of its own points to instead, chosen from its Room's Sensors — the choice accounts for where that Enclosure actually sits in the Room (nearer the window vs. the door, say), rather than always using the same one. Only available once the Enclosure belongs to a Room. Its Reading shows on that Enclosure's panel raw and uncolored, clearly labeled with its source — never judged against a Target Range, since a Room's Target Range reflects human comfort, not what's healthy for that specific animal.

**Plug**:
A device controlling a light/heat/cooling/etc. source, tagged with a Purpose, in one of two Tracking Modes: a `Smart Plug` is a Tuya-controlled Gosund smart plug, polled automatically; a `Manual Plug` has no device credentials — it's switched by hand (e.g. a mechanical timer). Either kind can carry a Target Schedule (see Target Schedule). A Plug belongs to either **one Room**, or **one-or-more Enclosures** — never both, never neither. Most Plugs serve exactly one Enclosure; a single physical switch controlling several tubs at once (common in smaller collections — "everything on one switch") is the same Plug linked to each of them, sharing one Purpose/Tracking Mode/Schedule since it's the same physical device doing the same physical thing for all of them. A Room-owned Plug is for a genuinely room-wide fixture (a rack's ambient light) rather than anything tied to specific Enclosures. Independently of Tracking Mode, a Plug also has a **Controller Kind** (see Controller Kind) describing what's downstream of the relay. Whether a Plug's current status (on/off, or Unreachable) shows on the Dashboard is its own per-Plug flag (`show_on_dashboard`), toggled from a checkbox on its parent's (Room's, or each linked Enclosure's) Admin page — the Admin page itself always lists every Plug regardless. Defaults on for the first 3 Plugs registered under the same parent, off after that; the user can flip any Plug's flag either way at any time (same pattern as Animal/Sensor's own `show_on_dashboard`). This is distinct from the Schedules section, which stays Admin-only.
_Avoid_: Outlet, switch

**Plug Group**:
A named container for several Plugs that are physically one multi-outlet Tuya device (a power strip with independently-switched relays, e.g. 3 relay-controlled outlets + a USB outlet + 3 hardwired-always-on outlets with no relay at all) — purely organizational plus one shared action, not a new control/polling concept. Solves the same ambiguous-naming problem `show_on_dashboard`'s Govee "ambient" collision exposed: without it, a multi-outlet strip's outlets have no shared identity in the UI beyond a repeated/guessed label. A Plug Group belongs to either one Room or one-or-more Enclosures — never both, never neither — same rule as Plug itself (see Plug), and every member Plug inherits that assignment; there is no per-member Enclosure override. Member Plugs otherwise behave exactly as before: each keeps its own Label, Purpose, Tracking Mode, on/off state, Schedule, etc. See All On/All Off for the one piece of shared behavior a Group adds. Created via a user-declared template at Plug-add time (see Plug Group Template) — not auto-detected from the device in the first version. An existing standalone Plug (e.g. one outlet registered before its strip's Group existed) can be attached to, or detached from, a Group later from its own Edit Plug page — attaching overwrites that Plug's Room/Enclosure assignment to match the Group's, since the Group is the source of truth for a member's parent. Deleting a Plug Group never deletes its member Plugs — same precedent as Enclosure deletion falling back to Unassigned (see Unassigned): members are ungrouped (become ordinary standalone Plugs, keeping their own row/history/Enclosure-Room assignment) and only the Group itself is removed.
_Avoid_: conflating with a single Plug linked to multiple Enclosures (one relay, one shared on/off state — see Plug) — a Plug Group is the opposite: several *independently switched* relays sharing one physical enclosure and one on-device master button.

**Plug Group Template**:
The set of known multi-outlet Tuya device layouts a user picks from when creating a Plug Group, rather than the app auto-detecting the physical device's type from Tuya metadata (out of scope for the first version — nothing in this codebase currently reads a device's category/product_id). The first template: 3 independently-switched relay outlets + 1 USB outlet (all Smart, all swept by All On/All Off) + 3 always-on outlets (no relay, no DPS key — see Always-On Outlet). Picking a template drives the Plug Group creation wizard: it creates all member Plug rows at once instead of the current one-at-a-time Admin flow, each pre-filled with a default label (e.g. "Reef — Outlet 1", "Reef — Always-On 1") that's fully editable before saving, same as Purpose (see Purpose — stays per-member, not shared across the Group).

**Always-On Outlet**:
A Plug Group member with no DPS key at all — a physically hardwired-on socket on a multi-outlet strip, wired straight to mains with no relay Tuya (or Husbandry Tracker) can address, distinct from the existing per-Plug **Always On** attribute (see Always On), which is a *setting* on an otherwise-controllable Plug. An Always-On Outlet is a `Manual` Tracking Mode Plug (no plugin/external_id — nothing to poll) with its existing `always_on` flag set, created with an editable name during Plug Group creation. Reuses the existing Plug/Manual/Always On model exactly as-is; the only actual gap it fills is bulk creation with a name, not new schema on `plug` itself.

**All On / All Off**:
A Plug Group's one shared action, mirroring the multi-outlet device's physical master button: sends an individual Command (see Command) to every *Smart* member of the group — the relay-controlled outlets and the USB outlet — turning them all on, or all off, in one click. Always-On Outlets are never included (nothing to toggle). Implemented as an ordinary fan-out of existing per-Plug Commands, not a new Outbox/Plugin-level concept.

**Purpose**:
The role a Plug serves — a free-text label (e.g. "light", "heat", "cooling", "UVB", "pump"), not a fixed set. Admin suggests the common ones but any value is valid, since husbandry setups use plugs for things beyond climate control (misting pumps, UVB fixtures distinct from general lighting, etc.). One Plug has exactly one Purpose, regardless of Tracking Mode or how many Enclosures it serves.

**Unassigned**:
A real Enclosure, always present, used as a holding pen for a Plug that doesn't (yet, or anymore) belong anywhere real — a newly-discovered Smart Plug not yet assigned to its actual Enclosure(s), or a Plug that just lost its last Enclosure link because that Enclosure was deleted. Keeps the Plug's credentials/history intact rather than losing them, ready to be reassigned through the normal Admin edit flow. Not a Room — an Unassigned Plug isn't grouped by physical space, it's explicitly "not placed yet."

**Tracking Mode**:
Whether a Sensor or Plug is watched by real hardware or tracked by hand — `Smart` (a real device exists and is polled automatically) or `Manual` (no device credentials; a person enters what's happening instead). Set independently per Sensor and per Plug, and changeable later without losing the row's history if the underlying hardware is swapped out (a smart plug replaced by a mechanical timer, or vice versa).

**Device Registration**:
The manual, admin-screen setup of a Sensor or Plug. For a `Smart` one, this maps its Plugin, External ID, and Plugin Config to the Enclosure (and, for Plugs, Purpose) it belongs to. For a `Manual` one, there's no hardware identifier to map — just the Enclosure, Purpose/label, and (Target Range or Target Schedule). A one-time setup step per Sensor/Plug, not an auto-discovery/pairing flow — edited only when hardware is added, swapped, or Tracking Mode changes.

**External ID**:
The opaque identifier a Plugin uses to address one physical device within its own protocol — a Govee MAC address, or a Tuya `device_id`+`switch_dps_key` pair joined into one string. Unique together with Plugin (two different Plugins may coincidentally reuse the same raw value, e.g. a MAC address, without colliding). Core never interprets its contents — only the owning Plugin knows how to parse or use it.

**Plugin Config**:
The connection/credential data a Smart Sensor's or Plug's Plugin needs beyond its External ID to actually reach the device — a Tuya `local_key` and optional pinned IP; empty for Govee, which needs nothing beyond the MAC address itself. Vendor-specific shape, stored opaque to core (JSON), never validated or interpreted outside the owning Plugin.

**Schedule**:
A Plug's on-time and off-time, made of two parts that exist independently and get compared: a **Target Schedule** (what you expect/intend) and, for a Smart Plug, a **Detected Schedule** (what's actually been observed) — see those terms, and Timer Warning. Not shown at all for a Plug with a Controller Kind set — see Controller Kind.
_Avoid_: Routine (that's Google Home's term for the thing that produces the state changes we observe); Declared Schedule/Inferred Schedule (superseded terms from an earlier version of this app — see Target Schedule, Detected Schedule).

**Target Schedule**:
The on-time/off-time you expect a Plug to run, entered directly — available on any Plug without a Controller Kind, Smart or Manual alike. For a `Manual Plug` this is the only schedule information there is, shown plainly with no claim about whether the Plug is actually on right now — it assumes the physical timer is working correctly, which is never verified. For a `Smart Plug` it's compared against the Detected Schedule — see Timer Warning. Mutually exclusive with Always On.

**Always On**:
A Plug attribute, only settable when Controller Kind is `none`, for one meant to run continuously with no on/off cycle at all — a filtration pump, say. Mutually exclusive with Target Schedule (a Plug has one, the other, or neither — never both). Purely descriptive, same as Target Schedule itself: disambiguates "deliberately has no schedule" from "no schedule set yet," but claims nothing about whether the Plug is actually powered right now and drives no Alert Condition. Shown in place of the Schedule column wherever a Plug's schedule normally appears (Admin, Enclosure, Room). Not offered at all for a Thermostat-/Hydrostat-Controlled Plug — that Controller Kind already implies the relay stays continuously powered so the downstream unit can do its own cycling, making a separate Always On flag redundant.

**Detected Schedule**:
A `Smart Plug`'s actual most-recently-observed on-time and off-time, derived from its Plug State Transition history — specifically, the time-of-day of the most recent transition to on, and separately the most recent transition to off. Not an average across days; the latest observed instance of each. Shows "no data yet" until at least one transition of that kind has been seen. Never shown for a Manual Plug — there's nothing to detect.

**Timer Warning**:
A per-Plug visual flag (the relevant time shown in red) when a Smart Plug's Target Schedule and Detected Schedule disagree by more than the **Schedule Drift Threshold** (an app-wide setting, default 15 minutes) on either the on-time or the off-time, checked independently. The comparison is wraparound-aware (23:50 vs 00:05 is a 15-minute gap, not a 23-hour one). Purely a dashboard-level indicator today — not wired into Send Alert/ntfy. A Timer Warning can be **cleared** ("Clear warning" on the Plug's Edit page), which records the Detected Schedule times it's showing for each of on and off. A cleared time reads neutral (not red) until the Detected Schedule moves to a different time, or the Target Schedule changes — either re-arms the warning. Clearing is per-time: clearing the on-time warning leaves a new off-time drift to show.

**Controller Kind**:
A Plug attribute, independent of Tracking Mode, describing what's downstream of the relay: `none` (the Plug powers the heat/cooling/moisture source directly — the common case), `Thermostat-Controlled` (see Thermostat-Controlled), or `Hydrostat-Controlled` (see Hydrostat-Controlled). Mutually exclusive — a Plug is one physical relay powering one downstream device, so it's at most one of the two, never both at once.

**Thermostat-Controlled**:
The Controller Kind for a Plug that powers a separate physical thermostat unit (a Herpstat, Vivarium Electronics, Jump Start, etc.) rather than the heat/cooling source directly. The thermostat does the actual on/off cycling downstream of the Plug — invisible to Tuya and to observation — so a Thermostat-Controlled Plug shows no Schedule (Inferred or Declared) at all, and instead shows its **Target Temperature**: the single setpoint value the thermostat is dialed to, entered directly (there's no device to read it from), shown plainly with no claim about whether the Enclosure is actually at that temperature — that's still the job of a real Sensor's Target Range.

**Hydrostat-Controlled**:
The Controller Kind for a Plug that powers a separate physical humidity controller (a MistKing misting system's control unit, a humidistat-driven fogger, etc.) rather than the moisture source directly. Same shape as Thermostat-Controlled but for humidity: shows no Schedule at all, and instead shows its **Target Humidity** — the single setpoint value the controller is dialed to, entered directly, shown plainly with no claim about whether the Enclosure is actually at that humidity — that's still the job of a real Sensor's Target Range.

**Light Schedule**:
A Room's on-time and off-time for its general lighting, entered directly since there's no device to observe, plus an optional free-text note for anything else worth capturing (e.g. "natural light from east window", "dimmed after 6pm"). Distinct from a Plug's Schedule — a Light Schedule isn't tied to any specific Plug/device, it describes the Room as a whole.
_Avoid_: Schedule alone (that term is reserved for a Plug's on/off tracking, Inferred or Declared)

**Data Capture**:
A Plug's captured telemetry snapshot — current wattage/voltage/current draw, and any active countdown timer — pulled from the same local Tuya status call the on/off poll already makes. The Plug-side equivalent of a Sensor's Reading. Written on a slower, independent cadence (every 1-5 minutes) from the 5-second on/off Plug State Transition watch, since wattage drifts continuously while a transition is edge-triggered (only recorded when on/off actually flips). Distinct from Probe (see Probe, ADR 0016): Data Capture is routinely collected and stored, but only for the four values core already knows to interpret; Probe is an on-demand, unstored, unfiltered look at everything the device currently reports.

**Auto-Update**:
A per-Sensor or per-Plug toggle, meaningful only for a `Smart` Sensor/Plug, that pauses automatic background collection (Readings for a Sensor; Plug State Transitions and Data Captures for a Plug) without changing Tracking Mode or losing device credentials/history. Distinct from Refresh, which is a one-off manual pull on demand — Auto-Update is an ongoing on/off state, for silencing a flaky or temporarily-irrelevant device (e.g. unplugged for the season) without deregistering it. Default on. Sending a Plug a Command while it's paused resumes Auto-Update as a side effect — see Command, ADR 0014.

**Plugin**:
An independent process that owns one vendor/protocol integration end-to-end (credentials, polling or listening cadence, protocol quirks) and talks to the rest of Husbandry Tracker only by reading and writing JSON files — never touching the database directly. Replaces "collector" as the term going forward; a Govee or Tuya Plugin today, but the shape admits any future vendor, in any language, without changing core code. See Ingest, Inbox, Registry, Plugin Event, and ADR 0013 for observation; Outbox, Command, and ADR 0014 for the one Plugin (`tuya_lan`) that also accepts control.
_Avoid_: Collector, integration, driver

**Ingest**:
The core process that scans the Inbox every **Ingest Interval** (an app-wide, Admin-editable setting, default 5s), validates each Plugin Event against schema, resolves it to the Sensor/Plug row it belongs to, and writes the resulting Reading/Plug State Transition/Data Capture — then evaluates Alert Conditions, the same role `collectors/alerts.py` played inline before ADR 0013. Deliberately not named "Monitor" — a leftover naming choice from when the app itself was called HerpMonitor; kept post-rename since "Ingest" is still the more accurate term for what this process does. Contains no vendor-specific code; adding a Plugin never touches it. Since a Plug's Plugin reports its state on every poll rather than only on change, a slow Ingest Interval only delays when a change is *seen* — it never loses one, unlike a slow BLE registry-refresh interval, which can genuinely miss an irregular broadcast.

**Plugin Event**:
The JSON file a Plugin writes to the Inbox for one observation, validated against `schemas/plugin_event.schema.json` — envelope shape `{schema_version, plugin, kind, external_id, observed_at, payload}`, where `kind` (`sensor_reading`, `plug_state`, `plug_telemetry`) determines the payload's shape. A Plugin never expects to read one back; Ingest consumes and removes each one it processes.

**Inbox**:
The shared directory (`data/inbox/<kind>/`) every Plugin writes Plugin Events into and Ingest alone drains — the Plugin-to-Core half of the filesystem contract described in ADR 0013. See Registry for the Core-to-Plugin half.

**Registry** (as in *the Registry*, not Device Registration):
The JSON file Core exports per Plugin (`data/registry/<plugin>.json`), re-written whenever Device Registration changes, listing exactly which devices that Plugin should watch — each one's External ID and Plugin Config. The Core-to-Plugin half of the filesystem contract; see Inbox for the other direction. A Plugin never queries the database directly to discover what it should watch.

**Outbox**:
The directory (`data/outbox/<plugin>/`) Core writes Commands into for a Plugin to execute — a second, narrower Core-to-Plugin filesystem contract alongside Registry, added by ADR 0014. One file per pending Command, named by External ID so a later Command for the same device supersedes an unprocessed earlier one rather than queuing behind it. Not every Plugin implements it — `govee_ble` is BLE sensors with nothing to actuate, and never reads it.

**Command**:
A one-shot instruction from Core to actuate a Smart Plug's relay right now — turn it on or off — issued by clicking the on/off control wherever a Plug appears (dashboard, Room, Enclosure). Not a held state: Core sends it once and moves on, the same as flipping a physical switch by hand — if the Plug also has its own onboard schedule or a downstream Thermostat-/Hydrostat-Controlled unit, that keeps doing its own thing afterward, Core never re-asserts a Command against it. Delivered to the owning Plugin via the Outbox and executed on the Plugin's own poll cadence; a `Manual Plug` has no Plugin to deliver to, so its Command is a synchronous, self-reported log entry instead — no relay actually changes. Every Command is logged as one `plug_command_log` row, Smart or Manual alike; see Interruption for when it also carries a note. Sending a Command on a Smart Plug that currently has Auto-Update paused resumes Auto-Update as a side effect, rather than its confirmation silently going unrecorded. See ADR 0014.

**Interruption**:
A Command sent to a Plug that has a *determined setting* — a Controller Kind other than `none`, a Target Schedule, or Always On — as opposed to a plain manual toggle on a Plug with none of those. The distinction matters because an Interruption doesn't change the setting itself; it's a deliberate, temporary departure the Plug is expected to return from on its own, worth optionally recording *why* — unlike routine day-to-day switching. Only an Interruption's `plug_command_log` row prompts for an optional, skippable note; a plain toggle never does.

**Supervisor**:
The tray-icon process that starts, stops, restarts, and watches the Website/Ingest/Govee
Plugin/Tuya Plugin processes (`tray/supervisor.py`), replacing `start.bat`'s four visible console
windows as the normal way to run Husbandry Tracker — see ADR 0015. Not a Plugin and not part of the
Inbox/Registry/Outbox contract; it manages OS processes and their log files and never opens the
database itself, with one exception — see Backup, Restore. Its tray menu opens the dashboard, shows
each of the four's status with its own Start/Stop/Restart, offers a "Start with Windows" toggle, and
triggers Backup/Restore.

**Backup**:
A point-in-time copy of `data/husbandrytracker.db` — the single file holding every durable piece of
Husbandry Tracker's state, including Device Registration's Plugin Config (Tuya/Govee credentials), so
restoring one Backup fully recovers a working system, not just readings — written to
`data/backups/` by Ingest (see CONTEXT.md: Ingest; ADR 0019) via SQLite's Online Backup API, which
safely snapshots a database other processes are actively reading/writing. Happens automatically
once a day, and on demand when the Supervisor's "Back Up Now" is clicked — a plain request file
Ingest notices on its next scan, the same filesystem-contract shape as Command/Outbox, deliberately
keeping this out of the Supervisor itself (see Supervisor). Backups older than the retention window
(14 days) are pruned automatically. Distinct from `data/` surviving an uninstall (see ADR 0018) —
that protects a reinstall to the same machine/folder; a Backup is a separate file you could also
copy anywhere else (a USB drive, a synced cloud folder) for real protection against drive failure.

**Restore**:
Replacing the live database with a chosen Backup — the one operation the Supervisor performs that
does touch the database, and only as a plain file copy while every process that could have it open
is stopped first (see Supervisor, ADR 0019), never as a live query. Triggered from the Supervisor's
"Restore from Backup" tray submenu (one item per Backup, newest first), behind a confirmation
dialog. Always safety-backs-up the current database as its own Backup immediately before
overwriting it, so a Restore can itself be undone the same way.

**Reading**:
A single Sensor data point at a point in time — any of the Target Range metrics that Sensor tracks (temperature, humidity, pH, ammonia, ...; see Target Range, Enclosure Type). A `Smart Sensor`'s Readings are collected automatically by the BLE listener (temperature/humidity only — a Govee device has nothing to report for the water-chemistry metrics). A `Manual Sensor`'s Readings are logged by hand through the Dashboard or Admin UI — one value per metric the Sensor actually tracks (has a Target Range configured for) — and, like a Care Event, can be backdated to when the measurement was actually taken instead of being forced to "now".

**Care Event**:
A manually-logged record that a Feeding, Watering, or Cleaning happened for an Enclosure (or, for a Spot-feed, a single Animal within it) at a point in time, backdatable to when it actually happened instead of being forced to "now". The app is both a dashboard (auto-collected Sensor/Schedule data) and a logbook (manually-entered Care Events).

**Feeding / Watering / Cleaning**:
The three kinds of Care Event. Watering and Cleaning are always logged per-Enclosure (not per-Animal), matching the physical action of tending the whole enclosure at once. Feeding is normally per-Enclosure too, but may instead be a Spot-feed — see Spot-feed. Cleaning splits into two distinct sub-kinds: Spot-clean and Deep-clean.

**Spot-feed**:
A Feeding Care Event scoped to one Animal within an Enclosure rather than the whole Enclosure — e.g. dropping an extra pellet for one underweight fish in a community tank. The ordinary (whole-Enclosure) Feeding stays the common case; Spot-feed isn't a fourth kind of Care Event, it's a Feeding with an Animal attached.

**Spot-clean / Deep-clean**:
The two kinds of Cleaning Care Event, tracked and displayed separately with their own Care Interval and staleness color-coding. Spot-clean is routine, frequent maintenance (removing waste, wiping glass). Deep-clean is a full substrate/decor overhaul.

**Enclosure Type**:
A required Enclosure attribute selecting which environmental parameters are relevant to it — checked in code to decide which Sensor Target Range fields and Plug controller setpoints apply, rather than a runtime-configurable parameter list (see decision: real columns gated by Enclosure Type). Four values: `Basic` (snake/lizard/tortoise/insect — temp + humidity only, the common case, since these all share the same monitoring needs), `Freshwater`, `Saltwater` (water-chemistry parameters — pH, salinity, ammonia/nitrite/nitrate, etc.; Saltwater's list is larger than Freshwater's), and `Amphibian` (setups with an aquatic component, e.g. aquatic turtles — a blend of terrestrial and water-chemistry parameters). Independent of Bioactive (see Bioactive), which can combine with any of the four.

**Bioactive**:
A flag on an Enclosure, independent of Enclosure Type, for one whose substrate hosts a live cleanup crew (isopods, springtails, etc.) and live plants that self-sustain the waste cycle. Combinable with any Enclosure Type — a planted Freshwater tank can be Bioactive too, not just a terrestrial Basic vivarium. Gates a longer default Deep-clean Care Interval (Bioactive Enclosures are, by design, spot-cleaned regularly but Deep-cleaned rarely) and the ability to track Plants and log Plant Health (see Plant, Plant Health) on top of whatever its Enclosure Type already provides.

**Care Interval**:
A per-Enclosure configurable number of days (`feeding_interval_days`, default 7; `watering_interval_days`, default 3; `spot_clean_interval_days`; `deep_clean_interval_days`) used to derive the panel's color-coded status for the days elapsed since the last Care Event of that kind. Not a global constant — different Enclosures may have very different intervals by species/life-stage/Bioactive status. Each kind's Dashboard pill is independently opt-in per Enclosure (`show_feeding_on_dashboard`/`show_watering_on_dashboard`/`show_spot_clean_on_dashboard`/`show_deep_clean_on_dashboard`, all default on) — same pattern as Animal/Sensor/Plug's own `show_on_dashboard`, just saved together with the rest of the Enclosure Settings form rather than a standalone toggle, since a Care kind has no per-row edit page of its own. Admin's own Care section always lists all four kinds regardless.

**Refresh**:
A per-Room or per-Enclosure dashboard action that forces a live BLE read from that entity's own Smart Sensor(s) right now, instead of waiting for the next passive broadcast the Govee Plugin happens to hear. Deliberately outside the Plugin/Registry/Inbox/Ingest pipeline (see ADR 0005, reaffirmed by ADR 0013) — `web` runs its own short-lived `BleakScanner` and writes straight to `sensor_reading`, the same as before this pivot; a Refresh-triggered Reading is never a Plugin Event. Scoped strictly to what that entity owns — a Room's Refresh never reaches into its Enclosures' own Sensors, and an Enclosure showing a Fallback Sensor's Reading has no Refresh of its own (use the Room's instead, since that's what actually owns the Sensor). Only shown where at least one Smart Sensor is actually owned — never for Manual Sensors, since there's nothing to broadcast. Waits up to the **Refresh Timeout** (an app-wide, Admin-editable setting, default 30s) before giving up on any Sensor that didn't report in time; whatever did report in that window is still written and shown. Distinct from Probe (Plug-only, see Probe) — Probe borrows this same on-demand-bypass shape (ADR 0005) for a different transport and a different purpose (diagnostic, not a Reading).

**Probe**:
An on-demand, read-only diagnostic query against a Smart Plug's physical device, run from its Edit Plug page — a synchronous local Tuya call (`tinytuya`'s `.status()`) made directly by `web`, mirroring Refresh's bypass-the-pipeline precedent (ADR 0005) rather than the Outbox/Command channel (ADR 0014). Shows the device's full raw response, unfiltered and unlabeled — including any DPS keys belonging to other Plug rows sharing the same physical device (see Plug: multi-outlet setups) — because the point is discovery: firmware or model differences mean the set of readings a given device actually exposes isn't fixed, and can grow or shrink over time. Purely diagnostic and ephemeral — nothing is persisted, unlike Data Capture's routine passive collection — and strictly read-only: Probe can never change a setting, only ask what the Plug itself currently reports. Uses whatever device credentials are currently typed into the Edit Plug form, even if unsaved, so new credentials can be tested before committing them. Never shown for a Manual Plug — there's no physical device to query. See ADR 0016.

**Alert**:
A record that one of a Sensor's or Plug's monitored conditions (see Alert Condition) crossed into an abnormal state, tracked as a state machine per entity+condition — `normal` → `pending` → `alerting` → `resolved` — not a stateless one-shot check. A condition must stay abnormal continuously for the **Alert Debounce** duration before it actually fires (avoids a false alarm from one noisy poll or a momentary blip); once `alerting`, it fires exactly one push notification and stays silent (no repeat spam) until the condition clears, at which point a distinct "resolved" notification fires too. Delivered via **ntfy** (see ADR 0010). Distinct from a Target Range's passive dashboard coloring, which still happens independently and immediately, with no debounce or notification.

**Alert Condition**:
The three kinds of Alert, each scoped to specific entities:
- **Out of Target Range** (Sensor only): a Reading falls outside the Sensor's configured Target Range.
- **Zero Power While On** (Plug only): a Smart Plug's relay reads on but its Data Capture reads ~0W — a burnt-out bulb or failed heating/pump element downstream, regardless of Controller Kind. Never fires while the relay reads off (0W while off is expected, not an anomaly).
- **Unreachable** (Sensor or Plug): the entity's Plugin has reported no observation at all — of any kind, changed or not — in at least the Alert Debounce duration. For a Sensor that's a Reading; for a Plug it's a raw on/off state report, whether or not it changed (see Ingest — Plug state is reported every poll, not just on change, precisely so this stays a plain absence check). A Smart Plug's local poll failing, or a Smart Sensor not broadcasting, both show up the same way: nothing arrives.

**Alert Debounce**:
An app-wide setting (single row on `app_setting`, same pattern as Refresh Timeout), default 10 minutes — the minimum duration an Alert Condition must remain continuously abnormal before it fires. One shared value across all three Alert Conditions, not configured per-kind.

**Target Range**:
A configurable acceptable min–max range (e.g. temp, humidity) attached to a Sensor, used to color-code its current Reading green/yellow/red the same way Care Intervals color-code Feeding/Watering staleness. Optional for a `Smart Sensor` (shows as "not set" until configured). **Required** for a `Manual Sensor` on at least one metric — it can't be saved with no Target Range at all, since a hand-entered Reading with nothing to judge it against isn't useful.
