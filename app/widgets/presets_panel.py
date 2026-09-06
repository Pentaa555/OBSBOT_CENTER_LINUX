from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout, QInputDialog, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)

import obsbot_bridge as bridge

PRESET_ID_ROLE = 1000


class PresetsPanel(QWidget):
    def __init__(self, device_manager, parent=None):
        super().__init__(parent)
        self._device_manager = device_manager

        self.list_widget = QListWidget()
        self.add_btn = QPushButton("Agregar")
        self.goto_btn = QPushButton("Ir")
        self.rename_btn = QPushButton("Renombrar")
        self.delete_btn = QPushButton("Borrar")
        self._buttons = (self.add_btn, self.goto_btn, self.rename_btn,
                          self.delete_btn)
        for btn in self._buttons:
            btn.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.list_widget)
        btn_row = QHBoxLayout()
        for btn in self._buttons:
            btn_row.addWidget(btn)
        layout.addLayout(btn_row)

        self.add_btn.clicked.connect(self._on_add)
        self.goto_btn.clicked.connect(self._on_goto)
        self.rename_btn.clicked.connect(self._on_rename)
        self.delete_btn.clicked.connect(self._on_delete)

        device_manager.device_connected.connect(self._on_connected)
        device_manager.device_disconnected.connect(self._on_disconnected)

    def _on_connected(self, sn: str, name: str) -> None:
        for btn in self._buttons:
            btn.setEnabled(True)
        self._refresh()

    def _on_disconnected(self, sn: str) -> None:
        for btn in self._buttons:
            btn.setEnabled(False)
        self.list_widget.clear()

    def _refresh(self) -> None:
        device = self._device_manager.device
        self.list_widget.clear()
        if device is None:
            return
        try:
            presets = device.list_presets()
        except bridge.ObsbotError:
            presets = []
        for preset in presets:
            item = QListWidgetItem(preset["name"] or f"Preset {preset['id']}")
            item.setData(PRESET_ID_ROLE, preset["id"])
            self.list_widget.addItem(item)

    def _on_add(self) -> None:
        device = self._device_manager.device
        if device is None:
            return
        name, ok = QInputDialog.getText(self, "Nuevo preset", "Nombre:")
        if not ok or not name:
            return
        try:
            angle = device.get_gimbal_angle()
            zoom = device.get_zoom()
            device.add_preset(name, angle["pitch"], angle["yaw"], 0.0, zoom)
        except bridge.ObsbotError:
            QMessageBox.warning(self, "Error", "No se pudo guardar el preset")
        self._refresh()

    def _on_goto(self) -> None:
        device = self._device_manager.device
        item = self.list_widget.currentItem()
        if device is None or item is None:
            return
        preset_id = item.data(PRESET_ID_ROLE)
        try:
            device.goto_preset(preset_id)
        except bridge.ObsbotError:
            QMessageBox.warning(self, "Error", "No se pudo mover al preset")

    def _on_rename(self, new_name: str | None = None) -> None:
        device = self._device_manager.device
        item = self.list_widget.currentItem()
        if device is None or item is None:
            return
        if new_name is None:
            new_name, ok = QInputDialog.getText(
                self, "Renombrar preset", "Nuevo nombre:")
            if not ok or not new_name:
                return
        preset_id = item.data(PRESET_ID_ROLE)
        try:
            device.rename_preset(preset_id, new_name)
        except bridge.ObsbotError:
            QMessageBox.warning(self, "Error", "No se pudo renombrar el preset")
            return
        item.setText(new_name)

    def _on_delete(self, confirm: bool | None = None) -> None:
        device = self._device_manager.device
        item = self.list_widget.currentItem()
        if device is None or item is None:
            return
        if confirm is None:
            confirm = QMessageBox.question(
                self, "Borrar preset", "¿Confirmar borrado?"
            ) == QMessageBox.Yes
        if not confirm:
            return
        preset_id = item.data(PRESET_ID_ROLE)
        try:
            device.delete_preset(preset_id)
        except bridge.ObsbotError:
            QMessageBox.warning(self, "Error", "No se pudo borrar el preset")
        self._refresh()
