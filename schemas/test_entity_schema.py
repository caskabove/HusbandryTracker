"""Guards the §9.15 promise that db/schema.sql stays the single source of truth for storage: each
entity's `Read` model (the fullest variant — every stored column, nothing extra) must name exactly
the same set of columns as `PRAGMA table_info(<table>)` reports for a fresh database built from
db/schema.sql. Catches the two ways these can silently drift apart: a column added/renamed in
schema.sql and forgotten in the model, or a model field that doesn't correspond to any real column.

Run with: pytest schemas/test_entity_schema.py
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from schemas.animal import AnimalRead
from schemas.care_event import CareEventRead
from schemas.enclosure import EnclosureRead
from schemas.plant import PlantRead
from schemas.plug import PlugRead
from schemas.room import RoomRead
from schemas.sensor import SensorRead

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


@pytest.fixture()
def schema_conn() -> sqlite3.Connection:
    """A fresh in-memory database built from the real db/schema.sql — never the live data file,
    so this test can't touch or depend on anything a developer has actually collected."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        yield conn
    finally:
        conn.close()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    if not rows:
        raise AssertionError(f"PRAGMA table_info returned nothing for {table!r} — table name typo?")
    return {row[1] for row in rows}  # row[1] is the column name


@pytest.mark.parametrize("model, table", [
    (SensorRead, "sensor"),
    (PlugRead, "plug"),
    (CareEventRead, "care_event"),
    (EnclosureRead, "enclosure"),
    (RoomRead, "room"),
    (AnimalRead, "animal"),
    (PlantRead, "plant"),
])
def test_read_model_matches_table_columns(schema_conn: sqlite3.Connection, model, table: str) -> None:
    schema_columns = _table_columns(schema_conn, table)
    model_fields = set(model.model_fields.keys())

    missing_from_model = schema_columns - model_fields
    extra_in_model = model_fields - schema_columns

    assert not missing_from_model, (
        f"{model.__name__} is missing columns present in {table!r}: {sorted(missing_from_model)}"
    )
    assert not extra_in_model, (
        f"{model.__name__} has fields with no matching column in {table!r}: {sorted(extra_in_model)}"
    )
