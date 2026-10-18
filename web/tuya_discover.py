"""On-demand Tuya Cloud lookup for the Add Plug / Add Plug Group forms' "Discover Devices" button
(see ADR 0030) — replaces the `python -m tinytuya wizard` Command Prompt step.

Unlike web/govee_refresh.py's discover_govee(), there's no local radio to listen to here: a Tuya
plug's device ID and local key live only in Tuya's cloud, tied to whatever account paired it in
Smart Life/Tuya Smart. This calls that cloud directly (tinytuya.Cloud, already a dependency of
plugins/tuya_lan) using Access ID/Secret the user saved once via the Tuya Cloud Credentials
settings card. Writes nothing to the database — purely diagnostic, same as Probe (ADR 0016) and
Discover/Govee (ADR 0029).

tinytuya.Cloud's HTTP calls are synchronous (the `requests` library); run via asyncio.to_thread so
a Discover click doesn't block the event loop.
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tinytuya


def _switch_key_guess(code: str) -> str | None:
    """Best-effort only — see ADR 0030. Tuya's own naming convention maps "switch_1" -> DPS key
    "1", "switch" (no suffix) -> "1", but a product with a non-standard DPS layout needs
    tools/tuya_probe.py's physical toggle-and-watch check regardless."""
    match = re.fullmatch(r"switch(?:_(\d+))?", code)
    if not match:
        return None
    return match.group(1) or "1"


def _discover_tuya_sync(access_id: str, access_secret: str, api_region: str) -> list[dict]:
    cloud = tinytuya.Cloud(apiRegion=api_region, apiKey=access_id, apiSecret=access_secret)
    if cloud.error:
        # Cloud.__init__ swallows an auth failure into .error/.token=None rather than raising, and
        # a token-less getdevices() below silently returns [] instead of surfacing it — so this has
        # to be checked here, right after construction, or a bad credential looks like "no devices."
        raise RuntimeError(cloud.error.get("Payload") or cloud.error.get("Error") or "Tuya Cloud rejected these credentials.")
    devices = cloud.getdevices()
    if isinstance(devices, dict) and "Error" in devices:
        raise RuntimeError(devices.get("Error") or "Tuya Cloud rejected these credentials.")

    results = []
    for dev in devices:
        device_id = dev.get("id")
        if not device_id:
            continue
        switch_key_guess = None
        status = cloud.getstatus(device_id)
        if isinstance(status, dict) and status.get("success"):
            for dp in status.get("result", []):
                switch_key_guess = _switch_key_guess(dp.get("code", ""))
                if switch_key_guess:
                    break
        results.append({
            "id": device_id,
            "name": dev.get("name") or dev.get("product_name") or device_id,
            "local_key": dev.get("key", ""),
            "category": dev.get("category", ""),
            "switch_key_guess": switch_key_guess,
        })
    return sorted(results, key=lambda d: d["name"].lower())


async def discover_tuya(access_id: str, access_secret: str, api_region: str) -> list[dict]:
    """access_id/access_secret: from the Tuya Cloud Credentials settings card. Raises RuntimeError
    with a message safe to show the user (never includes the secret) if Tuya's cloud rejects the
    credentials or the request otherwise fails."""
    return await asyncio.to_thread(_discover_tuya_sync, access_id, access_secret, api_region)
