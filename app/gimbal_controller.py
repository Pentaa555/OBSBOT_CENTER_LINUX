from __future__ import annotations

from PySide6.QtCore import QObject, QTimer

import obsbot_bridge as bridge

MAX_PITCH_SPEED = 40.0
MAX_PAN_SPEED = 60.0
TICK_INTERVAL_MS = 50  # 20 Hz


class GimbalController(QObject):
    def __init__(self, device_manager, parent=None):
        super().__init__(parent)
        self._device_manager = device_manager
        self._pending = (0.0, 0.0)
        self._last_sent = None
        self._ai_was_enabled = False
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_INTERVAL_MS)
        self._timer.timeout.connect(self._on_tick)

    def start(self) -> None:
        device = self._device_manager.device
        if device is None:
            return
        self._ai_was_enabled = self._device_manager.last_status.get(
            "ai_mode", 0) != 0
        self._pending = (0.0, 0.0)
        self._last_sent = None
        try:
            device.set_ai_enabled(False)
        except bridge.ObsbotError:
            pass
        self._timer.start()

    def update(self, x: float, y: float) -> None:
        self._pending = (x, y)

    def stop(self) -> None:
        self._timer.stop()
        device = self._device_manager.device
        if device is None:
            return
        try:
            device.stop_gimbal()
        except bridge.ObsbotError:
            pass
        if self._ai_was_enabled:
            try:
                device.set_ai_enabled(True)
            except bridge.ObsbotError:
                pass

    def _on_tick(self) -> None:
        device = self._device_manager.device
        if device is None:
            self._timer.stop()
            return
        if self._pending == self._last_sent:
            return
        x, y = self._pending
        pitch = -y * MAX_PITCH_SPEED
        pan = x * MAX_PAN_SPEED
        try:
            device.set_gimbal_speed(pitch, pan)
        except bridge.ObsbotError:
            pass
        self._last_sent = self._pending
