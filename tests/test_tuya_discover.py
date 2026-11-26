"""Tuya Discover Devices (ADR 0030): a Tuya Cloud refusal must reach the user as its real reason,
not as an empty "No devices found" list."""
from __future__ import annotations

import pytest

from web import tuya_discover


class _FakeCloud:
    probe: dict = {"success": True, "result": {"devices": []}}
    devices: list = []

    def __init__(self, **kwargs):
        self.error = None

    def cloudrequest(self, url, query=None):
        return self.probe

    def getdevices(self):
        return self.devices

    def getstatus(self, device_id):
        return {"success": True, "result": [{"code": "switch_1", "value": True}]}


@pytest.fixture
def fake_cloud(monkeypatch):
    monkeypatch.setattr(tuya_discover.tinytuya, "Cloud", _FakeCloud)
    _FakeCloud.probe = {"success": True, "result": {"devices": []}}
    _FakeCloud.devices = []
    return _FakeCloud


def test_expired_iot_core_subscription_is_reported_with_how_to_renew(fake_cloud):
    fake_cloud.probe = {"success": False, "code": 28841002,
                        "msg": "IoT Core service subscription has expired."}

    with pytest.raises(RuntimeError) as exc:
        tuya_discover._discover_tuya_sync("id", "secret", "us")

    assert "IoT Core service subscription has expired." in str(exc.value)
    assert "Extend Trial Period" in str(exc.value)
    assert "secret" not in str(exc.value)


def test_other_cloud_refusals_pass_tuyas_message_through(fake_cloud):
    fake_cloud.probe = {"success": False, "code": 1106, "msg": "permission deny"}

    with pytest.raises(RuntimeError, match="permission deny"):
        tuya_discover._discover_tuya_sync("id", "secret", "us")


def test_linked_devices_are_listed_with_a_switch_key_guess(fake_cloud):
    fake_cloud.devices = [{"id": "abc", "name": "Heat lamp", "key": "k", "category": "cz"}]

    devices = tuya_discover._discover_tuya_sync("id", "secret", "us")

    assert devices == [{"id": "abc", "name": "Heat lamp", "local_key": "k", "category": "cz",
                        "switch_key_guess": "1"}]
