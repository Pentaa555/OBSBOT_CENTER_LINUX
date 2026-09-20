from PySide6.QtCore import QSettings

from app.widgets.system_panel import SystemPanel


class _FakeSettings:
    """Minimal QSettings stand-in that stores values in a dict."""

    def __init__(self):
        self.store = {}

    def value(self, key, default=None, type=None):
        return self.store.get(key, default)

    def setValue(self, key, value):
        self.store[key] = value


def test_autostart_checkbox_reflects_disk_state(qtbot, monkeypatch):
    import app.widgets.system_panel as mod
    monkeypatch.setattr(mod.autostart, "is_enabled", lambda: True)
    panel = SystemPanel(settings=_FakeSettings())
    qtbot.addWidget(panel)
    assert panel.autostart_check.isChecked() is True


def test_toggling_autostart_calls_set_enabled(qtbot, monkeypatch):
    import app.widgets.system_panel as mod
    monkeypatch.setattr(mod.autostart, "is_enabled", lambda: False)
    calls = []
    monkeypatch.setattr(mod.autostart, "set_enabled", lambda v: calls.append(v))

    panel = SystemPanel(settings=_FakeSettings())
    qtbot.addWidget(panel)
    panel.autostart_check.setChecked(True)
    assert calls == [True]
    panel.autostart_check.setChecked(False)
    assert calls == [True, False]


def test_tray_preference_persisted_to_settings(qtbot, monkeypatch):
    import app.widgets.system_panel as mod
    monkeypatch.setattr(mod.autostart, "is_enabled", lambda: False)
    settings = _FakeSettings()
    panel = SystemPanel(settings=settings)
    qtbot.addWidget(panel)

    panel.tray_check.setChecked(False)
    assert settings.store[SystemPanel.MINIMIZE_TO_TRAY_KEY] is False
    assert panel.minimize_to_tray is False

    panel.tray_check.setChecked(True)
    assert settings.store[SystemPanel.MINIMIZE_TO_TRAY_KEY] is True
    assert panel.minimize_to_tray is True
