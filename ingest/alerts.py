"""Send Alert evaluator — the debounced state machine described in CONTEXT.md: Alert, Alert
Condition, Alert Debounce (see docs/adr/0010-send-alert-via-ntfy.md). Called from ingest/ingest.py
after applying each Plugin Event, and periodically for every Smart Sensor/Plug regardless of
whether one arrived this tick — not a separate process, keeping ADR 0001's overall process shape
(this moved here, out of each collector, as part of ADR 0013's Plugin/Ingest pivot).

Scope notes, so gaps here aren't mistaken for bugs later:

- Out of Range only ever checks temperature/humidity, even though `sensor_reading` now has columns
  for all 12 Target Range metrics (pH, ammonia, specific gravity, salinity, ...) and the
  Dashboard/Admin UI can both display and hand-log any of them (see
  schemas/enclosure_types.py's TARGET_RANGE_METRICS, ADR 0011) — extending Alerting to the other
  10 the same generic way is separate follow-up work, not done here.
- Zero Power While On is fully implemented against `plug_reading`, but stays inert until a
  telemetry-capable Plug is registered — see plugins/tuya_lan/plugin.py's module docstring.
- Plug Unreachable is driven by plug_last_seen, updated on every plug_state Plugin Event regardless
  of whether the state changed (see CONTEXT.md: Ingest) — a plain absence check, the same mechanism
  Sensor Unreachable already used. This is a deliberate change from the pre-ADR-0013 version of this
  file, which drove Plug Unreachable off an explicit poll-success/failure signal instead (a failed
  poll now simply produces no Plugin Event, which shows up as absence like everything else).

Delivery is via ntfy (a plain HTTP POST to a topic, stdlib urllib — no new dependency) configured
on app_setting.ntfy_server_url/ntfy_topic; either being empty just logs to the console instead of
sending, so this runs fine before ntfy is configured.
"""
from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.db import get_connection
from web.status import Status, target_range_status

ZERO_POWER_THRESHOLD_WATTS = 1.0  # "drawing ~0W" — see CONTEXT.md: Alert Condition


def _debounce_minutes(conn) -> int:
    row = conn.execute("SELECT alert_debounce_minutes FROM app_setting WHERE id = 1").fetchone()
    return row["alert_debounce_minutes"] if row else 10


def _send_ntfy(conn, title: str, message: str, priority: str) -> None:
    row = conn.execute("SELECT ntfy_server_url, ntfy_topic FROM app_setting WHERE id = 1").fetchone()
    server, topic = (row["ntfy_server_url"], row["ntfy_topic"]) if row else (None, None)
    if not server or not topic:
        print(f"[alerts] ntfy not configured — {title}: {message}")
        return
    url = f"{server.rstrip('/')}/{topic}"
    try:
        req = urllib.request.Request(
            url, data=message.encode("utf-8"), method="POST",
            headers={"Title": title, "Priority": priority},
        )
        urllib.request.urlopen(req, timeout=10)
        print(f"[alerts] sent: {title}: {message}")
    except urllib.error.URLError as exc:
        print(f"[alerts] ntfy delivery failed ({exc}) — {title}: {message}")


