# A generic "log" Plugin Event kind lets any Plugin or AI skill write free-form log entries

**Status**: accepted

**Context**: every Plugin Event kind so far (`sensor_reading`, `plug_state`, `plug_telemetry`) is
tied to a specific registered Sensor/Plug — Ingest drops the event if `(plugin, external_id)`
doesn't resolve to one (see `ingest/ingest.py`'s `_apply_event`). That's the right behavior for an
observation about a *device*, but it means there's no way for a Plugin, or anything shaped like
one — an AI skill that watches a camera feed, parses a voice command, or runs some other
automation — to record "something happened" unless it's willing to fake a device registration
first. There's also no logging infrastructure in this app at all today: every process (`ingest`,
`plugins/tuya_lan`, `plugins/govee_ble`) just `print()`s to its own console/log file, with nothing
captured in the database or queryable later.

**Decision**: add `log` as a fourth `kind` to `schemas/plugin_event.schema.json`, alongside the
three existing ones, reusing the exact same envelope and the exact same Inbox/Ingest machinery
(`data/inbox/log/*.json`, drained by Ingest every scan same as any other kind) — no new
mechanism, no new process. A `log` event's `payload` is `{level, message, data?}` instead of a
device reading, and Ingest's `_apply_event` writes it straight into a new `event_log` table
*without* the Registry-match step every other kind requires — a log entry doesn't need, and
shouldn't need, a registered Sensor/Plug to exist first, so it also skips Alert Condition
evaluation. `external_id` is repurposed as a free-form scope reference instead of a device id —
convention is `"<entity_type>:<id>"` (e.g. `"enclosure:3"`, `"animal:12"`) when the entry is about
something specific, or `"app"` when it isn't about anything in particular — rather than a
placeholder value, so `event_log.scope` stays genuinely useful for later filtering ("show me
everything logged against Enclosure 3") instead of being dead weight on every row.

Writing one is identical to writing any other Plugin Event: `plugins/common.py`'s existing
`write_event(plugin, external_id, kind, payload)` already takes an arbitrary `kind`, so
`write_event("feeding_skill", "enclosure:3", "log", {"level": "info", "message": "..."})` works
today with no code change to that helper. A third-party Plugin or skill in another language just
drops the equivalent JSON file into `data/inbox/log/` directly, same as it would for any other
kind.

**Considered Options**:
- **A dedicated logging endpoint/table outside the Plugin Event contract** (e.g. an HTTP endpoint
  `web` exposes, or a separate `data/logs/*.json` directory with its own schema) — rejected: it
  would duplicate the Inbox/Ingest machinery (validation, atomic write, drain-and-quarantine) this
  app already has for exactly this shape of problem, for no benefit. Reusing the existing kind
  mechanism keeps "a Plugin or skill reports something" one concept, not two.
- **Require a log event to resolve against the Registry like the other three kinds**, so
  `event_log` gained a real `sensor_id`/`plug_id` foreign key instead of a free-text `scope` —
  rejected: an AI skill's log entry is often about an Enclosure, an Animal, or nothing in
  particular, none of which are Registry-tracked entities the way a Sensor/Plug is; forcing every
  log entry to pretend to be a device observation would block the common case to serve a narrower
  one.
- **A `"-"` or `NULL` placeholder for `external_id` on a `log` event** — rejected in favor of the
  free-form scope-reference convention above: a placeholder is dead weight on every row, while a
  real scope reference costs nothing extra to write and immediately pays for itself the first time
  someone wants to filter the log by entity.

**Consequences**: `schemas/plugin_event.schema.json` gains `log` in its `kind` enum and a new
`log_payload` `$def`; `db/schema.sql` gains `event_log` (purely additive, via
`tools/migrate_2026_10_31_event_log.py`, same shape as every other `tools/migrate_*` script);
`ingest/ingest.py`'s `EVENT_KINDS` and `_apply_event` gain the fourth kind, and
`tools/verify_json_pipeline.py`'s own duplicate `EVENT_KINDS` list was updated to match — it would
otherwise have silently ignored the new kind's Inbox directory in every health check. No UI
surfaces `event_log` yet — reading it back (an Admin or View Data page) is left for whenever an
actual consumer of these logs is needed, same as this ADR not speculating about what a given skill
would log.
