# HerpMonitor

A local-only monitoring and husbandry-tracking system for a reptile collection: environmental readings (temperature, humidity), device schedules (light, heat, cooling), and care events (feeding, watering, cleaning).

## Language

**Enclosure**:
The physical housing unit (tank, tub, rack tray) that an environmental sensor and control devices belong to. The unit of monitoring — temp, humidity, and schedules are properties of the Enclosure, not of any single Animal inside it. May contain one Animal, a pair, or a colony.
_Avoid_: Tank, cage, habitat (use only when quoting a specific product/UI)

**Animal**:
An individual reptile with a name, species (common + scientific name), and DOB. Belongs to exactly one Enclosure. An Enclosure panel displays all Animals housed in it.
_Avoid_: Pet, specimen

**Sensor**:
An environmental monitor assigned to an Enclosure, in one of two Tracking Modes: a `Smart Sensor` is a Govee H5074 BLE temp/humidity device, polled automatically; a `Manual Sensor` has no physical device behind it — its Readings are logged by hand, and it must have a complete Target Range set on at least one metric (there's nothing to judge a hand-entered value against otherwise). An Enclosure may have more than one Sensor (e.g. warm-side/cool-side gradient, or a Smart Sensor for ambient plus a Manual Sensor for basking-spot checks).
_Avoid_: Hygrometer, thermometer (use Sensor as the umbrella term)

**Plug**:
A device controlling a light/heat/cooling/etc. source for an Enclosure, tagged with a Purpose, in one of two Tracking Modes: a `Smart Plug` is a Tuya-controlled Gosund smart plug, polled automatically; a `Manual Plug` has no device credentials — it's switched by hand (e.g. a mechanical timer) and carries a Declared Schedule instead. An Enclosure may have more than one Plug.
_Avoid_: Outlet, switch

**Purpose**:
The role a Plug serves for its Enclosure — a free-text label (e.g. "light", "heat", "cooling", "UVB", "pump"), not a fixed set. Admin suggests the common ones but any value is valid, since husbandry setups use plugs for things beyond climate control (misting pumps, UVB fixtures distinct from general lighting, etc.). One Plug has exactly one Purpose, regardless of Tracking Mode.

**Tracking Mode**:
Whether a Sensor or Plug is watched by real hardware or tracked by hand — `Smart` (a real device exists and is polled automatically) or `Manual` (no device credentials; a person enters what's happening instead). Set independently per Sensor and per Plug, and changeable later without losing the row's history if the underlying hardware is swapped out (a smart plug replaced by a mechanical timer, or vice versa).

**Device Registration**:
The manual, admin-screen setup of a Sensor or Plug. For a `Smart` one, this maps its hardware identifier (Govee MAC address, Tuya `device_id`) to the Enclosure (and, for Plugs, Purpose) it belongs to. For a `Manual` one, there's no hardware identifier to map — just the Enclosure, Purpose/label, and (Target Range or Declared Schedule). A one-time setup step per Sensor/Plug, not an auto-discovery/pairing flow — edited only when hardware is added, swapped, or Tracking Mode changes.

**Schedule**:
A Plug's on-time and off-time. For a `Smart Plug` this is **Inferred** — derived statistically from observed relay-state transitions rather than read from Google Home's routine configuration; lags behind changes made in Google Home, not a guaranteed-accurate value. For a `Manual Plug` this is **Declared** — entered directly by whoever set the physical timer, since there's nothing to observe. A Declared Schedule is shown plainly, with no claim about whether the Plug is actually on right now — it assumes the timer is working correctly, which is never verified.
_Avoid_: Routine (that's Google Home's term for the thing that produces the state changes we observe)

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

**Target Range**:
A configurable acceptable min–max range (e.g. temp, humidity) attached to a Sensor, used to color-code its current Reading green/yellow/red the same way Care Intervals color-code Feeding/Watering staleness. Optional for a `Smart Sensor` (shows as "not set" until configured). **Required** for a `Manual Sensor` on at least one metric — it can't be saved with no Target Range at all, since a hand-entered Reading with nothing to judge it against isn't useful.
