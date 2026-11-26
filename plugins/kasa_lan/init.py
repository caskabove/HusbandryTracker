"""kasa_lan's activate/deactivate hooks (see CONTEXT.md: Plugin Contract; docs/plugin-standard.md
section 4). No-ops, like every device Plugin's: activating only changes whether Ingest exports this
Plugin's Registry and runtime settings and accepts its Plugin Events.
"""
from __future__ import annotations


def activate() -> None:
    pass


def deactivate() -> None:
    pass
