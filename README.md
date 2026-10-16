# Husbandry Tracker

A CaskAbove product. A local-only monitoring and husbandry-tracking system for a reptile
collection: environmental readings (temperature, humidity), device schedules (light, heat,
cooling), and care events (feeding, watering, cleaning) — all in one private dashboard that runs on
your own computer.

**[⬇ Download for Windows](https://github.com/caskabove/HusbandryTracker/releases/latest)**

_The first installer release hasn't been published yet — until it is, use **Building from source** below._

No technical background needed — download `HusbandryTrackerSetup.exe` from the latest release above,
run it, and follow the prompts. Windows may show a "Windows protected your PC" warning the first
time, since this is a small open-source project without a paid code-signing certificate — click
**More info → Run anyway** to continue. Full setup and day-to-day usage instructions (adding
sensors and plugs, reading the dashboard, troubleshooting) are in
[`docs/USER_GUIDE.md`](docs/USER_GUIDE.md).

## What you need

- A Windows computer that stays on, near your animals (it listens for Govee sensors over
  Bluetooth — the closer, the more reliable).
- Govee **H5074** or **H5102** Bluetooth temp/humidity sensors, already set up in the Govee Home
  app.
- Optionally, Gosund smart plugs (for your lights, heat and cooling) set up through the Smart Life
  app. Husbandry Tracker monitors them — on/off state and schedules — but does not switch
  them on or off in this version.

See [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) for the complete walkthrough.

## Building from source

Husbandry Tracker is open source — clone the repo and run it directly with Python if you'd rather
not use the installer, or if you're on a platform other than Windows (note: Bluetooth/Tuya support
is currently only exercised on Windows).

```
git clone https://github.com/caskabove/HusbandryTracker.git
cd HusbandryTracker
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python tray\install.py
```

See [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) §2–3 for details, including how to run each
component manually without the tray Supervisor.

## Architecture

Husbandry Tracker's domain language and design decisions are documented as they're made:

- [`CONTEXT.md`](CONTEXT.md) — glossary of domain terms (Enclosure, Sensor, Plug, ...)
- [`docs/adr/`](docs/adr/) — architecture decision records, including why it's SQLite +
  local-only ([ADR 0001](docs/adr/0001-three-service-sqlite-architecture.md)), why Docker was
  dropped for local dev ([ADR 0002](docs/adr/0002-drop-docker-for-local-dev.md)), and how the
  Windows installer is packaged
  ([ADR 0018](docs/adr/0018-pyinstaller-innosetup-packaging.md)). The Windows installer is the supported install;
  `docker-compose.yml` remains as an optional, advanced way to run the web, ingest and Tuya
  processes (the Govee Bluetooth collector always runs on the host).

## License

Husbandry Tracker is free software, licensed under the GNU Affero General Public License v3.0 —
see [`LICENSE`](LICENSE). © CaskAbove.
