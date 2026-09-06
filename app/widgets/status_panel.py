from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout,
    QWidget,
)

import obsbot_bridge as bridge


def zoom_ratio_to_slider_value(zoom_ratio: int) -> int:
    return max(0, min(100, int(zoom_ratio)))


def slider_value_to_absolute_zoom(value: int) -> float:
    return 1.0 + (value / 100.0)


class StatusPanel(QWidget):
    error_occurred = Signal(str)

    def __init__(self, device_manager, parent=None):
        super().__init__(parent)
        self._device_manager = device_manager
        self._user_dragging_zoom = False

        self.connection_label = QLabel("Sin dispositivo conectado")

        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(0, 100)
        self.zoom_slider.setEnabled(False)

        self.ai_enabled_checkbox = QCheckBox("AI activo")
        self.ai_enabled_checkbox.setEnabled(False)

        self.mode_headroom_btn = QPushButton("cabezal")
        self.mode_standard_btn = QPushButton("estandar")
        self.mode_motion_btn = QPushButton("movimiento")
        self._mode_buttons = {
            bridge.TrackMode.Headroom: self.mode_headroom_btn,
            bridge.TrackMode.Standard: self.mode_standard_btn,
            bridge.TrackMode.Motion: self.mode_motion_btn,
        }
        for btn in self._mode_buttons.values():
            btn.setCheckable(True)
            btn.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.connection_label)
        layout.addWidget(self.zoom_slider)
        layout.addWidget(self.ai_enabled_checkbox)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.mode_headroom_btn)
        mode_row.addWidget(self.mode_standard_btn)
        mode_row.addWidget(self.mode_motion_btn)
        layout.addLayout(mode_row)

        self.zoom_slider.sliderPressed.connect(self._on_zoom_pressed)
        self.zoom_slider.sliderReleased.connect(self._on_zoom_released)
        self.zoom_slider.valueChanged.connect(self._on_zoom_changed)
        self.ai_enabled_checkbox.toggled.connect(self._on_ai_toggled)
        for mode, btn in self._mode_buttons.items():
            btn.clicked.connect(lambda _checked=False, m=mode: self._set_mode(m))

        device_manager.device_connected.connect(self._on_connected)
        device_manager.device_disconnected.connect(self._on_disconnected)
        device_manager.status_changed.connect(self._on_status_changed)

    def _on_connected(self, sn: str, name: str) -> None:
        self.connection_label.setText(f"Conectado: {name}")
        self.zoom_slider.setEnabled(True)
        self.ai_enabled_checkbox.setEnabled(True)
        for btn in self._mode_buttons.values():
            btn.setEnabled(True)

    def _on_disconnected(self, sn: str) -> None:
        self.connection_label.setText("Sin dispositivo conectado")
        self.zoom_slider.setEnabled(False)
        self.ai_enabled_checkbox.blockSignals(True)
        self.ai_enabled_checkbox.setChecked(False)
        self.ai_enabled_checkbox.blockSignals(False)
        self.ai_enabled_checkbox.setEnabled(False)
        for btn in self._mode_buttons.values():
            btn.setEnabled(False)
            btn.setChecked(False)

    def _on_status_changed(self, data: dict) -> None:
        if not self._user_dragging_zoom and "zoom_ratio" in data:
            self.zoom_slider.blockSignals(True)
            self.zoom_slider.setValue(
                zoom_ratio_to_slider_value(data["zoom_ratio"]))
            self.zoom_slider.blockSignals(False)
        if "ai_mode" in data:
            self.ai_enabled_checkbox.blockSignals(True)
            self.ai_enabled_checkbox.setChecked(bool(data["ai_mode"]))
            self.ai_enabled_checkbox.blockSignals(False)

    def _on_zoom_pressed(self) -> None:
        self._user_dragging_zoom = True

    def _on_zoom_released(self) -> None:
        self._user_dragging_zoom = False

    def _on_zoom_changed(self, value: int) -> None:
        device = self._device_manager.device
        if device is None:
            return
        try:
            device.set_zoom(slider_value_to_absolute_zoom(value))
        except bridge.ObsbotError as e:
            self.error_occurred.emit(str(e))

    def _set_mode(self, mode) -> None:
        device = self._device_manager.device
        if device is None:
            return
        try:
            device.set_tracking_mode(mode)
            device.set_ai_enabled(True)
        except bridge.ObsbotError as e:
            self.error_occurred.emit(str(e))
        for m, btn in self._mode_buttons.items():
            btn.setChecked(m == mode)
        self.ai_enabled_checkbox.blockSignals(True)
        self.ai_enabled_checkbox.setChecked(True)
        self.ai_enabled_checkbox.blockSignals(False)

    def _on_ai_toggled(self, checked: bool) -> None:
        device = self._device_manager.device
        if device is None:
            return
        try:
            device.set_ai_enabled(checked)
        except bridge.ObsbotError as e:
            self.error_occurred.emit(str(e))
