"""The kasa_lan Plugin (TP-Link Kasa / Tapo) and the Core pieces it needed: a Plug type on the Plug
forms, runtime Plugin Settings exported by Ingest, and Plugin validation in an installed build
(ADR 0062). No real hardware: python-kasa Devices are replaced with small fakes."""
from __future__ import annotations

import asyncio
import json
import shutil
import sys

import pytest
from starlette.requests import Request

from plugins.kasa_lan import discover as kasa_discover
from plugins.kasa_lan import identity, kasa_io
from plugins.kasa_lan import plugin as kasa_plugin
from web import admin as admin_routes
from web import admin_queries as q
from web import plugin_catalog
from web import plugin_queries as pq

MAC = "AA:BB:CC:DD:EE:01"
STRIP_MAC = "AA:BB:CC:DD:EE:02"


class FakeEnergy:
    def __init__(self, watts):
        self.current_consumption = watts
        self.voltage = 120.0
        self.current = round(watts / 120.0, 3)


class FakeDevice:
    def __init__(self, mac=MAC, alias="Basking lamp", host="192.168.1.40", is_on=True,
                 children=None, watts=None, model="KP115"):
        self.mac = mac
        self.alias = alias
        self.host = host
        self.is_on = is_on
        self.children = children or []
        self.model = model
        self.modules = {kasa_io.Module.Energy: FakeEnergy(watts)} if watts is not None else {}
        self.calls: list[str] = []

    async def update(self):
        self.calls.append("update")

    async def turn_on(self):
        self.calls.append("on")
        self.is_on = True

    async def turn_off(self):
        self.calls.append("off")
        self.is_on = False

    async def disconnect(self):
        self.calls.append("disconnect")


def _strip():
    children = [FakeDevice(mac=STRIP_MAC, alias=f"Outlet {i}", is_on=(i == 2), watts=10.0 * i) for i in (1, 2, 3)]
    return FakeDevice(mac=STRIP_MAC, alias="Rack strip", host="192.168.1.41", children=children, model="HS300")


# --- identity ---------------------------------------------------------------------------------

@pytest.mark.parametrize("raw", ["aa:bb:cc:dd:ee:01", "AA-BB-CC-DD-EE-01", "aabbccddee01", " AA:BB:CC:DD:EE:01 "])
def test_mac_is_normalized(raw):
    assert identity.normalize_mac(raw) == MAC


def test_bad_mac_is_explained():
    with pytest.raises(ValueError, match="isn't a MAC address"):
        identity.normalize_mac("192.168.1.40")


def test_external_id_round_trips_for_plug_and_outlet():
    assert identity.encode_external_id(MAC) == MAC
    assert identity.encode_external_id(MAC, "") == MAC
    assert identity.encode_external_id("aa:bb:cc:dd:ee:02", 2) == f"{STRIP_MAC}#2"
    assert identity.decode_external_id(f"{STRIP_MAC}#2") == (STRIP_MAC, 2)
    assert identity.decode_external_id(MAC) == (MAC, None)


def test_outlet_must_be_a_positive_number():
    with pytest.raises(ValueError):
        identity.encode_external_id(MAC, "two")
    with pytest.raises(ValueError):
        identity.encode_external_id(MAC, -1)


# --- discover.py ---------------------------------------------------------------------------------

def _fake_scan(devices, needs_login=0):
    async def scan(credentials):
        scan.credentials = credentials
        return devices, needs_login
    return scan


def test_scan_lists_single_plugs_and_each_strip_outlet(monkeypatch):
    plug, strip = FakeDevice(watts=55.0), _strip()
    monkeypatch.setattr(kasa_io, "scan", _fake_scan([plug, strip]))

    found = asyncio.run(kasa_discover.discover({}))

    ids = [d["external_id"] for d in found]
    assert ids == [MAC, f"{STRIP_MAC}#1", f"{STRIP_MAC}#2", f"{STRIP_MAC}#3"]
    assert found[0]["suggested_name"] == "Basking lamp"
    assert found[0]["plugin_config"] == {"host": "192.168.1.40"}
    assert "reports power use" in found[0]["summary"]
    assert "outlet 2 of HS300" in found[2]["summary"] and "currently on" in found[2]["summary"]
    assert "disconnect" in plug.calls and "disconnect" in strip.calls


