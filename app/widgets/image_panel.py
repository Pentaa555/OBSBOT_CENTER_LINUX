from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
    QVBoxLayout, QWidget,
)

import obsbot_bridge as bridge

# UVC image adjustments (brightness/contrast/saturation/sharpness) return
# in well under 1 ms on the Tiny2, so unlike optical zoom they don't need a
# worker thread. We still coalesce rapid drag events with a short timer so
# the camera isn't flooded with dozens of near-identical writes.
SEND_DELAY_MS = 40

# (attribute suffix, human label) for each adjustable parameter. The bridge
# exposes set_<name>/get_<name>/get_<name>_range for each.
PARAMS = (
    ("brightness", "Brillo"),
    ("contrast", "Contraste"),
    ("saturation", "Saturación"),
    ("sharpness", "Nitidez"),
)


class ImagePanel(QWidget):
    """Sliders for the camera's image adjustments."""

    error_occurred = Signal(str)

    def __init__(self, device_manager, parent=None):
        super().__init__(parent)
        self._device_manager = device_manager
        self._sliders: dict[str, QSlider] = {}
        self._value_labels: dict[str, QLabel] = {}
        self._defaults: dict[str, int] = {}
        self._pending: dict[str, int] = {}

        # A single coalescing timer flushes all pending writes together.
        self._flush_timer = QTimer(self)
        self._flush_timer.setSingleShot(True)
        self._flush_timer.setInterval(SEND_DELAY_MS)
        self._flush_timer.timeout.connect(self._flush_pending)

        # White balance temperature has its own coalescing timer.
        self._wb_timer = QTimer(self)
        self._wb_timer.setSingleShot(True)
        self._wb_timer.setInterval(SEND_DELAY_MS)
        self._wb_timer.timeout.connect(self._flush_white_balance)
        self._wb_pending: int | None = None
        self._wb_default = 5000

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        grid_host = QWidget()
        layout = QGridLayout(grid_host)
        layout.setContentsMargins(0, 0, 0, 0)

        for row, (name, label_text) in enumerate(PARAMS):
            label = QLabel(label_text)
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 100)
            slider.setEnabled(False)
            value_label = QLabel("-")
            value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value_label.setMinimumWidth(32)

            slider.valueChanged.connect(
                lambda v, n=name: self._on_slider_changed(n, v))

            layout.addWidget(label, row, 0)
            layout.addWidget(slider, row, 1)
            layout.addWidget(value_label, row, 2)

            self._sliders[name] = slider
            self._value_labels[name] = value_label

        root.addWidget(grid_host)

        # --- White balance ------------------------------------------------
        wb_host = QWidget()
        wb_layout = QVBoxLayout(wb_host)
        wb_layout.setContentsMargins(0, 0, 0, 0)
        wb_layout.setSpacing(6)

        self.wb_auto_checkbox = QCheckBox("Balance de blancos automático")
        self.wb_auto_checkbox.setEnabled(False)
        self.wb_auto_checkbox.toggled.connect(self._on_wb_auto_toggled)
        wb_layout.addWidget(self.wb_auto_checkbox)

        wb_row = QHBoxLayout()
        self.wb_temp_label = QLabel("Temperatura")
        self.wb_temp_slider = QSlider(Qt.Horizontal)
        self.wb_temp_slider.setRange(2800, 6500)
        self.wb_temp_slider.setEnabled(False)
        self.wb_temp_value = QLabel("-")
        self.wb_temp_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.wb_temp_value.setMinimumWidth(52)
        self.wb_temp_slider.valueChanged.connect(self._on_wb_temp_changed)
        wb_row.addWidget(self.wb_temp_label)
        wb_row.addWidget(self.wb_temp_slider, stretch=1)
        wb_row.addWidget(self.wb_temp_value)
        wb_layout.addLayout(wb_row)

        root.addWidget(wb_host)

        self.reset_button = QPushButton("Restablecer")
        self.reset_button.setEnabled(False)
        self.reset_button.clicked.connect(self._on_reset)
        root.addWidget(self.reset_button)

        device_manager.device_connected.connect(self._on_connected)
        device_manager.device_disconnected.connect(self._on_disconnected)

    def _set_enabled(self, enabled: bool) -> None:
        for slider in self._sliders.values():
            slider.setEnabled(enabled)
        self.reset_button.setEnabled(enabled)
        self.wb_auto_checkbox.setEnabled(enabled)
        # The temperature slider follows the auto checkbox when enabled.
        self._update_wb_temp_enabled()

    def _update_wb_temp_enabled(self) -> None:
        manual = (self.wb_auto_checkbox.isEnabled()
                  and not self.wb_auto_checkbox.isChecked())
        self.wb_temp_slider.setEnabled(manual)

    def _on_connected(self, sn: str, name: str) -> None:
        device = self._device_manager.device
        if device is None:
            return
        for param, _label in PARAMS:
            slider = self._sliders[param]
            try:
                rng = getattr(device, f"get_{param}_range")()
                current = getattr(device, f"get_{param}")()
            except (bridge.ObsbotError, AttributeError):
                continue
            self._defaults[param] = int(rng.get("default", rng.get("min", 0)))
            slider.blockSignals(True)
            slider.setRange(int(rng.get("min", 0)), int(rng.get("max", 100)))
            step = int(rng.get("step", 1)) or 1
            slider.setSingleStep(step)
            slider.setValue(int(current))
            slider.blockSignals(False)
            self._value_labels[param].setText(str(int(current)))

        # White balance: configure range, then reflect current state.
        try:
            wb_range = device.get_white_balance_range()
            wb_state = device.get_white_balance()
        except (bridge.ObsbotError, AttributeError):
            wb_range = None
            wb_state = None
        if wb_range is not None:
            self._wb_default = int(
                wb_range.get("default", wb_range.get("min", 5000)))
            self.wb_temp_slider.blockSignals(True)
            self.wb_temp_slider.setRange(
                int(wb_range.get("min", 2800)),
                int(wb_range.get("max", 6500)))
            step = int(wb_range.get("step", 100)) or 100
            self.wb_temp_slider.setSingleStep(step)
            self.wb_temp_slider.blockSignals(False)
        if wb_state is not None:
            is_auto = bool(wb_state.get("auto", True))
            temp = int(wb_state.get("temp", self._wb_default) or self._wb_default)
            self.wb_auto_checkbox.blockSignals(True)
            self.wb_auto_checkbox.setChecked(is_auto)
            self.wb_auto_checkbox.blockSignals(False)
            self.wb_temp_slider.blockSignals(True)
            self.wb_temp_slider.setValue(temp)
            self.wb_temp_slider.blockSignals(False)
            self.wb_temp_value.setText(f"{temp} K")

        self._set_enabled(True)

    def _on_disconnected(self, sn: str) -> None:
        self._flush_timer.stop()
        self._wb_timer.stop()
        self._pending.clear()
        self._wb_pending = None
        self._set_enabled(False)
        for name in self._sliders:
            self._value_labels[name].setText("-")
        self.wb_temp_value.setText("-")

    def _on_slider_changed(self, name: str, value: int) -> None:
        self._value_labels[name].setText(str(value))
        self._pending[name] = value
        if not self._flush_timer.isActive():
            self._flush_timer.start()

    def _flush_pending(self) -> None:
        device = self._device_manager.device
        if device is None:
            self._pending.clear()
            return
        pending, self._pending = self._pending, {}
        for name, value in pending.items():
            try:
                getattr(device, f"set_{name}")(value)
            except bridge.ObsbotError as e:
                self.error_occurred.emit(str(e))

    def _on_wb_auto_toggled(self, checked: bool) -> None:
        self._update_wb_temp_enabled()
        device = self._device_manager.device
        if device is None:
            return
        try:
            if checked:
                self._wb_timer.stop()
                self._wb_pending = None
                device.set_white_balance_auto()
            else:
                # Switching to manual: apply the current slider temperature.
                device.set_white_balance_manual(int(self.wb_temp_slider.value()))
        except bridge.ObsbotError as e:
            self.error_occurred.emit(str(e))

    def _on_wb_temp_changed(self, value: int) -> None:
        self.wb_temp_value.setText(f"{value} K")
        # Only meaningful in manual mode; coalesce like the image sliders.
        if self.wb_auto_checkbox.isChecked():
            return
        self._wb_pending = value
        if not self._wb_timer.isActive():
            self._wb_timer.start()

    def _flush_white_balance(self) -> None:
        device = self._device_manager.device
        if device is None or self._wb_pending is None:
            self._wb_pending = None
            return
        temp, self._wb_pending = self._wb_pending, None
        try:
            device.set_white_balance_manual(int(temp))
        except bridge.ObsbotError as e:
            self.error_occurred.emit(str(e))

    def _on_reset(self) -> None:
        for name, slider in self._sliders.items():
            if name in self._defaults:
                slider.setValue(self._defaults[name])
        # Reset white balance back to automatic.
        if self.wb_auto_checkbox.isEnabled():
            self.wb_auto_checkbox.setChecked(True)
