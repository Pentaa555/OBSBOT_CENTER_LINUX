from app import autostart


def test_enable_creates_entry(tmp_path):
    assert autostart.is_enabled(tmp_path) is False
    path = autostart.enable(tmp_path)
    assert path.exists()
    assert autostart.is_enabled(tmp_path) is True


def test_disable_removes_entry(tmp_path):
    autostart.enable(tmp_path)
    autostart.disable(tmp_path)
    assert autostart.is_enabled(tmp_path) is False


def test_disable_is_idempotent(tmp_path):
    # No error when disabling something that was never enabled.
    autostart.disable(tmp_path)
    assert autostart.is_enabled(tmp_path) is False


def test_set_enabled_toggles(tmp_path):
    autostart.set_enabled(True, tmp_path)
    assert autostart.is_enabled(tmp_path) is True
    autostart.set_enabled(False, tmp_path)
    assert autostart.is_enabled(tmp_path) is False


def test_entry_contents_are_valid_desktop_file(tmp_path):
    path = autostart.enable(tmp_path)
    text = path.read_text()
    assert text.startswith("[Desktop Entry]")
    assert "Type=Application" in text
    assert "Name=OBSBOT Control" in text
    assert "Exec=" in text
    # GNOME-specific flag so it isn't silently disabled there.
    assert "X-GNOME-Autostart-enabled=true" in text


def test_build_entry_text_embeds_command_and_icon():
    text = autostart.build_entry_text("/path/run.sh", "/path/icon.png")
    assert "Exec=/path/run.sh" in text
    assert "Icon=/path/icon.png" in text


def test_default_autostart_dir_respects_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert autostart.default_autostart_dir() == tmp_path / "autostart"


def test_app_autostart_exec_passes_tray_flag(tmp_path):
    # Started at login it should pass --tray so it can honour the tray pref.
    path = autostart.enable(tmp_path)
    assert "--tray" in path.read_text()


# --- virtual camera autostart (independent of the app entry) -------------

def test_vcam_enable_creates_separate_entry(tmp_path):
    assert autostart.is_vcam_enabled(tmp_path) is False
    path = autostart.enable_vcam(tmp_path)
    assert path.exists()
    assert autostart.is_vcam_enabled(tmp_path) is True
    # It must be a different file than the app entry.
    assert path.name != "obsbot-control-autostart.desktop"


def test_vcam_and_app_entries_are_independent(tmp_path):
    autostart.enable(tmp_path)          # app on
    autostart.set_vcam_enabled(True, tmp_path)   # vcam on
    assert autostart.is_enabled(tmp_path) is True
    assert autostart.is_vcam_enabled(tmp_path) is True

    autostart.disable(tmp_path)         # app off, vcam should stay on
    assert autostart.is_enabled(tmp_path) is False
    assert autostart.is_vcam_enabled(tmp_path) is True


def test_vcam_disable_removes_entry(tmp_path):
    autostart.enable_vcam(tmp_path)
    autostart.set_vcam_enabled(False, tmp_path)
    assert autostart.is_vcam_enabled(tmp_path) is False
