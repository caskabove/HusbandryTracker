"""Ingest — see CONTEXT.md: Ingest; ADR 0013. The one core process that:

1. Exports each Plugin's Registry (data/registry/<plugin>.json) from the sensor/plug tables, so a
   Plugin never queries the database directly to learn what to watch — plus one Skill-specific
   export, log_husbandry's own Rooms/Enclosures/Animals snapshot (see CONTEXT.md: Skill; ADR 0046).
   Every Registry export, device Plugin or Skill alike, is gated on being an Active Plugin (see
   CONTEXT.md: Active Plugin; ADR 0045/0047) — deactivating one removes its file the same way
   deregistering its last device already did.
2. Drains the Inbox (data/inbox/<kind>/*.json), validating every Plugin Event against
   schemas/plugin_event.schema.json before writing the resulting Reading/Plug State Transition/
   Data Capture/Log Event/Care Event, then evaluating Alert Conditions. A device-observation kind
   whose Plugin isn't Active is silently dropped, same as an unregistered device (routine, not
   worth surfacing); a Log Event skips Alert evaluation entirely (it's not about a registered
   Sensor/Plug); a Care Event Plugin Event also skips it, and quarantines — rather than silently
   dropping — on a stale entity reference *or* an inactive Plugin, since it represents a specific,
   human-confirmed action, not a routine poll (see CONTEXT.md: Log Event, Care Event Plugin Event,
   Active Plugin; ADR 0044/0045/0046/0047).
3. Periodically re-evaluates Unreachable for every registered Smart Sensor/Plug, since that
   condition needs to fire even when *nothing* arrives, not just when something does.

Device-observation kinds (sensor_reading/plug_state/plug_telemetry) deliberately contain no
vendor-specific code — resolving one only ever keys off its generic (plugin, external_id) pair,
never a vendor's own field names, and adding a new device Plugin never requires a change here.
log_husbandry's own Registry export and its care_event handling are the one deliberate exception
— see each one's own docstring/comment for why a Skill doesn't fit that same generic shape yet.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jsonschema

from active_plugins import read_active_plugins
from app_paths import APP_ROOT
from db.db import backup_database, get_connection, init_db
from ingest import alerts
from web.admin_queries import get_last_feeding_detail, log_feeding
from web.queries import log_care_event

INBOX_DIR = APP_ROOT / "data" / "inbox"
REGISTRY_DIR = APP_ROOT / "data" / "registry"
REJECTED_DIR = INBOX_DIR / "_rejected"
SCHEMA_PATH = APP_ROOT / "schemas" / "plugin_event.schema.json"
EVENT_KINDS = ["sensor_reading", "plug_state", "plug_telemetry", "log", "care_event"]

DEFAULT_SCAN_INTERVAL_SECONDS = 5

# See CONTEXT.md: Backup; ADR 0019. BACKUP_REQUEST_PATH is a trigger file — tray/supervisor.py
# touches it when "Back Up Now" is clicked, deliberately never importing db.db itself (matches this
# codebase's existing "each process's own half of a filesystem contract" pattern, e.g. Outbox/
# Command — see web/outbox.py's docstring), so Ingest is still the only process that ever opens the
# database for anything beyond a Supervisor-orchestrated restore's stop-everything file swap.
BACKUP_DIR = APP_ROOT / "data" / "backups"
BACKUP_REQUEST_PATH = APP_ROOT / "data" / "backup_requested"
BACKUP_RETENTION_DAYS = 14
_BACKUP_STEM_FMT = "husbandrytracker-%Y%m%d-%H%M%S"


def _load_validator() -> jsonschema.Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def _atomic_write_json(path: Path, data) -> None:
    import os
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    tmp_path.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp_path, path)


# log_husbandry's own Registry export (_export_log_husbandry_registry) is a Skill, not a device
# Plugin — it's never a key in _export_registry()'s entries_by_plugin (no sensor/plug row ever
# references it), so _export_registry()'s own stale-file cleanup below must not treat its file as
# an orphan and delete it out from under that other function. See CONTEXT.md: Plugin Contract.
_SKILL_REGISTRY_NAMES = {"log_husbandry"}


def _export_registry() -> None:
    """See CONTEXT.md: Registry, Active Plugin; ADR 0013/0045/0047. Groups every Smart Sensor/Plug
    row by its own `plugin` value, whatever that happens to be, but only actually writes a
    Registry file for one that's currently an Active Plugin — a device Plugin referenced by a
    registered device but not (yet, or anymore) Active has its file removed, same treatment as one
    with no devices registered to it at all."""
    active = set(read_active_plugins())
    entries_by_plugin: dict[str, list[dict]] = {}
    with get_connection() as conn:
        for table in ("sensor", "plug"):
            rows = conn.execute(
                f"SELECT plugin, external_id, plugin_config, auto_update_enabled FROM {table} "
                f"WHERE tracking_mode = 'smart' AND plugin IS NOT NULL"
            ).fetchall()
            for row in rows:
                entries_by_plugin.setdefault(row["plugin"], []).append({
                    "external_id": row["external_id"],
                    "plugin_config": json.loads(row["plugin_config"]) if row["plugin_config"] else None,
                    "auto_update_enabled": bool(row["auto_update_enabled"]),
                })

    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    existing_files = {p.stem for p in REGISTRY_DIR.glob("*.json")}
    for plugin_name, entries in entries_by_plugin.items():
        if plugin_name in active:
            _atomic_write_json(REGISTRY_DIR / f"{plugin_name}.json", entries)
        else:
            (REGISTRY_DIR / f"{plugin_name}.json").unlink(missing_ok=True)
    for stale in existing_files - entries_by_plugin.keys() - _SKILL_REGISTRY_NAMES:
        (REGISTRY_DIR / f"{stale}.json").unlink(missing_ok=True)


def _export_log_husbandry_registry() -> None:
    """See CONTEXT.md: Skill, Registry; ADR 0046. Unlike _export_registry() above — fully generic,
    one device list per device Plugin — log_husbandry's Registry export is specific to what this
    one Skill actually needs (Rooms/Enclosures/Animals, not devices), since there's currently no
    generic way for a Skill to declare what domain data it wants (manifest.json's scope is
    narrower than that for now — see CONTEXT.md: Plugin Contract). Only exported while
    log_husbandry is itself an Active Plugin — removed the moment it's deactivated, same
    stale-file cleanup _export_registry() already does for a deregistered device Plugin."""
    path = REGISTRY_DIR / "log_husbandry.json"
    if "log_husbandry" not in read_active_plugins():
        path.unlink(missing_ok=True)
        return
    with get_connection() as conn:
        rooms = [dict(row) for row in conn.execute("SELECT id, name FROM room")]
        enclosures = [dict(row) for row in conn.execute("SELECT id, name, room_id FROM enclosure")]
        animals = [dict(row) for row in conn.execute("SELECT id, name, enclosure_id FROM animal")]
    _atomic_write_json(path, {"rooms": rooms, "enclosures": enclosures, "animals": animals})


def _quarantine(path: Path, reason: str) -> None:
    dest_dir = REJECTED_DIR / path.parent.name
    dest_dir.mkdir(parents=True, exist_ok=True)
    print(f"[ingest] rejecting {path.name}: {reason}")
    path.replace(dest_dir / path.name)


def _apply_event(event: dict) -> None:
    """Writes the event's DB row(s) in one short-lived connection, closes it, THEN evaluates Alert
    Conditions — each alerts.py function opens its own connection (see ingest/alerts.py), and this
    app's non-WAL journal mode (ADR 0002) means a same-process connection can't stay open while
    another one writes without hitting "database is locked". Mirrors how the pre-ADR-0013
    collectors always called alerts.* only after their own `with get_connection()` block had
    already closed."""
    plugin = event["plugin"]
    external_id = event["external_id"]
    kind = event["kind"]
    observed_at = event["observed_at"]
    payload = event["payload"]

    # See CONTEXT.md: Active Plugin; ADR 0045/0047. Only the three device-observation kinds are
    # gated here — a device Plugin deactivated mid-flight is the same as it never having watched
    # that device at all, so this is silently dropped exactly like the "not registered" case just
    # below, not quarantined. `log`/`care_event` have their own, kind-specific handling further
    # down (care_event's own Active check raises instead of silently dropping — see its branch).
    if kind in ("sensor_reading", "plug_state", "plug_telemetry") and plugin not in read_active_plugins():
        return

    if kind == "sensor_reading":
        with get_connection() as conn:
            sensor = conn.execute(
                "SELECT id FROM sensor WHERE plugin = ? AND external_id = ? "
                "AND tracking_mode = 'smart' AND auto_update_enabled = 1",
                (plugin, external_id),
            ).fetchone()
            if sensor is None:
                return  # not registered (or paused) — e.g. deregistered after the Plugin last read the Registry
            conn.execute(
                "INSERT INTO sensor_reading (sensor_id, recorded_at, temperature_c, humidity_pct, battery_pct) "
                "VALUES (?, ?, ?, ?, ?)",
                (sensor["id"], observed_at, payload.get("temperature_c"), payload.get("humidity_pct"),
                 payload.get("battery_pct")),
            )
            sensor_id = sensor["id"]
        alerts.evaluate_sensor_out_of_range(sensor_id)
        alerts.evaluate_sensor_unreachable(sensor_id)

    elif kind == "plug_state":
        with get_connection() as conn:
            plug = conn.execute(
                "SELECT id FROM plug WHERE plugin = ? AND external_id = ? "
                "AND tracking_mode = 'smart' AND auto_update_enabled = 1",
                (plugin, external_id),
            ).fetchone()
            if plug is None:
                return
            plug_id = plug["id"]
            is_on = bool(payload["is_on"])
            last = conn.execute(
                "SELECT is_on FROM plug_state_transition WHERE plug_id = ? ORDER BY recorded_at DESC LIMIT 1",
                (plug_id,),
            ).fetchone()
            if last is None or bool(last["is_on"]) != is_on:  # edge-triggered — see CONTEXT.md: Ingest
                conn.execute(
                    "INSERT INTO plug_state_transition (plug_id, recorded_at, is_on) VALUES (?, ?, ?)",
                    (plug_id, observed_at, int(is_on)),
                )
            conn.execute(
                "INSERT INTO plug_last_seen (plug_id, last_seen_at) VALUES (?, ?) "
                "ON CONFLICT(plug_id) DO UPDATE SET last_seen_at = excluded.last_seen_at",
                (plug_id, observed_at),
            )
        alerts.evaluate_plug_unreachable(plug_id)
        alerts.evaluate_plug_zero_power(plug_id)

    elif kind == "plug_telemetry":
        with get_connection() as conn:
            plug = conn.execute(
                "SELECT id FROM plug WHERE plugin = ? AND external_id = ? "
                "AND tracking_mode = 'smart' AND auto_update_enabled = 1",
                (plugin, external_id),
            ).fetchone()
            if plug is None:
                return
            plug_id = plug["id"]
            conn.execute(
                "INSERT INTO plug_reading (plug_id, recorded_at, watts, volts, amps, countdown_seconds) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (plug_id, observed_at, payload.get("watts"), payload.get("volts"), payload.get("amps"),
                 payload.get("countdown_seconds")),
            )
        alerts.evaluate_plug_zero_power(plug_id)

    elif kind == "log":
        # Deliberately no Registry match and no Alert evaluation — a Log Event isn't about a
        # registered Sensor/Plug (see CONTEXT.md: Log Event; ADR 0044), so every well-formed one
        # is written straight through.
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO event_log (source, scope, level, message, data, recorded_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (plugin, external_id, payload.get("level", "info"), payload["message"],
                 json.dumps(payload["data"]) if "data" in payload else None, observed_at),
            )

    elif kind == "care_event":
        # See CONTEXT.md: Care Event Plugin Event; ADR 0046. enclosure_id/animal_id are already
        # resolved ids from the Skill's own Registry snapshot (_export_log_husbandry_registry) —
        # re-validated here since that snapshot can be stale by the time this file is actually
        # drained (the Skill may have written it while nothing was even running). A mismatch
        # raises ValueError, which _drain_inbox's own try/except already quarantines rather than
        # silently dropping — this is a specific, human-confirmed action, not a routine device
        # poll, so a failure needs to stay visible.
        #
        # occurred_at is deliberately NOT taken from this event's own observed_at (UTC) — unlike
        # every other kind above, care_event.occurred_at is stored as LOCAL wall-clock time (see
        # web/queries.py's _normalize_datetime_local), and this Skill doesn't support backdating
        # yet anyway (ADR 0046) — passing occurred_at=None lets it default to "now" in the right
        # timezone instead of misinterpreting a UTC stamp as local.
        #
        # Unlike the three device kinds above (silently dropped when their Plugin isn't Active —
        # see this function's own top), a care_event whose Plugin isn't currently Active raises
        # instead, for the same "stay visible" reason as a stale enclosure_id/animal_id below —
        # e.g. the Skill wrote this while Active, then got deactivated before Ingest drained it.
        if plugin not in read_active_plugins():
            raise ValueError(f"{plugin!r} is not an Active Plugin")
        enclosure_id = payload["enclosure_id"]
        animal_id = payload.get("animal_id")
        care_kind = payload["care_kind"]
        note = payload.get("note")

        with get_connection() as conn:
            if conn.execute("SELECT 1 FROM enclosure WHERE id = ?", (enclosure_id,)).fetchone() is None:
                raise ValueError(f"Enclosure {enclosure_id} does not exist")
            if animal_id is not None and conn.execute(
                "SELECT 1 FROM animal WHERE id = ? AND enclosure_id = ?", (animal_id, enclosure_id)
            ).fetchone() is None:
                raise ValueError(f"Animal {animal_id} does not belong to Enclosure {enclosure_id}")

        if care_kind == "feeding":
            food = payload.get("food")
            count = payload.get("count")
            prey_state = payload.get("prey_state")
            result = payload.get("result")
            if food is None or count is None or prey_state is None or result is None:
                # "Repeat last Feeding" fallback — same rule the Log Feeding Dialog's quick-log
                # buttons already use (ADR 0042), applied per-field rather than all-or-nothing,
                # since a sentence often states some Feeding Detail fields but not others.
                last = get_last_feeding_detail(enclosure_id, animal_id)
                if food is None and last is not None:
                    food = last["food"]
                if count is None and last is not None:
                    count = last["count"]
                if prey_state is None:
                    prey_state = last["prey_state"] if last is not None else "frozen_thawed"
                if result is None:
                    result = last["result"] if last is not None else "accepted"
            log_feeding(enclosure_id, note=note, animal_id=animal_id,
                        food=food, count=count, prey_state=prey_state, result=result)
        else:
            log_care_event(enclosure_id, care_kind, note=note, animal_id=animal_id)


def _drain_inbox(validator: jsonschema.Draft202012Validator) -> None:
    if not INBOX_DIR.exists():
        return
    for kind in EVENT_KINDS:
        kind_dir = INBOX_DIR / kind
        if not kind_dir.is_dir():
            continue
        for path in sorted(kind_dir.glob("*.json")):
            try:
                event = json.loads(path.read_text(encoding="utf-8"))
                validator.validate(event)
            except json.JSONDecodeError as exc:
                _quarantine(path, f"invalid JSON ({exc})")
                continue
            except jsonschema.ValidationError as exc:
                _quarantine(path, f"schema violation ({exc.message})")
                continue
            try:
                _apply_event(event)
            except Exception as exc:  # a bad/unexpected row shouldn't wedge the whole drain
                _quarantine(path, f"failed to apply ({exc})")
                continue
            path.unlink(missing_ok=True)


def _run_periodic_unreachable_checks() -> None:
    with get_connection() as conn:
        sensor_ids = [row["id"] for row in conn.execute(
            "SELECT id FROM sensor WHERE tracking_mode = 'smart' AND auto_update_enabled = 1"
        )]
        plug_ids = [row["id"] for row in conn.execute(
            "SELECT id FROM plug WHERE tracking_mode = 'smart' AND auto_update_enabled = 1"
        )]
    for sensor_id in sensor_ids:
        alerts.evaluate_sensor_unreachable(sensor_id)
    for plug_id in plug_ids:
        alerts.evaluate_plug_unreachable(plug_id)


def _unique_backup_path(reason: str) -> Path:
    """Two backups requested within the same second (e.g. a manual click landing in the same
    second as the daily auto-check) would otherwise collide on filename and silently overwrite
    each other — append -2, -3, ... until the name's actually free."""
    stem = f"{datetime.now().strftime(_BACKUP_STEM_FMT)}-{reason}"
    dest = BACKUP_DIR / f"{stem}.db"
    n = 2
    while dest.exists():
        dest = BACKUP_DIR / f"{stem}-{n}.db"
        n += 1
    return dest