def test_scan_passes_the_saved_login(monkeypatch):
    scan = _fake_scan([])
    monkeypatch.setattr(kasa_io, "scan", scan)

    asyncio.run(kasa_discover.discover({"username": "me@example.com", "password": "pw"}))

    assert scan.credentials.username == "me@example.com"


def test_scan_explains_when_plugs_need_a_login(monkeypatch):
    monkeypatch.setattr(kasa_io, "scan", _fake_scan([], needs_login=2))
    with pytest.raises(RuntimeError, match="2 TP-Link devices need your TP-Link login"):
        asyncio.run(kasa_discover.discover({}))


def test_scan_says_when_the_saved_login_is_refused(monkeypatch):
    monkeypatch.setattr(kasa_io, "scan", _fake_scan([], needs_login=1))
    with pytest.raises(RuntimeError, match="refused the TP-Link login"):
        asyncio.run(kasa_discover.discover({"username": "me@example.com", "password": "wrong"}))


def test_scan_keeps_found_plugs_and_still_mentions_locked_ones(monkeypatch):
    monkeypatch.setattr(kasa_io, "scan", _fake_scan([FakeDevice()], needs_login=1))
    found = asyncio.run(kasa_discover.discover({}))
    assert len(found) == 1 and "need" in found[0]["summary"]


def test_registration_fields_fill_the_kasa_form():
    assert kasa_discover.registration_fields(f"{STRIP_MAC}#3", {"host": "192.168.1.41"}) == {
        "plug_plugin": "kasa_lan", "kasa_mac": STRIP_MAC, "kasa_outlet": "3", "kasa_host": "192.168.1.41",
    }
    assert kasa_discover.registration_fields(MAC, None)["kasa_outlet"] == ""


# --- plugin.py (background process) ------------------------------------------------------------

def _write_registry(json_dirs, entries, settings=None):
    registry = json_dirs["registry"]
    registry.mkdir(parents=True, exist_ok=True)
    (registry / "kasa_lan.json").write_text(json.dumps(entries), encoding="utf-8")
    if settings is not None:
        (registry / "settings").mkdir(exist_ok=True)
        (registry / "settings" / "kasa_lan.json").write_text(json.dumps(settings), encoding="utf-8")


def _events(json_dirs, kind):
    folder = json_dirs["inbox"] / kind
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))] if folder.exists() else []


def test_registry_groups_strip_outlets_under_one_device(json_dirs):
    _write_registry(json_dirs, [
        {"external_id": f"{STRIP_MAC}#1", "plugin_config": {"host": "192.168.1.41"}, "auto_update_enabled": True},
        {"external_id": f"{STRIP_MAC}#3", "plugin_config": None, "auto_update_enabled": False},
        {"external_id": MAC, "plugin_config": None, "auto_update_enabled": True},
    ], settings={"username": "me@example.com", "password": "pw"})

    kasa_plugin.refresh_registry()

    assert kasa_plugin._hosts == {STRIP_MAC: "192.168.1.41", MAC: None}
    assert sorted(kasa_plugin.outlets_for(STRIP_MAC)) == [f"{STRIP_MAC}#1", f"{STRIP_MAC}#3"]
    assert kasa_plugin._settings["username"] == "me@example.com"


