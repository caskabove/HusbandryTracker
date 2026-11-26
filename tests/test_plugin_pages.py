"""Plugin Standard, Plugin Settings Pages, Plugin Settings, and Known Devices (see CONTEXT.md:
Plugin Standard, Plugin Settings Page, Plugin Setting, Known Device; docs/plugin-standard.md;
ADR 0061)."""
from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from starlette.requests import Request

from db.migrations import m0033_plugin_settings_and_known_devices as m0033
from web import admin as admin_routes
from web import admin_queries as q
from web import plugin_catalog
from web import plugin_queries as pq

SHIPPED = ["govee_ble", "kasa_lan", "log_husbandry", "tuya_lan"]


def _request(path: str) -> Request:
    from web.main import app
    return Request({"type": "http", "method": "GET", "path": path, "query_string": b"",
                    "headers": [], "app": app, "root_path": "", "state": {"user": None}})


# --- The Plugin Standard: every Plugin shipped in plugins/ must conform -------------------------

@pytest.mark.parametrize("name", SHIPPED)
def test_shipped_plugin_meets_the_standard(name):
    manifest, errors = plugin_catalog.validate_plugin_dir(plugin_catalog.PLUGINS_DIR / name)
    assert errors == []
    assert manifest["name"] == name


def test_every_plugin_folder_meets_the_standard(active_plugins_path):
    """The guard for future Plugins: adding a folder under plugins/ that doesn't conform fails CI."""
    invalid = {p.name: p.errors for p in plugin_catalog.list_plugins() if not p.valid}
    assert invalid == {}


@pytest.mark.parametrize("name", SHIPPED)
def test_shipped_plugin_hooks_have_the_standard_signatures(name):
    init = importlib.import_module(f"plugins.{name}.init")
    assert callable(init.activate) and callable(init.deactivate)
    plugin = plugin_catalog.get_plugin(name)
    if plugin.discovery:
        discover = importlib.import_module(f"plugins.{name}.discover")
        assert inspect.iscoroutinefunction(discover.discover)
        assert list(inspect.signature(discover.discover).parameters) == ["settings"]


# --- Validation of a non-conforming Plugin -------------------------------------------------------

