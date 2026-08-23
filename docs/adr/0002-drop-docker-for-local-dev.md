# Run the web app directly via uvicorn instead of Docker, for now

**Status**: accepted — amends ADR 0001

ADR 0001 containerized `web` via docker-compose. In practice this bought nothing: `govee-collector`
already had to run on the host (BLE), `tuya-collector` isn't deployed yet, and containerizing `web`
was the direct cause of a real bug (SQLite WAL mode failing over Docker Desktop's Windows↔container
bind-mount bridge, worked around with `PRAGMA journal_mode = DELETE` and a connection-retry loop in
`db/db.py`). For a single local user on a single Windows machine, Docker's isolation/reproducibility
benefits aren't doing any work, and it's an extra large install for a tool meant to be simple to run.

`web` now runs directly via `uvicorn web.main:app` from the same venv the collectors use — no
Docker Desktop dependency for day-to-day use. The `Dockerfile` and `docker-compose.yml` stay in the
repo unused rather than deleted: cheap to keep, and worth revisiting if this ever moves to a
different machine (e.g. a Raspberry Pi) or genuinely needs isolation. The `DELETE` journal mode
change from the WAL bug stays either way — it works fine without Docker too, and switching back to
WAL for a marginal concurrency gain at this write volume isn't worth reintroducing the risk.
