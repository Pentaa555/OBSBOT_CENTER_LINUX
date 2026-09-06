from __future__ import annotations

from PySide6.QtCore import QObject, Signal

import obsbot_bridge as bridge


class DeviceManager(QObject):
    device_connected = Signal(str, str)
    device_disconnected = Signal(str)
    status_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.device = None
        self.last_status: dict = {}
        self._sn: str | None = None
        bridge.set_device_changed_callback(self._on_device_changed)

    def start(self) -> None:
        """Pick up a camera that was already plugged in before the app
        launched. Call this once, after every consumer (widgets) has
        connected to device_connected/device_disconnected/status_changed —
        otherwise an already-connected device's signal fires before anyone
        is listening."""
        for info in bridge.list_devices():
            self._on_device_changed(info["sn"], True)

    def _on_device_changed(self, sn: str, connected: bool) -> None:
        if connected:
            if self.device is not None:
                return
            device = bridge.get_device_by_sn(sn)
            if device is None:
                return
            self.device = device
            self._sn = sn
            device.set_status_callback(self._on_status)
            self.device_connected.emit(sn, device.name)
        else:
            if sn != self._sn:
                return
            self.device = None
            self._sn = None
            self.device_disconnected.emit(sn)

    def _on_status(self, data: dict) -> None:
        self.last_status = data
        self.status_changed.emit(data)

    def shutdown(self) -> None:
        bridge.close()
