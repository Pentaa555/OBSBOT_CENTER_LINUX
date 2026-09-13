import pytest
from app.gimbal_controller import GimbalController
from app.widgets.controls_panel import ControlsPanel
from tests.fake_bridge import FakeDevice


class FakeDeviceManager:
    def __init__(self, device):
        self.device = device
        self.last_status = {}


def test_controls_panel_inversion_toggles(qtbot):
    device = FakeDevice("SN1", "Tiny2")
    manager = FakeDeviceManager(device)
    controller = GimbalController(manager)
    panel = ControlsPanel(controller)
    qtbot.addWidget(panel)

    assert not controller.invert_pan
    assert not controller.invert_tilt

    panel.inv_pan_cb.setChecked(True)
    assert controller.invert_pan is True

    panel.inv_tilt_cb.setChecked(True)
    assert controller.invert_tilt is True


def test_controls_panel_speed_and_mode(qtbot):
    device = FakeDevice("SN1", "Tiny2")
    manager = FakeDeviceManager(device)
    controller = GimbalController(manager)
    panel = ControlsPanel(controller)
    qtbot.addWidget(panel)

    panel.speed_slider.setValue(50)
    assert controller.speed_scale == 0.5
    assert panel.speed_label.text() == "Velocidad: 50%"

    assert not controller.precision_mode
    panel.mode_btn.click()
    assert controller.precision_mode is True
    assert panel.mode_btn.text() == "Modo: Preciso"

    panel.mode_btn.click()
    assert controller.precision_mode is False
    assert panel.mode_btn.text() == "Modo: Grueso"

