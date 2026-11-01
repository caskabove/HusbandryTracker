# Retrofit tuya_lan/govee_ble onto the Plugin Contract and real Active Plugin gating

**Status**: accepted — reverses the deferral in ADR 0045

**Context**: ADR 0045 deliberately deferred retrofitting `tuya_lan`/`govee_ble` onto the new
Plugin Contract (`manifest.json`/`init.py`), to avoid stalling the `log_husbandry` Skill on a
change that was really about Plugin infrastructure in general. That left a real gap: neither
Plugin shows up in the Admin Plugins card at all (no `manifest.json`), and — more importantly —
Ingest's Registry export and device-event handling never actually checked Active Plugin status
for them, only for `log_husbandry`. An Admin "Activate"/"Deactivate" button for a device Plugin
with no corresponding runtime effect would be purely decorative, which defeats the point of having
added the concept in the first place.

**Decision**: `tuya_lan` and `govee_ble` each gain a `manifest.json` (`kind: "device"`) and an
`init.py` whose `activate()`/`deactivate()` are both no-ops — there's no install/uninstall side
effect for a device Plugin the way there is for a Skill's Claude Code files, so there's nothing
for either hook to actually do. The real change is in `ingest/ingest.py`:

- `_export_registry()` now only writes a device Plugin's Registry file while it's an Active
  Plugin — not-Active gets the same treatment as "no devices registered to it at all" (file
  removed). Its own stale-file cleanup is also fixed to never touch `log_husbandry.json`
  (`_export_log_husbandry_registry` owns that file; before this change, `_export_registry()` would
  have deleted it as an "orphan" every single scan, immediately undone one function call later —
  harmless by luck of call order in `main()`, but fragile and worth fixing while this code was
  already open).
- `_apply_event` now drops a `sensor_reading`/`plug_state`/`plug_telemetry` event whose Plugin
  isn't Active, silently — the same treatment as an event for a device that was never registered
  at all, since this is routine/high-frequency and "Plugin got deactivated mid-poll" isn't more
  noteworthy than "device got deregistered mid-poll," which this app already doesn't surface.
- `care_event` gains the same Active check, but **raises** instead of silently dropping (the same
  way a stale `enclosure_id`/`animal_id` already does — see ADR 0046) — a Skill deactivated
  between writing an event and Ingest draining it is a specific, human-confirmed action going
  missing, not a routine poll, so it stays visible via quarantine rather than vanishing.

This is safe to do now, with no backward-compatibility concern, because nothing has shipped yet —
confirmed empty `data/active_plugins.json` and no real `data/husbandrytracker.db` in this
environment. A real install would need `tuya_lan`/`govee_ble` added via the Admin Plugins card (or
the eventual Setup Wizard step) before their existing Smart Sensors/Plugs resume updating.

**Considered Options**:
- **Add `manifest.json`/`init.py` without wiring real gating** — rejected: leaves the Admin card's
  Activate/Deactivate buttons for these two doing nothing, which is worse than not having them.
- **Leave the retrofit deferred indefinitely** — rejected once asked for directly; the gap it left
  (gating applying to Skills but not device Plugins, despite ADR 0045's own stated general
  principle) was always meant to be temporary, not a permanent two-tier system.

**Consequences**: `plugins/tuya_lan/manifest.json`, `plugins/tuya_lan/init.py`,
`plugins/govee_ble/manifest.json`, `plugins/govee_ble/init.py` are new; both now appear in the
Admin Plugins card. `ingest/ingest.py` gains an Active-Plugin check at the top of `_apply_event`
for the three device-observation kinds, a `care_event`-specific one, and a device-gated
`_export_registry()` plus the `log_husbandry.json`-preserving fix to its stale-file cleanup. A
device Plugin's richer, originally-envisioned `manifest.json` shape (External ID/Plugin Config
field lists, emitted kinds, `schema_version` — see Plugin Contract) is still not built; only
`name`/`description`/`kind` exist, same as `log_husbandry`'s own.
