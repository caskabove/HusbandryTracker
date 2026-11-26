# Kasa/Tapo Plugin, a Plug type on Plug forms, and runtime Plugin Settings

**Status**: accepted

**Context**: Tuya/Gosund was the only Smart Plug option. Its device keys live only in Tuya's
cloud, and getting them needs a Tuya developer project whose free IoT Core trial can only be
extended a limited number of times (see `docs/HOWTO_ADD_GOSUND_PLUG.md`, "The free trial runs
out"). TP-Link's Kasa and Tapo plugs answer on the local network instead: a broadcast finds them,
and the open-source `python-kasa` library reads and switches both families. Newer Kasa firmware and
all Tapo plugs check the owner's TP-Link (app) email and password, but that check happens on the
plug itself over the LAN, with no developer account or trial.

Adding a second plug vendor exposed three gaps:

1. The Add/Edit Plug forms and `create_plug`/`update_plug` assumed every Smart Plug was Tuya
   (`tuya_*` fields only). ADR 0061 already noted that a third vendor would still need its own
   registration fields there.
2. A Plugin's background process never reads the database (ADR 0013), but Kasa/Tapo polling needs
   the TP-Link login at runtime, not just during a Scan. The Plugin Standard said to "ask for it to
   be added to your Registry export", but there was no mechanism.
3. While packaging the new Plugin, we found that an installed (PyInstaller) build couldn't validate
   any Plugin. `schemas/plugin_manifest.schema.json` wasn't bundled, and the Plugin Standard's
   file checks looked for `.py` files on disk, while the installer packs them inside the executable.

**Decision**:

- **New `kasa_lan` device Plugin** (`plugins/kasa_lan/`, `python-kasa>=0.12`). External ID is the
  device's MAC address (stable across DHCP changes), with `#<n>` for outlet *n* of a power strip;
  Plugin Config is only the last-known `{"host"}` and is treated as a hint. The background process
  groups outlets by MAC (one connection per physical device, as `tuya_lan` does), reports
  `plug_state` every 5 seconds, and reports `plug_telemetry` every 2 minutes for models with an
  energy meter. It executes `set_power` Commands at most once. After 3 failed polls it rediscovers
  the MAC by broadcast and uses the new address in memory only. `discover.py` scans the LAN and
  lists each outlet of a strip separately. Bulbs, cameras and hubs are skipped.
- **Plug type on the Plug forms.** A `plug_plugin` select (Tuya / Gosund, TP-Link Kasa / Tapo)
  sits in each Plug form's Smart block. Each vendor's fields are a `[data-plug-hw="<plugin>"]` block,
  and `applyPlugHardware()` in `app.js` shows and enables only the chosen one. Kasa's fields come
  from shared templates (`_plug_type_select.html`, `_kasa_plug_fields.html`).
  `create_plug`/`update_plug` take `plugin` plus `kasa_*` keyword arguments, and Tuya stays the
  default, so every existing caller and test is unchanged. Plug Groups stay Tuya-only: picking a
  Group forces Tuya. A Kasa strip's outlets are registered as separate Plugs. Probe stays
  Tuya-only and says so.
- **Generic Discover button.** `onDiscoverPluginClick(button, plugin)` runs the Plugin's own
  Settings-page scan (`/admin/plugins/<name>/discover`), which now also returns each device's
  `registration_fields`. The Named-devices picker also recognises it, by `data-plugin`. A future
  plug Plugin needs no new JavaScript.
- **Runtime Plugin Settings** (a Plugin Standard change). A manifest setting can be marked
  `"runtime": true`. While the Plugin is Active, Ingest copies only those keys to
  `data/registry/settings/<name>.json`, and removes the file when the Plugin is inactive or nothing
  is saved. Plugins read it with `plugins/common.read_plugin_settings()`. The file lives in a
  subfolder so the Registry's stale-file cleanup can't delete it. Opt-in per key, so a value only
  the web process needs (such as `tuya_lan`'s cloud Access Secret) never lands on disk outside the
  database.
- **Validation works in an installed build.** The manifest schema is bundled. In a frozen build,
  `validate_plugin_dir` looks up a missing `.py` file as a bundled module with
  `importlib.util.find_spec`, which locates it without running it. From a source checkout the
  check is unchanged, and CI still requires the real files. Each Plugin's `discover` module is
  named as a required hidden import, so a broken bundle fails the build rather than the user's
  Scan.

**Consequences**:

- Keepers have a plug option with no cloud developer account. The trade-off is in `kasa_lan`'s
  "can't" list: TP-Link firmware updates have broken local login before, and the fix is upgrading
  `python-kasa`.
- The TP-Link password is stored in `plugin_setting` like every Plugin Setting, and in
  `data/registry/settings/kasa_lan.json` while the Plugin is Active. That's the same protection as
  `tuya_lan`'s local keys, which already sit in its Registry file.
- The Supervisor runs a fifth child process, "Plug Plugin (Kasa/Tapo)"
  (`HusbandryTrackerKasa.exe`). It idles harmlessly when nothing is registered.
- Not yet tested against real Kasa or Tapo hardware. Unit tests use fake python-kasa Devices, and a
  real LAN scan ran cleanly with no devices present.
- Installers built before this change (up to `v1.0.7-beta8`) list every Plugin as Invalid or fail
  to list Plugins at all. Fixed here.
