# Dashboard Refresh scans for BLE itself, from the web process

**Status**: accepted

The dashboard's Sensor readings only update when the always-on `govee_collector.py` process
happens to hear a broadcast — real Govee sensors advertise irregularly (10-60+ seconds between
broadcasts, confirmed live against an H5102). A Refresh action (see `CONTEXT.md`) needs to actively
wait for a fresh one on demand, not just re-display whatever's already stored.

The open question was *who* does that live BLE listen, given `govee_collector.py` already owns
continuous scanning as a separate long-running process (ADR 0001) and `web` is a separate FastAPI
process with no BLE code of its own. Two processes both listening for BLE advertisements
concurrently is unremarkable — passive scanning is receive-only, not a connection, so multiple
listeners on the same host coexist the same way multiple apps can each see the same WiFi networks.
Given that, `web` now opens its own short-lived `BleakScanner` per Refresh request, reusing
`collectors/govee_protocol.py`'s decoders unchanged, rather than building any coordination channel
with the existing collector process.

Refresh is deliberately narrow in scope, matching a general rule for this app: **an action lives on
the entity that owns what it acts on, with no cascading through containment.** A Room's Refresh
button only reaches its own Sensor(s), never its Enclosures'; an Enclosure showing a borrowed
Fallback Sensor's Reading gets no Refresh button of its own — the Room's is the one that actually
owns that Sensor. One click's scan window listens for all of that entity's own Sensor MACs at once
(not sequential waits per Sensor), returning as soon as all have reported or the Refresh Timeout
elapses, whichever comes first.

Refresh Timeout is the first app-wide setting this codebase has ever needed (every other timing
knob — Tuya poll interval, registry refresh interval — is a plain code constant). Rather than build
a generic key-value settings mechanism for a single value, it's one column on a single-row
`app_setting` table, editable from Admin. Concurrent Refresh requests within the web process are
serialized by a lock — running two `BleakScanner` instances in the *same* process is untested
territory on Windows' underlying Bluetooth API, unlike the cross-process case above, which is
standard. A second request silently waits its turn rather than being rejected; this is single-user
software, so that queuing only ever matters for an accidental double-click.

Two alternatives were rejected:
- **Signaling the existing collector process** (a local socket, signal file, or queue table) to
  have it service the Refresh instead — rejected as real inter-process coordination for a problem a
  second independent scanner already solves, the same reasoning ADR 0002 used to drop Docker.
- **A Room's Refresh cascading to its Enclosures** (or vice versa) — rejected because it breaks the
  "action matches what it's attached to" rule above, trading a predictable click for a variable,
  hidden-scope one.

**Consequences**: `web/` gains a BLE dependency (`bleak`) it didn't have before — no longer purely a
DB-reading process. Refresh is a plain blocking form POST like every other action in this app (no
new client-side JavaScript); the browser just waits out the scan. Because `bleak`'s scanning is
`asyncio`-native and FastAPI route handlers are `async def`, a long-running Refresh request doesn't
block the event loop for other concurrent dashboard traffic — only concurrent Refresh requests
specifically serialize against each other. `_DECODERS` (the manufacturer-ID → decode-function list)
moves from being duplicated in `govee_collector.py` and `govee_discover.py` into
`collectors/govee_protocol.py` as the one shared source, now that a third consumer needs it.
