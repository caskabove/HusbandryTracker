"""Plugins — independent processes that each own one vendor/protocol integration end-to-end and
talk to the rest of HerpMonitor only via JSON files (the Registry export and the Inbox). See
CONTEXT.md: Plugin, Registry, Inbox, Plugin Event; ADR 0013. No plugin module here imports db.db —
that boundary is what keeps a Plugin swappable/rewritable in any language.
"""
