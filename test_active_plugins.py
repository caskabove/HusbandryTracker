"""Covers active_plugins.py — the Active Plugin list. See CONTEXT.md: Active Plugin; ADR 0045.

Run with: pytest test_active_plugins.py
"""
from __future__ import annotations

from active_plugins import is_plugin_active, read_active_plugins, write_active_plugins


def test_missing_file_means_nothing_active(active_plugins_path) -> None:
    assert read_active_plugins() == []
    assert is_plugin_active("log_husbandry") is False


def test_write_then_read_round_trip(active_plugins_path) -> None:
    write_active_plugins(["tuya_lan", "log_husbandry"])

    assert read_active_plugins() == ["tuya_lan", "log_husbandry"]
    assert is_plugin_active("log_husbandry") is True
    assert is_plugin_active("govee_ble") is False


def test_corrupt_file_treated_as_empty(active_plugins_path) -> None:
    active_plugins_path.parent.mkdir(parents=True, exist_ok=True)
    active_plugins_path.write_text("{not valid json", encoding="utf-8")

    assert read_active_plugins() == []


def test_write_is_atomic_no_leftover_tmp_file(active_plugins_path) -> None:
    write_active_plugins(["log_husbandry"])

    leftovers = list(active_plugins_path.parent.glob("*.tmp-*"))
    assert leftovers == []
    assert active_plugins_path.exists()
