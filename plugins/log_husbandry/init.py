"""log_husbandry's activate/deactivate hooks — see CONTEXT.md: Plugin Contract, Skill; ADR 0045.

Activating this Plugin copies its bundled Claude Code skill (this folder's skill/ subdirectory)
into the Husbandry Tracker repo's own project-scoped .claude/skills/log_husbandry/ — never the
user's global ~/.claude/skills/, since this Skill is useless outside a Husbandry Tracker install.
Deactivating removes it again, so a deactivated Skill leaves no dangling slash command behind.
web/plugin_catalog.py only persists the Active Plugin list change once whichever of these two
calls succeeds.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from app_paths import APP_ROOT

_PLUGIN_DIR = Path(__file__).resolve().parent
_BUNDLED_SKILL_DIR = _PLUGIN_DIR / "skill"
_INSTALLED_SKILL_DIR = APP_ROOT / ".claude" / "skills" / "log_husbandry"


def activate() -> None:
    if _INSTALLED_SKILL_DIR.exists():
        shutil.rmtree(_INSTALLED_SKILL_DIR)
    shutil.copytree(_BUNDLED_SKILL_DIR, _INSTALLED_SKILL_DIR)


def deactivate() -> None:
    if _INSTALLED_SKILL_DIR.exists():
        shutil.rmtree(_INSTALLED_SKILL_DIR)
