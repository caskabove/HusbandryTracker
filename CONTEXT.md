# HerpMonitor

A local-only monitoring and husbandry-tracking system for a reptile collection: environmental readings (temperature, humidity), device schedules (light, heat, cooling), and care events (feeding, watering, cleaning).

## Language

**Enclosure**:
The physical housing unit (tank, tub, rack tray) that an environmental sensor and control devices belong to. The unit of monitoring — temp, humidity, and schedules are properties of the Enclosure, not of any single Animal inside it. May contain one Animal, a pair, or a colony. May optionally belong to a Room (see Room, Fallback Sensor).
_Avoid_: Tank, cage, habitat (use only when quoting a specific product/UI)

**Room**:
A named grouping of Enclosures sharing a physical space (e.g. "Living Room", "Reptile Rack"), with its own ambient Sensor(s) and Light Schedule. Optional — an Enclosure need not belong to one. Unlike an Enclosure, a Room has no Animals, no Bioactive flag, and no Care Events; it exists purely to group Enclosures on the dashboard and to monitor/schedule the shared space around them.

**Animal**:
An individual reptile with a name, species (common + scientific name), and DOB. Belongs to exactly one Enclosure. An Enclosure panel displays all Animals housed in it.
_Avoid_: Pet, specimen

**Plant**:
An individual live plant tracked within a Bioactive Enclosure, with a name and species (optional) — analogous to Animal, but only creatable on an Enclosure with Bioactive set. Not required: a Bioactive Enclosure's plants can be logged purely at the Enclosure level (see Plant Health) without ever naming an individual Plant.

**Plant Health**:
A manually-logged, backdatable observation about a Bioactive Enclosure's plants (e.g. "pothos yellowing, moved out of direct light") — scoped to either the Enclosure as a whole or one specific Plant, at the logger's choice. Not a Care Event: it's a status observation, not an action performed, and lives in its own table rather than stacking a second conditionally-valid entity reference onto `care_event` alongside Spot-feed's `animal_id`.

**Sensor**:
An environmental monitor assigned to either an Enclosure or a Room (never both), in one of two Tracking Modes: a `Smart Sensor` is a Govee H5074 BLE temp/humidity device, polled automatically; a `Manual Sensor` has no physical device behind it — its Readings are logged by hand, and it must have a complete Target Range set on at least one metric (there's nothing to judge a hand-entered value against otherwise). An Enclosure or a Room may have more than one Sensor (e.g. an Enclosure's warm-side/cool-side gradient, or a Room with one Sensor near a window and one near a door).
_Avoid_: Hygrometer, thermometer (use Sensor as the umbrella term)

**Fallback Sensor**:
The specific Sensor an Enclosure with no Sensor of its own points to instead, chosen from its Room's Sensors — the choice accounts for where that Enclosure actually sits in the Room (nearer the window vs. the door, say), rather than always using the same one. Only available once the Enclosure belongs to a Room. Its Reading shows on that Enclosure's panel raw and uncolored, clearly labeled with its source — never judged against a Target Range, since a Room's Target Range reflects human comfort, not what's healthy for that specific animal.

