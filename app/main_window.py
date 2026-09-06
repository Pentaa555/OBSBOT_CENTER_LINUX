from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QVBoxLayout, QWidget

from app.device_manager import DeviceManager
from app.gimbal_controller import GimbalController
from app.widgets.joystick import JoystickWidget
from app.widgets.presets_panel import PresetsPanel
from app.widgets.status_panel import StatusPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OBSBOT Tiny2 Control")

        self.device_manager = DeviceManager(self)
        self.gimbal_controller = GimbalController(self.device_manager, self)

        self.joystick = JoystickWidget()
        self.status_panel = StatusPanel(self.device_manager)
        self.presets_panel = PresetsPanel(self.device_manager)

        self.joystick.pressed.connect(self.gimbal_controller.start)
        self.joystick.moved.connect(self.gimbal_controller.update)
        self.joystick.released.connect(self.gimbal_controller.stop)

        self.gimbal_controller.error_occurred.connect(self.statusBar().showMessage)
        self.status_panel.error_occurred.connect(self.statusBar().showMessage)

        central = QWidget()
        root = QHBoxLayout(central)
        left = QVBoxLayout()
        left.addWidget(self.joystick)
        left.addWidget(self.status_panel)
        root.addLayout(left)
        root.addWidget(self.presets_panel)
        self.setCentralWidget(central)

        # Must run last: DeviceManager's constructor only registers the SDK
        # callback, it does not scan for an already-connected camera (see
        # Task 8) — start() does that scan, and by now every widget above
        # has already connected to device_connected/status_changed, so none
        # of them miss the initial event if a camera is already plugged in.
        self.device_manager.start()

    def shutdown(self) -> None:
        self.device_manager.shutdown()
