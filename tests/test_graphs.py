"""Tests for the Graphs page (see CONTEXT.md: Graphs, Overlay, Sparkline; ADR 0022) — both the
query layer's raw/aggregate/marker row shapes and the routes that render them.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from starlette.requests import Request

from web import admin as admin_routes
from web import graphs_queries as gq


def _request(path: str, query: str = "") -> Request:
    from web.main import app
    scope = {"type": "http", "method": "GET", "path": path, "query_string": query.encode(),
             "headers": [], "app": app, "root_path": ""}
    return Request(scope)


def _html(response) -> str:
    return response.body.decode("utf-8")


def _create_room(conn, name="Rack") -> int:
    conn.execute("INSERT INTO room (name) VALUES (?)", (name,))
    conn.commit()
    return conn.execute("SELECT id FROM room WHERE name = ?", (name,)).fetchone()["id"]


def _create_enclosure(conn, name="Tank") -> int:
    conn.execute("INSERT INTO enclosure (name) VALUES (?)", (name,))
    conn.commit()
    return conn.execute("SELECT id FROM enclosure WHERE name = ?", (name,)).fetchone()["id"]


def _create_manual_sensor(conn, enclosure_id: int, label="Probe") -> int:
    conn.execute(
        """INSERT INTO sensor (enclosure_id, label, tracking_mode, target_temp_min_c, target_temp_max_c)
           VALUES (?, ?, 'manual', 20, 30)""",
        (enclosure_id, label),
    )
    conn.commit()
    return conn.execute("SELECT id FROM sensor WHERE label = ?", (label,)).fetchone()["id"]


def _create_smart_sensor(conn, enclosure_id: int, label="Govee") -> int:
    conn.execute(
        """INSERT INTO sensor (enclosure_id, label, tracking_mode, plugin, external_id)
           VALUES (?, ?, 'smart', 'govee_ble', ?)""",
        (enclosure_id, label, f"AA:BB:{label}"),
    )
    conn.commit()
    return conn.execute("SELECT id FROM sensor WHERE label = ?", (label,)).fetchone()["id"]


def test_room_graphs_page_renders_for_an_empty_room(temp_db):
    room_id = _create_room(temp_db)

    html = _html(admin_routes.admin_room_graphs(_request(f"/admin/rooms/{room_id}/graphs"), room_id))

    assert "Rack" in html
    assert "Graphs" in html


def test_enclosure_graphs_page_always_shows_care_events_section(temp_db):
    enclosure_id = _create_enclosure(temp_db)

    html = _html(admin_routes.admin_enclosure_graphs(_request(f"/admin/enclosures/{enclosure_id}/graphs"), enclosure_id))

    assert "Care Events" in html


def test_manual_sensor_reading_is_a_raw_line_row(temp_db):
    enclosure_id = _create_enclosure(temp_db)
    sensor_id = _create_manual_sensor(temp_db, enclosure_id)
    temp_db.execute(
        "INSERT INTO sensor_reading (sensor_id, recorded_at, temperature_c) VALUES (?, datetime('now'), 25.0)",
        (sensor_id,),
    )
    temp_db.commit()

    end = date.today()
    sections = gq.build_enclosure_graph_sections(enclosure_id, end - timedelta(days=6), end, 7)

    rows = {r["key"]: r for s in sections for r in s["rows"]}
    row = rows[f"reading-{sensor_id}-temperature"]
    assert row["chart_type"] == "line"
    assert row["shape"] == "raw"
    assert len(row["series"]) == 1
    assert row["series"][0][1] == 77.0  # 25C -> 77F


def test_smart_sensor_readings_stay_raw_within_a_month(temp_db):
    enclosure_id = _create_enclosure(temp_db)
    sensor_id = _create_smart_sensor(temp_db, enclosure_id)
    for temp_c in (20.0, 21.0, 22.0):
        temp_db.execute(
            "INSERT INTO sensor_reading (sensor_id, recorded_at, temperature_c) VALUES (?, datetime('now'), ?)",
            (sensor_id, temp_c),
        )
    temp_db.commit()

    end = date.today()
    sections = gq.build_enclosure_graph_sections(enclosure_id, end - timedelta(days=29), end, 30)

    rows = {r["key"]: r for s in sections for r in s["rows"]}
    row = rows[f"reading-{sensor_id}-temperature"]
    assert row["shape"] == "raw"
    assert len(row["series"]) == 3


def test_smart_sensor_readings_aggregate_into_a_band_beyond_a_month(temp_db):
    enclosure_id = _create_enclosure(temp_db)
    sensor_id = _create_smart_sensor(temp_db, enclosure_id)
    for temp_c in (20.0, 22.0, 24.0):
        temp_db.execute(
            "INSERT INTO sensor_reading (sensor_id, recorded_at, temperature_c) VALUES (?, datetime('now'), ?)",
            (sensor_id, temp_c),
        )
    temp_db.commit()

    end = date.today()
    sections = gq.build_enclosure_graph_sections(enclosure_id, end - timedelta(days=364), end, 365)

    rows = {r["key"]: r for s in sections for r in s["rows"]}
    row = rows[f"reading-{sensor_id}-temperature"]
    assert row["shape"] == "band"
    assert len(row["series"]) == 1  # all three readings land in the same bucket
    _epoch, lo, avg, hi = row["series"][0]
    assert lo == 68.0 and hi == 75.2  # 20C/24C -> F
    assert lo < avg < hi


def test_care_event_marker_includes_animal_and_note(temp_db):
    enclosure_id = _create_enclosure(temp_db)
    temp_db.execute("INSERT INTO animal (enclosure_id, name) VALUES (?, 'Rex')", (enclosure_id,))
    temp_db.commit()
    animal_id = temp_db.execute("SELECT id FROM animal WHERE name = 'Rex'").fetchone()["id"]
    # occurred_at is local wall-clock, not UTC (see ADR 0021/0022) — the real app's own Today/
    # Yesterday/N-days-ago buttons already compute and store it that way, so the test does too
    # rather than relying on the column's raw datetime('now') (UTC) default.
    now_local = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    temp_db.execute(
        "INSERT INTO care_event (enclosure_id, animal_id, kind, note, occurred_at) VALUES (?, ?, 'feeding', 'extra pellet', ?)",
        (enclosure_id, animal_id, now_local),
    )
    temp_db.commit()

    end = date.today()
    sections = gq.build_enclosure_graph_sections(enclosure_id, end - timedelta(days=6), end, 7)

    rows = {r["key"]: r for s in sections for r in s["rows"]}
    row = rows[f"care-{enclosure_id}-feeding"]
    assert row["chart_type"] == "marker"
    assert len(row["series"]) == 1
    label = row["series"][0][1]
    assert "Rex" in label and "extra pellet" in label


def test_rows_by_key_filters_and_ignores_unknown_keys():
    sections = [
        {"title": "A", "rows": [{"key": "a1", "label": "A1"}, {"key": "a2", "label": "A2"}]},
        {"title": "B", "rows": [{"key": "b1", "label": "B1"}]},
    ]

    selected = gq.rows_by_key(sections, ["a2", "b1", "does-not-exist"])

    assert [row["key"] for row in selected] == ["a2", "b1"]


def test_overlay_chart_renders_when_rows_selected(temp_db):
    enclosure_id = _create_enclosure(temp_db)
    sensor_id = _create_manual_sensor(temp_db, enclosure_id)
    temp_db.execute(
        "INSERT INTO sensor_reading (sensor_id, recorded_at, temperature_c) VALUES (?, datetime('now'), 25.0)",
        (sensor_id,),
    )
    temp_db.commit()

    html = _html(admin_routes.admin_enclosure_graphs(
        _request(f"/admin/enclosures/{enclosure_id}/graphs", query=f"rows=reading-{sensor_id}-temperature"),
        enclosure_id,
    ))

    assert "Overlay" in html
    assert f"reading-{sensor_id}-temperature" in html