**Plug**:
A device controlling a light/heat/cooling/etc. source, tagged with a Purpose, in one of two Tracking Modes: a `Smart Plug` is a Tuya-controlled Gosund smart plug, polled automatically; a `Manual Plug` has no device credentials — it's switched by hand (e.g. a mechanical timer) and carries a Declared Schedule instead. A Plug belongs to either **one Room**, or **one-or-more Enclosures** — never both, never neither. Most Plugs serve exactly one Enclosure; a single physical switch controlling several tubs at once (common in smaller collections — "everything on one switch") is the same Plug linked to each of them, sharing one Purpose/Tracking Mode/Schedule since it's the same physical device doing the same physical thing for all of them. A Room-owned Plug is for a genuinely room-wide fixture (a rack's ambient light) rather than anything tied to specific Enclosures. Independently of Tracking Mode, a Plug also has a **Controller Kind** (see Controller Kind) describing what's downstream of the relay.
_Avoid_: Outlet, switch

**Purpose**:
The role a Plug serves — a free-text label (e.g. "light", "heat", "cooling", "UVB", "pump"), not a fixed set. Admin suggests the common ones but any value is valid, since husbandry setups use plugs for things beyond climate control (misting pumps, UVB fixtures distinct from general lighting, etc.). One Plug has exactly one Purpose, regardless of Tracking Mode or how many Enclosures it serves.

**Unassigned**:
A real Enclosure, always present, used as a holding pen for a Plug that doesn't (yet, or anymore) belong anywhere real — a newly-discovered Smart Plug not yet assigned to its actual Enclosure(s), or a Plug that just lost its last Enclosure link because that Enclosure was deleted. Keeps the Plug's credentials/history intact rather than losing them, ready to be reassigned through the normal Admin edit flow. Not a Room — an Unassigned Plug isn't grouped by physical space, it's explicitly "not placed yet."

**Tracking Mode**:
Whether a Sensor or Plug is watched by real hardware or tracked by hand — `Smart` (a real device exists and is polled automatically) or `Manual` (no device credentials; a person enters what's happening instead). Set independently per Sensor and per Plug, and changeable later without losing the row's history if the underlying hardware is swapped out (a smart plug replaced by a mechanical timer, or vice versa).

**Device Registration**:
The manual, admin-screen setup of a Sensor or Plug. For a `Smart` one, this maps its hardware identifier (Govee MAC address, Tuya `device_id`) to the Enclosure (and, for Plugs, Purpose) it belongs to. For a `Manual` one, there's no hardware identifier to map — just the Enclosure, Purpose/label, and (Target Range or Declared Schedule). A one-time setup step per Sensor/Plug, not an auto-discovery/pairing flow — edited only when hardware is added, swapped, or Tracking Mode changes.

**Schedule**:
A Plug's on-time and off-time. For a `Smart Plug` this is **Inferred** — derived statistically from observed relay-state transitions rather than read from Google Home's routine configuration; lags behind changes made in Google Home, not a guaranteed-accurate value. For a `Manual Plug` this is **Declared** — entered directly by whoever set the physical timer, since there's nothing to observe. A Declared Schedule is shown plainly, with no claim about whether the Plug is actually on right now — it assumes the timer is working correctly, which is never verified.
_Avoid_: Routine (that's Google Home's term for the thing that produces the state changes we observe). Not shown at all for a Plug with a Controller Kind set — see Controller Kind.

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
A Plug's captured telemetry snapshot — current wattage/voltage/current draw, and any active countdown timer — pulled from the same local Tuya status call the on/off poll already makes. The Plug-side equivalent of a Sensor's Reading. Written on a slower, independent cadence (every 1-5 minutes) from the 5-second on/off Plug State Transition watch, since wattage drifts continuously while a transition is edge-triggered (only recorded when on/off actually flips).

**Auto-Update**:
A per-Sensor or per-Plug toggle, meaningful only for a `Smart` Sensor/Plug, that pauses automatic background collection (Readings for a Sensor; Plug State Transitions and Data Captures for a Plug) without changing Tracking Mode or losing device credentials/history. Distinct from Refresh, which is a one-off manual pull on demand — Auto-Update is an ongoing on/off state, for silencing a flaky or temporarily-irrelevant device (e.g. unplugged for the season) without deregistering it. Default on.

**Reading**:
A single Sensor data point (temperature and/or humidity) at a point in time. A `Smart Sensor`'s Readings are collected automatically by the BLE listener. A `Manual Sensor`'s Readings are logged by hand through the Admin UI — one value per metric the Sensor actually tracks — and, like a Care Event, can be backdated to when the measurement was actually taken instead of being forced to "now".

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
A per-Enclosure configurable number of days (`feeding_interval_days`, default 7; `watering_interval_days`, default 3; `spot_clean_interval_days`; `deep_clean_interval_days`) used to derive the panel's color-coded status for the days elapsed since the last Care Event of that kind. Not a global constant — different Enclosures may have very different intervals by species/life-stage/Bioactive status.

**Refresh**:
A per-Room or per-Enclosure dashboard action that forces a live BLE read from that entity's own Smart Sensor(s) right now, instead of waiting for the next passive broadcast the collector happens to hear. Scoped strictly to what that entity owns — a Room's Refresh never reaches into its Enclosures' own Sensors, and an Enclosure showing a Fallback Sensor's Reading has no Refresh of its own (use the Room's instead, since that's what actually owns the Sensor). Only shown where at least one Smart Sensor is actually owned — never for Manual Sensors, since there's nothing to broadcast. Waits up to the **Refresh Timeout** (an app-wide, Admin-editable setting, default 30s) before giving up on any Sensor that didn't report in time; whatever did report in that window is still written and shown.

**Alert**:
A record that one of a Sensor's or Plug's monitored conditions (see Alert Condition) crossed into an abnormal state, tracked as a state machine per entity+condition — `normal` → `pending` → `alerting` → `resolved` — not a stateless one-shot check. A condition must stay abnormal continuously for the **Alert Debounce** duration before it actually fires (avoids a false alarm from one noisy poll or a momentary blip); once `alerting`, it fires exactly one push notification and stays silent (no repeat spam) until the condition clears, at which point a distinct "resolved" notification fires too. Delivered via **ntfy** (see ADR 0010). Distinct from a Target Range's passive dashboard coloring, which still happens independently and immediately, with no debounce or notification.

**Alert Condition**:
The three kinds of Alert, each scoped to specific entities:
- **Out of Target Range** (Sensor only): a Reading falls outside the Sensor's configured Target Range.
- **Zero Power While On** (Plug only): a Smart Plug's relay reads on but its Data Capture reads ~0W — a burnt-out bulb or failed heating/pump element downstream, regardless of Controller Kind. Never fires while the relay reads off (0W while off is expected, not an anomaly).
- **Unreachable** (Sensor or Plug): no successful Reading/Data Capture has been collected for the entity in at least the Alert Debounce duration — a Smart Plug's local poll is failing, or a Smart Sensor hasn't broadcast in that window.

**Alert Debounce**:
An app-wide setting (single row on `app_setting`, same pattern as Refresh Timeout), default 10 minutes — the minimum duration an Alert Condition must remain continuously abnormal before it fires. One shared value across all three Alert Conditions, not configured per-kind.

**Target Range**:
A configurable acceptable min–max range (e.g. temp, humidity) attached to a Sensor, used to color-code its current Reading green/yellow/red the same way Care Intervals color-code Feeding/Watering staleness. Optional for a `Smart Sensor` (shows as "not set" until configured). **Required** for a `Manual Sensor` on at least one metric — it can't be saved with no Target Range at all, since a hand-entered Reading with nothing to judge it against isn't useful.