def test_report_writes_state_per_outlet_and_telemetry_when_due(json_dirs):
    _write_registry(json_dirs, [
        {"external_id": f"{STRIP_MAC}#2", "plugin_config": None, "auto_update_enabled": True},
        {"external_id": f"{STRIP_MAC}#3", "plugin_config": None, "auto_update_enabled": False},
    ])
    kasa_plugin.refresh_registry()

    kasa_plugin.report(_strip(), kasa_plugin.outlets_for(STRIP_MAC), capture_telemetry=True)

    states = _events(json_dirs, "plug_state")
    assert [(e["external_id"], e["payload"]) for e in states] == [(f"{STRIP_MAC}#2", {"is_on": True})]
    telemetry = _events(json_dirs, "plug_telemetry")
    assert telemetry[0]["payload"] == {"watts": 20.0, "volts": 120.0, "amps": 0.167, "countdown_seconds": None}


def test_report_skips_an_outlet_number_the_strip_does_not_have(json_dirs, capsys):
    _write_registry(json_dirs, [{"external_id": f"{STRIP_MAC}#9", "plugin_config": None, "auto_update_enabled": True}])
    kasa_plugin.refresh_registry()

    kasa_plugin.report(_strip(), [f"{STRIP_MAC}#9"], capture_telemetry=False)

    assert _events(json_dirs, "plug_state") == []
    assert "none numbered 9" in capsys.readouterr().out


def _run_one_poll(monkeypatch, device):
    """Runs poll_device for one cycle against a fake device."""
    connected = []

    async def connect(host, credentials):
        connected.append(host)
        return device

    monkeypatch.setattr(kasa_io, "connect", connect)

    async def go():
        stop = asyncio.Event()
        task = asyncio.create_task(kasa_plugin.poll_device(MAC, stop))
        for _ in range(50):
            await asyncio.sleep(0.01)
            if "update" in device.calls[1:] or device.calls.count("update") >= 1:
                break
        stop.set()
        await task

    asyncio.run(go())
    return connected


def test_poll_executes_a_pending_command_then_reports_the_new_state(json_dirs, monkeypatch):
    from web.outbox import write_command
    _write_registry(json_dirs, [{"external_id": MAC, "plugin_config": {"host": "192.168.1.40"}, "auto_update_enabled": True}])
    kasa_plugin.refresh_registry()
    write_command("kasa_lan", MAC, False, request_id=1)
    device = FakeDevice(is_on=True)

    connected = _run_one_poll(monkeypatch, device)

    assert connected == ["192.168.1.40"]
    assert device.calls[:2] == ["off", "update"]
    assert _events(json_dirs, "plug_state")[0]["payload"] == {"is_on": False}
    assert "disconnect" in device.calls


def test_poll_finds_a_plug_registered_without_an_ip_by_its_mac(json_dirs, monkeypatch):
    _write_registry(json_dirs, [{"external_id": MAC, "plugin_config": None, "auto_update_enabled": True}])
    kasa_plugin.refresh_registry()

    async def find_host(mac):
        return "192.168.1.77" if mac == MAC else None

    monkeypatch.setattr(kasa_plugin, "find_host", find_host)

    connected = _run_one_poll(monkeypatch, FakeDevice(host="192.168.1.77"))

    assert connected == ["192.168.1.77"]


def test_poll_refuses_a_different_device_at_the_old_address(json_dirs, monkeypatch, capsys):
    _write_registry(json_dirs, [{"external_id": MAC, "plugin_config": {"host": "192.168.1.40"}, "auto_update_enabled": True}])
    kasa_plugin.refresh_registry()

    _run_one_poll(monkeypatch, FakeDevice(mac="11:22:33:44:55:66"))

    assert _events(json_dirs, "plug_state") == []
    assert "is now a different device" in capsys.readouterr().out


# --- Core: Plug type on the Plug forms -----------------------------------------------------------

def _enclosure():
    return q.create_enclosure("Dart", "basic", False, 7, 3, 7, 30)


