"""One-time setup for the Supervisor (see tray/supervisor.py, CONTEXT.md: Supervisor, ADR 0015):
creates a Desktop shortcut that launches it with pythonw.exe, so there's never a console window to
double-click into. Run once, from the activated venv:

    python tray\\install.py

After that, double-click the Desktop shortcut instead of running this again. Tick "Start with
Windows" in the Supervisor's own tray menu once it's running if you want it to launch automatically
at login too — that's a separate, smaller shortcut in your Startup folder, managed from the tray
menu, not by this script.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHONW = REPO_ROOT / ".venv" / "Scripts" / "pythonw.exe"
SUPERVISOR = Path(__file__).resolve().parent / "supervisor.py"


def main() -> None:
    if not VENV_PYTHONW.exists():
        raise SystemExit(
            "Virtual environment not found (.venv). Run the one-time setup steps in "
            "docs\\USER_GUIDE.md first, then try again."
        )

    # Resolve the Desktop via .NET's Environment.GetFolderPath (the same official API Explorer
    # itself uses) inside the same PowerShell call that creates the shortcut, rather than assuming
    # %USERPROFILE%\Desktop — OneDrive's "Known Folder Move" (and other redirections) can and does
    # move the real Desktop somewhere else entirely, and that folder silently just not existing is
    # exactly what makes CreateShortcut's Save() fail.
    script = f'''
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop 'HerpMonitor.lnk'
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut($shortcutPath)
$s.TargetPath = "{VENV_PYTHONW}"
$s.Arguments = '"{SUPERVISOR}"'
$s.WorkingDirectory = "{REPO_ROOT}"
$s.Description = "HerpMonitor Supervisor"
$s.Save()
Write-Output $shortcutPath
'''
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True, capture_output=True, text=True,
    )
    shortcut = result.stdout.strip().splitlines()[-1]
    print(f"Created {shortcut}")
    print('Double-click it to start HerpMonitor. Once it\'s running, tick "Start with Windows" in')
    print("its tray icon menu if you want it to launch automatically at login.")


if __name__ == "__main__":
    main()
