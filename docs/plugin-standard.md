# The Plugin Standard

Every Plugin lives in its own folder under `plugins/<name>/` and must follow this standard before
Husbandry Tracker will activate it. Admin lists any folder that doesn't conform as **Invalid**,
shows the reasons on its Settings page, and refuses to activate it. `tests/test_plugin_pages.py`
(`test_every_plugin_folder_meets_the_standard`) fails CI for the same reasons, so a broken Plugin
can't be merged either.

The rules are checked by `web/plugin_catalog.py`'s `validate_plugin_dir()` against
`schemas/plugin_manifest.schema.json`. That schema is the source of truth; this page explains it.
See ADR 0061 for why it's shaped this way, and `CONTEXT.md` for the terms (Plugin, Skill, Registry,
Inbox, Outbox, Known Device).

## 1. Pick a name

- Lowercase `snake_case`, 2–40 characters, starting with a letter: `^[a-z][a-z0-9_]{1,39}$`.
- Name it after the vendor and the transport, e.g. `govee_ble`, `tuya_lan`, `shelly_http`.
- The folder name, `manifest.json`'s `name`, the Python package, the Registry file
  (`data/registry/<name>.json`), the Outbox folder, and the `plugin` value stored on every
  Sensor/Plug are all this same string. **Never rename a shipped Plugin**: every Sensor/Plug
  registered against it would be orphaned.

## 2. Required files

```
plugins/<name>/
├── __init__.py        empty; makes the folder an importable package
├── manifest.json      what the Plugin is (section 3)
├── init.py            activate() / deactivate() hooks (section 4)
├── <entry_point>      the Plugin itself: plugin.py for a device Plugin, skill/SKILL.md for a Skill
├── discover.py        only if manifest.json has "discovery" (section 5), and required if it does
└── identity.py        recommended for device Plugins: encode/decode your External ID in one place
```

## 3. `manifest.json`

| Field | Required | Notes |
|---|---|---|
| `schema_version` | yes | Always `1` for now. |
| `name` | yes | Must equal the folder name. |
| `display_name` | yes | Human name shown in Admin, e.g. "Govee Bluetooth Sensors". At most 60 characters. |
| `version` | yes | `MAJOR.MINOR.PATCH`. Bump it when behavior changes. |
| `kind` | yes | `"device"` (talks to hardware) or `"skill"` (no devices: see CONTEXT.md, Skill). |
| `description` | yes | One line for the Plugins card. At most 200 characters. |
| `how_it_works` | yes | A short paragraph for the Settings page: how it reaches devices, and what it needs from the user (Bluetooth, an account, the same Wi-Fi). Write it for a keeper, not a developer. |
| `can` | yes | At least one item. Concrete abilities, e.g. "Turn a Plug on or off when you click its control." |
| `cannot` | yes | At least one item. Honest limits a user would otherwise trip over: range, accounts, models it won't read, things it can't control. This list matters as much as `can`. |
| `device_types` | device: yes | `["sensor"]`, `["plug"]`, or both. A Skill leaves it out or uses `[]`. |
| `entry_point` | yes | Path to the Plugin file, relative to the folder. Must exist. |
| `discovery` | no | `{"button_label", "duration_hint"?, "requires_settings"?}`. Include it only if you ship `discover.py`. Not allowed on a Skill. Every key in `requires_settings` must be one of your `settings`. |
| `settings` | no | The Plugin's own settings fields (section 6). |
| `setup_help` | no | Ordered steps shown above the settings form, e.g. where to get an API key. |

No other top-level fields are allowed. If you need a new one, change the schema in the same change
and say why in an ADR.

## 4. `init.py`

```python
def activate() -> None: ...
def deactivate() -> None: ...
```

- Runs **inside the web process**, synchronously, when an admin clicks Activate/Deactivate on the
  Plugin's Settings page.
- `activate()` runs **before** the Plugin is added to `data/active_plugins.json`. If it raises, the
  Plugin stays inactive and the error message is shown to the user, so make it readable.
- `deactivate()` is the exact inverse, and must succeed even if `activate()` never ran.
- A device Plugin's hooks are normally no-ops (`pass`). A Skill installs and removes its files here.
- Never touch the database here.

## 5. `discover.py` (optional): finding reachable devices

