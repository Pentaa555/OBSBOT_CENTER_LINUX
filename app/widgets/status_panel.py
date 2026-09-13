from __future__ import annotations

import time
from threading import Condition, Thread

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QHBoxLayout, QLabel, QPushButton, QSlider,
    QVBoxLayout, QWidget,
)

import obsbot_bridge as bridge

DEFAULT_ZOOM_MIN = 1.0
DEFAULT_ZOOM_MAX = 2.0

# Minimum spacing between zoom commands sent to the camera. The Tiny2
# firmware processes zoom requests serially and occasionally blocks for
# ~300 ms; flooding it during a drag makes the lens lag and only catch up
# on release. Throttling keeps it responsive while dragging.
ZOOM_MIN_INTERVAL_S = 0.033  # ~30 Hz

# Largest change in normalized zoom applied per command. Capping the step
# turns a fast drag into a smooth glide instead of an abrupt jump, without
# raising the command rate. At 30 Hz a 0.08 step covers the full 1.0->2.0
# range in ~0.4 s of continuous travel.
ZOOM_MAX_STEP = 0.08


def zoom_ratio_to_slider_value(zoom_ratio: int) -> int:
    return max(0, min(100, int(zoom_ratio)))


def slider_value_to_absolute_zoom(
    value: int,
    min_zoom: float = DEFAULT_ZOOM_MIN,
    max_zoom: float = DEFAULT_ZOOM_MAX,
) -> float:
    return min_zoom + (value / 100.0) * (max_zoom - min_zoom)


