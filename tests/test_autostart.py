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
