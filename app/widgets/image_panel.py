from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QGridLayout, QLabel, QPushButton, QSlider, QWidget,
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

        layout = QGridLayout(self)
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

        self.reset_button = QPushButton("Restablecer")
        self.reset_button.setEnabled(False)
        self.reset_button.clicked.connect(self._on_reset)
        layout.addWidget(self.reset_button, len(PARAMS), 0, 1, 3)

        device_manager.device_connected.connect(self._on_connected)
        device_manager.device_disconnected.connect(self._on_disconnected)

    def _set_enabled(self, enabled: bool) -> None:
        for slider in self._sliders.values():
            slider.setEnabled(enabled)
        self.reset_button.setEnabled(enabled)

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
        self._set_enabled(True)

    def _on_disconnected(self, sn: str) -> None:
        self._flush_timer.stop()
        self._pending.clear()
        self._set_enabled(False)
        for name in self._sliders:
            self._value_labels[name].setText("-")

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

    def _on_reset(self) -> None:
        for name, slider in self._sliders.items():
            if name in self._defaults:
                slider.setValue(self._defaults[name])
