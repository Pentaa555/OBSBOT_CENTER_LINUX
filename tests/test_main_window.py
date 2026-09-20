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


def test_shutdown_stops_gimbal_before_closing_bridge(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.device_manager.device = FakeDevice("SN1", "Tiny2")
    window.joystick.pressed.emit()
    assert window.gimbal_controller._timer.isActive()

    window.shutdown()

    assert not window.gimbal_controller._timer.isActive()
    assert ("stop_gimbal",) in window.device_manager.device.calls


def test_error_signals_wired_to_status_bar(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.gimbal_controller.error_occurred.emit("boom")
    assert window.statusBar().currentMessage() == "boom"

    window.status_panel.error_occurred.emit("oops")
    assert window.statusBar().currentMessage() == "oops"

    window.video_format_panel.error_occurred.emit("v4l2 fail")
    assert window.statusBar().currentMessage() == "v4l2 fail"


def test_close_hides_to_tray_when_enabled(qtbot):
    from PySide6.QtGui import QCloseEvent

    window = MainWindow()
    qtbot.addWidget(window)
    # This behaviour only applies when a system tray is actually available.
    if window.tray_icon is None:
        import pytest
        pytest.skip("no system tray in this environment")

    window.system_panel.tray_check.setChecked(True)
    window.show()

    event = QCloseEvent()
    window.closeEvent(event)

    # Window hidden, app NOT shut down, event was swallowed.
    assert window.isVisible() is False
    assert event.isAccepted() is False
    assert getattr(window, "_shutdown_done", False) is False


def test_quit_from_tray_really_shuts_down(qtbot):
    from PySide6.QtGui import QCloseEvent

    window = MainWindow()
    qtbot.addWidget(window)
    if window.tray_icon is None:
        import pytest
        pytest.skip("no system tray in this environment")

    window.system_panel.tray_check.setChecked(True)
    window._force_quit = True
    event = QCloseEvent()
    window.closeEvent(event)

    assert event.isAccepted() is True
    assert window._shutdown_done is True


def test_close_shuts_down_when_tray_disabled(qtbot):
    from PySide6.QtGui import QCloseEvent

    window = MainWindow()
    qtbot.addWidget(window)
    window.system_panel.tray_check.setChecked(False)

    event = QCloseEvent()
    window.closeEvent(event)

    assert event.isAccepted() is True
    assert window._shutdown_done is True


def test_shutdown_is_idempotent(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.shutdown()
    # Second call must not raise (both closeEvent and aboutToQuit call it).
    window.shutdown()
    assert window._shutdown_done is True
