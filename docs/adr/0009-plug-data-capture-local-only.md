# Plug Data Capture stays local — no Tuya Cloud API integration

**Status**: accepted

ADR 0001 chose local Tuya (`tinytuya`, LAN, `local_key`) specifically for the single-machine,
low-dependency deployment target; `tuya_collector.py` already polls each Smart Plug's local
`device.status()` every 5 seconds and already receives the full `dps` dict back, but only reads the
switch key — `cur_power`/`cur_voltage`/`cur_current`/`countdown_1` arrive in that same response
today and are discarded. Separately, the Tuya Cloud IoT API (`GET /v1.0/devices`,
`/v1.0/iot-03/devices/{id}/report-logs`, timer endpoints) was raised as an option — it would add
historical logs and visibility into the user's Tuya-app-configured schedules, but requires cloud
`client_id`/`secret` credentials and an external HTTPS dependency this app has never had.

Decision: extend the existing local poll to also read and store the telemetry DPS values already
being fetched, on a slower cadence (1-5 minutes) independent of the 5-second edge-triggered
`plug_state_transition` watch, since wattage drifts continuously while on/off is a discrete edge.
Do **not** add Tuya Cloud API integration now — it solves problems (multi-week power history, reading
Tuya-app timers) nobody has asked for yet, at the cost of a new credential-management surface that
cuts against ADR 0001's original reasoning.

**Consequences**: new `plug_reading` table (mirroring `sensor_reading`) written by
`tuya_collector.py` on its own timer, distinct from the transition-watch loop. `cur_power` reading
~0 while the switch DPS reads on becomes the basis for the Zero Power While On Alert Condition (see
`CONTEXT.md`: Alert Condition; ADR 0010). Revisit Cloud API only if a real need for historical
graphs or reading the user's existing Tuya-app schedules actually shows up — not before.