Ship this if your Plugin can list devices before they're registered. It powers the Scan button on
the Plugin's Settings page, where the user names each device it finds (a **Known Device**), and
the **Named devices** pick-list on the Add Sensor/Add Plug forms.

```python
async def discover(settings: dict[str, str]) -> list[dict]:
    """settings: this Plugin's saved settings values, secrets included."""
    return [{
        "external_id": "AA:BB:CC:DD:EE:FF",   # required: exactly what you'd store as External ID
        "suggested_name": "GVH5074_1234",      # optional: placeholder for the name box
        "summary": "74.8°F / 52% RH",          # optional: one short line to help the user tell devices apart
        "plugin_config": None,                 # optional: dict saved with the Known Device (keys, IPs)
    }]

def registration_fields(external_id: str, plugin_config: dict | None) -> dict[str, str]:
    """Optional. Which Add Sensor/Add Plug form fields to fill in for a named device."""
    return {"mac_address": external_id}
```

Rules:

- It runs **inside the web process** (like `init.py`), not in your background Plugin process. Keep
  it short: finish within about 30 seconds, and don't leave threads, sockets, or scanners running.
- **Read-only.** Never write to the database, the Inbox, or the Outbox. Scanning must never change
  a device.
- Raise an exception with a **user-readable message** if the scan can't run ("Save your Access ID
  first", "Bluetooth is off"). The message is shown as-is, so never put a secret in it.
- `external_id` must be the same string your Plugin uses at registration. That's how a scan result
  is matched to an existing Sensor/Plug and to its saved name.
- Return each physical device or channel once. For a multi-outlet device, return one entry per
  outlet if each is registered separately.
- Import heavy or web-only modules **inside** the function, so importing `discover.py` stays cheap.

## 6. Settings

Declare fields in `manifest.json`. Core renders them on the Settings page and stores the values in
the `plugin_setting` table. Never add a column to `app_setting` for a Plugin.

```json
"settings": [
  {"key": "access_id", "label": "Access ID", "type": "text", "help": "From your cloud project."},
  {"key": "access_secret", "label": "Access Secret", "type": "secret"},
  {"key": "api_region", "label": "API Region", "type": "select", "default": "us",
   "options": [{"value": "us", "label": "Americas"}, {"value": "eu", "label": "Europe"}]}
]
```

- `text`: shown and editable. Leaving it blank clears it.
- `secret`: **never rendered back into any page.** Leaving it blank keeps the saved value; a
  "Clear saved …" checkbox removes it.
- `select`: needs `options`; Core rejects any value not listed.
- `key` is lowercase `snake_case`. Values are always strings, so parse them yourself.
- Your `discover()` receives the values. Your background Plugin process doesn't read the database,
  so if it needs a setting at runtime, ask for it to be added to your Registry export (Ingest) in
  the same change.

## 7. The runtime contract (device Plugins)

These rules come from ADR 0013/0014 and haven't changed:

- **Never open the database.** Read `data/registry/<name>.json` for what to watch, and write
  Plugin Events into `data/inbox/<kind>/` (validated against `schemas/plugin_event.schema.json`).
  If you accept Commands, read them from `data/outbox/<name>/`.
- **Only run while Active.** Ingest stops exporting your Registry and rejects your events when
  you're deactivated, so treat an empty Registry as "nothing to do".
- Write files atomically (write to a temp file, then rename). `plugins/common.py` does this for
  Python Plugins.
- Report on every poll, not only on change. Core works out the transitions.
- Log to stdout/stderr. The Supervisor captures it.

## 8. Checklist before opening a PR

- [ ] Folder name, `name`, and package all match, and follow section 1.
- [ ] `manifest.json` passes the schema. `pytest tests/test_plugin_pages.py` is green.
- [ ] `how_it_works`, `can`, and `cannot` are written for a keeper and are honest about limits.
- [ ] `init.py` hooks are idempotent and inverse of each other.
- [ ] If there's discovery: `discover.py` is read-only, finishes quickly, and raises readable errors.
- [ ] No secret is ever logged, put in an exception message, or written to a Plugin Event.
- [ ] The Plugin's Settings page renders, and Activate/Deactivate work.
- [ ] CONTEXT.md and an ADR are updated if you changed the standard itself.
