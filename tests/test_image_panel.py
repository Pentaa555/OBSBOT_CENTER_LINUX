import sys

from app.widgets.image_panel import ImagePanel, PARAMS
from app.device_manager import DeviceManager


def _connect(bridge, manager):
    device = bridge.add_device("SN1", "Tiny2")
    bridge.connect_device("SN1")
    return device


def test_connect_enables_sliders_and_loads_current(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    panel = ImagePanel(manager)
    qtbot.addWidget(panel)

    device = _connect(bridge, manager)
    device.set_brightness(30)  # (also seeds a known current value)

    # Reconnect so the panel reads the seeded value.
    bridge.remove_device("SN1")
    device = bridge.add_device("SN1", "Tiny2")
    device._image["brightness"] = 30
    bridge.connect_device("SN1")

    assert panel._sliders["brightness"].isEnabled()
    assert panel.reset_button.isEnabled()
    assert panel._sliders["brightness"].value() == 30
    assert panel._sliders["brightness"].maximum() == 100


def test_disconnect_disables_sliders(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    panel = ImagePanel(manager)
    qtbot.addWidget(panel)
    _connect(bridge, manager)
    bridge.remove_device("SN1")

    assert not panel._sliders["contrast"].isEnabled()
    assert not panel.reset_button.isEnabled()


def test_moving_slider_sends_value(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    panel = ImagePanel(manager)
    qtbot.addWidget(panel)
    device = _connect(bridge, manager)

    panel._sliders["saturation"].setValue(72)

    qtbot.waitUntil(
        lambda: ("set_saturation", 72) in device.calls, timeout=1000)
    assert panel._value_labels["saturation"].text() == "72"


def test_rapid_changes_are_coalesced(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    panel = ImagePanel(manager)
    qtbot.addWidget(panel)
    device = _connect(bridge, manager)

    slider = panel._sliders["brightness"]
    for v in range(40, 61):
        slider.setValue(v)

    qtbot.waitUntil(
        lambda: ("set_brightness", 60) in device.calls, timeout=1000)
    # Coalescing must send fewer writes than the number of slider steps.
    brightness_calls = [c for c in device.calls if c[0] == "set_brightness"]
    assert len(brightness_calls) < 21
    assert brightness_calls[-1] == ("set_brightness", 60)


def test_reset_restores_defaults(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    panel = ImagePanel(manager)
    qtbot.addWidget(panel)
    device = _connect(bridge, manager)

    panel._sliders["sharpness"].setValue(10)
    panel._on_reset()

    assert panel._sliders["sharpness"].value() == 50  # fake default
    qtbot.waitUntil(
        lambda: ("set_sharpness", 50) in device.calls, timeout=1000)


def test_all_params_present(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    panel = ImagePanel(manager)
    qtbot.addWidget(panel)

    names = {name for name, _ in PARAMS}
    assert names == {"brightness", "contrast", "saturation", "sharpness"}
    for name in names:
        assert name in panel._sliders
