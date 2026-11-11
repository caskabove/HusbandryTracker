"""Shared constants for db/migrations/* — kept apart from db.db so migration modules never import
db.db (which imports the runner, which imports these), and so SCHEMA_PATH is the same file
db.db uses."""
from __future__ import annotations

from app_paths import APP_ROOT

SCHEMA_PATH = APP_ROOT / "db" / "schema.sql"
