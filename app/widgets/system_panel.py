"""System-integration preferences: launch on login and tray behaviour.

Kept separate from ControlsPanel because these settings are about the OS
integration of the app, not the camera/gimbal, and they don't need a
connected device to work.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QGroupBox, QLabel, QVBoxLayout, QWidget

from app import autostart


class SystemPanel(QWidget):
    """Checkboxes for launch-on-login and minimise-to-tray."""

    MINIMIZE_TO_TRAY_KEY = "system/minimize_to_tray"

    def __init__(self, settings=None, parent=None):
        super().__init__(parent)
        self._settings = settings

        group = QGroupBox("Sistema")
        layout = QVBoxLayout(group)

        self.autostart_check = QCheckBox("Iniciar al encender el equipo")
        # Reflect the real on-disk state, not a stored preference, so the
        # checkbox never disagrees with what the desktop will actually do.
        self.autostart_check.setChecked(autostart.is_enabled())
        self.autostart_check.toggled.connect(self._on_autostart_toggled)
        layout.addWidget(self.autostart_check)

        self.tray_check = QCheckBox(
            "Al cerrar la ventana, mantener en segundo plano (bandeja)")
        initial_tray = True
        if settings is not None:
            initial_tray = settings.value(
                self.MINIMIZE_TO_TRAY_KEY, True, type=bool)
        self.tray_check.setChecked(initial_tray)
        self.tray_check.toggled.connect(self._on_tray_toggled)
        layout.addWidget(self.tray_check)

        hint = QLabel(
            "Con la bandeja activada, cerrar la ventana no cierra la app: "
            "sigue disponible desde el icono de la barra de tareas.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(hint)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(group)

    @property
    def minimize_to_tray(self) -> bool:
        return self.tray_check.isChecked()

    def _on_autostart_toggled(self, checked: bool) -> None:
        autostart.set_enabled(checked)

    def _on_tray_toggled(self, checked: bool) -> None:
        if self._settings is not None:
            self._settings.setValue(self.MINIMIZE_TO_TRAY_KEY, checked)
            # Flush to disk now so the choice survives even if this process
            # is killed rather than closed cleanly.
            self._settings.sync()
