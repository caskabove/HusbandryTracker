# Three-service architecture with SQLite, Govee collector on host

**Status**: accepted

HerpMonitor is split into three logical services sharing one SQLite database on a Windows machine: `govee-collector` (Govee H5074 BLE listener), `tuya-collector` (local-Tuya Plug state watcher), and `web` (uvicorn dashboard/logbook on `localhost:22255`). `tuya-collector` and `web` run as docker-compose services; `govee-collector` runs as a host process rather than in a container, because Docker Desktop on Windows does not cleanly pass a Bluetooth adapter through to a container. SQLite was chosen over Postgres because the system is single-machine, single-user, and low write-volume (at most a few writes per minute) — an extra database container would add operational weight with no real benefit here.

If the collectors and database ever move off this machine (e.g. onto a Raspberry Pi nearer the animals), this decision should be revisited — the host/container split for BLE and the SQLite choice were both made specifically for the "one Windows machine" deployment target.

**Amended by ADR 0002**: `web` no longer runs via docker-compose day-to-day — it runs directly via uvicorn, same as the collectors. The SQLite choice and the host-process requirement for `govee-collector` are unaffected.

**Superseded in part by ADR 0013**: `govee-collector` and `tuya-collector` no longer read the database or write to it directly — each becomes a Plugin communicating with a new Ingest process via JSON files. The SQLite choice, the three-process shape, and the host-process requirement for BLE all remain unaffected; only "the collectors talk to SQLite directly" is superseded.