def _normalise_zoom_bound(value, fallback: float) -> float:
    """Accept SDK ranges represented either as 1..2 or 100..200."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return fallback
    if value > 10.0:
        value /= 100.0
    return value


def _format_zoom(value: float) -> str:
    return f"{value:.1f}x"


class StatusPanel(QWidget):
    error_occurred = Signal(str)

    def __init__(self, device_manager, compact=False, parent=None):
        super().__init__(parent)
        self._device_manager = device_manager
        self._user_dragging_zoom = False
        self._zoom_condition = Condition()
        self._zoom_pending: tuple[object, float] | None = None
        self._zoom_thread: Thread | None = None
        self._zoom_shutdown = False
        self._requested_zoom_ratio: int | None = None
        self.zoom_min = DEFAULT_ZOOM_MIN
        self.zoom_max = DEFAULT_ZOOM_MAX

        self.connection_label = QLabel("Sin dispositivo conectado")

        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(0, 100)
        self.zoom_slider.setTracking(True)
        self.zoom_slider.setEnabled(False)
        self.zoom_value_input = QDoubleSpinBox()
        self.zoom_value_input.setDecimals(1)
        self.zoom_value_input.setSingleStep(0.1)
        self.zoom_value_input.setRange(self.zoom_min, self.zoom_max)
        self.zoom_value_input.setValue(self.zoom_min)
        self.zoom_value_input.setSuffix("x")
        self.zoom_value_input.setEnabled(False)
        self.zoom_value_input.setMinimumWidth(74)
        self.zoom_value_input.setAlignment(Qt.AlignRight)

        self.zoom_row = QWidget()
        zoom_layout = QHBoxLayout(self.zoom_row)
        zoom_layout.setContentsMargins(0, 0, 0, 0)
        zoom_layout.addWidget(self.zoom_slider, stretch=1)
        zoom_layout.addWidget(self.zoom_value_input)
        self.zoom_slider.setToolTip("Zoom de la cámara")

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
        if not compact:
            layout.addWidget(self.connection_label)
            layout.addWidget(self.zoom_row)
        layout.addWidget(self.ai_enabled_checkbox)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.mode_headroom_btn)
        mode_row.addWidget(self.mode_standard_btn)
        mode_row.addWidget(self.mode_motion_btn)
        layout.addLayout(mode_row)

        self.zoom_slider.sliderPressed.connect(self._on_zoom_pressed)
        self.zoom_slider.sliderReleased.connect(self._on_zoom_released)
        self.zoom_slider.valueChanged.connect(self._on_zoom_changed)
        self.zoom_value_input.valueChanged.connect(self._on_zoom_input_changed)
        self.ai_enabled_checkbox.toggled.connect(self._on_ai_toggled)
        for mode, btn in self._mode_buttons.items():
            btn.clicked.connect(lambda _checked=False, m=mode: self._set_mode(m))

        device_manager.device_connected.connect(self._on_connected)
        device_manager.device_disconnected.connect(self._on_disconnected)
        device_manager.status_changed.connect(self._on_status_changed)

    def _configure_zoom_range(self) -> None:
        device = self._device_manager.device
        self.zoom_min = DEFAULT_ZOOM_MIN
        self.zoom_max = DEFAULT_ZOOM_MAX
        if device is not None:
            get_range = getattr(device, "get_zoom_range", None)
            if get_range is not None:
                try:
                    zoom_range = get_range()
                    self.zoom_min = _normalise_zoom_bound(
                        zoom_range.get("min"), DEFAULT_ZOOM_MIN)
                    self.zoom_max = _normalise_zoom_bound(
                        zoom_range.get("max"), DEFAULT_ZOOM_MAX)
                except (bridge.ObsbotError, AttributeError, TypeError):
                    pass
        # Some Tiny2 firmware versions report a normalized 0..1 capability
        # range even though set_zoom uses the documented absolute 1..2 scale.
        if self.zoom_min < DEFAULT_ZOOM_MIN or self.zoom_max <= self.zoom_min:
            self.zoom_min = DEFAULT_ZOOM_MIN
            self.zoom_max = DEFAULT_ZOOM_MAX

        self._requested_zoom_ratio = None
        self.zoom_value_input.blockSignals(True)
        self.zoom_value_input.setRange(self.zoom_min, self.zoom_max)
        self.zoom_value_input.setValue(slider_value_to_absolute_zoom(
            self.zoom_slider.value(), self.zoom_min, self.zoom_max))
        self.zoom_value_input.setToolTip(
            f"Zoom actual; máximo {_format_zoom(self.zoom_max)}")
        self.zoom_value_input.blockSignals(False)

    def _on_connected(self, sn: str, name: str) -> None:
        self.connection_label.setText(f"Conectado: {name}")
        self._configure_zoom_range()
        self.zoom_slider.setEnabled(True)
        self.zoom_value_input.setEnabled(True)
        self.ai_enabled_checkbox.setEnabled(True)
        for btn in self._mode_buttons.values():
            btn.setEnabled(True)

    def _on_disconnected(self, sn: str) -> None:
        with self._zoom_condition:
            self._zoom_pending = None
        self._requested_zoom_ratio = None
        self.connection_label.setText("Sin dispositivo conectado")
        self.zoom_slider.setEnabled(False)
        self.zoom_value_input.setEnabled(False)
        self.zoom_value_input.blockSignals(True)
        self.zoom_value_input.setRange(DEFAULT_ZOOM_MIN, DEFAULT_ZOOM_MAX)
        self.zoom_value_input.setValue(DEFAULT_ZOOM_MIN)
        self.zoom_value_input.blockSignals(False)
        self.ai_enabled_checkbox.blockSignals(True)
        self.ai_enabled_checkbox.setChecked(False)
        self.ai_enabled_checkbox.blockSignals(False)
        self.ai_enabled_checkbox.setEnabled(False)
        for btn in self._mode_buttons.values():
            btn.setEnabled(False)
            btn.setChecked(False)

    def _on_status_changed(self, data: dict) -> None:
        if "zoom_ratio" in data:
            zoom_ratio = zoom_ratio_to_slider_value(data["zoom_ratio"])
            if self._requested_zoom_ratio is not None:
                if abs(zoom_ratio - self._requested_zoom_ratio) <= 1:
                    self._requested_zoom_ratio = None
                else:
                    # Ignore stale periodic status while the camera is still
                    # applying the user's latest zoom command.
                    zoom_ratio = None
            if zoom_ratio is not None and not self._user_dragging_zoom:
                self.zoom_slider.blockSignals(True)
                self.zoom_slider.setValue(zoom_ratio)
                self.zoom_slider.blockSignals(False)
                self.zoom_value_input.blockSignals(True)
                self.zoom_value_input.setValue(slider_value_to_absolute_zoom(
                    zoom_ratio, self.zoom_min, self.zoom_max))
                self.zoom_value_input.blockSignals(False)
        if "ai_mode" in data:
            self.ai_enabled_checkbox.blockSignals(True)
            self.ai_enabled_checkbox.setChecked(bool(data["ai_mode"]))
            self.ai_enabled_checkbox.blockSignals(False)

    def _on_zoom_pressed(self) -> None:
        self._user_dragging_zoom = True

    def _on_zoom_released(self) -> None:
        self._user_dragging_zoom = False

    def _set_slider_from_zoom(self, zoom: float) -> None:
        if self.zoom_max <= self.zoom_min:
            return
        ratio = round((zoom - self.zoom_min) /
                      (self.zoom_max - self.zoom_min) * 100)
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(max(0, min(100, ratio)))
        self.zoom_slider.blockSignals(False)

    def _zoom_worker_loop(self) -> None:
        last_sent = 0.0
        current = None  # last zoom value actually sent to the camera
        while True:
            with self._zoom_condition:
                while self._zoom_pending is None and not self._zoom_shutdown:
                    self._zoom_condition.wait()
                if self._zoom_shutdown:
                    return

                elapsed = time.monotonic() - last_sent
                if elapsed < ZOOM_MIN_INTERVAL_S:
                    self._zoom_condition.wait(ZOOM_MIN_INTERVAL_S - elapsed)
                    if self._zoom_shutdown:
                        return
                    if self._zoom_pending is None:
                        continue

                device, target = self._zoom_pending

                # Step toward the target instead of jumping straight to it,
                # so a fast drag becomes a smooth glide.
                if current is None:
                    step = target
                else:
                    delta = target - current
                    if abs(delta) <= ZOOM_MAX_STEP:
                        step = target
                    else:
                        step = current + (ZOOM_MAX_STEP if delta > 0
                                          else -ZOOM_MAX_STEP)

                if step == target:
                    # Reached the target; clear it so we sleep afterwards.
                    self._zoom_pending = None
                # else: keep _zoom_pending so the loop continues gliding.

            if self._device_manager.device is not device:
                current = None
                continue
            try:
                # The absolute API is the reliable path for the connected
                # Tiny2 firmware; the worker keeps it off the UI thread.
                device.set_zoom(step)
                current = step
                last_sent = time.monotonic()
            except bridge.ObsbotError as e:
                self.error_occurred.emit(str(e))

    def _send_zoom(self, zoom: float) -> None:
        device = self._device_manager.device
        if device is None:
            return
        with self._zoom_condition:
            if self._zoom_shutdown:
                return
            self._zoom_pending = (device, float(zoom))
            if self._zoom_thread is None or not self._zoom_thread.is_alive():
                self._zoom_thread = Thread(
                    target=self._zoom_worker_loop,
                    name="obsbot-zoom-worker",
                    daemon=True,
                )
                self._zoom_thread.start()
            self._zoom_condition.notify()

    def shutdown(self) -> None:
        with self._zoom_condition:
            self._zoom_shutdown = True
            self._zoom_pending = None
            self._zoom_condition.notify_all()
        if self._zoom_thread is not None:
            self._zoom_thread.join(timeout=1.0)

    def _on_zoom_changed(self, value: int) -> None:
        self._requested_zoom_ratio = max(0, min(100, int(value)))
        zoom = slider_value_to_absolute_zoom(
            value, self.zoom_min, self.zoom_max)
        self.zoom_value_input.blockSignals(True)
        self.zoom_value_input.setValue(zoom)
        self.zoom_value_input.blockSignals(False)
        self._send_zoom(zoom)

    def _on_zoom_input_changed(self, zoom: float) -> None:
        self._requested_zoom_ratio = max(0, min(100, round(
            (zoom - self.zoom_min) / (self.zoom_max - self.zoom_min) * 100)))
        self._set_slider_from_zoom(zoom)
        self._send_zoom(zoom)

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