def _advance(conn, table: str, id_column: str, id_value: int, condition_kind: str, is_bad: bool,
             subject: str, alert_message: str, resolved_message: str,
             already_debounced: bool = False) -> None:
    """One evaluation tick of an (entity, condition) Alert's state machine — see CONTEXT.md: Alert.

    normal/resolved -> pending -> alerting -> resolved -> normal-equivalent (resolved behaves like
    normal for detecting the *next* problem). Fires the Alert notification on entering `alerting`,
    the Resolved notification on entering `resolved`; every other transition is silent.

    is_bad should be a simple "as of right now" signal — the pending state accumulates how long
    it's stayed continuously true and only fires once that reaches Alert Debounce, so a single
    debounce duration governs every condition uniformly. Pass already_debounced=True only when the
    caller has already measured "continuously bad for at least the debounce window" itself (e.g.
    Sensor/Plug Unreachable, computed straight from an observation's age) — that skips the pending
    wait so the duration isn't counted twice.
    """
    row = conn.execute(
        f"SELECT state FROM {table} WHERE {id_column} = ? AND condition_kind = ?",
        (id_value, condition_kind),
    ).fetchone()
    if row is None:
        conn.execute(
            f"INSERT INTO {table} ({id_column}, condition_kind, state) VALUES (?, ?, 'normal')",
            (id_value, condition_kind),
        )
        state = "normal"
    else:
        state = row["state"]

    def set_state(new_state: str) -> None:
        conn.execute(
            f"UPDATE {table} SET state = ?, state_entered_at = datetime('now') "
            f"WHERE {id_column} = ? AND condition_kind = ?",
            (new_state, id_value, condition_kind),
        )

    if state in ("normal", "resolved"):
        if not is_bad:
            return
        if already_debounced:
            set_state("alerting")
            _send_ntfy(conn, f"Husbandry Tracker Alert: {subject}", alert_message, "high")
        else:
            set_state("pending")
    elif state == "pending":
        if not is_bad:
            set_state("normal")
            return
        minutes_in_state = conn.execute(
            f"SELECT (julianday('now') - julianday(state_entered_at)) * 1440 AS m "
            f"FROM {table} WHERE {id_column} = ? AND condition_kind = ?",
            (id_value, condition_kind),
        ).fetchone()["m"]
        if minutes_in_state >= _debounce_minutes(conn):
            set_state("alerting")
            _send_ntfy(conn, f"Husbandry Tracker Alert: {subject}", alert_message, "high")
    elif state == "alerting":
        if not is_bad:
            set_state("resolved")
            _send_ntfy(conn, f"Husbandry Tracker Resolved: {subject}", resolved_message, "default")


def evaluate_sensor_out_of_range(sensor_id: int) -> None:
    """Call right after applying a sensor_reading Plugin Event for a Smart Sensor."""
    with get_connection() as conn:
        sensor = conn.execute(
            "SELECT * FROM sensor WHERE id = ? AND tracking_mode = 'smart' AND auto_update_enabled = 1",
            (sensor_id,),
        ).fetchone()
        if sensor is None:
            return
        reading = conn.execute(
            "SELECT temperature_c, humidity_pct FROM sensor_reading WHERE sensor_id = ? "
            "ORDER BY recorded_at DESC LIMIT 1",
            (sensor_id,),
        ).fetchone()
        if reading is None:
            return

        temp_status = target_range_status(reading["temperature_c"], sensor["target_temp_min_c"], sensor["target_temp_max_c"])
        humidity_status = target_range_status(reading["humidity_pct"], sensor["target_humidity_min"], sensor["target_humidity_max"])
        is_bad = temp_status == Status.RED or humidity_status == Status.RED

        bits = []
        if temp_status == Status.RED:
            bits.append(f"temp {reading['temperature_c']:.1f}C (target {sensor['target_temp_min_c']}-{sensor['target_temp_max_c']})")
        if humidity_status == Status.RED:
            bits.append(f"humidity {reading['humidity_pct']:.0f}% (target {sensor['target_humidity_min']}-{sensor['target_humidity_max']})")

        _advance(
            conn, "sensor_alert_state", "sensor_id", sensor_id, "out_of_range", is_bad,
            subject=f"{sensor['label']} out of range",
            alert_message=f"{sensor['label']}: " + "; ".join(bits),
            resolved_message=f"{sensor['label']} back within Target Range",
        )


