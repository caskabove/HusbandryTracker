"""Ingest — see CONTEXT.md: Ingest; ADR 0013. The one core process that:

1. Exports each Plugin's Registry (data/registry/<plugin>.json) from the sensor/plug tables, so a
   Plugin never queries the database directly to learn what to watch.
2. Drains the Inbox (data/inbox/<kind>/*.json), validating every Plugin Event against
   schemas/plugin_event.schema.json before writing the resulting Reading/Plug State Transition/
   Data Capture, then evaluating Alert Conditions.
3. Periodically re-evaluates Unreachable for every registered Smart Sensor/Plug, since that
   condition needs to fire even when *nothing* arrives, not just when something does.

Deliberately contains no vendor-specific code — resolving a Plugin Event only ever keys off its
generic (plugin, external_id) pair, never a vendor's own field names. Adding a new Plugin type
never requires a change here.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jsonschema

from db.db import get_connection, init_db
from ingest import alerts

REPO_ROOT = Path(__file__).resolve().parent.parent
INBOX_DIR = REPO_ROOT / "data" / "inbox"
REGISTRY_DIR = REPO_ROOT / "data" / "registry"
REJECTED_DIR = INBOX_DIR / "_rejected"
SCHEMA_PATH = REPO_ROOT / "schemas" / "plugin_event.schema.json"
EVENT_KINDS = ["sensor_reading", "plug_state", "plug_telemetry"]

DEFAULT_SCAN_INTERVAL_SECONDS = 5


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


def _export_registry() -> None:
    """See CONTEXT.md: Registry. Fully generic — groups every Smart Sensor/Plug row by its own
    `plugin` value, whatever that happens to be, and writes/removes files to match exactly what's
    currently registered (a Plugin whose last device was just deleted gets its file removed, not
    left stale)."""
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
        _atomic_write_json(REGISTRY_DIR / f"{plugin_name}.json", entries)
    for stale in existing_files - entries_by_plugin.keys():
        (REGISTRY_DIR / f"{stale}.json").unlink(missing_ok=True)


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
            _drain_inbox(validator)
            _run_periodic_unreachable_checks()
            time.sleep(_scan_interval_seconds())
    except KeyboardInterrupt:
        print("\n[ingest] stopping...")


if __name__ == "__main__":
    main()