def _perform_backup(reason: str) -> None:
    dest = _unique_backup_path(reason)
    try:
        backup_database(dest)
        print(f"[ingest] backup written: {dest.name}")
    except Exception as exc:  # a failed backup shouldn't crash the scan loop
        print(f"[ingest] backup failed: {exc}")


def _prune_old_backups() -> None:
    cutoff = time.time() - BACKUP_RETENTION_DAYS * 86400
    for path in BACKUP_DIR.glob("husbandrytracker-*.db"):
        if path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)


def _run_backup_check() -> None:
    """Runs a backup (see CONTEXT.md: Backup; ADR 0019) once a day automatically, plus on-demand
    whenever tray/supervisor.py's "Back Up Now" has touched BACKUP_REQUEST_PATH — checked every scan
    interval, so a manual request lands within one cycle (default 5s)."""
    manual_request = BACKUP_REQUEST_PATH.exists()
    if manual_request:
        BACKUP_REQUEST_PATH.unlink(missing_ok=True)

    today_prefix = f"husbandrytracker-{datetime.now():%Y%m%d}-"
    has_todays_backup = BACKUP_DIR.is_dir() and any(
        p.name.startswith(today_prefix) for p in BACKUP_DIR.glob("*.db")
    )

    if manual_request or not has_todays_backup:
        _perform_backup("manual" if manual_request else "auto")
        _prune_old_backups()


def _scan_interval_seconds() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT ingest_scan_interval_seconds FROM app_setting WHERE id = 1").fetchone()
    return row["ingest_scan_interval_seconds"] if row else DEFAULT_SCAN_INTERVAL_SECONDS


def main() -> None:
    init_db()
    for kind in EVENT_KINDS:
        (INBOX_DIR / kind).mkdir(parents=True, exist_ok=True)
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    validator = _load_validator()
    print("[ingest] starting...")

    try:
        while True:
            _export_registry()
            _export_log_husbandry_registry()
            _drain_inbox(validator)
            _run_periodic_unreachable_checks()
            _run_backup_check()
            time.sleep(_scan_interval_seconds())
    except KeyboardInterrupt:
        print("\n[ingest] stopping...")


if __name__ == "__main__":
    main()
