"""Smoke test for MainWindow's Qt wiring — not a re-test of any widget's
own already-covered behavior (see test_gimbal_controller.py,
test_joystick_widget.py, etc.). Uses the fake obsbot_bridge module
installed by tests/conftest.py, so no real device or bridge is needed.
"""
from __future__ import annotations

from app.main_window import MainWindow
from tests.fake_bridge import FakeDevice


def test_joystick_wired_to_gimbal_controller(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    # GimbalController.start() is a no-op when device_manager.device is
    # None (already covered by test_gimbal_controller.py), so give it a
    # device directly here — no need to go through bridge.add_device /
    # connect_device, this is purely a MainWindow wiring smoke test.
    window.device_manager.device = FakeDevice("SN1", "Tiny2")

    assert not window.gimbal_controller._timer.isActive()

    window.joystick.pressed.emit()
    assert window.gimbal_controller._timer.isActive()

    window.joystick.moved.emit(1.0, -1.0)
    assert window.gimbal_controller._pending == (1.0, -1.0)

    window.joystick.released.emit()
    assert not window.gimbal_controller._timer.isActive()


def test_error_signals_wired_to_status_bar(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.gimbal_controller.error_occurred.emit("boom")
    assert window.statusBar().currentMessage() == "boom"

    window.status_panel.error_occurred.emit("oops")
    assert window.statusBar().currentMessage() == "oops"
