# A tray-icon Supervisor replaces start.bat as the normal way to run HerpMonitor

**Status**: accepted

`start.bat` launched the Website, Ingest, and both Plugins each in their own visible `cmd /k`
window, left open on purpose — closing one was the only way to stop that part, and the console was
the only place to see its output. In practice this is four windows on the taskbar every time
HerpMonitor runs, with no way to start it automatically at login the way a normal background app
(Docker Desktop, Steam) does — those aren't Windows Services either, they're an ordinary
login-session process with a tray icon, autostarted via a Startup-folder shortcut. This ADR adopts
that same shape: a new **Supervisor** (`tray/supervisor.py`, see CONTEXT.md) is a small always-running
tray-icon process that starts, stops, restarts, and watches the other four, replacing `start.bat` as
the day-to-day entry point.

**Shape:**

- **Windowless children, not just a windowless Supervisor.** The Supervisor itself runs under
  `pythonw.exe` (no console of its own), and launches Website/Ingest/Govee/Tuya via `python.exe`
  with `subprocess.CREATE_NO_WINDOW` and their stdout/stderr redirected straight to a file — the
  combination that fully suppresses a console window even though `python.exe` itself is a
  console-subsystem executable. Losing the visible windows means losing the only place their output
  went, so each gets its own rotating log at `data/logs/<name>.log`, capped at 5MB and rotated
  (previous file renamed to `.log.1`) the next time that process starts or restarts — not
  continuously, since renaming a file out from under a process that's still writing to it doesn't
  reliably sever the old handle on Windows. A long-lived, never-crashing, never-manually-restarted
  process could in principle grow past the cap between rotations; accepted for a home system this
  size rather than building real log-rotation machinery for four processes that mostly get restarted
  by ordinary reboots and updates anyway.
- **Auto-restart with backoff, not silent, not infinite.** A component that crashes on its own is
  restarted automatically with a growing delay (2s/5s/15s/30s/60s), and the tray icon changes color
  (green/yellow/red/gray) so a crash loop is visible instead of silent. Staying up at least 60s
  resets the failure count; more than 5 quick failures in a row stops auto-restarting and leaves
  that component `failed` until someone clicks Start by hand — a crash loop that never gives up is
  worse than one that stops and asks for attention.
- **Per-component control, not just one Start/Stop for everything.** The tray menu lists all four
  with their own status and Start/Stop/Restart — mirroring what closing one of `start.bat`'s windows
  used to do — plus a top-level Start All/Stop All. Also: Open Dashboard, View Logs (opens
  `data/logs/` in Explorer), and a "Start with Windows" checkbox.
- **"Start with Windows" writes a Startup-folder shortcut, not a registry key or a scheduled task.**
  Toggling it adds/removes `HerpMonitor.lnk` in the per-user Startup folder pointing at the same
  `pythonw.exe tray/supervisor.py` invocation — visible and removable by hand if something goes
  wrong, the same mechanism most tray apps use, and it needs no admin rights. The shortcut itself is
  created via a one-off PowerShell call to `WScript.Shell`'s COM object rather than adding a
  dependency (`pywin32`, `winshell`) just for this. **Neither the Desktop nor the Startup folder is
  assumed at `%USERPROFILE%\Desktop`/`%APPDATA%\...\Startup`** — both are resolved via .NET's
  `[Environment]::GetFolderPath(...)`, the same API Explorer itself uses, inside that same
  PowerShell call. Found the hard way during rollout: a real machine had its Desktop redirected (via
  OneDrive's Known Folder Move, or a manual Properties → Location change — either can do this) to a
  folder that didn't exist, so `%USERPROFILE%\Desktop` silently wasn't a real path and shortcut
  creation failed. Resolving the known folder properly fixes it generically instead of special-casing
  OneDrive; the Startup-folder lookup is cached after its first call since it's checked on every tray
  menu refresh (~2s) and a redirected folder doesn't move again mid-session. See
  `docs/USER_GUIDE.md` §7 ("The Desktop shortcut didn't appear") for the user-facing fix when the
  Desktop folder itself doesn't exist yet.
- **Stays in the venv.** The Supervisor is just another script run the same way Ingest/the Plugins
  already are — no PyInstaller build, no standalone `.exe`, no installer. `tray/install.py` is a
  one-time setup step (same pattern as `db/db.py`) that creates a Desktop shortcut for the first
  manual launch; the tray's own checkbox handles the Startup-folder one from then on.
- **Always opens the dashboard**, a few seconds after launch (same delay `start.bat` used), whether
  that launch was manual or via the Startup shortcut at login — matching what `start.bat` already
  did, on the reasoning that the dashboard is this app's primary surface, not an optional extra.

**Considered Options**:
- **Just hide the windows, keep `start.bat`** (`pythonw`/`CREATE_NO_WINDOW` with no supervisor, no
  tray icon) — rejected: solves the clutter half but not the "run it like a background app,
  start/stop it, autostart it" half that motivated this in the first place, and removes the only
  stop mechanism (the visible window) without replacing it with anything.
- **A real Windows Service** (via `pywin32`'s `win32serviceutil` or NSSM) for Website/Ingest/the
  Plugins — rejected: heavier to install (admin rights, a service-install step) and to debug than
  what Docker Desktop/Steam — the explicit reference points for this decision — actually are; neither
  of those is a service either.
- **PyInstaller-bundled standalone `.exe`** — rejected for now: closer to a "real installed app" feel,
  but adds a build pipeline, an icon asset, and likely a Windows SmartScreen "unknown publisher"
  warning, for a single-user local tool that's fine staying in its existing venv-based install model.
  Left open if this ever needs to be handed to someone else to install.
- **One combined log file** for all four processes, tagged by source — rejected in favor of four
  separate files: easier to isolate one component's noise, and `View Logs` opening a folder in
  Explorer works either way.

**Consequences**: new `tray/` directory (`supervisor.py`, `install.py`); `pystray` and `Pillow` added
to `requirements.txt`; `start.bat` removed; `docs/USER_GUIDE.md`/`docs/PHASE1.md` updated to point at
`tray/install.py` + the Supervisor's tray menu instead. `data/logs/` is new (already covered by the
existing blanket `data/` gitignore rule). Not built here: a real installer/`.exe` (see Considered
Options), and log rotation continuous enough to cap a process that runs for weeks without ever
restarting.
