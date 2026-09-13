"""Supervisor — see CONTEXT.md: Supervisor; ADR 0015. A tray-icon process supervisor that starts,
stops, restarts, and watches the four processes that make up a running HerpMonitor: Website
(uvicorn), Ingest, and the Govee/Tuya Plugins. Replaces start.bat as the normal way to run this day
to day.

Runs windowless — launch it with pythonw.exe (see tray/install.py), never python.exe, or you'll get
exactly the console window this exists to avoid. It launches its four children with a hidden
console of their own (CREATE_NO_WINDOW) and their stdout/stderr redirected to data/logs/<name>.log,
since a hidden window can't be watched directly the way start.bat's visible ones could.

Not a Plugin, not part of the Inbox/Registry/Outbox contract (see ADR 0013/0014) — it doesn't talk
to the database or to any Plugin's data at all, it only starts OS processes and watches whether
they're still alive.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
VENV_PYTHONW = REPO_ROOT / ".venv" / "Scripts" / "pythonw.exe"
LOG_DIR = REPO_ROOT / "data" / "logs"
DASHBOARD_URL = "http://localhost:22255"
DASHBOARD_OPEN_DELAY_SECONDS = 3  # give uvicorn a moment to come up first, same as start.bat did

MAX_LOG_BYTES = 5 * 1024 * 1024  # a log past this size is rotated the next time its process (re)starts
CRASH_BACKOFF_SECONDS = [2, 5, 15, 30, 60]  # capped, growing delay between auto-restarts of a crasher
MAX_CONSECUTIVE_FAILURES = 5  # stop auto-restarting and go to FAILED after this many quick deaths
MIN_HEALTHY_SECONDS = 60  # staying up this long resets a component's failure count back to 0

# One entry per child process. "args" is what follows VENV_PYTHON on the command line.
COMPONENTS = {
    "website": {
        "label": "Website",
        "args": ["-u", "-m", "uvicorn", "web.main:app", "--host", "127.0.0.1", "--port", "22255"],
    },
    "ingest": {
        "label": "Ingest",
        "args": ["-u", "ingest/ingest.py"],
    },
    "govee": {
        "label": "Sensor Plugin (Govee)",
        "args": ["-u", "plugins/govee_ble/plugin.py"],
    },
    "tuya": {
        "label": "Plug Plugin (Tuya)",
        "args": ["-u", "plugins/tuya_lan/plugin.py"],
    },
}

STATUS_COLORS = {
    "running": (46, 160, 67, 255),
    "starting": (46, 160, 67, 255),
    "restarting": (219, 171, 9, 255),
    "failed": (209, 36, 47, 255),
    "stopped": (110, 118, 129, 255),
}


def _open_log(name: str):
    """Open data/logs/<name>.log for append, rotating the previous one out of the way first if
    it's grown past MAX_LOG_BYTES. Rotation only happens here — at process (re)start — not
    continuously; see ADR 0015's Consequences for why that's an accepted tradeoff."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"{name}.log"
    if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
        backup = LOG_DIR / f"{name}.log.1"
        try:
            if backup.exists():
                backup.unlink()
            path.rename(backup)
        except OSError:
            pass  # best-effort — a locked file just keeps growing until a rotation actually succeeds
    return open(path, "a", encoding="utf-8", errors="replace")


class Component:
    """One supervised child process. `_run` owns the whole start/wait/restart loop and is the only
    method that touches `self.process` from a background thread; everything else just reads state
    or requests a stop."""

    def __init__(self, key: str, spec: dict):
        self.key = key
        self.spec = spec
        self.process: subprocess.Popen | None = None
        self.state = "stopped"
        self.failure_count = 0
        self._stop_requested = False
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self.state in ("starting", "running", "restarting"):
                return
            self.failure_count = 0
            self._stop_requested = False
            self.state = "starting"
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self) -> None:
        with self._lock:
            self._stop_requested = True
            proc = self.process
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    def restart(self) -> None:
        self.stop()
        self.start()

    def _run(self) -> None:
        while True:
            log_fh = _open_log(self.key)
            proc = subprocess.Popen(
                [str(VENV_PYTHON), *self.spec["args"]],
                cwd=str(REPO_ROOT),
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            with self._lock:
                self.process = proc
                self.state = "running"
            started_at = time.monotonic()

            proc.wait()

            try:
                log_fh.close()
            except OSError:
                pass
            uptime = time.monotonic() - started_at

            with self._lock:
                stop_requested = self._stop_requested
                self.process = None
            if stop_requested:
                with self._lock:
                    self.state = "stopped"
                return

            # Crashed on its own — decide whether to auto-restart it.
            if uptime >= MIN_HEALTHY_SECONDS:
                self.failure_count = 0
            self.failure_count += 1
            if self.failure_count > MAX_CONSECUTIVE_FAILURES:
                with self._lock:
                    self.state = "failed"
                return

            with self._lock:
                self.state = "restarting"
            delay = CRASH_BACKOFF_SECONDS[min(self.failure_count - 1, len(CRASH_BACKOFF_SECONDS) - 1)]
            time.sleep(delay)
            with self._lock:
                if self._stop_requested:
                    self.state = "stopped"
                    return
            # loop around and start it again


components: dict[str, Component] = {key: Component(key, spec) for key, spec in COMPONENTS.items()}


def start_all() -> None:
    for comp in components.values():
        comp.start()


def stop_all() -> None:
    threads = [threading.Thread(target=comp.stop) for comp in components.values()]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)


def _run_powershell(script: str, capture: bool = False) -> str:
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True, capture_output=capture, text=capture,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return result.stdout.strip() if capture else ""


