from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QInputDialog, QLabel, QListWidget,
    QListWidgetItem, QMenu, QMessageBox, QPushButton, QToolButton,
    QVBoxLayout, QWidget,
)

import obsbot_bridge as bridge

PRESET_ID_ROLE = 1000


class PresetsPanel(QWidget):
    def __init__(self, device_manager, parent=None):
        super().__init__(parent)
        self._device_manager = device_manager
        self.preset_buttons: dict[int, QPushButton] = {}
        self.preset_action_buttons: dict[int, QToolButton] = {}
        self.preset_menus: dict[int, QMenu] = {}

        self.title_label = QLabel("Posiciones Guardadas (Presets)")
        # The hidden list remains the selection model used by the existing
        # actions and keeps the widget API stable for integrations/tests.
        self.list_widget = QListWidget()
        self.list_widget.hide()
        self.preset_grid = QGridLayout()
        self.preset_grid.setSpacing(8)

        self.add_btn = QPushButton("Agregar")
        self.update_btn = QPushButton("Actualizar")
        self.goto_btn = QPushButton("Ir")
        self.rename_btn = QPushButton("Renombrar")
        self.delete_btn = QPushButton("Borrar")

        self._all_buttons = (
            self.add_btn, self.update_btn, self.goto_btn,
            self.rename_btn, self.delete_btn,
        )
        self._selection_buttons = (
            self.update_btn, self.goto_btn, self.rename_btn, self.delete_btn,
        )

        for btn in self._all_buttons:
            btn.setEnabled(False)
        # Per-preset menus replace these global action buttons visually. They
        # remain connected for compatibility with callers and existing tests.
        self.add_btn.hide()
        for btn in self._selection_buttons:
            btn.hide()

        layout = QVBoxLayout(self)
        layout.addWidget(self.title_label)
        layout.addLayout(self.preset_grid)
        layout.addStretch()

        self.add_btn.clicked.connect(self._on_add)
        self.update_btn.clicked.connect(self._on_update)
        self.goto_btn.clicked.connect(self._on_goto)
        self.rename_btn.clicked.connect(self._on_rename)
        self.delete_btn.clicked.connect(self._on_delete)

        self.list_widget.itemSelectionChanged.connect(self._update_button_states)
        self.list_widget.itemDoubleClicked.connect(lambda: self._on_goto())

        device_manager.device_connected.connect(self._on_connected)
        device_manager.device_disconnected.connect(self._on_disconnected)

    def _clear_preset_buttons(self) -> None:
        self.preset_buttons.clear()
        self.preset_action_buttons.clear()
        self.preset_menus.clear()
        while self.preset_grid.count():
            item = self.preset_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _selected_preset_id(self) -> int | None:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        return int(item.data(PRESET_ID_ROLE))

    def _update_button_states(self) -> None:
        has_device = self._device_manager.device is not None
        self.add_btn.setEnabled(has_device)
        has_item = self.list_widget.currentItem() is not None and has_device
        for btn in self._selection_buttons:
            btn.setEnabled(has_item)

        selected_id = self._selected_preset_id()
        for preset_id, button in self.preset_buttons.items():
            button.setEnabled(has_device)
            button.blockSignals(True)
            button.setChecked(has_device and preset_id == selected_id)
            button.blockSignals(False)
        for button in self.preset_action_buttons.values():
            button.setEnabled(has_device)

    def _on_connected(self, sn: str, name: str) -> None:
        self.add_btn.setEnabled(True)
        self._refresh()

    def _on_disconnected(self, sn: str) -> None:
        for btn in self._all_buttons:
            btn.setEnabled(False)
        self.list_widget.clear()
        self._clear_preset_buttons()
        self.title_label.setText("Posiciones Guardadas (Presets)")

    def _refresh(self) -> None:
        device = self._device_manager.device
        self.list_widget.clear()
        self._clear_preset_buttons()
        if device is None:
            self._update_button_states()
            return
        try:
            presets = device.list_presets()
        except bridge.ObsbotError:
            QMessageBox.warning(self, "Error", "No se pudieron cargar los presets")
            presets = []

        is_tiny1 = getattr(device, "product_type", None) in (
            bridge.ProductType.Tiny,
            bridge.ProductType.Tiny4k,
        )
        max_slots = 3 if is_tiny1 else 16
        self.title_label.setText(f"Presets ({len(presets)}/{max_slots})")

        for index, preset in enumerate(presets):
            preset_id = preset["id"]
            name = preset["name"] or f"Preset {preset_id}"
            item = QListWidgetItem(name)
            item.setData(PRESET_ID_ROLE, preset_id)
            self.list_widget.addItem(item)

            card = QWidget()
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(0, 0, 0, 0)
            card_layout.setSpacing(2)

            button = QPushButton(name)
            button.setCheckable(True)
            button.setMinimumHeight(42)
            button.setToolTip("Ir a este preset")
            button.clicked.connect(
                lambda _checked=False, selected_id=preset_id:
                self._on_preset_button_clicked(selected_id))
            card_layout.addWidget(button)
            self.preset_buttons[preset_id] = button

            action_button = QToolButton()
            action_button.setArrowType(Qt.RightArrow)
            action_button.setToolTip("Acciones del preset")
            action_button.setAutoRaise(True)
            menu = QMenu(action_button)
            menu.addAction("Actualizar").triggered.connect(
                lambda _checked=False, selected_id=preset_id:
                self._run_preset_action(selected_id, self._on_update))
            menu.addAction("Renombrar").triggered.connect(
                lambda _checked=False, selected_id=preset_id:
                self._run_preset_action(selected_id, self._on_rename))
            menu.addSeparator()
            menu.addAction("Borrar").triggered.connect(
                lambda _checked=False, selected_id=preset_id:
                self._run_preset_action(selected_id, self._on_delete))
            action_button.setMenu(menu)
            action_button.setPopupMode(QToolButton.InstantPopup)
            card_layout.addWidget(action_button)
            self.preset_action_buttons[preset_id] = action_button
            self.preset_menus[preset_id] = menu

            row, column = divmod(index, 4)
            self.preset_grid.addWidget(card, row, column)
        self._update_button_states()

    def _select_preset(self, preset_id: int) -> bool:
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            if item.data(PRESET_ID_ROLE) == preset_id:
                self.list_widget.setCurrentRow(row)
                return True
        return False

    def _run_preset_action(self, preset_id: int, action) -> None:
        if self._select_preset(preset_id):
            action()

    def _on_preset_button_clicked(self, preset_id: int) -> None:
        if self._select_preset(preset_id):
            self._on_goto()

    def _on_add(self) -> None:
        device = self._device_manager.device
        if device is None:
            return
        try:
            presets = device.list_presets()
        except bridge.ObsbotError:
            presets = []

        is_tiny1 = getattr(device, "product_type", None) in (
            bridge.ProductType.Tiny,
            bridge.ProductType.Tiny4k,
        )
        max_slots = 3 if is_tiny1 else 16

        target_slot = -1
        if len(presets) >= max_slots:
            items = [f"Slot {p['id']}: {p['name'] or f'Preset {p['id']}'}" for p in presets]
            chosen, ok = QInputDialog.getItem(
                self,
                "Memoria de Presets Llena",
                f"La memoria está llena ({len(presets)}/{max_slots}).\n"
                "Selecciona cuál preset deseas sobrescribir:",
                items,
                0,
                False,
            )
            if not ok or not chosen:
                return
            idx = items.index(chosen)
            target_slot = presets[idx]["id"]

        default_name = f"Preset {target_slot + 1}" if target_slot >= 0 else ""
        name, ok = QInputDialog.getText(self, "Nuevo preset", "Nombre:", text=default_name)
        if not ok or not name.strip():
            return
        try:
            angle = device.get_gimbal_angle()
            zoom = device.get_zoom()
            device.add_preset(name.strip(), angle["pitch"], angle["yaw"], 0.0, zoom, id=target_slot)
        except bridge.ObsbotError:
            QMessageBox.warning(self, "Error", "No se pudo guardar el preset")
        self._refresh()

    def _on_update(self) -> None:
        device = self._device_manager.device
        item = self.list_widget.currentItem()
        if device is None or item is None:
            QMessageBox.information(
                self, "Actualizar preset", "Selecciona un preset para actualizarlo."
            )
            return
        preset_id = item.data(PRESET_ID_ROLE)
        name = item.text()
        confirm = QMessageBox.question(
            self,
            "Actualizar preset",
            f"¿Deseas actualizar el preset '{name}' con la posición y zoom actuales de la cámara?",
        ) == QMessageBox.Yes
        if not confirm:
            return
        try:
            angle = device.get_gimbal_angle()
            zoom = device.get_zoom()
            device.add_preset(name, angle["pitch"], angle["yaw"], 0.0, zoom, id=preset_id)
        except bridge.ObsbotError:
            QMessageBox.warning(self, "Error", "No se pudo actualizar el preset")
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
                self, "Renombrar preset", "Nuevo nombre:", text=item.text())
            if not ok or not new_name.strip():
                return
            new_name = new_name.strip()
        preset_id = item.data(PRESET_ID_ROLE)
        try:
            device.rename_preset(preset_id, new_name)
        except bridge.ObsbotError:
            QMessageBox.warning(self, "Error", "No se pudo renombrar el preset")
            return
        item.setText(new_name)
        if preset_id in self.preset_buttons:
            self.preset_buttons[preset_id].setText(new_name)

    def _on_delete(self, confirm: bool | None = None) -> None:
        device = self._device_manager.device
        item = self.list_widget.currentItem()
        if device is None or item is None:
            return
        if confirm is None:
            confirm = QMessageBox.question(
                self, "Borrar preset", f"¿Confirmar borrado de '{item.text()}'?"
            ) == QMessageBox.Yes
        if not confirm:
            return
        preset_id = item.data(PRESET_ID_ROLE)
        try:
            device.delete_preset(preset_id)
        except bridge.ObsbotError:
            QMessageBox.warning(self, "Error", "No se pudo borrar el preset")
        self._refresh()
