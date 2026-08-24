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

**Sensor**:
An environmental monitor assigned to either an Enclosure or a Room (never both), in one of two Tracking Modes: a `Smart Sensor` is a Govee H5074 BLE temp/humidity device, polled automatically; a `Manual Sensor` has no physical device behind it — its Readings are logged by hand, and it must have a complete Target Range set on at least one metric (there's nothing to judge a hand-entered value against otherwise). An Enclosure or a Room may have more than one Sensor (e.g. an Enclosure's warm-side/cool-side gradient, or a Room with one Sensor near a window and one near a door).
_Avoid_: Hygrometer, thermometer (use Sensor as the umbrella term)

**Fallback Sensor**:
The specific Sensor an Enclosure with no Sensor of its own points to instead, chosen from its Room's Sensors — the choice accounts for where that Enclosure actually sits in the Room (nearer the window vs. the door, say), rather than always using the same one. Only available once the Enclosure belongs to a Room. Its Reading shows on that Enclosure's panel raw and uncolored, clearly labeled with its source — never judged against a Target Range, since a Room's Target Range reflects human comfort, not what's healthy for that specific animal.

**Plug**:
A device controlling a light/heat/cooling/etc. source, tagged with a Purpose, in one of two Tracking Modes: a `Smart Plug` is a Tuya-controlled Gosund smart plug, polled automatically; a `Manual Plug` has no device credentials — it's switched by hand (e.g. a mechanical timer) and carries a Declared Schedule instead. A Plug belongs to either **one Room**, or **one-or-more Enclosures** — never both, never neither. Most Plugs serve exactly one Enclosure; a single physical switch controlling several tubs at once (common in smaller collections — "everything on one switch") is the same Plug linked to each of them, sharing one Purpose/Tracking Mode/Schedule since it's the same physical device doing the same physical thing for all of them. A Room-owned Plug is for a genuinely room-wide fixture (a rack's ambient light) rather than anything tied to specific Enclosures.
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
_Avoid_: Routine (that's Google Home's term for the thing that produces the state changes we observe)

**Light Schedule**:
A Room's on-time and off-time for its general lighting, entered directly since there's no device to observe, plus an optional free-text note for anything else worth capturing (e.g. "natural light from east window", "dimmed after 6pm"). Distinct from a Plug's Schedule — a Light Schedule isn't tied to any specific Plug/device, it describes the Room as a whole.
_Avoid_: Schedule alone (that term is reserved for a Plug's on/off tracking, Inferred or Declared)

**Reading**:
A single Sensor data point (temperature and/or humidity) at a point in time. A `Smart Sensor`'s Readings are collected automatically by the BLE listener. A `Manual Sensor`'s Readings are logged by hand through the Admin UI — one value per metric the Sensor actually tracks — and, like a Care Event, can be backdated to when the measurement was actually taken instead of being forced to "now".

**Care Event**:
A manually-logged record that a Feeding, Watering, or Cleaning happened for an Enclosure at a point in time, backdatable to when it actually happened instead of being forced to "now". The app is both a dashboard (auto-collected Sensor/Schedule data) and a logbook (manually-entered Care Events).

**Feeding / Watering / Cleaning**:
The three kinds of Care Event, each logged per-Enclosure (not per-Animal), matching the physical action of tending the whole enclosure at once. Cleaning splits into two distinct sub-kinds: Spot-clean and Deep-clean.

**Spot-clean / Deep-clean**:
The two kinds of Cleaning Care Event, tracked and displayed separately with their own Care Interval and staleness color-coding. Spot-clean is routine, frequent maintenance (removing waste, wiping glass). Deep-clean is a full substrate/decor overhaul.

**Bioactive**:
An informational flag on an Enclosure whose substrate hosts a live cleanup crew (isopods, springtails, etc.) and live plants that self-sustain the waste cycle. Bioactive Enclosures are, by design, spot-cleaned regularly but Deep-cleaned rarely — that reality is captured entirely by setting a longer Deep-clean Care Interval on that Enclosure, not by any special-cased behavior keyed off the flag itself.

**Care Interval**:
A per-Enclosure configurable number of days (`feeding_interval_days`, default 7; `watering_interval_days`, default 3; `spot_clean_interval_days`; `deep_clean_interval_days`) used to derive the panel's color-coded status for the days elapsed since the last Care Event of that kind. Not a global constant — different Enclosures may have very different intervals by species/life-stage/Bioactive status.

**Refresh**:
A per-Room or per-Enclosure dashboard action that forces a live BLE read from that entity's own Smart Sensor(s) right now, instead of waiting for the next passive broadcast the collector happens to hear. Scoped strictly to what that entity owns — a Room's Refresh never reaches into its Enclosures' own Sensors, and an Enclosure showing a Fallback Sensor's Reading has no Refresh of its own (use the Room's instead, since that's what actually owns the Sensor). Only shown where at least one Smart Sensor is actually owned — never for Manual Sensors, since there's nothing to broadcast. Waits up to the **Refresh Timeout** (an app-wide, Admin-editable setting, default 30s) before giving up on any Sensor that didn't report in time; whatever did report in that window is still written and shown.

**Target Range**:
A configurable acceptable min–max range (e.g. temp, humidity) attached to a Sensor, used to color-code its current Reading green/yellow/red the same way Care Intervals color-code Feeding/Watering staleness. Optional for a `Smart Sensor` (shows as "not set" until configured). **Required** for a `Manual Sensor` on at least one metric — it can't be saved with no Target Range at all, since a hand-entered Reading with nothing to judge it against isn't useful.
