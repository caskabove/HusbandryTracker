"""Water-chemistry Target Range metrics after RHA-115 / ADR 0060: Ammonia/Nitrite retired (hidden in
code, columns kept), KH/TDS/Phosphate on Freshwater, KH relabeled everywhere."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import db.db as db_module
from db.migrate import run_migrations
from db.migrations import LATEST_VERSION
from schemas import enclosure_types as et
from schemas.species_profile_kb import PROFILE_CATEGORIES as CATEGORIES
from web import admin_queries as q


def _keys(enclosure_type: str) -> list[str]:
    return [m.key for m in et.target_range_metrics_for(enclosure_type)]


# --- which metrics each Enclosure Type offers ------------------------------------------------------

def test_freshwater_metrics_in_display_order():
    assert _keys("freshwater") == ["temperature", "ph", "alkalinity", "tds", "nitrate", "phosphate"]


def test_saltwater_metrics_in_display_order():
    assert _keys("saltwater") == [
        "temperature", "ph", "alkalinity", "nitrate",
        "specific_gravity", "salinity", "calcium", "magnesium", "phosphate",
    ]


def test_amphibian_metrics():
    assert _keys("amphibian") == ["temperature", "humidity", "uvb", "ph", "nitrate"]


def test_ammonia_and_nitrite_are_retired_everywhere():
    for etype in et.ENCLOSURE_TYPES:
        assert "ammonia" not in _keys(etype) and "nitrite" not in _keys(etype)
    assert {m.key for m in et.RETIRED_TARGET_RANGE_METRICS} == {"ammonia", "nitrite"}
    with pytest.raises(ValueError):
        et.metric_by_key("ammonia")


def test_kh_label_and_tds_shape():
    kh = et.metric_by_key("alkalinity")
    assert (kh.label, kh.unit) == ("KH", "dKH")
    tds = et.metric_by_key("tds")
    assert (tds.label, tds.unit, tds.step, tds.decimals, tds.default_volatility) == ("TDS", "ppm", "1", 0, "slow")


def test_tds_rejected_on_saltwater():
    with pytest.raises(ValueError, match="TDS"):
        et.validate_target_ranges("saltwater", ["tds"])


# --- Knowledge Base ----------------------------------------------------------------------------------

def test_kb_hides_ammonia_nitrite_and_says_kh():
    columns = {f.column for c in CATEGORIES for f in c.fields}
    assert "ammonia_ppm_max" not in columns and "nitrite_ppm_max" not in columns
    invert = next(c for c in CATEGORIES if c.key == "saltwater_invert")
    labels = {f.column: f.label for f in invert.fields}
    assert labels["alkalinity_dkh_min"] == "KH min" and labels["alkalinity_dkh_max"] == "KH max"


# --- database --------------------------------------------------------------------------------------

def test_freshwater_sensor_saves_tds_and_leaves_retired_columns_alone(temp_db: sqlite3.Connection):
    enclosure_id = q.create_enclosure("Tank", "freshwater", False, 1, 1, 1, 1)
    q.create_sensor(enclosure_id, "Test kit", "manual", None,
                    {"tds": (150, 250), "alkalinity": (3, 8), "phosphate": (0, 1)}, {"tds": "fast"})
    sensor_id = temp_db.execute("SELECT id FROM sensor").fetchone()[0]
    # Simulate an older install's Ammonia Target Range — a save must not wipe it.
    temp_db.execute("UPDATE sensor SET target_ammonia_ppm_max = 0.25 WHERE id = ?", (sensor_id,))
    temp_db.commit()

    q.update_sensor(sensor_id, enclosure_id, "Test kit", "manual", None, {"tds": (100, 300)}, True, {})
    row = temp_db.execute(
        "SELECT target_tds_ppm_min, target_tds_ppm_max, target_ammonia_ppm_max FROM sensor WHERE id = ?",
        (sensor_id,),
    ).fetchone()
    assert tuple(row) == (100, 300, 0.25)


def test_migration_30_adds_tds_columns_to_an_existing_database(tmp_path: Path, monkeypatch):
    path = tmp_path / "husbandrytracker.db"
    monkeypatch.setattr(db_module, "DB_PATH", path)
    run_migrations()
    conn = sqlite3.connect(path)
    conn.execute("ALTER TABLE sensor DROP COLUMN target_tds_ppm_min")
    conn.execute("ALTER TABLE sensor DROP COLUMN target_tds_ppm_max")
    conn.execute("ALTER TABLE sensor DROP COLUMN volatility_tds")
    conn.execute("ALTER TABLE sensor_reading DROP COLUMN tds_ppm")
    conn.execute("PRAGMA user_version = 29")
    conn.commit()
    conn.close()

    assert run_migrations() == LATEST_VERSION - 29
    conn = sqlite3.connect(path)
    sensor_cols = {r[1] for r in conn.execute("PRAGMA table_info(sensor)")}
    reading_cols = {r[1] for r in conn.execute("PRAGMA table_info(sensor_reading)")}
    conn.close()
    assert {"target_tds_ppm_min", "target_tds_ppm_max", "volatility_tds"} <= sensor_cols
    assert "tds_ppm" in reading_cols
    # Retired columns are still physically present.
    assert {"target_ammonia_ppm_min", "volatility_nitrite"} <= sensor_cols
    assert {"ammonia_ppm", "nitrite_ppm"} <= reading_cols