@pytest.fixture()
def fake_plugins_dir(tmp_path, monkeypatch):
    """A private plugins/ holding a copy of govee_ble to break in various ways."""
    root = tmp_path / "plugins"
    shutil.copytree(plugin_catalog.PLUGINS_DIR / "govee_ble", root / "govee_ble",
                    ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setattr(plugin_catalog, "PLUGINS_DIR", root)
    return root


def _rewrite_manifest(plugin_dir: Path, **changes):
    path = plugin_dir / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for key, value in changes.items():
        if value is None:
            manifest.pop(key, None)
        else:
            manifest[key] = value
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_missing_required_field_is_invalid(fake_plugins_dir, active_plugins_path):
    _rewrite_manifest(fake_plugins_dir / "govee_ble", cannot=None)
    plugin = plugin_catalog.get_plugin("govee_ble")
    assert not plugin.valid
    assert any("cannot" in e for e in plugin.errors)


def test_name_must_match_folder(fake_plugins_dir, active_plugins_path):
    shutil.move(fake_plugins_dir / "govee_ble", fake_plugins_dir / "other_name")
    plugin = plugin_catalog.get_plugin("other_name")
    assert any("must match its folder name" in e for e in plugin.errors)


def test_discovery_without_discover_py_is_invalid(fake_plugins_dir, active_plugins_path):
    (fake_plugins_dir / "govee_ble" / "discover.py").unlink()
    assert any("discover.py is missing" in e for e in plugin_catalog.get_plugin("govee_ble").errors)


def test_device_plugin_needs_device_types(fake_plugins_dir, active_plugins_path):
    _rewrite_manifest(fake_plugins_dir / "govee_ble", device_types=[])
    assert not plugin_catalog.get_plugin("govee_ble").valid


def test_folder_without_manifest_is_listed_as_invalid(fake_plugins_dir, active_plugins_path):
    half = fake_plugins_dir / "half_written"
    half.mkdir()
    (half / "plugin.py").write_text("", encoding="utf-8")
    found = {p.name: p for p in plugin_catalog.list_plugins()}
    assert found["half_written"].errors == ["missing manifest.json"]


def test_helper_folders_are_not_listed(fake_plugins_dir, active_plugins_path):
    (fake_plugins_dir / "__pycache__").mkdir()
    (fake_plugins_dir / "notes").mkdir()
    assert [p.name for p in plugin_catalog.list_plugins()] == ["govee_ble"]


def test_invalid_plugin_cannot_be_activated(fake_plugins_dir, active_plugins_path):
    _rewrite_manifest(fake_plugins_dir / "govee_ble", how_it_works=None)
    with pytest.raises(ValueError, match="Plugin Standard"):
        plugin_catalog.activate_plugin("govee_ble")
    from active_plugins import read_active_plugins
    assert "govee_ble" not in read_active_plugins()


def test_get_plugin_rejects_path_tricks(active_plugins_path):
    for name in ["../web", "..", "__pycache__", "", "plugins/govee_ble"]:
        assert plugin_catalog.get_plugin(name) is None


# --- Plugin Settings -----------------------------------------------------------------------------

def _tuya_fields():
    return plugin_catalog.get_plugin("tuya_lan").settings


def test_settings_save_and_secret_is_never_shown(temp_db, active_plugins_path):
    pq.save_plugin_settings("tuya_lan", _tuya_fields(), {"access_id": "abc", "access_secret": "s3cret", "api_region": "eu"})
    assert pq.get_plugin_settings("tuya_lan") == {"access_id": "abc", "access_secret": "s3cret", "api_region": "eu"}
    view = pq.public_plugin_settings("tuya_lan", _tuya_fields())
    assert view["access_secret"] == {"value": "", "is_set": True}
    assert view["access_id"]["value"] == "abc"


def test_blank_secret_keeps_it_and_clear_removes_it(temp_db, active_plugins_path):
    fields = _tuya_fields()
    pq.save_plugin_settings("tuya_lan", fields, {"access_id": "abc", "access_secret": "s3cret", "api_region": "us"})
    pq.save_plugin_settings("tuya_lan", fields, {"access_id": "abc", "access_secret": "", "api_region": "us"})
    assert pq.get_plugin_settings("tuya_lan")["access_secret"] == "s3cret"
    pq.save_plugin_settings("tuya_lan", fields, {"access_id": "abc", "api_region": "us"}, clear_secrets={"access_secret"})
    assert "access_secret" not in pq.get_plugin_settings("tuya_lan")


def test_select_setting_must_be_a_declared_option(temp_db, active_plugins_path):
    with pytest.raises(ValueError, match="API Region"):
        pq.save_plugin_settings("tuya_lan", _tuya_fields(), {"api_region": "mars"})


def test_select_default_is_shown_before_anything_is_saved(temp_db, active_plugins_path):
    assert pq.public_plugin_settings("tuya_lan", _tuya_fields())["api_region"]["value"] == "us"


def test_migration_moves_tuya_credentials():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE app_setting (id INTEGER PRIMARY KEY, tuya_access_id TEXT, "
                 "tuya_access_secret TEXT, tuya_api_region TEXT NOT NULL DEFAULT 'us')")
    conn.execute("INSERT INTO app_setting VALUES (1, 'id1', 'sec1', 'eu')")
    m0033.migrate(conn)
    rows = dict(conn.execute("SELECT key, value FROM plugin_setting WHERE plugin = 'tuya_lan'").fetchall())
    assert rows == {"access_id": "id1", "access_secret": "sec1", "api_region": "eu"}
    m0033.migrate(conn)  # idempotent
    assert conn.execute("SELECT COUNT(*) FROM plugin_setting").fetchone()[0] == 3


# --- Known Devices -------------------------------------------------------------------------------

MAC = "AA:BB:CC:DD:EE:01"


def _sensor(label="warm side", mac=MAC) -> int:
    enclosure_id = q.create_enclosure("Tub", "basic", False, 7, 3, 7, 30)
    q.create_sensor(enclosure_id, label, "smart", mac, {})
    with temp_conn() as conn:
        return conn.execute("SELECT id FROM sensor WHERE external_id = ?", (mac,)).fetchone()[0]


def temp_conn():
    from db.db import get_connection
    return get_connection()


def test_name_an_unregistered_device(temp_db):
    pq.save_known_device("govee_ble", MAC, "Hide sensor", summary="75.0°F", seen=True)
    (device,) = pq.list_known_devices("govee_ble")
    assert device["name"] == "Hide sensor"
    assert device["registered"] is None
    assert device["last_seen_at"]
    assert [d["name"] for d in pq.unregistered_known_devices("govee_ble")] == ["Hide sensor"]


def test_blank_name_is_rejected(temp_db):
    with pytest.raises(ValueError):
        pq.save_known_device("govee_ble", MAC, "   ")


def test_registered_devices_appear_even_if_never_named(temp_db):
    _sensor("cool side")
    (device,) = pq.list_known_devices("govee_ble")
    assert device["name"] == "cool side"
    assert device["registered"]["type"] == "sensor"
    assert pq.unregistered_known_devices("govee_ble") == []


def test_renaming_a_registered_device_renames_the_sensor(temp_db):
    sensor_id = _sensor("old label")
    pq.save_known_device("govee_ble", MAC, "Basking probe")
    with temp_conn() as conn:
        assert conn.execute("SELECT label FROM sensor WHERE id = ?", (sensor_id,)).fetchone()[0] == "Basking probe"


def test_rename_keeps_scan_details(temp_db):
    pq.save_known_device("tuya_lan", "dev1:1", "Heat mat", plugin_config={"local_key": "k"}, summary="cz", seen=True)
    pq.save_known_device("tuya_lan", "dev1:1", "Heat mat 2")
    (device,) = pq.list_known_devices("tuya_lan")
    assert device["plugin_config"] == {"local_key": "k"}
    assert device["summary"] == "cz"


def test_forget_never_touches_a_registered_sensor(temp_db):
    _sensor("keep me")
    pq.save_known_device("govee_ble", MAC, "keep me")
    pq.forget_known_device("govee_ble", MAC)
    (device,) = pq.list_known_devices("govee_ble")
    assert device["registered"] and device["name"] == "keep me"


# --- Routes --------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", SHIPPED)
def test_every_shipped_plugin_has_a_settings_page(temp_db, active_plugins_path, name):
    response = admin_routes.admin_plugin_settings(_request(f"/admin/plugins/{name}"), name)
    html = response.body.decode("utf-8")
    assert response.status_code == 200
    assert "<h3>It can</h3>" in html and "<h3>It can't</h3>" in html
    assert ">Activate</button>" in html


def test_tuya_settings_page_never_renders_the_secret(temp_db, active_plugins_path):
    pq.save_plugin_settings("tuya_lan", _tuya_fields(), {"access_id": "abc", "access_secret": "TOPSECRET", "api_region": "us"})
    html = admin_routes.admin_plugin_settings(_request("/admin/plugins/tuya_lan"), "tuya_lan").body.decode("utf-8")
    assert "TOPSECRET" not in html
    assert "saved — leave blank to keep it" in html


def test_unknown_plugin_page_is_404(temp_db, active_plugins_path):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        admin_routes.admin_plugin_settings(_request("/admin/plugins/nope"), "nope")
    assert exc.value.status_code == 404


def test_admin_plugins_card_links_to_settings_instead_of_buttons(temp_db, active_plugins_path):
    html = admin_routes.admin_app(_request("/admin/app")).body.decode("utf-8")
    card = html[html.index("<h2>Plugins</h2>"):]
    card = card[:card.index("</section>")]
    assert 'href="/admin/plugins/tuya_lan">Settings</a>' in card
    assert "Activate</button>" not in card and "Deactivate</button>" not in card
    assert "Tuya Cloud Credentials" not in html


def test_scan_marks_named_devices(temp_db, active_plugins_path, monkeypatch):
    pq.save_known_device("govee_ble", MAC, "Hide sensor")

    async def fake_discover(name, settings):
        return [{"external_id": MAC, "suggested_name": "GVH5074", "summary": "75°F", "plugin_config": None},
                {"external_id": "AA:BB:CC:DD:EE:02", "suggested_name": "GVH5074", "summary": "70°F", "plugin_config": None}]
    monkeypatch.setattr(plugin_catalog, "run_discovery", fake_discover)

    data = json.loads(asyncio.run(admin_routes.admin_plugin_discover("govee_ble")).body)
    assert [d["name"] for d in data["devices"]] == ["Hide sensor", ""]


def test_scan_without_required_settings_explains_what_to_fill_in(temp_db, active_plugins_path):
    response = asyncio.run(admin_routes.admin_plugin_discover("tuya_lan"))
    assert response.status_code == 400
    assert "Access ID" in json.loads(response.body)["error"]


def test_skill_has_no_scan(temp_db, active_plugins_path):
    response = asyncio.run(admin_routes.admin_plugin_discover("log_husbandry"))
    assert response.status_code == 400


def test_known_devices_endpoint_gives_add_plug_form_fields(temp_db, active_plugins_path):
    pq.save_known_device("tuya_lan", "dev9:2", "Basking lamp", plugin_config={"local_key": "lk", "ip_address": None})
    data = json.loads(admin_routes.admin_plugin_known_devices("tuya_lan").body)
    assert data["devices"] == [{
        "name": "Basking lamp", "external_id": "dev9:2",
        "fields": {"tuya_device_id": "dev9", "switch_dps_key": "2", "tuya_local_key": "lk", "tuya_ip_address": ""},
    }]


def test_known_devices_endpoint_gives_add_sensor_form_fields(temp_db, active_plugins_path):
    pq.save_known_device("govee_ble", MAC, "Hide sensor")
    data = json.loads(admin_routes.admin_plugin_known_devices("govee_ble").body)
    assert data["devices"][0]["fields"] == {"mac_address": MAC}
