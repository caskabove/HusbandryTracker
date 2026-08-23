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
A Govee H5074 BLE temp/humidity device assigned to an Enclosure. An Enclosure may have more than one Sensor (e.g. warm-side/cool-side gradient).
_Avoid_: Hygrometer, thermometer (use Sensor as the umbrella term)

**Plug**:
A Gosund smart plug assigned to an Enclosure, tagged with a Purpose (light / heat / cooling). An Enclosure may have more than one Plug.
_Avoid_: Outlet, switch

**Purpose**:
The role a Plug serves for its Enclosure: light, heat, or cooling. One Plug has exactly one Purpose.

**Device Registration**:
The manual, admin-screen mapping of a physical device's hardware identifier (Govee MAC address, Tuya `device_id`) to the Enclosure (and, for Plugs, Purpose) it belongs to. A one-time setup step per device, not an auto-discovery/pairing flow — edited only when hardware is added or swapped.

**Schedule**:
A Plug's on-time and duration, derived from observed relay-state transitions (on/off history) rather than read from Google Home's routine configuration. Statistical/typical, not a guaranteed-accurate config value; lags behind changes made in Google Home.
_Avoid_: Routine (that's Google Home's term for the thing that produces the state changes we observe)

**Care Event**:
A manually-logged record that a Feeding, Watering, or Cleaning happened for an Enclosure at a point in time. The app is both a dashboard (auto-collected Sensor/Schedule data) and a logbook (manually-entered Care Events).

**Feeding / Watering / Cleaning**:
The three kinds of Care Event, each logged per-Enclosure (not per-Animal), matching the physical action of tending the whole enclosure at once. Cleaning splits into two distinct sub-kinds: Spot-clean and Deep-clean.

**Spot-clean / Deep-clean**:
The two kinds of Cleaning Care Event, tracked and displayed separately with their own Care Interval and staleness color-coding. Spot-clean is routine, frequent maintenance (removing waste, wiping glass). Deep-clean is a full substrate/decor overhaul.

**Bioactive**:
An informational flag on an Enclosure whose substrate hosts a live cleanup crew (isopods, springtails, etc.) and live plants that self-sustain the waste cycle. Bioactive Enclosures are, by design, spot-cleaned regularly but Deep-cleaned rarely — that reality is captured entirely by setting a longer Deep-clean Care Interval on that Enclosure, not by any special-cased behavior keyed off the flag itself.

**Care Interval**:
A per-Enclosure configurable number of days (`feeding_interval_days`, default 7; `watering_interval_days`, default 3; `spot_clean_interval_days`; `deep_clean_interval_days`) used to derive the panel's color-coded status for the days elapsed since the last Care Event of that kind. Not a global constant — different Enclosures may have very different intervals by species/life-stage/Bioactive status.

**Target Range**:
A configurable acceptable min–max range (e.g. temp, humidity) attached to a Sensor, used to color-code its current reading green/yellow/red the same way Care Intervals color-code Feeding/Watering staleness.
