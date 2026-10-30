# Tuya Discover: a Cloud-API-backed button, not the `tinytuya wizard` Command Prompt detour

**Status**: accepted — Phase 2 of GitHub issue
[caskabove/HusbandryTracker#3](https://github.com/caskabove/HusbandryTracker/issues/3)

Phase 1 (ADR 0029) gave Govee a "Discover Devices" button because a Govee sensor's MAC address is
plain to read off a passive Bluetooth advertisement — no account, no credentials, nothing Tuya-shaped
about it. A Gosund plug's device ID and local key are not broadcast by anything; they only exist in
Tuya's own cloud, tied to whatever account paired the plug in Smart Life/Tuya Smart. Today, getting
them means a Command Prompt, `pip install -r requirements.txt`, and `python -m tinytuya wizard` — a
multi-step interactive flow that creates a Tuya IoT developer account, links a "Cloud" project to the
Smart Life account (usually via a phone QR-code scan), and finally prints every linked device's ID and
key. **That account-linking step is Tuya's, not ours, and stays exactly as it is** — no code in this
app can shortcut a QR-code scan on Tuya's own website. What this ADR removes is everything *after*
that: the Command Prompt, the `pip install`, and the wizard script itself.

**Decision**: once a user has gone through Tuya's one-time account linking and has an Access ID and
Access Secret from their Tuya IoT Cloud project, they type those into a new **Tuya Cloud Credentials**
card on the Control Panel (`/admin`), saved once into `app_setting`. From then on, every Add Plug and
Add Plug Group form gets a **"Discover Devices"** button next to the device ID/local key fields,
backed by a new `discover_tuya()` in `web/tuya_discover.py`. It calls `tinytuya.Cloud(...).getdevices()`
— already a dependency, since `plugins/tuya_lan` uses the same library for LAN control — to ask Tuya's
cloud for every device linked to that account, returning each one's device ID, local key, display
name, and category. For each device it also calls `getstatus()` and, best-effort, reads off the DPS
`code` string (e.g. `"switch_1"`) as a **suggested** switch/outlet key — not authoritative; a product
with a non-standard DPS layout still needs `tools/tuya_probe.py`'s physical toggle-and-watch check,
exactly the caveat the existing how-to already gives today. This fully replaces the `tinytuya wizard`
step; it narrows, but doesn't eliminate, the separate DPS-confirmation step.

**Why `web` calls an external cloud service directly, for this one**: Refresh (ADR 0005), Probe (ADR
0016), and Discover/Govee (ADR 0029) all talk to a *local* radio the always-on Plugin also listens to.
Tuya has no local radio to ask — device ID and local key live nowhere but Tuya's cloud, so the "direct
bypass from `web`, skip the Plugin contract" shape (same reasoning as those three ADRs: a person
wants an answer in seconds, nothing durable to write) necessarily means an HTTPS call to
`openapi.tuya<region>.com` instead of a BLE scan. `tinytuya_lan`'s Plugin never needs the Cloud API
once the fields exist — Phase 1's precedent that this doesn't belong routed through Outbox/Inbox still
holds, since this is diagnostic account lookup, not steady-state sensor data.

**Why the credentials get their own card and route, not the existing generic Settings form**: Access
Secret is a real credential, account-wide rather than per-device, and the existing `/admin/settings`
POST re-renders every field's current value into the page on every load — fine for a refresh timeout,
not something to do with a secret. `POST /admin/settings/tuya-credentials` is a separate route against
the same `app_setting` row (same precedent as `schema.sql`'s own comment: add columns, don't
generalize into a key-value store) with its own `update_tuya_credentials()` query function; the
rendered form never echoes the saved secret back, and leaving the Access Secret field blank on save
means "keep what's already there," not "clear it" — otherwise saving any other setting on the same
page would risk wiping it by accident.

**Why this is a JSON endpoint instead of the usual redirect-and-redisplay**: same reasoning as ADR
0029 — the button sits inside an in-progress Add Plug/Add Plug Group form, and a full-page round trip
would discard whatever else the user had already typed. `POST /admin/plugs/discover-tuya` is this
app's second plain JSON API route (after Discover/Govee); `onDiscoverTuyaClick()` in `web/static/app.js`
fetches it and fills in device ID/local key/switch key the same way `onDiscoverGoveeClick()` does for
MAC address.

**Why no new Plugin-declared "tool manifest" concept, again**: same rejection as ADR 0029 — this is a
second `discover_<vendor>()` bypass function living in `web`, not a generic subprocess launcher.

**Consequences**: `db/schema.sql`'s `app_setting` table gains `tuya_access_id`, `tuya_access_secret`,
`tuya_api_region` (default `"us"`), with a matching `tools/migrate_*` script for existing databases;
`web/admin_queries.py` gains `update_tuya_credentials()`; `web/tuya_discover.py` is new
(`discover_tuya()`); `web/admin.py` gains `POST /admin/settings/tuya-credentials` and
`POST /admin/plugs/discover-tuya` (JSON); `web/static/app.js` gains `onDiscoverTuyaClick()`;
`admin_index.html` gains a Tuya Cloud Credentials card and a Discover button on both the standalone
Add Plug form and the Add Plug Group form. `docs/HOWTO_ADD_GOSUND_PLUG.md` is updated to describe the
button flow in place of the wizard; the DPS-confirmation step (section 4) stays, reframed as
confirming a *suggestion* rather than finding the key from scratch. This closes out issue #3.