def test_create_a_kasa_plug(temp_db):
    eid = _enclosure()
    plug_id = q.create_plug("Basking lamp", "heat", "smart", None, None, None,
                            enclosure_ids=[eid], plugin="kasa_lan", kasa_mac="aa:bb:cc:dd:ee:02",
                            kasa_outlet="2", kasa_host="192.168.1.41")

    row = temp_db.execute("SELECT plugin, external_id, plugin_config FROM plug WHERE id = ?", (plug_id,)).fetchone()
    assert (row["plugin"], row["external_id"]) == ("kasa_lan", f"{STRIP_MAC}#2")
    assert json.loads(row["plugin_config"]) == {"host": "192.168.1.41"}
    plug = q.get_plug(plug_id)
    assert (plug["plug_plugin"], plug["kasa_mac"], plug["kasa_outlet"], plug["kasa_host"]) == \
        ("kasa_lan", STRIP_MAC, "2", "192.168.1.41")


def test_kasa_plug_needs_a_mac(temp_db):
    with pytest.raises(ValueError, match="needs its MAC address"):
        q.create_plug("Lamp", "heat", "smart", None, None, None, enclosure_ids=[_enclosure()], plugin="kasa_lan")


def test_same_kasa_outlet_cannot_be_registered_twice(temp_db):
    eid = _enclosure()
    q.create_plug("Lamp", "heat", "smart", None, None, None, enclosure_ids=[eid], plugin="kasa_lan", kasa_mac=MAC)
    with pytest.raises(ValueError, match="already registered"):
        q.create_plug("Lamp 2", "heat", "smart", None, None, None, enclosure_ids=[eid], plugin="kasa_lan", kasa_mac=MAC)


def test_unknown_plug_type_is_rejected(temp_db):
    with pytest.raises(ValueError, match="Unknown plug type"):
        q.create_plug("Lamp", "heat", "smart", None, None, None, enclosure_ids=[_enclosure()], plugin="nope")


def test_switching_a_tuya_plug_to_kasa(temp_db):
    eid = _enclosure()
    plug_id = q.create_plug("Lamp", "heat", "smart", "dev1", "key1", None, enclosure_ids=[eid])
    q.update_plug(plug_id, "Lamp", "heat", "smart", "1", None, None, None, enclosure_ids=[eid],
                  plugin="kasa_lan", kasa_mac=MAC)
    row = temp_db.execute("SELECT plugin, external_id, plugin_config FROM plug WHERE id = ?", (plug_id,)).fetchone()
    assert (row["plugin"], row["external_id"], row["plugin_config"]) == ("kasa_lan", MAC, None)


def test_tuya_plugs_are_unchanged_by_default(temp_db):
    plug_id = q.create_plug("Lamp", "heat", "smart", "dev1", "key1", "10.0.0.5", "2", enclosure_ids=[_enclosure()])
    plug = q.get_plug(plug_id)
    assert (plug["plug_plugin"], plug["tuya_device_id"], plug["switch_dps_key"]) == ("tuya_lan", "dev1", "2")
    assert plug["kasa_mac"] == ""


def _request(path: str) -> Request:
    from web.main import app
    return Request({"type": "http", "method": "GET", "path": path, "query_string": b"",
                    "headers": [], "app": app, "root_path": "", "state": {"user": None}})


def test_edit_page_preselects_kasa_and_shows_its_fields(temp_db, active_plugins_path):
    plug_id = q.create_plug("Lamp", "heat", "smart", None, None, None, enclosure_ids=[_enclosure()],
                            plugin="kasa_lan", kasa_mac=MAC, kasa_host="192.168.1.40")
    html = admin_routes._render_plug_edit(_request(f"/admin/plugs/{plug_id}/edit"), plug_id).body.decode()
    assert '<option value="kasa_lan" selected>' in html
    assert f'name="kasa_mac" value="{MAC}"' in html
    assert 'name="kasa_host" value="192.168.1.40"' in html
    assert "activate it on its Settings page" in html  # kasa_lan isn't Active in this test


def test_add_plug_forms_offer_the_plug_type(temp_db, active_plugins_path):
    html = admin_routes.admin_index(_request("/admin/")).body.decode()
    assert 'name="plug_plugin"' in html and 'data-plug-hw="kasa_lan"' in html
    assert "onDiscoverPluginClick(this, &#39;kasa_lan&#39;)" in html or "onDiscoverPluginClick(this, 'kasa_lan')" in html


