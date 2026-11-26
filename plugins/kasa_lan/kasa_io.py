"""The python-kasa calls shared by kasa_lan's discover.py (web process) and plugin.py (background
process). Kept in one place so both see a device the same way, especially how a power strip's
outlets are numbered, which is part of every outlet's External ID (see identity.py).

python-kasa talks to both TP-Link families over the local network:
- older Kasa plugs use the legacy local protocol and need no login;
- newer Kasa firmware and every Tapo plug need the owner's TP-Link (Kasa/Tapo app) email and
  password. The login is checked by the plug itself on the LAN; nothing goes through TP-Link's
  cloud, and there's no developer account or trial involved.
"""
from __future__ import annotations

from kasa import AuthenticationError, Credentials, Device, DeviceType, Discover, Module

# What this Plugin registers as a Plug. Bulbs, cameras, hubs etc. are left out of a scan.
SWITCHABLE_TYPES = {DeviceType.Plug, DeviceType.Strip, DeviceType.WallSwitch, DeviceType.Dimmer}

DISCOVERY_TIMEOUT_SECONDS = 5


def credentials_from(settings: dict[str, str]) -> Credentials | None:
    username = (settings.get("username") or "").strip()
    password = settings.get("password") or ""
    if username and password:
        return Credentials(username, password)
    return None


def outlets(device: Device) -> list[tuple[int | None, Device]]:
    """[(outlet_number, switchable)] for one updated device: [(None, device)] for a single plug, or
    [(1, child1), (2, child2), ...] for a power strip, in the order the strip reports them."""
    children = list(device.children or [])
    if not children:
        return [(None, device)]
    return [(index + 1, child) for index, child in enumerate(children)]


def outlet_device(device: Device, outlet: int | None) -> Device | None:
    """The Device to read/switch for one registered outlet, or None if the strip has fewer outlets
    than this one's number (the user typed the wrong number, or swapped the hardware)."""
    if outlet is None:
        return device
    children = list(device.children or [])
    if 1 <= outlet <= len(children):
        return children[outlet - 1]
    return None


def energy(device: Device) -> dict[str, float | None] | None:
    """{"watts", "volts", "amps"} for a device or outlet with an energy meter (e.g. Kasa KP115,
    EP25, HS300 per outlet; Tapo P110/P115), or None if it has none. A strip whose outlets have no
    meter of their own falls back to the strip's meter only for a single-outlet read."""
    module = device.modules.get(Module.Energy) if device.modules else None
    if module is None:
        return None
    reading = {
        "watts": _float_or_none(getattr(module, "current_consumption", None)),
        "volts": _float_or_none(getattr(module, "voltage", None)),
        "amps": _float_or_none(getattr(module, "current", None)),
    }
    return None if all(v is None for v in reading.values()) else reading


def _float_or_none(value) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def safe_mac(device: Device) -> str | None:
    """device.mac, or None when python-kasa can't tell yet (a plug that refused an unauthenticated
    update may not have reported it)."""
    try:
        mac = device.mac
    except Exception:  # python-kasa raises different errors per family before a successful update
        return None
    return mac or None


async def scan(credentials: Credentials | None) -> tuple[list[Device], int]:
    """One broadcast discovery on the local network. Returns (updated switchable devices,
    how many TP-Link devices refused because a TP-Link login is needed or wrong). Every Device in
    the first list has had update() called; the caller must disconnect() them."""
    found = await Discover.discover(credentials=credentials, discovery_timeout=DISCOVERY_TIMEOUT_SECONDS)
    devices: list[Device] = []
    needs_login = 0
    for device in found.values():
        try:
            await device.update()
        except AuthenticationError:
            needs_login += 1
            await _quiet_disconnect(device)
            continue
        except Exception:  # unreachable mid-scan, or a model python-kasa can't fully read
            await _quiet_disconnect(device)
            continue
        if device.device_type in SWITCHABLE_TYPES:
            devices.append(device)
        else:
            await _quiet_disconnect(device)
    return devices, needs_login


async def connect(host: str, credentials: Credentials | None) -> Device | None:
    """Connects to one known address and updates it. None if nothing TP-Link answers there."""
    device = await Discover.discover_single(host, credentials=credentials,
                                             discovery_timeout=DISCOVERY_TIMEOUT_SECONDS)
    if device is None:
        return None
    await device.update()
    return device


async def _quiet_disconnect(device: Device) -> None:
    try:
        await device.disconnect()
    except Exception:
        pass


disconnect = _quiet_disconnect
