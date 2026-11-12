"""Which version of Husbandry Tracker is running — shown on the About page.

The release workflow (.github/workflows/release.yml) writes the tag's version (e.g. "1.0.7" from
tag v1.0.7) into a VERSION file at the repo root before freezing, and packaging/husbandrytracker.spec
bundles it next to the .exe's (APP_ROOT). A source checkout has no VERSION file (it's gitignored),
so it falls back to `git describe`, then to a plain "development build".
"""
from __future__ import annotations

import subprocess

from app_paths import APP_ROOT

VERSION_FILE = APP_ROOT / "VERSION"
DEV_VERSION = "development build"


def _read_version() -> str:
    try:
        text = VERSION_FILE.read_text(encoding="utf-8").strip()
        if text:
            return text
    except OSError:
        pass
    try:
        described = subprocess.run(
            ["git", "describe", "--tags", "--always", "--dirty"],
            cwd=APP_ROOT, capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout.strip()
        if described:
            return f"{DEV_VERSION} ({described})"
    except (OSError, subprocess.SubprocessError):
        pass
    return DEV_VERSION


APP_VERSION = _read_version()
