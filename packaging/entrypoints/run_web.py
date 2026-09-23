"""PyInstaller entry point for the frozen Website process (tray/supervisor.py's "website"
component, see ADR 0018) — equivalent to `uvicorn web.main:app --host 127.0.0.1 --port 22255`.
Imports the FastAPI `app` object directly and calls uvicorn.run() with it, rather than uvicorn's
string-based `"web.main:app"` target, since that form re-imports by module name through a resolver
uvicorn's reloader needs but a frozen build (no reload) doesn't, and direct import avoids any
ambiguity about where PyInstaller's frozen importer should find that name.
"""
from __future__ import annotations

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import uvicorn

from web.main import app

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=22255)
