from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

import obsbot_bridge as bridge

MAX_PITCH_SPEED = 40.0
MAX_PAN_SPEED = 60.0
TICK_INTERVAL_MS = 50  # 20 Hz


class GimbalController(QObject):
    error_occurred = Signal(str)

    def __init__(self, device_manager, parent=None):
        super().__init__(parent)
        self._device_manager = device_manager
        self._pending = (0.0, 0.0)
        self._last_sent = None
        self._ai_was_enabled = False
        self.invert_pan: bool = False
        self.invert_tilt: bool = False
        self.speed_scale: float = 1.0
        self.precision_mode: bool = False
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_INTERVAL_MS)
        self._timer.timeout.connect(self._on_tick)

    def set_invert_pan(self, invert: bool) -> None:
        self.invert_pan = bool(invert)

    def set_invert_tilt(self, invert: bool) -> None:
        self.invert_tilt = bool(invert)

    def set_speed_scale(self, scale: float) -> None:
        self.speed_scale = max(0.1, min(1.0, float(scale)))

    def set_precision_mode(self, enabled: bool) -> None:
        self.precision_mode = bool(enabled)

    def start(self) -> None:
        device = self._device_manager.device
        if device is None:
            return
        last_status = self._device_manager.last_status
        self._ai_was_enabled = bool(last_status.get("ai_mode", 0) or last_status.get("ai_target", 0))
        self._pending = (0.0, 0.0)
        self._last_sent = None
        try:
            device.set_ai_enabled(False)
        except bridge.ObsbotError as e:
            self.error_occurred.emit(str(e))
        self._timer.start()

    def update(self, x: float, y: float) -> None:
        self._pending = (x, y)

    def stop(self) -> None:
        self._timer.stop()
        self._pending = (0.0, 0.0)
        self._last_sent = None
        device = self._device_manager.device
        if device is None:
            return
        try:
            device.stop_gimbal()
        except bridge.ObsbotError as e:
            self.error_occurred.emit(str(e))
        if self._ai_was_enabled:
            try:
                device.set_ai_enabled(True)
            except bridge.ObsbotError as e:
                self.error_occurred.emit(str(e))

    def _on_tick(self) -> None:
        device = self._device_manager.device
        if device is None:
            self._timer.stop()
            return
        if self._pending == self._last_sent:
            return
        x, y = self._pending
        sign_y = 1.0 if self.invert_tilt else -1.0
        sign_x = -1.0 if self.invert_pan else 1.0
        mode_factor = 0.25 if self.precision_mode else 1.0
        pitch = sign_y * y * MAX_PITCH_SPEED * self.speed_scale * mode_factor
        pan = sign_x * x * MAX_PAN_SPEED * self.speed_scale * mode_factor
        try:
            device.set_gimbal_speed(pitch, pan)
        except bridge.ObsbotError as e:
            self.error_occurred.emit(str(e))
        self._last_sent = self._pending