_startup_dir_cache: Path | None = None


def _startup_dir() -> Path:
    """The per-user Startup folder, resolved via .NET's Environment.GetFolderPath (the same
    official API Explorer itself uses) rather than assumed as %APPDATA%\\...\\Startup — a known
    folder can be redirected (OneDrive's "Known Folder Move" does this to Desktop on this same
    machine; see tray/install.py). Cached after the first call since this is checked on every tray
    menu refresh (~every 2s) and a redirected folder doesn't move again mid-session."""
    global _startup_dir_cache
    if _startup_dir_cache is None:
        _startup_dir_cache = Path(_run_powershell("[Environment]::GetFolderPath('Startup')", capture=True))
    return _startup_dir_cache


def _startup_shortcut_path() -> Path:
    return _startup_dir() / "HerpMonitor.lnk"


def is_autostart_enabled() -> bool:
    return _startup_shortcut_path().exists()


def enable_autostart() -> None:
    """Drop a Startup-folder shortcut pointing at this same pythonw+supervisor.py invocation — the
    same mechanism Windows shortcuts always use, just written by PowerShell's WScript.Shell COM
    object instead of a bundled dependency (avoids adding pywin32 just for this)."""
    shortcut = _startup_shortcut_path()
    script = f'''
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut("{shortcut}")
$s.TargetPath = "{VENV_PYTHONW}"
$s.Arguments = '"{Path(__file__).resolve()}"'
$s.WorkingDirectory = "{REPO_ROOT}"
$s.Description = "HerpMonitor Supervisor"
$s.Save()
'''
    _run_powershell(script)


def disable_autostart() -> None:
    path = _startup_shortcut_path()
    if path.exists():
        path.unlink()


def make_icon_image(color: tuple[int, int, int, int]) -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 60, 60), fill=color, outline=(30, 30, 30, 255), width=3)
    draw.text((24, 16), "H", fill="white")
    return img


def _overall_color() -> tuple[int, int, int, int]:
    states = {comp.state for comp in components.values()}
    if "failed" in states:
        return STATUS_COLORS["failed"]
    if "restarting" in states:
        return STATUS_COLORS["restarting"]
    if "starting" in states:
        return STATUS_COLORS["starting"]
    if states == {"stopped"}:
        return STATUS_COLORS["stopped"]
    if states == {"running"}:
        return STATUS_COLORS["running"]
    return STATUS_COLORS["starting"]  # mixed running/stopped — treat as "in flux", not alarming


def _open_dashboard(icon=None, item=None) -> None:
    webbrowser.open(DASHBOARD_URL)


def _open_logs(icon=None, item=None) -> None:
    os.startfile(LOG_DIR)  # noqa: S606 — trusted, fixed, local path; not user input


def _toggle_autostart(icon, item) -> None:
    if is_autostart_enabled():
        disable_autostart()
    else:
        enable_autostart()


def _quit(icon, item) -> None:
    stop_all()
    icon.stop()


def _component_text(key: str):
    def text(item):
        comp = components[key]
        return f"{comp.spec['label']} — {comp.state}"

    return text


def _make_start(key: str):
    return lambda icon, item: components[key].start()


def _make_stop(key: str):
    return lambda icon, item: components[key].stop()


def _make_restart(key: str):
    return lambda icon, item: components[key].restart()


def _can_start(key: str):
    return lambda item: components[key].state in ("stopped", "failed")


def _can_stop_or_restart(key: str):
    return lambda item: components[key].state in ("running", "starting", "restarting")


def build_menu() -> pystray.Menu:
    component_items = [
        pystray.MenuItem(
            _component_text(key),
            pystray.Menu(
                pystray.MenuItem("Start", _make_start(key), enabled=_can_start(key)),
                pystray.MenuItem("Stop", _make_stop(key), enabled=_can_stop_or_restart(key)),
                pystray.MenuItem("Restart", _make_restart(key), enabled=_can_stop_or_restart(key)),
            ),
        )
        for key in COMPONENTS
    ]
    return pystray.Menu(
        pystray.MenuItem("Open Dashboard", _open_dashboard, default=True),
        pystray.Menu.SEPARATOR,
        *component_items,
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Start All", lambda icon, item: start_all()),
        pystray.MenuItem("Stop All", lambda icon, item: stop_all()),
        pystray.MenuItem("View Logs", _open_logs),
        pystray.MenuItem("Start with Windows", _toggle_autostart, checked=lambda item: is_autostart_enabled()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", _quit),
    )


def _ui_refresh_loop(icon: pystray.Icon) -> None:
    last_color = None
    while True:
        color = _overall_color()
        if color != last_color:
            icon.icon = make_icon_image(color)
            last_color = color
        icon.update_menu()
        time.sleep(2)


def _delayed_open_dashboard() -> None:
    time.sleep(DASHBOARD_OPEN_DELAY_SECONDS)
    _open_dashboard()


def main() -> None:
    if not VENV_PYTHON.exists():
        raise SystemExit(
            "Virtual environment not found (.venv). Run the one-time setup steps in "
            "docs\\USER_GUIDE.md first, then try again."
        )

    start_all()
    threading.Thread(target=_delayed_open_dashboard, daemon=True).start()

    icon = pystray.Icon("herpmonitor", make_icon_image(STATUS_COLORS["starting"]), "HerpMonitor", menu=build_menu())
    threading.Thread(target=_ui_refresh_loop, args=(icon,), daemon=True).start()
    icon.run()


if __name__ == "__main__":
    main()
