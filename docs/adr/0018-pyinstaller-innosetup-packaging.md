# Package HerpMonitor as a Windows installer via PyInstaller + Inno Setup

**Status**: accepted — resolves the open question ADR 0015 deliberately left unaddressed

ADR 0015 rejected a PyInstaller-bundled `.exe`/installer "for now," noting it was "left open if
this ever needs to be handed to someone else to install." HerpMonitor now needs exactly that: a
download-and-install path for a non-technical user, on top of the existing open-source repository
for anyone who wants to build from source.

**Decision**: freeze all five entry points (`tray/supervisor.py`, `web.main:app`, `ingest/ingest.py`,
`plugins/govee_ble/plugin.py`, `plugins/tuya_lan/plugin.py`) with PyInstaller as a single **onedir**
build — one shared `dist/` folder with five `.exe`s and one shared lib directory, not five
independent onefile bundles. The Supervisor restarts crashed children with backoff (2s/5s/15s/30s/60s,
ADR 0015); onefile's per-launch self-extraction cost would hit on every one of those restarts, and
five separate bundles would duplicate the shared dependency tree (fastapi, bleak, tinytuya, ...)
five times over in install size.

That `dist/` folder is wrapped in an **Inno Setup** installer (`.iss` script checked into the repo)
that:
- Installs per-user to `%LOCALAPPDATA%\Programs\HerpMonitor` — no admin rights, no UAC prompt.
  `data/db/logs` keep resolving relative to the install folder exactly as they do today
  (`db/db.py`, `ingest/ingest.py`, `tray/supervisor.py` all use `Path(__file__)`-relative paths);
  a Program Files install was rejected specifically because it would force moving those to
  `%LOCALAPPDATA%` separately and adding admin-rights handling for no real benefit to a
  single-user local tool.
- Creates the Start Menu entry and Desktop shortcut (replacing `tray/install.py`'s job).
- On uninstall, removes only the installed program files — `data/` (database, logs, Reading/Care
  Event history) is left behind by default. A reptile-care logbook's history is exactly the kind
  of thing an uninstall-reinstall shouldn't silently destroy.

The installer is **unsigned**. No code-signing certificate — an OV cert doesn't buy an instant
clean SmartScreen pass anyway (it still needs download reputation), and an EV cert's recurring
cost/hardware-token overhead isn't justified for a hobby open-source project. `docs/USER_GUIDE.md`
documents the "More info → Run anyway" click-through.

**Distribution**: GitHub Releases only, built by a GitHub Actions workflow on `windows-latest`
triggered by a pushed version tag (PyInstaller freeze → Inno Setup compile → attach `setup.exe` to
the matching Release), not built by hand. No in-app auto-updater — new versions are manual
download-and-run, which Inno Setup upgrades in place without touching `data/`.

Scoped to **Windows only** — matches the app's existing design (BLE via `bleak`, Tuya LAN
discovery, the Startup-folder autostart shortcut), all of which would need real rework to support
macOS/Linux. Cross-platform packaging is out of scope here, not just deferred.

**Consequences**: new `packaging/` (or similar) directory for the PyInstaller spec and the `.iss`
script; new `.github/workflows/release.yml`; `tray/install.py` and its Desktop-shortcut logic are
superseded by the installer for end users (still useful for someone running from source); a
top-level `README.md` and `LICENSE` (MIT) were added alongside this, since a repo with no README
was a dead end for the exact non-technical audience this packaging targets; first tagged release is
`v1.0.0`. Not addressed here: code signing, auto-update, and any non-Windows target — each would be
its own future decision.
