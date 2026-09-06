import sys

from app.widgets.status_panel import (
    StatusPanel,
    slider_value_to_absolute_zoom,
    zoom_ratio_to_slider_value,
)
from app.device_manager import DeviceManager


def test_zoom_conversion_round_trip():
    assert zoom_ratio_to_slider_value(0) == 0
    assert zoom_ratio_to_slider_value(100) == 100
    assert slider_value_to_absolute_zoom(0) == 1.0
    assert slider_value_to_absolute_zoom(100) == 2.0
    assert slider_value_to_absolute_zoom(50) == 1.5


def test_connect_enables_controls(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    panel = StatusPanel(manager)
    qtbot.addWidget(panel)

    bridge.add_device("SN1", "Tiny2")
    bridge.connect_device("SN1")

    assert panel.zoom_slider.isEnabled()
    assert panel.mode_standard_btn.isEnabled()
    assert panel.ai_enabled_checkbox.isEnabled()


def test_ai_checkbox_reflects_status_and_toggles_device(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    panel = StatusPanel(manager)
    qtbot.addWidget(panel)
    device = bridge.add_device("SN1", "Tiny2")
    bridge.connect_device("SN1")

    device.push_status({"ai_mode": 1})
    assert panel.ai_enabled_checkbox.isChecked()

    panel.ai_enabled_checkbox.setChecked(False)
    assert ("set_ai_enabled", False) in device.calls


def test_status_update_moves_zoom_slider_when_not_dragging(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    panel = StatusPanel(manager)
    qtbot.addWidget(panel)
    device = bridge.add_device("SN1", "Tiny2")
    bridge.connect_device("SN1")

    device.push_status({"zoom_ratio": 73})

    assert panel.zoom_slider.value() == 73


def test_clicking_mode_button_calls_set_tracking_mode_and_enables_ai(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    panel = StatusPanel(manager)
    qtbot.addWidget(panel)
    device = bridge.add_device("SN1", "Tiny2")
    bridge.connect_device("SN1")

    panel.mode_motion_btn.click()

    assert ("set_tracking_mode", bridge.TrackMode.Motion) in device.calls
    assert ("set_ai_enabled", True) in device.calls
    assert panel.mode_motion_btn.isChecked()


def test_error_occurred_signal_emitted_on_device_error(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    panel = StatusPanel(manager)
    qtbot.addWidget(panel)
    device = bridge.add_device("SN1", "Tiny2")
    bridge.connect_device("SN1")

    def raise_error(*args, **kwargs):
        raise bridge.ObsbotError("Device communication failed")
    device.set_zoom = raise_error

    emitted_errors = []
    panel.error_occurred.connect(lambda msg: emitted_errors.append(msg))

    panel.zoom_slider.setValue(42)

    assert emitted_errors == ["Device communication failed"]
