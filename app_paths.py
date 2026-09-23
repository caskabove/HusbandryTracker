"""Resolves HerpMonitor's on-disk root directory — the folder containing data/, db/schema.sql,
schemas/*.json, web/templates, web/static, and docs/USER_GUIDE.md — whether running from a source
checkout or as a PyInstaller-frozen onedir build (see ADR 0018).

A frozen pure-Python module's own `Path(__file__)` doesn't reliably point at a real path on disk
(it may live inside PyInstaller's bundled archive), so every module that used to derive its root via
`Path(__file__).resolve().parent[.parent...]` imports APP_ROOT from here instead. In frozen mode,
the root is the folder holding the running .exe, which the PyInstaller build (packaging/herpmonitor.spec)
populates with the same data/db/schemas/web/docs layout a source checkout has.
"""
from __future__ import annotations

import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    APP_ROOT = Path(sys.executable).resolve().parent
else:
    APP_ROOT = Path(__file__).resolve().parent
