import sys

from app.device_manager import DeviceManager
from app.widgets.presets_panel import PRESET_ID_ROLE, PresetsPanel


def test_connect_populates_existing_presets(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    device = bridge.add_device("SN1", "Tiny2")
    device.add_preset("home", 0.0, 0.0, 0.0, 1.0)
    panel = PresetsPanel(manager)
    qtbot.addWidget(panel)

    bridge.connect_device("SN1")

    assert panel.list_widget.count() == 1
    assert panel.list_widget.item(0).text() == "home"


def test_goto_calls_goto_preset_with_selected_id(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    device = bridge.add_device("SN1", "Tiny2")
    preset_id = device.add_preset("home", 0.0, 0.0, 0.0, 1.0)
    panel = PresetsPanel(manager)
    qtbot.addWidget(panel)
    bridge.connect_device("SN1")

    panel.list_widget.setCurrentRow(0)
    panel.goto_btn.click()

    assert ("goto_preset", preset_id) in device.calls


def test_delete_removes_from_device_and_refreshes(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    device = bridge.add_device("SN1", "Tiny2")
    device.add_preset("home", 0.0, 0.0, 0.0, 1.0)
    panel = PresetsPanel(manager)
    qtbot.addWidget(panel)
    bridge.connect_device("SN1")

    panel.list_widget.setCurrentRow(0)
    panel._on_delete(confirm=True)

    assert panel.list_widget.count() == 0
    assert device.list_presets() == []


def test_rename_calls_rename_preset_and_refreshes_label(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    device = bridge.add_device("SN1", "Tiny2")
    preset_id = device.add_preset("home", 0.0, 0.0, 0.0, 1.0)
    panel = PresetsPanel(manager)
    qtbot.addWidget(panel)
    bridge.connect_device("SN1")

    panel.list_widget.setCurrentRow(0)
    panel._on_rename(new_name="office")

    assert ("rename_preset", preset_id, "office") in device.calls
    assert panel.list_widget.item(0).text() == "office"


def test_disconnect_clears_list_and_disables_buttons(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    device = bridge.add_device("SN1", "Tiny2")
    device.add_preset("home", 0.0, 0.0, 0.0, 1.0)
    panel = PresetsPanel(manager)
    qtbot.addWidget(panel)
    bridge.connect_device("SN1")

    bridge.remove_device("SN1")

    assert panel.list_widget.count() == 0
    assert not panel.add_btn.isEnabled()
    assert not panel.rename_btn.isEnabled()


def test_list_presets_error_shows_warning(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    device = bridge.add_device("SN1", "Tiny2")
    device.add_preset("home", 0.0, 0.0, 0.0, 1.0)
    panel = PresetsPanel(manager)
    qtbot.addWidget(panel)

    # Capture warning calls
    warning_calls = []
    original_warning = QMessageBox.warning

    def mock_warning(*args, **kwargs):
        warning_calls.append(args)
        return None

    monkeypatch.setattr(QMessageBox, "warning", mock_warning)

    # Make list_presets raise an error
    def raise_error():
        raise bridge.ObsbotError("Test error")

    monkeypatch.setattr(device, "list_presets", raise_error)

    # Connect device, which triggers _refresh()
    bridge.connect_device("SN1")

    # Verify warning was shown
    assert len(warning_calls) > 0
    # warning_calls[0] is (widget, title, message)
    assert warning_calls[0][1] == "Error"
    assert warning_calls[0][2] == "No se pudieron cargar los presets"
    # Verify list is empty
    assert panel.list_widget.count() == 0


def test_update_preset_calls_add_preset_with_same_id(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    device = bridge.add_device("SN1", "Tiny2")
    preset_id = device.add_preset("home", 0.0, 0.0, 0.0, 1.0)
    panel = PresetsPanel(manager)
    qtbot.addWidget(panel)
    bridge.connect_device("SN1")

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    panel.list_widget.setCurrentRow(0)
    panel.update_btn.click()

    add_calls = [c for c in device.calls if c[0] == "add_preset"]
    assert len(add_calls) >= 2  # initial add + update
    last_call = add_calls[-1]
    assert last_call[1] == "home"
    assert last_call[-1] == preset_id


def test_preset_action_arrow_has_update_rename_delete_menu(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    device = bridge.add_device("SN1", "Tiny2")
    preset_id = device.add_preset("home", 0.0, 0.0, 0.0, 1.0)
    panel = PresetsPanel(manager)
    qtbot.addWidget(panel)
    bridge.connect_device("SN1")

    assert preset_id in panel.preset_action_buttons
    assert panel.preset_action_buttons[preset_id].arrowType().name == "RightArrow"
    assert [action.text() for action in panel.preset_menus[preset_id].actions()
            if not action.isSeparator()] == ["Actualizar", "Renombrar", "Borrar"]