def evaluate_sensor_unreachable(sensor_id: int) -> None:
    """Call periodically (every Ingest tick) for every registered Smart Sensor."""
    with get_connection() as conn:
        sensor = conn.execute(
            "SELECT * FROM sensor WHERE id = ? AND tracking_mode = 'smart' AND auto_update_enabled = 1",
            (sensor_id,),
        ).fetchone()
        if sensor is None:
            return
        row = conn.execute(
            "SELECT (julianday('now') - julianday(MAX(recorded_at))) * 1440 AS minutes_since "
            "FROM sensor_reading WHERE sensor_id = ?",
            (sensor_id,),
        ).fetchone()
        minutes_since = row["minutes_since"]
        debounce_minutes = _debounce_minutes(conn)
        # minutes_since is None if this Sensor has never reported a Reading at all — that's "been
        # unreachable since it was registered," already past any debounce window.
        is_bad = minutes_since is None or minutes_since >= debounce_minutes

        _advance(
            conn, "sensor_alert_state", "sensor_id", sensor_id, "unreachable", is_bad,
            subject=f"{sensor['label']} unreachable",
            alert_message=f"{sensor['label']} hasn't reported in over {debounce_minutes} minutes",
            resolved_message=f"{sensor['label']} is reporting again",
            already_debounced=True,
        )


def evaluate_plug_unreachable(plug_id: int) -> None:
    """Call periodically (every Ingest tick) for every registered Smart Plug — mirrors
    evaluate_sensor_unreachable exactly, now that plug_last_seen gives Plugs the same kind of
    "last successful observation" signal a Sensor's own sensor_reading table already provides. See
    CONTEXT.md: Unreachable, Ingest; ADR 0013."""
    with get_connection() as conn:
        plug = conn.execute(
            "SELECT * FROM plug WHERE id = ? AND tracking_mode = 'smart' AND auto_update_enabled = 1",
            (plug_id,),
        ).fetchone()
        if plug is None:
            return
        row = conn.execute(
            "SELECT (julianday('now') - julianday(last_seen_at)) * 1440 AS minutes_since "
            "FROM plug_last_seen WHERE plug_id = ?",
            (plug_id,),
        ).fetchone()
        minutes_since = row["minutes_since"] if row else None
        debounce_minutes = _debounce_minutes(conn)
        is_bad = minutes_since is None or minutes_since >= debounce_minutes

        _advance(
            conn, "plug_alert_state", "plug_id", plug_id, "unreachable", is_bad,
            subject=f"{plug['label']} unreachable",
            alert_message=f"{plug['label']} hasn't reported in over {debounce_minutes} minutes — "
                          f"check power/WiFi/local_key",
            resolved_message=f"{plug['label']} is reporting again",
            already_debounced=True,
        )


def evaluate_plug_zero_power(plug_id: int) -> None:
    """Call after applying a plug_state or plug_telemetry Plugin Event — inert until plug_reading
    has rows; see plugins/tuya_lan/plugin.py's module docstring and ADR 0009."""
    with get_connection() as conn:
        plug = conn.execute(
            "SELECT * FROM plug WHERE id = ? AND tracking_mode = 'smart' AND auto_update_enabled = 1",
            (plug_id,),
        ).fetchone()
        if plug is None:
            return
        transition = conn.execute(
            "SELECT is_on FROM plug_state_transition WHERE plug_id = ? ORDER BY recorded_at DESC LIMIT 1",
            (plug_id,),
        ).fetchone()
        if transition is None or not transition["is_on"]:
            # Off (or never seen on) is never itself an anomaly — but resolve a stale "alerting" if
            # it just got switched off, rather than leaving that Alert stuck open.
            _advance(
                conn, "plug_alert_state", "plug_id", plug_id, "zero_power_while_on", is_bad=False,
                subject=f"{plug['label']} drawing no power", alert_message="",
                resolved_message=f"{plug['label']} switched off",
            )
            return

        reading = conn.execute(
            "SELECT watts FROM plug_reading WHERE plug_id = ? ORDER BY recorded_at DESC LIMIT 1",
            (plug_id,),
        ).fetchone()
        if reading is None or reading["watts"] is None:
            return  # no Data Capture yet — see ADR 0009; nothing to judge

        is_bad = reading["watts"] < ZERO_POWER_THRESHOLD_WATTS
        _advance(
            conn, "plug_alert_state", "plug_id", plug_id, "zero_power_while_on", is_bad,
            subject=f"{plug['label']} drawing no power",
            alert_message=f"{plug['label']} ({plug['purpose']}) is switched on but drawing "
                           f"{reading['watts']:.1f}W — bulb/element may have failed",
            resolved_message=f"{plug['label']} is drawing power again",
        )
