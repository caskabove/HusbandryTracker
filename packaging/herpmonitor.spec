# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for HerpMonitor (see ADR 0018) — freezes all five entry points that
tray/supervisor.py manages (Supervisor itself, Website, Ingest, the Govee plugin, the Tuya plugin)
into one shared onedir build: five .exe's in a single output folder, sharing one lib directory,
rather than five independent bundles. MERGE() is what makes that sharing possible — see PyInstaller's
"Multi-Package Bundles" docs — without it, each Analysis below would produce its own fully
duplicated copy of Python + every dependency (fastapi, bleak, tinytuya, ...).

Build with (from the repo root, using a venv that has `pip install -r requirements.txt pyinstaller`):
    pyinstaller packaging/herpmonitor.spec --distpath dist --workpath build --noconfirm

Output lands in dist/HerpMonitor/ — that whole folder is what packaging/herpmonitor.iss wraps into
the Windows installer. tray/supervisor.py's COMPONENTS dict expects these exact five .exe names
(HerpMonitorSupervisor.exe launches the other four as siblings in the same folder).
"""
from pathlib import Path

from PyInstaller.building.api import COLLECT, EXE, MERGE, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.utils.hooks import collect_all, collect_submodules

REPO_ROOT = Path(SPECPATH).resolve().parent

# Non-Python assets every entry point may need at runtime, resolved via app_paths.APP_ROOT (the
# folder holding the running .exe — see app_paths.py). Attached only to the "website" Analysis;
# COLLECT below places everything into one shared output folder regardless of which Analysis
# contributed it, so there's no need to repeat this list five times.
DATAS = [
    (str(REPO_ROOT / "web" / "templates"), "web/templates"),
    (str(REPO_ROOT / "web" / "static"), "web/static"),
    (str(REPO_ROOT / "docs" / "USER_GUIDE.md"), "docs"),
    (str(REPO_ROOT / "db" / "schema.sql"), "db"),
    (str(REPO_ROOT / "schemas" / "plugin_event.schema.json"), "schemas"),
    (str(REPO_ROOT / "schemas" / "plug_command.schema.json"), "schemas"),
]

# uvicorn and bleak both pick implementations dynamically at runtime (uvicorn's protocol/loop
# backends by string name; bleak's Windows backend via the `winrt` WinRT-projection namespace
# package spread across several winrt-Windows.* distributions), which PyInstaller's static import
# analysis can't see. pystray similarly selects its backend (`pystray._win32` on Windows) at import
# time based on platform. collect_all/collect_submodules pull in everything under each so a
# hidden-import gets bundled even though nothing directly `import`s it by name.
HIDDEN_IMPORTS = (
    collect_submodules("uvicorn")
    + collect_submodules("winrt")
    + ["pystray._win32"]
)
UVICORN_DATAS, UVICORN_BINARIES, _ = collect_all("uvicorn")
WINRT_DATAS, WINRT_BINARIES, _ = collect_all("winrt")
DATAS += UVICORN_DATAS + WINRT_DATAS
EXTRA_BINARIES = UVICORN_BINARIES + WINRT_BINARIES

PATHEX = [str(REPO_ROOT)]

COMMON_EXCLUDES = ["tkinter", "pytest", "test", "tests"]


def _analysis(script: str, extra_datas=None) -> Analysis:
    return Analysis(
        [str(REPO_ROOT / script)],
        pathex=PATHEX,
        binaries=EXTRA_BINARIES,
        datas=(extra_datas or []),
        hiddenimports=HIDDEN_IMPORTS,
        excludes=COMMON_EXCLUDES,
        noarchive=False,
    )


a_supervisor = _analysis("tray/supervisor.py")
a_web = _analysis("packaging/entrypoints/run_web.py", DATAS)
a_ingest = _analysis("ingest/ingest.py")
a_govee = _analysis("plugins/govee_ble/plugin.py")
a_tuya = _analysis("plugins/tuya_lan/plugin.py")

MERGE(
    (a_supervisor, "supervisor", "HerpMonitorSupervisor"),
    (a_web, "run_web", "HerpMonitorWeb"),
    (a_ingest, "ingest", "HerpMonitorIngest"),
    (a_govee, "plugin", "HerpMonitorGovee"),
    (a_tuya, "plugin", "HerpMonitorTuya"),
)


def _exe(analysis: Analysis, name: str, console: bool) -> EXE:
    pyz = PYZ(analysis.pure)
    return EXE(
        pyz,
        analysis.scripts,
        [],
        exclude_binaries=True,
        name=name,
        console=console,
        icon=None,
        # Flattens PyInstaller 6+'s default "everything but the exe goes in _internal/" onedir
        # layout back to the classic flat one (must be set per-EXE; COLLECT below just inherits it
        # from these) — app_paths.APP_ROOT resolves bundled data (web/templates, db/schema.sql,
        # ...) *and* the app's own writable data/ folder both directly beside the exe, and that
        # assumption is simpler to keep true than to special-case.
        contents_directory=".",
    )


# Supervisor is windowless (launched via pythonw-equivalent, no console — see ADR 0015); the
# other four keep a console=True subsystem even though Supervisor always launches them with
# CREATE_NO_WINDOW, matching how they already run today via python.exe (not pythonw.exe).
exe_supervisor = _exe(a_supervisor, "HerpMonitorSupervisor", console=False)
exe_web = _exe(a_web, "HerpMonitorWeb", console=True)
exe_ingest = _exe(a_ingest, "HerpMonitorIngest", console=True)
exe_govee = _exe(a_govee, "HerpMonitorGovee", console=True)
exe_tuya = _exe(a_tuya, "HerpMonitorTuya", console=True)

COLLECT(
    exe_supervisor, a_supervisor.binaries, a_supervisor.zipfiles, a_supervisor.datas,
    exe_web, a_web.binaries, a_web.zipfiles, a_web.datas,
    exe_ingest, a_ingest.binaries, a_ingest.zipfiles, a_ingest.datas,
    exe_govee, a_govee.binaries, a_govee.zipfiles, a_govee.datas,
    exe_tuya, a_tuya.binaries, a_tuya.zipfiles, a_tuya.datas,
    strip=False,
    upx=False,
    name="HerpMonitor",
)
