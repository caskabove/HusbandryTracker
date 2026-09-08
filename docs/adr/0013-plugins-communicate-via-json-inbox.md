# Plugins communicate via JSON files in a shared Inbox, not direct database access

**Status**: accepted — supersedes part of ADR 0001

The requirements doc's original v1 spec (§2.2) called for an MQTT broker + ESP32 BLE proxy for
sensor ingestion, never built; the actual code has `govee_collector.py`/`tuya_collector.py` reading
the `sensor`/`plug` tables directly and writing `sensor_reading`/`plug_state_transition`/
`plug_reading` straight into SQLite themselves — coupling every future integration to this app's
Python and its schema. This ADR replaces both: each vendor/protocol integration is now a **Plugin**
(see CONTEXT.md), an independent process that never touches SQLite. Core exports each Plugin's
device list as `data/registry/<plugin>.json` (Device Registration now maps a Sensor/Plug to a
Plugin, External ID, and Plugin Config — see CONTEXT.md); each Plugin drops one JSON file per
observation into `data/inbox/<kind>/`; a new **Ingest** process scans the Inbox on a preconfigured
interval, validates against schema, resolves `(plugin, external_id)` to the owning Sensor/Plug,
writes the DB row, and evaluates Alert Conditions — the same role `collectors/alerts.py` already
played, just called from Ingest instead of from each collector. The Plugin Event envelope is a real,
machine-readable `schemas/plugin_event.schema.json` (JSON Schema), validated via the `jsonschema`
package — not just documented in prose — so a Plugin author in any language has something concrete
to validate against or generate a client from; this is the one new runtime dependency this decision
introduces. Ingest's scan cadence is a new `app_setting.ingest_scan_interval_seconds` (default 5s,
Admin-editable, same pattern as `ble_refresh_timeout_seconds`) — since Plugins report Plug state on
every poll rather than only on change, a slower Ingest tick only delays when a change is *seen*, it
never loses one.

This is deliberately not literal MQTT: no broker to install, matching this app's local-first/
no-new-dependency philosophy (the same reasoning ADR 0001 used for SQLite over Postgres). It gets
the same decoupling benefit MQTT would have provided — a future MQTT-bridge Plugin (subscribing to
a broker, translating messages into the same JSON contract) could sit behind Ingest later without
Ingest ever changing.

**Considered Options**:
- **Adopt MQTT + ESP32 BLE proxy literally**, per the requirements doc's original v1 spec —
  rejected for now: no ESP32 hardware exists in this collection yet, and it would require running a
  broker process this single-machine, single-user app doesn't otherwise need. Left open as
  something an MQTT-bridge Plugin could add later without touching Ingest.
- **Keep collectors writing directly to the DB, generalize with an in-process plugin interface**
  (e.g. a Python ABC each vendor module implements) — rejected because it still requires every
  Plugin to be Python, in this repo, sharing this schema; the whole point is letting a Plugin be
  written in any language and dropped in without touching core.

**Consequences**: `collectors/govee_collector.py` and `collectors/tuya_collector.py` are renamed to
`plugins/govee_ble/plugin.py` and `plugins/tuya_lan/plugin.py`; `collectors/alerts.py`'s role moves
to a new `ingest/` module, called from Ingest instead of from each Plugin. `sensor.mac_address` and
`plug.tuya_device_id`/`tuya_local_key`/`tuya_ip_address`/`switch_dps_key` are replaced by generic
`plugin`/`external_id`/`plugin_config` columns (see CONTEXT.md: External ID, Plugin Config) —
existing rows are migrated, not dropped. Plug Unreachable changes from an explicit poll-success/
failure signal to a plain absence check (no `plug_state` event in the Alert Debounce window), which
also fixes a standing mismatch between CONTEXT.md's Unreachable definition and the old
implementation. Resolves reqs-alignment-review punch-list item #1 — deliberately not by adopting
MQTT/ESP32 as originally specced (see Considered Options above).
