# HerpMonitor

A local-only monitoring and husbandry-tracking system for a reptile collection: environmental
readings (temperature, humidity), device schedules (light, heat, cooling), and care events
(feeding, watering, cleaning) — all in one private dashboard that runs on your own computer.

**[⬇ Download for Windows](https://github.com/kevinramsey2002/HerpMonitor/releases/latest)**

No technical background needed — download `HerpMonitorSetup.exe` from the latest release above,
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
- Optionally, Gosund smart plugs (light/heat/cooling control) set up through the Smart Life app.

See [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) for the complete walkthrough.

## Building from source

HerpMonitor is open source — clone the repo and run it directly with Python if you'd rather not
use the installer, or if you're on a platform other than Windows (note: Bluetooth/Tuya support is
currently only exercised on Windows).

```
git clone https://github.com/kevinramsey2002/HerpMonitor.git
cd HerpMonitor
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python tray\install.py
```

See [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) §2–3 for details, including how to run each
component manually without the tray Supervisor.

## Architecture

HerpMonitor's domain language and design decisions are documented as they're made:

- [`CONTEXT.md`](CONTEXT.md) — glossary of domain terms (Enclosure, Sensor, Plug, ...)
- [`docs/adr/`](docs/adr/) — architecture decision records, including why it's SQLite +
  local-only ([ADR 0001](docs/adr/0001-three-service-sqlite-architecture.md)), why Docker was
  dropped for local dev ([ADR 0002](docs/adr/0002-drop-docker-for-local-dev.md)), and how the
  Windows installer is packaged
  ([ADR 0018](docs/adr/0018-pyinstaller-innosetup-packaging.md)).

## License

[MIT](LICENSE)
