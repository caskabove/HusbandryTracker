"""Covers web/plugin_catalog.py — Plugin discovery and (de)activation. See CONTEXT.md: Plugin
Contract, Active Plugin, Skill; ADR 0045/0046.

Run with: pytest web/test_plugin_catalog.py
"""
from __future__ import annotations

import json

import pytest

from web import plugin_catalog


@pytest.fixture()
def installed_skill_dir(tmp_path, monkeypatch):
    """Redirects log_husbandry's own init.py's install target so activating/deactivating it in a
    test never touches this repo's real .claude/skills/ — see plugins/log_husbandry/init.py."""
    import plugins.log_husbandry.init as log_husbandry_init
    target = tmp_path / "installed-skill"
    monkeypatch.setattr(log_husbandry_init, "_INSTALLED_SKILL_DIR", target)
    return target


# --- list_plugins (against the real plugins/ dir — proves the shipped manifest.json is found) --

def test_list_plugins_finds_log_husbandry(active_plugins_path) -> None:
    found = {p.name: p for p in plugin_catalog.list_plugins()}

    assert "log_husbandry" in found
    assert found["log_husbandry"].kind == "skill"
    assert found["log_husbandry"].active is False


def test_list_plugins_reflects_active_status(active_plugins_path) -> None:
    from active_plugins import write_active_plugins
    write_active_plugins(["log_husbandry"])

    found = {p.name: p for p in plugin_catalog.list_plugins()}
    assert found["log_husbandry"].active is True


# --- activate_plugin / deactivate_plugin (real log_husbandry, redirected install target) --------

def test_activate_plugin_installs_skill_and_marks_active(active_plugins_path, installed_skill_dir) -> None:
    plugin_catalog.activate_plugin("log_husbandry")

    assert (installed_skill_dir / "SKILL.md").exists()
    from active_plugins import read_active_plugins
    assert "log_husbandry" in read_active_plugins()


def test_deactivate_plugin_removes_skill_and_unmarks_active(active_plugins_path, installed_skill_dir) -> None:
    plugin_catalog.activate_plugin("log_husbandry")
    plugin_catalog.deactivate_plugin("log_husbandry")

    assert not installed_skill_dir.exists()
    from active_plugins import read_active_plugins
    assert "log_husbandry" not in read_active_plugins()


def test_activating_twice_does_not_duplicate_active_list_entry(active_plugins_path, installed_skill_dir) -> None:
    plugin_catalog.activate_plugin("log_husbandry")
    plugin_catalog.activate_plugin("log_husbandry")

    from active_plugins import read_active_plugins
    assert read_active_plugins() == ["log_husbandry"]


# --- error paths, against a synthetic plugin folder ----------------------------------------------

def test_activate_unknown_plugin_raises(active_plugins_path) -> None:
    with pytest.raises(ValueError):
        plugin_catalog.activate_plugin("no_such_plugin")


def test_plugin_with_no_importable_init_cannot_be_activated(active_plugins_path, tmp_path, monkeypatch) -> None:
    # _load_init's manifest-existence check is satisfied via a synthetic PLUGINS_DIR, but
    # importlib still resolves plugins.<name>.init against the real package tree — there's no
    # such real package, so this exercises the same failure path a Plugin satisfying only half
    # the contract (a manifest, no init.py — tuya_lan/govee_ble's actual shape today, ADR 0045)
    # would hit.
    plugins_dir = tmp_path / "plugins"
    plugin_dir = plugins_dir / "half_contract"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "manifest.json").write_text(
        json.dumps({"name": "half_contract", "description": "no init.py", "kind": "device"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(plugin_catalog, "PLUGINS_DIR", plugins_dir)

    with pytest.raises(ValueError):
        plugin_catalog.activate_plugin("half_contract")
