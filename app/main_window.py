from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu,
    QPushButton, QSystemTrayIcon, QTabWidget, QToolButton, QVBoxLayout,
    QWidget,
)

from app.device_manager import DeviceManager
from app.gimbal_controller import GimbalController
from app.widgets.controls_panel import ControlsPanel
from app.widgets.image_panel import ImagePanel
from app.widgets.joystick import JoystickWidget
from app.widgets.presets_panel import PresetsPanel
from app.widgets.status_panel import StatusPanel
from app.widgets.system_panel import SystemPanel
from app.widgets.video_format_panel import VideoFormatPanel


class CollapsibleSection(QWidget):
    """A titled content section that can be collapsed with its arrow."""

    def __init__(self, title: str, content: QWidget, parent=None):
        super().__init__(parent)
        self.toggle_button = QToolButton()
        self.toggle_button.setText(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(True)
        self.toggle_button.setAutoRaise(True)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.DownArrow)
        self.toggle_button.clicked.connect(self._toggle_content)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self.toggle_button)
        header.addStretch()

        self.content = content
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(header)
        layout.addWidget(content)

    def _toggle_content(self, expanded: bool) -> None:
        self.content.setVisible(expanded)
        self.toggle_button.setArrowType(
            Qt.DownArrow if expanded else Qt.RightArrow)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OBSBOT Control")

        self.device_manager = DeviceManager(self)
        self.gimbal_controller = GimbalController(self.device_manager, self)
        self.settings = QSettings("OBSBOT", "OBSBOT Control")

        self.joystick = JoystickWidget()
        self.controls_panel = ControlsPanel(
            self.gimbal_controller,
            settings=self.settings,
            compact=True,
        )
        self.status_panel = StatusPanel(self.device_manager, compact=True)
        self.presets_panel = PresetsPanel(self.device_manager)
        self.image_panel = ImagePanel(self.device_manager)
        self.video_format_panel = VideoFormatPanel()
        self.system_panel = SystemPanel(settings=self.settings)

        self.mode_button = self.controls_panel.mode_btn
        self.speed_button = QPushButton("‹")
        self.speed_button.setFixedWidth(36)
        self.speed_button.setToolTip("Mostrar la velocidad")
        self.speed_button.clicked.connect(self._toggle_speed_popup)

        self.speed_popup = QFrame()
        self.speed_popup.setFrameShape(QFrame.StyledPanel)
        self.speed_popup.setFixedSize(76, 220)
        speed_popup_layout = QVBoxLayout(self.speed_popup)
        speed_popup_layout.setContentsMargins(8, 8, 8, 8)
        speed_popup_layout.addWidget(
            self.controls_panel.speed_label, alignment=Qt.AlignCenter)
        speed_popup_layout.addWidget(
            self.controls_panel.speed_slider, alignment=Qt.AlignHCenter)
        self.controls_panel.speed_slider.setMinimumHeight(170)

        self.speed_container = QWidget()
        self.speed_container.setFixedSize(76, 220)
        speed_container_layout = QVBoxLayout(self.speed_container)
        speed_container_layout.setContentsMargins(0, 0, 0, 0)
        speed_container_layout.addWidget(self.speed_popup)

        self.joystick.pressed.connect(self.gimbal_controller.start)
        self.joystick.moved.connect(self.gimbal_controller.update)
        self.joystick.released.connect(self.gimbal_controller.stop)

        self.gimbal_controller.error_occurred.connect(self.statusBar().showMessage)
        self.status_panel.error_occurred.connect(self.statusBar().showMessage)
        self.image_panel.error_occurred.connect(self.statusBar().showMessage)
        self.video_format_panel.error_occurred.connect(self.statusBar().showMessage)
        self.device_manager.device_connected.connect(self._on_device_connected)
        self.device_manager.device_disconnected.connect(self._on_device_disconnected)

        # The infrequently changed/large sections are independently
        # collapsible, with AI tracking above the presets as requested.
        self.ai_section = CollapsibleSection(
            "Seguimiento con IA", self.status_panel)
        self.presets_section = CollapsibleSection(
            "Presets", self.presets_panel)

        gimbal_header = QHBoxLayout()
        gimbal_header.setContentsMargins(0, 0, 0, 0)
        gimbal_header.addWidget(QLabel("Gimbal"))
        gimbal_header.addStretch()
        gimbal_header.addWidget(self.mode_button)

        joystick_row = QHBoxLayout()
        joystick_row.setSpacing(6)
        joystick_row.addStretch(1)
        balance = QWidget()
        balance.setFixedWidth(76 + 36 + 6)
        joystick_row.addWidget(balance)
        joystick_row.addWidget(self.joystick)
        joystick_row.addWidget(self.speed_container, alignment=Qt.AlignVCenter)
        joystick_row.addWidget(self.speed_button, alignment=Qt.AlignVCenter)
        joystick_row.addStretch(1)

        gimbal_content = QVBoxLayout()
        gimbal_content.setContentsMargins(0, 0, 0, 0)
        gimbal_content.addLayout(joystick_row)
        gimbal_content.addWidget(self.status_panel.zoom_row)

        gimbal_section = QWidget()
        gimbal_section_layout = QVBoxLayout(gimbal_section)
        gimbal_section_layout.setContentsMargins(0, 0, 0, 0)
        gimbal_section_layout.addLayout(gimbal_header)
        gimbal_section_layout.addLayout(gimbal_content)
        self.gimbal_section = gimbal_section

        # --- Tab: Console (camera control) --------------------------------
        console_tab = QWidget()
        console_layout = QVBoxLayout(console_tab)
        console_layout.addWidget(self.ai_section)
        console_layout.addWidget(self.presets_section)
        console_layout.addWidget(gimbal_section)
        console_layout.addStretch(1)

        # --- Tab: Image (image/beauty adjustments) ------------------------
        image_tab = QWidget()
        image_tab_layout = QVBoxLayout(image_tab)
        image_tab_layout.addWidget(self.image_panel)
        image_tab_layout.addStretch(1)

        # --- Tab: More (control configuration) ----------------------------
        more_tab = QWidget()
        more_tab_layout = QVBoxLayout(more_tab)
        more_tab_layout.addWidget(self.controls_panel)
        more_tab_layout.addWidget(self.system_panel)
        more_tab_layout.addStretch(1)

        # --- Tab: Video (virtual camera resolution/fps) -------------------
        video_tab = QWidget()
        video_tab_layout = QVBoxLayout(video_tab)
        video_tab_layout.addWidget(self.video_format_panel)
        video_tab_layout.addStretch(1)

        self.tabs = QTabWidget()
        self.tabs.addTab(console_tab, "Console")
        self.tabs.addTab(image_tab, "Image")
        self.tabs.addTab(more_tab, "More")
        self.tabs.addTab(video_tab, "Video")

        central = QWidget()
        root = QVBoxLayout(central)
        self.no_device_label = QLabel("No hay dispositivo conectado")
        self.no_device_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self.no_device_label)
        root.addWidget(self.tabs)
        root.setStretch(1, 1)
        self.setCentralWidget(central)
        self._set_camera_controls_visible(False)

        # System tray: lets the app keep running in the background when the
        # window is closed (see closeEvent). Guarded because a tray isn't
        # always available (e.g. headless/CI or a desktop with no tray).
        self._force_quit = False
        self.tray_icon = None
        self._setup_tray_icon()

        # Must run last: DeviceManager's constructor only registers the SDK
        # callback, it does not scan for an already-connected camera (see
        # Task 8) — start() does that scan, and by now every widget above
        # has already connected to device_connected/device_disconnected/status_changed,
        # so none of them miss the initial event if a camera is already plugged in.
        self.device_manager.start()

    def _setup_tray_icon(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = self.windowIcon()
        if icon.isNull():
            app_icon = QApplication.windowIcon()
            icon = app_icon if not app_icon.isNull() else QIcon()
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip("OBSBOT Control")

        menu = QMenu()
        show_action = QAction("Mostrar", self)
        show_action.triggered.connect(self._show_from_tray)
        quit_action = QAction("Salir", self)
        quit_action.triggered.connect(self._quit_from_tray)
        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason) -> None:
        # A left click (Trigger) toggles the window back into view.
        if reason == QSystemTrayIcon.Trigger:
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_from_tray(self) -> None:
        self._force_quit = True
        self.close()

    def closeEvent(self, event) -> None:
        # If tray-minimising is enabled and a tray exists, closing the window
        # just hides it (the app keeps running and stays reachable from the
        # tray). A real quit goes through the tray's "Salir" action, which
        # sets _force_quit first.
        tray_enabled = self.system_panel.minimize_to_tray
        if not self._force_quit and tray_enabled and self.tray_icon is not None:
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "OBSBOT Control",
                "La app sigue en segundo plano. Ábrela desde la bandeja.",
                QSystemTrayIcon.Information,
                3000,
            )
            return
        # Real shutdown path.
        self.shutdown()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        event.accept()

    def _set_camera_controls_visible(self, visible: bool) -> None:
        self.no_device_label.setVisible(not visible)
        self.tabs.setVisible(visible)
        self.status_panel.zoom_row.setVisible(visible)
        self.mode_button.setVisible(visible)
        self.speed_button.setVisible(visible)
        self.joystick.setEnabled(visible)
        if not visible:
            self.speed_popup.hide()

    def _on_device_connected(self, sn: str, name: str) -> None:
        self._set_camera_controls_visible(True)

    def _on_device_disconnected(self, sn: str) -> None:
        self._set_camera_controls_visible(False)

    def _toggle_speed_popup(self) -> None:
        self.speed_popup.setVisible(not self.speed_popup.isVisible())

    def shutdown(self) -> None:
        # Idempotent: both closeEvent (real-quit path) and the app's
        # aboutToQuit signal call this, so guard against running twice.
        if getattr(self, "_shutdown_done", False):
            return
        self._shutdown_done = True
        # Stop first: quitting mid-drag would otherwise leave the physical
        # gimbal panning with AI tracking disabled after the process exits.
        # GimbalController.stop() is a no-op with no device/drag active.
        self.gimbal_controller.stop()
        self.status_panel.shutdown()
        self.video_format_panel.shutdown()
        self.device_manager.shutdown()
