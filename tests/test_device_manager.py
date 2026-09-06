import sys

from app.device_manager import DeviceManager


def test_start_picks_up_already_connected_device(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    bridge.add_device("SN1", "Tiny2")  # present before the manager exists
    manager = DeviceManager()

    with qtbot.waitSignal(manager.device_connected, timeout=1000) as blocker:
        manager.start()

    assert blocker.args == ["SN1", "Tiny2"]


def test_connect_emits_signal_and_exposes_device(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    bridge.add_device("SN123", "Tiny2")

    with qtbot.waitSignal(manager.device_connected, timeout=1000) as blocker:
        bridge.connect_device("SN123")

    assert blocker.args == ["SN123", "Tiny2"]
    assert manager.device is not None
    assert manager.device.sn == "SN123"


def test_disconnect_clears_device(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    bridge.add_device("SN123", "Tiny2")
    bridge.connect_device("SN123")

    with qtbot.waitSignal(manager.device_disconnected, timeout=1000):
        bridge.remove_device("SN123")

    assert manager.device is None


def test_status_update_populates_last_status_and_emits(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    device = bridge.add_device("SN123", "Tiny2")
    bridge.connect_device("SN123")

    with qtbot.waitSignal(manager.status_changed, timeout=1000) as blocker:
        device.push_status({"zoom_ratio": 42})

    assert blocker.args == [{"zoom_ratio": 42}]
    assert manager.last_status == {"zoom_ratio": 42}


def test_unsupported_product_type_is_ignored(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    bridge.add_device("SN1", "Some Meet Camera",
                      product_type=bridge.ProductType.Meet)

    manager.start()

    assert manager.device is None


def test_shutdown_closes_bridge():
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    manager.shutdown()
    assert bridge.closed is True
