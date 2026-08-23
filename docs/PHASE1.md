# Phase 1: getting real data flowing

Walk through these in order. Terms below match `CONTEXT.md`.

## 0. Install dependencies

```
.venv\Scripts\activate
pip install -r requirements.txt
python db\db.py          # creates data\herpmonitor.db with the schema
```

## 1. Find your Govee sensors' MAC addresses

```
python tools\govee_discover.py 20
```

Run this near a sensor (Bluetooth must be on). It prints every Govee-looking BLE advertisement it
hears, the raw manufacturer-data bytes, and a **best-effort** decoded temp/humidity/battery.

**Before trusting the decoded numbers**, open the Govee app for the same sensor at the same
moment and compare. If they don't match, tell me the raw hex it printed and what the Govee app
actually shows — `collectors/govee_protocol.py`'s decode needs adjusting against your real
hardware, not guessed further from memory.

Write down each sensor's MAC address (e.g. `A4:C1:38:XX:XX:XX`) — you'll register it in step 4.

## 2. Get your Gosund plugs' Tuya credentials

Local Tuya control needs each plug's `device_id` and `local_key`, which only the Tuya cloud API
can hand out (one-time — after this, control is fully local/LAN, no more cloud calls needed).

```
python -m tinytuya wizard
```

This walks you through creating a free Tuya IoT Platform developer account, linking it to the
same account your Gosund/Smart Life app uses, and prints every device's `device_id`, `local_key`,
and last-known LAN IP into `devices.json` / `snapshot.json` in the current directory. **Those
files contain credentials — they're already gitignored, don't commit them.**

## 3. Verify each plug's on/off DPS key

Tuya devices report state as a `dps` dict; key `"1"` is the on/off switch for most single-outlet
plugs, but it's not guaranteed for every model.

```
python tools\tuya_probe.py <device_id> <local_key> --ip <ip_from_wizard>
```

Toggle the plug from the Google Home app while this runs and confirm which key flips. If it's not
`"1"`, tell me — `collectors/tuya_collector.py`'s `SWITCH_DPS_KEY` needs to change.

## 4. Register everything

One Enclosure per physical tank/tub, then its Animal(s), Sensor(s), and Plug(s):

```
python tools\register_device.py enclosure-add "Ball Python Tub" --bioactive
python tools\register_device.py animal-add "Ball Python Tub" "Noodle" --common "Ball Python" --scientific "Python regius" --dob 2019-04-02
python tools\register_device.py sensor-add "Ball Python Tub" "warm side" A4:C1:38:XX:XX:XX --temp-min 26 --temp-max 32
python tools\register_device.py plug-add "Ball Python Tub" "UTH" heat abc123deviceid 0123456789abcdef --ip 192.168.1.50
python tools\register_device.py list
```

## 5. Run the collectors

Two separate processes (see ADR 0001 for why Govee stays out of Docker for now):

```
python -u collectors\govee_collector.py
python -u collectors\tuya_collector.py
```

(`-u` disables Python's stdout buffering — without it, `print()` output only shows up in bursts
when piped/redirected rather than in a real terminal, even though DB writes happen immediately
either way.)

Leave both running. Check `data\herpmonitor.db` (e.g. with the `sqlite3` CLI or DB Browser for
SQLite) — `sensor_reading` rows should accumulate continuously, and `plug_state_transition` rows
should appear whenever a light/heat/cooling plug actually flips.

## What's NOT built yet

- No web UI — this phase is collectors + raw data only, per the CONTEXT.md decisions.
- No Schedule inference logic yet (deriving "on ~08:00 for ~12h" from `plug_state_transition`
  history) — that's a Phase 2 concern once there's enough transition history to infer from.
- No Docker/compose yet — these scripts run directly via the venv for now; containerizing
  `tuya_collector` + the future `web` service comes with Phase 2.