def test_probe_explains_it_is_tuya_only(temp_db, active_plugins_path):
    plug_id = q.create_plug("Lamp", "heat", "smart", None, None, None, enclosure_ids=[_enclosure()],
                            plugin="kasa_lan", kasa_mac=MAC)
    html = admin_routes.admin_probe_plug(_request(f"/admin/plugs/{plug_id}/probe"), plug_id,
                                          plug_plugin="kasa_lan").body.decode()
    assert "Probe only works with Tuya plugs" in html


def test_scan_route_returns_form_fields_for_each_device(temp_db, active_plugins_path, monkeypatch):
    async def fake_discovery(name, settings):
        return [{"external_id": f"{STRIP_MAC}#1", "suggested_name": "Outlet 1", "plugin_config": {"host": "192.168.1.41"}}]
    monkeypatch.setattr(plugin_catalog, "run_discovery", fake_discovery)

    data = json.loads(asyncio.run(admin_routes.admin_plugin_discover("kasa_lan")).body)

    assert data["devices"][0]["fields"]["kasa_outlet"] == "1"


# --- Ingest: runtime Plugin Settings ----------------------------------------------------------

def test_ingest_exports_only_runtime_settings_of_active_plugins(temp_db, json_dirs, active_plugins_path):
    import active_plugins
    from ingest import ingest
    kasa_fields = plugin_catalog.get_plugin("kasa_lan").settings
    tuya_fields = plugin_catalog.get_plugin("tuya_lan").settings
    pq.save_plugin_settings("kasa_lan", kasa_fields, {"username": "me@example.com", "password": "pw"}, [])
    pq.save_plugin_settings("tuya_lan", tuya_fields, {"access_id": "id", "access_secret": "s3cret", "api_region": "us"}, [])
    settings_dir = json_dirs["registry"] / "settings"

    active_plugins.write_active_plugins(["kasa_lan", "tuya_lan"])
    ingest._export_runtime_settings()
    assert json.loads((settings_dir / "kasa_lan.json").read_text(encoding="utf-8")) == \
        {"username": "me@example.com", "password": "pw"}
    assert not (settings_dir / "tuya_lan.json").exists()  # nothing of tuya_lan's is runtime

    active_plugins.write_active_plugins(["tuya_lan"])
    ingest._export_runtime_settings()
    assert not (settings_dir / "kasa_lan.json").exists()


def test_runtime_settings_file_survives_registry_cleanup(temp_db, json_dirs, active_plugins_path):
    import active_plugins
    from ingest import ingest
    pq.save_plugin_settings("kasa_lan", plugin_catalog.get_plugin("kasa_lan").settings,
                            {"username": "me@example.com", "password": "pw"}, [])
    active_plugins.write_active_plugins(["kasa_lan"])
    ingest._export_runtime_settings()
    ingest._export_registry()
    assert (json_dirs["registry"] / "settings" / "kasa_lan.json").exists()


# --- Plugin validation in an installed (frozen) build --------------------------------------------

def test_installed_build_accepts_a_plugin_whose_code_is_bundled(tmp_path, monkeypatch):
    """In the installer only manifest.json is on disk; the .py files are inside the executable."""
    folder = tmp_path / "kasa_lan"
    folder.mkdir()
    shutil.copy(plugin_catalog.PLUGINS_DIR / "kasa_lan" / "manifest.json", folder / "manifest.json")
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    _, errors = plugin_catalog.validate_plugin_dir(folder)

    assert errors == []


def test_source_checkout_still_requires_the_files(tmp_path):
    folder = tmp_path / "kasa_lan"
    folder.mkdir()
    shutil.copy(plugin_catalog.PLUGINS_DIR / "kasa_lan" / "manifest.json", folder / "manifest.json")

    _, errors = plugin_catalog.validate_plugin_dir(folder)

    assert any("init.py" in e for e in errors)
