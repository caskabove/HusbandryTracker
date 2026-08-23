# Manual Tracking Mode for Plug and Sensor

**Status**: accepted

Not every Plug is Tuya-controlled and not every Sensor is a Govee BLE device — some enclosures use a
physical mechanical timer, or a handheld thermometer/moisture meter for occasional spot-checks, instead.
Rather than build two separate, differently-shaped features for that, both entities gain a shared
**Tracking Mode** (`Smart`/`Manual` — see `CONTEXT.md`), switchable after creation without losing the
row's id or history if the underlying hardware is later swapped.

A `Manual Plug` carries a **Declared Schedule** (on-time/off-time entered directly by whoever set the
timer) instead of an Inferred one, since there's nothing to observe. The dashboard shows it plainly with
no claim about the Plug's actual current state — a Declared Schedule assumes the timer is working
correctly, which is never verified, the same way even a Smart Plug's Inferred Schedule is documented as
statistical rather than guaranteed.

A `Manual Sensor` reuses the existing `sensor_reading` table for hand-logged Readings rather than a new
table, and must have a complete Target Range on at least one metric (temp or humidity) before it can be
saved.

Two alternatives were rejected:
- **Logging every Manual Plug on/off flip** (mirroring `plug_state_transition`) instead of a single
  Declared Schedule — rejected because nobody wants to hand-log a light switch multiple times a day; a
  declared on-time/off-time captures what a manual timer actually does with one data entry, not a
  running log.
- **Requiring both temp and humidity ranges on every Manual Sensor** — rejected because real spot-check
  tools are often single-metric (an IR thermometer has no humidity reading to give), and forcing a
  number for the unmeasured metric would just be noise.

**Consequences**: `plug.tuya_device_id`/`tuya_local_key` and `sensor.mac_address` become nullable,
enforced instead by a CHECK tied to `tracking_mode`. The Tuya/Govee collectors and the CLI registration
tools (`tools/register_device.py`, `tools/tuya_probe.py`, `tools/govee_discover.py`) stay Smart-only —
there's no hardware for them to discover or poll on a Manual entity, so Manual Plug/Sensor creation is
Admin-UI-only. Logging a Care Event or a Reading can now be backdated via a `datetime-local` picker
instead of always being "now"; viewing/editing already-logged entries is explicitly deferred, not built
here — the schema doesn't preclude it later (plain rows with a mutable timestamp), it's just not exposed
in the UI yet.
