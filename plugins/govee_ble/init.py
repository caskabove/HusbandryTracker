"""govee_ble's activate/deactivate hooks — see CONTEXT.md: Plugin Contract; ADR 0045/0047. A no-op
for every device Plugin today: activating/deactivating one only changes whether Ingest exports its
Registry and accepts its Inbox events (see ingest/ingest.py's Active Plugin checks); there's no
install/uninstall side effect the way a Skill's init has (see plugins/log_husbandry/init.py).
"""
from __future__ import annotations


def activate() -> None:
    pass


def deactivate() -> None:
    pass
