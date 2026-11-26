# Plugin Settings pages, Known Devices, and an enforced Plugin Standard

**Status**: accepted

**Context**: The Admin Plugins card mixed directory, explanation, and controls in one table row:
an Activate/Deactivate button plus a sentence or two of fine print. Users found it confusing. It
said nothing about what a Plugin could or couldn't do, and vendor settings lived elsewhere (the
Tuya Cloud Credentials card on Admin, written specifically for Tuya). Device discovery existed only
inside the Add Sensor/Add Plug forms, so there was no single place to see every reachable device,
and no way to name one before deciding which Enclosure it belonged to. `manifest.json` held only
`name`/`description`/`kind`, and nothing checked that a new Plugin folder followed the Plugin
Contract. The richer manifest ADR 0014 and requirements §9.14 anticipated was still open (see
CONTEXT.md, Plugin Contract).

**Decision**:

- **Each Plugin gets its own Settings page** at `/admin/plugins/<name>`. The Plugins card on Admin
  becomes a directory: display name, kind, one-line description, status (Active/Inactive/Invalid),
  and a **Settings** link. Activate/Deactivate moves onto the Settings page, next to the
  explanation of what changes when you do it.
- **The manifest grows into the Plugin Standard** (`schemas/plugin_manifest.schema.json`,
  `docs/plugin-standard.md`). New required fields: `schema_version`, `display_name`, `version`,
  `how_it_works`, `can`, `cannot`, `entry_point`, and `device_types` for device Plugins. New
  optional fields: `discovery`, `settings`, `setup_help`. The Settings page is rendered entirely
  from the manifest, with no per-vendor template code.
- **The standard is enforced.** `web/plugin_catalog.py` validates every Plugin-shaped folder
  (any folder holding `manifest.json`, `init.py` or `plugin.py`) on every listing. A folder that
  fails is still listed, as **Invalid** with its reasons, rather than hidden. It can't be
  activated, but it can always be deactivated so a broken Plugin can be switched off. A test
  fails CI if any folder under `plugins/` doesn't conform. Validation never imports Plugin code;
  only Activate, Scan, and the Add-form pick-list do.
- **Discovery becomes part of the Plugin**, as an optional `discover.py` exposing
  `async discover(settings) -> list[dict]` (plus an optional `registration_fields()` that maps a
  device onto the Add form's fields). Like `init.py`, it runs in the web process. This is a
  deliberate, narrow exception to "a Plugin only talks to Core through files": it's read-only,
  user-initiated, and short-lived, and it needs to return an answer to the click that started it.
  `govee_ble`/`tuya_lan` wrap the existing `web/govee_refresh.py`/`web/tuya_discover.py` lookups, so
  Govee keeps sharing the one BLE lock with Refresh. The Add forms' own Discover Devices buttons are
  unchanged.
- **Known Device**: a new `known_device` table holding (plugin, external_id, name, plugin_config,
  summary, last_seen_at). The Settings page's Scan lists everything reachable and lets the user name
  each device. That is separate from Device Registration, which still happens on Add Sensor/Add Plug
  because it needs an Enclosure/Room, Purpose, and Targets. Those forms gain a **Named devices**
  pick-list that fills in the IDs/keys and the Label. The Settings page also lists every registered
  Sensor/Plug on the Plugin, named or not, so it's the one place every device can be renamed.
  Renaming a registered one writes its `sensor.label`/`plug.label` too, and that label stays the
  name of record. Forgetting a Known Device never touches a registered row. It's matched by
  (plugin, external_id), not a foreign key, since either can exist without the other.
- **Plugin Settings**: a generic `plugin_setting (plugin, key, value)` table holds whatever a
  manifest's `settings` declares. A `secret` is never rendered back, and leaving it blank keeps the
  saved value (the same rule ADR 0030 set for the Tuya Access Secret). The Tuya Cloud Credentials
  move here as `tuya_lan`'s `access_id`/`access_secret`/`api_region`: migration 33 copies them over,
  and the Admin card is removed. The old `app_setting.tuya_*` columns stay in place, unread.

**Consequences**:

- A new vendor integration now needs no Core template or settings code: a conforming folder gets a
  Settings page, a settings form, and (with `discover.py`) a Scan and named-device picker for free.
  The Add Sensor/Add Plug forms are still per-vendor (`mac_address`, `tuya_*` fields), so a third
  vendor still needs its own registration fields there. `registration_fields()` is what lets the
  pick-list fill them without Core decoding an External ID.
- A third-party Plugin written in another language can still run its background process in any
  language, but `init.py` and `discover.py` must be Python, since they're imported in-process.
- Existing installs keep their Tuya credentials across the upgrade. Anyone who bookmarked
  `/admin/app#tuya-cloud-credentials` lands on Admin without that card.
- The pick-list is injected by `app.js` beside every existing Discover Devices button, rather than
  edited into each of the Add-form templates (Plugs and Sensors, Room, Admin, Edit pages). It only
  appears when the Plugin has named, unregistered devices.
