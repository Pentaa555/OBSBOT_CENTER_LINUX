"""UI panel to run the app-owned virtual camera at a chosen resolution/fps.

This is the user-facing half of the v4l2loopback approach documented in
`app.virtual_camera`. It:
  - enumerates the real camera's modes (read-only, safe while OBS is open),
  - lets the user pick a resolution + fps + format,
  - creates the loopback device and starts a GStreamer pipeline feeding it,
so OBS can then select "OBSBOT Virtual" and receive that exact mode.

Important usage note surfaced in the UI: the real camera can only be opened
by one consumer at a time, so the pipeline can only start when OBS (or any
other app) is NOT currently holding /dev/video0. Starting will fail
otherwise; that failure is reported via error_occurred rather than crashing.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
    QWidget,
)

from app import autostart
from app.video_formats import (
    V4l2NotAvailable, VideoMode, enumerate_modes,
)
from app.virtual_camera import (
    DependencyMissing, FLIP_LABELS, FLIP_METHODS, VirtualCamera,
    VirtualCameraConfig,
)


class VideoFormatPanel(QWidget):
    """Pick a capture mode and expose it to OBS via a virtual camera."""

    error_occurred = Signal(str)

    ORIENTATION_KEY = "video/flip"
    WIDTH_KEY = "video/width"
    HEIGHT_KEY = "video/height"
    FPS_KEY = "video/fps"
    FOURCC_KEY = "video/fourcc"

    def __init__(
        self,
        real_device: str = "/dev/video0",
        virtual_camera: VirtualCamera | None = None,
        settings=None,
        parent=None,
    ):
        super().__init__(parent)
        self._real_device = real_device
        self._settings = settings
        self._camera = virtual_camera or VirtualCamera(
            VirtualCameraConfig(real_device=real_device)
        )
        self._modes: list[VideoMode] = []

        layout = QVBoxLayout(self)

        explanation = QLabel(
            "Selecciona resolución y FPS para la cámara virtual. En OBS elige "
            f"la fuente «{self._camera.config.card_label}» en lugar de la "
            "cámara real. Nota: cierra la cámara en OBS antes de iniciar, "
            "porque solo una app puede abrir el video a la vez."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        # Two chained columns: pick a resolution on the left, and the right
        # column shows only the fps actually available for that resolution.
        picker_row = QHBoxLayout()

        res_col = QVBoxLayout()
        res_col.addWidget(QLabel("Resolución"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.currentIndexChanged.connect(
            self._on_resolution_changed)
        res_col.addWidget(self.resolution_combo)
        picker_row.addLayout(res_col, 1)

        fps_col = QVBoxLayout()
        fps_col.addWidget(QLabel("FPS"))
        self.fps_combo = QComboBox()
        fps_col.addWidget(self.fps_combo)
        picker_row.addLayout(fps_col, 1)

        layout.addLayout(picker_row)

        # Orientation selector: corrects an inverted/mirrored image. Its
        # value is remembered across sessions and can be changed live while
        # streaming (the pipeline is restarted with the new flip).
        orient_row = QHBoxLayout()
        orient_row.addWidget(QLabel("Orientación"))
        self.orientation_combo = QComboBox()
        for key in FLIP_METHODS:
            self.orientation_combo.addItem(FLIP_LABELS[key], userData=key)
        if settings is not None:
            saved = settings.value(self.ORIENTATION_KEY, "none", type=str)
            i = self.orientation_combo.findData(saved)
            if i >= 0:
                self.orientation_combo.setCurrentIndex(i)
        self.orientation_combo.currentIndexChanged.connect(
            self._on_orientation_changed)
        orient_row.addWidget(self.orientation_combo, 1)
        layout.addLayout(orient_row)

        # One-time setup button: only shown until the virtual camera has been
        # configured to auto-load at boot, after which it's redundant.
        self.setup_button = QPushButton("Configurar cámara virtual (una vez)")
        self.setup_button.setToolTip(
            "Configura la cámara virtual para que funcione siempre sin pedir "
            "contraseña. Solo se hace una vez.")
        self.setup_button.clicked.connect(self._on_setup)
        layout.addWidget(self.setup_button)

        button_row = QHBoxLayout()
        self.refresh_button = QPushButton("Actualizar modos")
        self.refresh_button.clicked.connect(self.reload_modes)
        self.start_button = QPushButton("Iniciar cámara virtual")
        self.start_button.clicked.connect(self._on_start)
        self.stop_button = QPushButton("Detener")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._on_stop)
        button_row.addWidget(self.refresh_button)
        button_row.addWidget(self.start_button)
        button_row.addWidget(self.stop_button)
        layout.addLayout(button_row)

        # Start the virtual camera automatically at login (runs the headless
        # pipeline service, not the whole app). This is the stable path for
        # OBS: the pipeline comes up once at boot and isn't torn down each
        # time the control app opens/closes.
        self.autostart_vcam_check = QCheckBox(
            "Iniciar cámara virtual al encender el equipo")
        self.autostart_vcam_check.setChecked(autostart.is_vcam_enabled())
        self.autostart_vcam_check.toggled.connect(
            self._on_autostart_vcam_toggled)
        layout.addWidget(self.autostart_vcam_check)

        self._update_setup_visibility()

        self.status_label = QLabel("Detenida")
        layout.addWidget(self.status_label)

        self.reload_modes()
        self._sync_running_state()

    def _sync_running_state(self) -> None:
        """Reflect a pipeline that may already be running in another process.

        The virtual camera can be running from the login service or a
        previous session. Without this, the panel would always open showing
        "Detenida" even while video is streaming. We detect the external
        pipeline and set the label/buttons to match reality.
        """
        try:
            running = self._camera.is_running_anywhere()
        except Exception:
            running = False
        if running:
            self.status_label.setText("Transmitiendo (cámara virtual activa)")
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
        else:
            self.status_label.setText("Detenida")
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)

    def reload_modes(self) -> None:
        """Query the real camera and populate the resolution dropdown.

        Resolutions are listed largest-first. The fps column is filled in
        reactively by _on_resolution_changed. Raw YUYV modes are kept but
        sink to the bottom of each resolution's fps list because they top
        out at very low fps and aren't useful for the 60fps goal.
        """
        self.resolution_combo.blockSignals(True)
        self.resolution_combo.clear()
        self.fps_combo.clear()
        self._modes = []
        try:
            groups = enumerate_modes(self._real_device)
        except V4l2NotAvailable as e:
            self.resolution_combo.blockSignals(False)
            self.status_label.setText("v4l2-ctl no instalado")
            self.error_occurred.emit(str(e))
            return
        except Exception as e:  # device busy/unreadable - report, don't crash
            self.resolution_combo.blockSignals(False)
            self.status_label.setText("No se pudieron leer los modos")
            self.error_occurred.emit(str(e))
            return

        self._modes = [m for g in groups for m in g.modes]

        # Unique resolutions, largest area first.
        seen: dict[tuple[int, int], None] = {}
        for m in self._modes:
            seen.setdefault((m.width, m.height), None)
        resolutions = sorted(seen, key=lambda wh: -(wh[0] * wh[1]))
        for w, h in resolutions:
            best = max(
                (m.fps for m in self._modes if (m.width, m.height) == (w, h)),
                default=0.0,
            )
            # Surface the max fps right in the label so the useful ones stand out.
            self.resolution_combo.addItem(
                f"{w}x{h}  (hasta {best:g}fps)", userData=(w, h))

        self.resolution_combo.blockSignals(False)

        if not self._modes:
            self.status_label.setText("Sin modos disponibles")
            return

        # Trigger the initial fps population for the first resolution.
        self.resolution_combo.setCurrentIndex(0)
        self._on_resolution_changed(0)

    def _on_resolution_changed(self, _index: int) -> None:
        """Repopulate the fps column for the currently selected resolution."""
        self.fps_combo.clear()
        data = self.resolution_combo.currentData()
        if data is None:
            return
        width, height = data
        modes = [
            m for m in self._modes if (m.width, m.height) == (width, height)
        ]
        # Highest fps first; within equal fps, compressed formats before YUYV.
        modes.sort(key=lambda m: (-m.fps, m.fourcc == "YUYV"))
        for m in modes:
            self.fps_combo.addItem(f"{m.fps:g} fps  ({m.fourcc})", userData=m)

    def _selected_mode(self) -> VideoMode | None:
        return self.fps_combo.currentData()

    def _selected_flip(self) -> str:
        return self.orientation_combo.currentData() or "none"

    def _on_start(self) -> None:
        mode = self._selected_mode()
        if mode is None:
            self.error_occurred.emit("No hay un modo seleccionado.")
            return
        try:
            self._camera.check_dependencies()
            self._camera.ensure_loopback()
            self._camera.start(mode, flip=self._selected_flip())
        except (DependencyMissing, Exception) as e:
            self.error_occurred.emit(str(e))
            self.status_label.setText("Error al iniciar")
            return
        # Remember what worked so the login service can restart the exact
        # same mode without the GUI.
        self._save_mode(mode)
        self.status_label.setText(f"Transmitiendo {mode}")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

    def _save_mode(self, mode: VideoMode) -> None:
        if self._settings is None:
            return
        self._settings.setValue(self.WIDTH_KEY, mode.width)
        self._settings.setValue(self.HEIGHT_KEY, mode.height)
        self._settings.setValue(self.FPS_KEY, float(mode.fps))
        self._settings.setValue(self.FOURCC_KEY, mode.fourcc)
        self._settings.sync()

    def _on_autostart_vcam_toggled(self, checked: bool) -> None:
        # Persist the current selection first so the login service starts
        # the same mode the user just chose.
        mode = self._selected_mode()
        if mode is not None:
            self._save_mode(mode)
        if self._settings is not None:
            self._settings.setValue(self.ORIENTATION_KEY, self._selected_flip())
            self._settings.sync()
        try:
            autostart.set_vcam_enabled(checked)
        except Exception as e:
            self.error_occurred.emit(str(e))

    def _on_stop(self) -> None:
        self._camera.stop()
        self.status_label.setText("Detenida")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def _on_orientation_changed(self, _index: int) -> None:
        """Persist the flip choice and apply it live if already streaming."""
        flip = self._selected_flip()
        if self._settings is not None:
            self._settings.setValue(self.ORIENTATION_KEY, flip)
            self._settings.sync()
        # If the virtual camera is running, restart it so the new flip takes
        # effect immediately without the user re-clicking Start.
        if self._camera.is_running:
            mode = self._selected_mode()
            if mode is None:
                return
            try:
                self._camera.start(mode, flip=flip)
            except (DependencyMissing, Exception) as e:
                self.error_occurred.emit(str(e))
                self.status_label.setText("Error al aplicar orientación")
                self.start_button.setEnabled(True)
                self.stop_button.setEnabled(False)
                return
            self.status_label.setText(f"Transmitiendo {mode}")

    def _update_setup_visibility(self) -> None:
        """Hide the setup button once the virtual camera is configured."""
        try:
            configured = self._camera.is_configured()
        except Exception:
            configured = False
        self.setup_button.setVisible(not configured)

    def _on_setup(self) -> None:
        try:
            self._camera.check_dependencies()
            self._camera.setup_persistent()
        except (DependencyMissing, Exception) as e:
            self.error_occurred.emit(str(e))
            return
        self.status_label.setText(
            "Cámara virtual configurada. Ya puedes iniciarla sin contraseña.")
        self._update_setup_visibility()

    def shutdown(self) -> None:
        self._camera.stop()
