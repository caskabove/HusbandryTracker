# Plugins become explicitly activatable, and gain a Skill variant with no devices

**Status**: accepted

**Context**: every Plugin today (`tuya_lan`, `govee_ble`) works purely because a Sensor/Plug row
references its name — there's no concept of a Plugin being "on" or "off" independent of whether a
device happens to point at it, and no lifecycle hook runs when one starts being used. That's fine
as long as every Plugin is a device integration this app ships with. It stops being fine once a
Plugin can be something with no devices at all — specifically, a **Skill**: a Plugin that resolves
human language into a structured Husbandry Tracker action instead of polling hardware (see
CONTEXT.md: Skill; the first one, `log_husbandry`, is designed in a companion ADR). A Skill has
nothing to register the way a device does, and activating one has a real, one-time side effect
(installing a Claude Code skill) that a user may not want at all — "not everyone likes AI," and
nothing should be written to `.claude/skills/` until they've explicitly said so.

**Decision**: add `data/active_plugins.json`, a plain JSON array of currently-Active Plugin names,
owned and written by the web app (an Admin "Plugins" card, and a Setup Wizard step offering to
activate one at install time) rather than hand-edited, even though nothing stops a user from
hand-editing it directly — same as every other half of this app's filesystem contracts. A missing
or empty file means **no** Plugin is Active — deliberately not "everything is Active" — since
there's no existing install to stay backward-compatible with yet; a fresh install's Wizard always
writes this file explicitly before the dashboard is ever reached. Ingest reads it on every scan
(same cadence as its Registry export) and only exports a Registry for, or accepts Inbox events
from, a Plugin name currently listed.

Every Plugin folder (`plugins/<name>/`) now follows a **Plugin Contract**: a `manifest.json`
(name, description, and whether it's a device Plugin or a Skill), an `init.py` (a one-time hook
run when a Plugin transitions from not-Active to Active, and its inverse on deactivation — a no-op
for a device Plugin, but for a Skill, the actual install/uninstall of its Claude Code skill files),
and the Plugin's own implementation (`plugin.py`'s polling loop for a device Plugin; a Skill's
`SKILL.md` and instructions for a Skill). Core calls `init` synchronously as part of the same
Admin request that would add the name to `active_plugins.json`, and only on success does the name
actually get written — activation is one atomic action, never a state where a Plugin is listed
Active but its `init` never actually ran. "Available" Plugin discovery (what the Admin Plugins
card lists as activatable) is just scanning `plugins/` for folders satisfying this contract — one
mechanism for every Plugin kind, built-in or third-party, device or Skill, with no separate
discovery protocol needed for Skills specifically.

`manifest.json` is the name the original requirements doc (§9.14) and ADR 0014's own open
punch-list already reserved for this exact idea ("no way for core to know a plugin exists before a
device is registered to it") — picked over `identity.json` specifically because `identity.py`
already exists in `plugins/tuya_lan/`/`plugins/govee_ble/` today, meaning something unrelated
(External ID encode/decode logic for that one Plugin's devices). Calling the new manifest
`identity.json` too would have every future reader scanning `plugins/*/` finding two different
"identity" concepts with nothing in common. This is narrower than §9.14's own eventual vision
(which also wants the External ID/Plugin Config field list, the Inbox `kind`s emitted, and the
`schema_version` spoken, so Admin could render device-registration forms generically) — this round
only needs `name`/`description`/`kind` (device vs. Skill), enough for `log_husbandry`'s own
manifest and the Admin Plugins card; the richer version stays open for whenever `tuya_lan`/
`govee_ble` actually get retrofitted onto this contract (deliberately not this round — see above).

This isn't the same thing ADR 0029 already rejected ("no new Plugin-declared 'tool manifest'
concept") — that rejection was specifically about Core launching a Plugin's own long-running
process on demand to serve a UI button, which would be a second channel alongside the filesystem
contract. `init.py` never launches a Plugin's polling process; it's a one-time, synchronous local
function call (copying/removing files for a Skill, a no-op for a device Plugin today) invoked only
during activation/deactivation, not an on-demand feature.

A Skill's installed files live at this repo's own **project-scoped** `.claude/skills/<name>/`,
never the user's global `~/.claude/skills/` — a Skill is useless outside a Husbandry Tracker
install, so it has no business appearing in every other Claude Code session on the machine.
Deactivating removes those files again, rather than leaving a dangling slash command that silently
does nothing once Ingest stops accepting events from it.

**Considered Options**:
- **Backward-compatible default (missing file = everything Active)** — rejected: there's no
  pre-release install to protect, and the alternative is a real foot-gun (activating your first
  Skill would silently narrow what already worked, the moment the file starts existing, unless the
  user remembers to also list every device Plugin already in use).
- **Retrofitting `tuya_lan`/`govee_ble` onto the Plugin Contract as part of this change** —
  rejected for now: they work today with zero lifecycle hooks, there's no urgency forcing that
  migration, and bundling it in risks stalling the Skill work this ADR exists to unblock on a
  change that's really about Plugin infrastructure in general. Left as separate future work.
- **A real Skill-discovery protocol** (the app somehow learns a Skill exists before it's ever
  activated, independent of the `plugins/` folder) — rejected: once a Skill is just another
  `plugins/<name>/` folder satisfying the same contract, this isn't a separate problem at all.

**Consequences**: `plugins/log_husbandry/` is the first folder to actually satisfy the Plugin
Contract; `tuya_lan`/`govee_ble` remain contract-less until a separate migration picks that up.
Ingest's Registry export and Inbox drain both gain an Active-Plugin check. The Admin Plugins card
and Setup Wizard step are new UI surfaces, scoped only to listing/activating/deactivating — no
other admin behavior changes.
