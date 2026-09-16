"""On-demand diagnostic query against a Smart Plug's own device — see CONTEXT.md: Probe, ADR 0016.

Deliberately outside the Outbox/Plugin pipeline (see ADR 0014) — the same "web talks to the device
directly, right now" shape web/govee_refresh.py already uses for Sensor Refresh (ADR 0005), just for
a different transport (a synchronous local Tuya call instead of a BLE scan). Strictly read-only:
never calls anything on the device but status() — Probe exists to observe, not to control.
"""
from __future__ import annotations

import tinytuya

# A plain hardcoded constant, not the Sensor-scoped Refresh Timeout setting (see ADR 0016) — a local
# LAN call has different failure behavior than a BLE broadcast wait. connection_retry_limit=1 keeps
# a failed Probe bounded to roughly this long instead of tinytuya's own default 5-retry backoff,
# which would leave someone staring at a blocked page for tens of seconds.
PROBE_TIMEOUT_SECONDS = 5


def probe_plug(tuya_device_id: str, tuya_local_key: str, tuya_ip_address: str | None, switch_dps_key: str) -> dict:
    """Makes one synchronous local status() call and returns the full raw dps dict, unfiltered —
    deliberately not narrowed to switch_dps_key's own value, since a shared power-strip device can
    report sibling outlets' keys in the same response (see CONTEXT.md: Plug, Probe).

    Raises RuntimeError on any failure (offline device, wrong local_key, bad IP, unreachable LAN
    address) with a message suitable to show directly on the Edit Plug page. tinytuya sometimes
    raises a plain Exception on a hard socket failure and sometimes returns an {"Error": ...} dict
    instead (see tinytuya.core.error_helper.error_json) — both are normalized to the same exception
    here so the caller only needs one except block.
    """
    device = tinytuya.OutletDevice(
        tuya_device_id, tuya_ip_address or "Auto", tuya_local_key, version="3.3",
        connection_timeout=PROBE_TIMEOUT_SECONDS, connection_retry_limit=1,
    )
    try:
        status = device.status()
    except Exception as exc:  # tinytuya raises plain exceptions on some timeout/network errors
        raise RuntimeError(str(exc)) from exc
    if not status or "Error" in status:
        raise RuntimeError(status.get("Error", "no response from device") if status else "no response from device")
    return status.get("dps", {})
