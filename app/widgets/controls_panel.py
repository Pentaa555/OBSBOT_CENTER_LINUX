from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QGroupBox, QHBoxLayout, QLabel, QPushButton, QSlider,
    QVBoxLayout, QWidget,
)


class ControlsPanel(QWidget):
    """Controls whose values can be reused across application launches.

    ``compact=True`` is used by the main window: only the inversion options
    remain in this panel, while the mode button and speed slider are placed in
    the main controls area and speed popup respectively.
    """

    INVERT_PAN_KEY = "controls/invert_pan"
    INVERT_TILT_KEY = "controls/invert_tilt"
    SPEED_SCALE_KEY = "controls/speed_scale"
    PRECISION_MODE_KEY = "controls/precision_mode"

    def __init__(self, gimbal_controller, settings=None, parent=None, compact=False):
        super().__init__(parent)
        self._gimbal = gimbal_controller
        self._settings = settings

        if settings is not None:
            self._gimbal.set_invert_pan(
                settings.value(self.INVERT_PAN_KEY, False, type=bool))
            self._gimbal.set_invert_tilt(
                settings.value(self.INVERT_TILT_KEY, False, type=bool))
            self._gimbal.set_speed_scale(
                settings.value(self.SPEED_SCALE_KEY, 1.0, type=float))
            self._gimbal.set_precision_mode(
                settings.value(self.PRECISION_MODE_KEY, False, type=bool))

        inversion_group = QGroupBox("Ajustes de Control")
        inversion_layout = QVBoxLayout(inversion_group)

        inv_row = QHBoxLayout()
        self.inv_pan_cb = QCheckBox("Invertir Pan (horizontal)")
        self.inv_tilt_cb = QCheckBox("Invertir Tilt (vertical)")
        self.inv_pan_cb.setChecked(self._gimbal.invert_pan)
        self.inv_tilt_cb.setChecked(self._gimbal.invert_tilt)
        inv_row.addWidget(self.inv_pan_cb)
        inv_row.addWidget(self.inv_tilt_cb)
        inversion_layout.addLayout(inv_row)

        self.speed_label = QLabel(
            f"Velocidad: {int(self._gimbal.speed_scale * 100)}%")
        self.speed_slider = QSlider(Qt.Vertical)
        self.speed_slider.setRange(10, 100)
        self.speed_slider.setValue(int(self._gimbal.speed_scale * 100))
        self.speed_slider.setToolTip("Velocidad del movimiento")

        self.mode_btn = QPushButton()
        self.mode_btn.setCheckable(True)
        self.mode_btn.setChecked(self._gimbal.precision_mode)
        self._refresh_mode_button()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(inversion_group)
        if not compact:
            speed_row = QHBoxLayout()
            speed_row.addWidget(self.speed_label)
            speed_row.addWidget(self.speed_slider)
            speed_row.addWidget(self.mode_btn)
            layout.addLayout(speed_row)

        self.inv_pan_cb.toggled.connect(self._on_inv_pan_toggled)
        self.inv_tilt_cb.toggled.connect(self._on_inv_tilt_toggled)
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        self.mode_btn.clicked.connect(self._on_mode_toggled)

    def _save_value(self, key: str, value) -> None:
        if self._settings is not None:
            self._settings.setValue(key, value)
            self._settings.sync()

    def _on_inv_pan_toggled(self, checked: bool) -> None:
        self._gimbal.set_invert_pan(checked)
        self._save_value(self.INVERT_PAN_KEY, checked)

    def _on_inv_tilt_toggled(self, checked: bool) -> None:
        self._gimbal.set_invert_tilt(checked)
        self._save_value(self.INVERT_TILT_KEY, checked)

    def _on_speed_changed(self, value: int) -> None:
        self.speed_label.setText(f"Velocidad: {value}%")
        self._gimbal.set_speed_scale(value / 100.0)
        self._save_value(self.SPEED_SCALE_KEY, value / 100.0)

    def _on_mode_toggled(self, checked: bool) -> None:
        self._gimbal.set_precision_mode(checked)
        self._save_value(self.PRECISION_MODE_KEY, checked)
        self._refresh_mode_button()

    def _refresh_mode_button(self) -> None:
        if self.mode_btn.isChecked():
            self.mode_btn.setText("Modo: Preciso")
            self.mode_btn.setStyleSheet(
                "background-color: #1976D2; color: white; font-weight: bold;")
        else:
            self.mode_btn.setText("Modo: Grueso")
            self.mode_btn.setStyleSheet("")
