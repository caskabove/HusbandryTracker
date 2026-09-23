# Debugging the Registry/Inbox/Outbox JSON Pipeline

Core, each Plugin, and Ingest never talk to each other directly or share the database — they pass
JSON files back and forth through `data/registry/`, `data/inbox/`, and `data/outbox/`. See
`CONTEXT.md`'s **Plugin**, **Registry**, **Inbox**, **Outbox**, **Plugin Event**, and **Command**
entries (and ADR 0013/ADR 0014) for the full contract. This doc is for when something in that
pipeline looks wrong and you need to work out which side of it broke.

## Start here

Run the read-only diagnostic before anything else:

```
.venv/Scripts/python.exe tools/verify_json_pipeline.py
```

It cross-checks the Registry against the database, flags Inbox/Outbox files that have sat too
long, lists anything sitting in quarantine, and re-validates every file currently on disk against
the real schemas. It never writes anything, so it's safe to run against a live instance at any
time, including while Ingest and both Plugins are running. Re-run it after every step below —
most of these symptoms resolve to one specific line in its output.

Relevant log files (`data/logs/`): `ingest.log`, `tuya.log`, `govee.log`, `website.log` — each
process appends to its own file; a `.1` suffix is the previous run's rotated log.

## Symptom -> likely cause -> what to check

### A Smart Sensor or Plug shows "Unreachable" on the Dashboard

Unreachable fires when nothing has arrived for that device in a while — see CONTEXT.md's
**Unreachable**/**Ingest** entries — so the question is which link in the chain stopped.

1. Run the diagnostic. If it's `MISSING FROM FILE` or `MISSING FILE` under Registry, the Plugin
   was never told to watch this device — check `ingest.log` for whether Ingest's export loop is
   running at all.
2. If the Registry looks correct, check whether the owning Plugin process is even running
   (`tuya.log` / `govee.log`) — a crashed Plugin writes nothing to the Inbox, which looks
   identical to a healthy Plugin that just can't reach the device.
3. If the Plugin is running but the device itself is the problem: for Tuya, run
   `tools/tuya_verify_connections.py` or `tools/tuya_probe.py` against that device directly — they
   bypass the whole Registry/Inbox contract and talk to the device the same way the live Plugin
   does. `govee_ble` has no equivalent probe tool today; check `govee.log` for connection errors
   instead.
4. If events ARE arriving (check `data/inbox/<kind>/` while the Plugin is between polls, or watch
   `ingest.log`), but the Dashboard still shows Unreachable, the mismatch is more likely in
   `auto_update_enabled` (Auto-Update paused) or a stale `plugin`/`external_id` pairing than in the
   JSON pipeline itself — check the device's Admin edit page.

### Registry file missing or has stale/missing entries

The diagnostic's Registry section reports this directly. Cause is almost always that Ingest's
export loop (`ingest/ingest.py`'s `_export_registry`, called once per scan interval — see
`app_setting.ingest_scan_interval_seconds`) either isn't running or hasn't looped since the
database changed.

- Check `ingest.log` for whether the process is alive and recently active.
- If Ingest is running but the file still hasn't updated, check the file's own mtime against how
  long ago the device was added/removed in Admin — it should update within one scan interval
  (default 5s).

### Inbox files piling up (`STUCK` in the diagnostic's Inbox section)

Ingest drains the whole Inbox on every scan loop, one file at a time, and a single bad file gets
quarantined rather than blocking the rest (see `ingest/ingest.py`'s `_drain_inbox`/`_quarantine`)
— so a real backlog almost always means Ingest itself isn't running or is stuck, not that one file
is jamming the queue.

- Check `ingest.log` first. No recent activity there means Ingest crashed or was never started.
- If Ingest looks alive but the backlog isn't shrinking, check for a `sqlite3.OperationalError:
  database is locked` in `ingest.log` — `db/db.py`'s non-WAL journal mode (see its module
  docstring) means a long-held connection elsewhere can briefly block Ingest's writes; this should
  self-clear within Ingest's own retry window, not persist.

### Files showing up in `data/inbox/_rejected/`

The diagnostic's Rejected section lists these. Each one failed `schemas/plugin_event.schema.json`
validation once and was moved aside — Ingest never retries a quarantined file (see
`ingest/ingest.py`'s `_quarantine`), so it sits there until someone looks.

1. Open the file and compare its shape against `schemas/plugin_event.schema.json` — most often
   this is a missing/extra payload field for its `kind`, or a malformed `observed_at` timestamp
   (must be `YYYY-MM-DD HH:MM:SS`, no timezone suffix).
2. Trace it back to the Plugin that wrote it (the `plugin` field, and the filename's
   `<plugin>__<external_id>__...` prefix — see `plugins/common.py`'s `write_event`) and check that
   Plugin's `_extract_telemetry`/event-construction code for a recent change.
3. Once the underlying bug is fixed, the quarantined file itself is safe to delete — it will never
   be picked up again as-is.

### A Plug command (turning a Smart Plug on/off from Admin) doesn't seem to take effect

See CONTEXT.md's **Command**/**Outbox** entries and ADR 0014. A Command is taken at most once and
never retried if the Plugin can't reach the device at that moment (see
`plugins/tuya_lan/plugin.py`'s `_execute_command`) — silently, from the UI's point of view.

1. Run the diagnostic's Outbox section. `STUCK` means the target Plugin isn't polling (check its
   log); `ORPHAN` means the command targets a device that's no longer registered under that plugin
   (likely deregistered after the command was issued but before the Plugin picked it up).
2. Check `web/admin_queries.py`'s corresponding `plug_command_log` row in the database — it
   records whether Core itself considered the write successful, independent of whether the Plugin
   ever executed it.
3. Check the Plugin's own log (`tuya.log` for `tuya_lan` — `govee_ble` never implements command
   execution, see its module docstring) for a `"Command failed"` line, which means the device was
   unreachable at the moment the Plugin tried it and the command was dropped, not retried.

### Root-level `devices.json` / `tinytuya.json` / `tuya-raw.json` / `snapshot.json` look out of date

These are one-off discovery dumps referenced in `plugins/tuya_lan/plugin.py`'s module docstring,
not part of the live Registry/Inbox/Outbox contract — nothing in the running app reads or writes
them. They're not covered by `tools/verify_json_pipeline.py` and going stale is expected; they're
not a symptom of anything.
