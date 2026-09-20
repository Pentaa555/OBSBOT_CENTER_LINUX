import app.widgets.video_format_panel as panel_mod
from app.video_formats import FormatGroup, VideoMode
from app.widgets.video_format_panel import VideoFormatPanel


class FakeCamera:
    """Stand-in for VirtualCamera that records calls instead of touching
    the kernel module or spawning GStreamer."""

    def __init__(self, configured=False):
        self.started_with = None
        self.started_flip = None
        self.stopped = False
        self.loopback_ensured = False
        self.deps_checked = False
        self.setup_called = False
        self._configured = configured
        self._running = False
        from app.virtual_camera import VirtualCameraConfig
        self.config = VirtualCameraConfig()

    def check_dependencies(self):
        self.deps_checked = True

    def ensure_loopback(self):
        self.loopback_ensured = True

    def is_configured(self):
        return self._configured

    def setup_persistent(self):
        self.setup_called = True
        self._configured = True

    def start(self, mode, flip="none"):
        self.started_with = mode
        self.started_flip = flip
        self._running = True

    def stop(self):
        self.stopped = True
        self._running = False

    @property
    def is_running(self):
        return self._running

    def is_running_anywhere(self):
        return self._running


def _install_modes(monkeypatch, groups):
    monkeypatch.setattr(
        panel_mod, "enumerate_modes", lambda device: groups
    )


def test_populates_modes_best_first(qtbot, monkeypatch):
    groups = [
        FormatGroup("MJPG", "", [
            VideoMode("MJPG", 1280, 720, 60.0),
            VideoMode("MJPG", 1920, 1080, 30.0),
        ]),
        FormatGroup("YUYV", "", [VideoMode("YUYV", 640, 480, 30.0)]),
    ]
    _install_modes(monkeypatch, groups)
    p = VideoFormatPanel(virtual_camera=FakeCamera())
    qtbot.addWidget(p)

    # Resolutions listed largest-area first; 640x480 (YUYV) last.
    assert "1920x1080" in p.resolution_combo.itemText(0)
    assert "640x480" in p.resolution_combo.itemText(
        p.resolution_combo.count() - 1)


def test_fps_column_reacts_to_resolution(qtbot, monkeypatch):
    groups = [
        FormatGroup("MJPG", "", [
            VideoMode("MJPG", 1280, 720, 60.0),
            VideoMode("MJPG", 1280, 720, 30.0),
            VideoMode("MJPG", 1920, 1080, 30.0),
        ]),
    ]
    _install_modes(monkeypatch, groups)
    p = VideoFormatPanel(virtual_camera=FakeCamera())
    qtbot.addWidget(p)

    # Select 720p -> both 60 and 30 fps available, 60 first.
    idx_720 = next(
        i for i in range(p.resolution_combo.count())
        if "1280x720" in p.resolution_combo.itemText(i)
    )
    p.resolution_combo.setCurrentIndex(idx_720)
    fps_texts = [p.fps_combo.itemText(i) for i in range(p.fps_combo.count())]
    assert fps_texts[0].startswith("60")
    assert any(t.startswith("30") for t in fps_texts)

    # Select 1080p -> only 30 fps available.
    idx_1080 = next(
        i for i in range(p.resolution_combo.count())
        if "1920x1080" in p.resolution_combo.itemText(i)
    )
    p.resolution_combo.setCurrentIndex(idx_1080)
    fps_texts = [p.fps_combo.itemText(i) for i in range(p.fps_combo.count())]
    assert len(fps_texts) == 1
    assert fps_texts[0].startswith("30")


def test_start_creates_loopback_and_streams_selected_mode(qtbot, monkeypatch):
    groups = [FormatGroup("MJPG", "", [VideoMode("MJPG", 1280, 720, 60.0)])]
    _install_modes(monkeypatch, groups)
    cam = FakeCamera()
    p = VideoFormatPanel(virtual_camera=cam)
    qtbot.addWidget(p)

    # reload_modes already selected the only resolution and populated fps.
    p._on_start()

    assert cam.deps_checked is True
    assert cam.loopback_ensured is True
    assert cam.started_with == VideoMode("MJPG", 1280, 720, 60.0)
    assert p.start_button.isEnabled() is False
    assert p.stop_button.isEnabled() is True


def test_stop_stops_camera_and_resets_buttons(qtbot, monkeypatch):
    groups = [FormatGroup("MJPG", "", [VideoMode("MJPG", 1280, 720, 60.0)])]
    _install_modes(monkeypatch, groups)
    cam = FakeCamera()
    p = VideoFormatPanel(virtual_camera=cam)
    qtbot.addWidget(p)
    p._on_start()

    p._on_stop()

    assert cam.stopped is True
    assert p.start_button.isEnabled() is True
    assert p.stop_button.isEnabled() is False


def test_start_error_is_reported_not_raised(qtbot, monkeypatch):
    groups = [FormatGroup("MJPG", "", [VideoMode("MJPG", 1280, 720, 60.0)])]
    _install_modes(monkeypatch, groups)

    cam = FakeCamera()

    def boom(mode, flip="none"):
        raise RuntimeError("device busy")

    cam.start = boom
    p = VideoFormatPanel(virtual_camera=cam)
    qtbot.addWidget(p)

    errors = []
    p.error_occurred.connect(errors.append)
    p._on_start()

    assert errors and "device busy" in errors[0]
    # Buttons stay in the stopped state after a failed start.
    assert p.start_button.isEnabled() is True


def test_missing_v4l2_tool_reports_error(qtbot, monkeypatch):
    from app.video_formats import V4l2NotAvailable

    def raise_missing(device):
        raise V4l2NotAvailable("v4l2-ctl not found")

    monkeypatch.setattr(panel_mod, "enumerate_modes", raise_missing)
    errors = []
    p = VideoFormatPanel(virtual_camera=FakeCamera())
    qtbot.addWidget(p)
    p.error_occurred.connect(errors.append)
    p.reload_modes()

    assert p.resolution_combo.count() == 0
    assert errors and "v4l2-ctl" in errors[0]


def test_setup_button_visible_when_not_configured(qtbot, monkeypatch):
    _install_modes(monkeypatch, [])
    p = VideoFormatPanel(virtual_camera=FakeCamera(configured=False))
    qtbot.addWidget(p)
    # isHidden() reflects the explicit setVisible() state regardless of
    # whether the parent window has been shown yet.
    assert p.setup_button.isHidden() is False


def test_setup_button_hidden_when_already_configured(qtbot, monkeypatch):
    _install_modes(monkeypatch, [])
    p = VideoFormatPanel(virtual_camera=FakeCamera(configured=True))
    qtbot.addWidget(p)
    # A configured system doesn't need the one-time setup button.
    assert p.setup_button.isHidden() is True


def test_setup_runs_persistent_setup_and_hides_button(qtbot, monkeypatch):
    _install_modes(monkeypatch, [])
    cam = FakeCamera(configured=False)
    p = VideoFormatPanel(virtual_camera=cam)
    qtbot.addWidget(p)

    p._on_setup()

    assert cam.setup_called is True
    assert p.setup_button.isHidden() is True


def test_setup_error_is_reported(qtbot, monkeypatch):
    _install_modes(monkeypatch, [])
    cam = FakeCamera(configured=False)

    def boom():
        raise RuntimeError("autenticación cancelada")

    cam.setup_persistent = boom
    p = VideoFormatPanel(virtual_camera=cam)
    qtbot.addWidget(p)
    errors = []
    p.error_occurred.connect(errors.append)

    p._on_setup()

    assert errors and "cancelada" in errors[0]


class _FakeSettings:
    def __init__(self):
        self.store = {}
        self.synced = 0

    def value(self, key, default=None, type=None):
        return self.store.get(key, default)

    def setValue(self, key, value):
        self.store[key] = value

    def sync(self):
        self.synced += 1


def test_start_passes_selected_flip(qtbot, monkeypatch):
    groups = [FormatGroup("MJPG", "", [VideoMode("MJPG", 1280, 720, 60.0)])]
    _install_modes(monkeypatch, groups)
    cam = FakeCamera(configured=True)
    p = VideoFormatPanel(virtual_camera=cam)
    qtbot.addWidget(p)

    # Select the horizontal-mirror option.
    i = p.orientation_combo.findData("horizontal")
    p.orientation_combo.setCurrentIndex(i)
    p._on_start()

    assert cam.started_flip == "horizontal"


def test_orientation_default_is_none(qtbot, monkeypatch):
    groups = [FormatGroup("MJPG", "", [VideoMode("MJPG", 1280, 720, 60.0)])]
    _install_modes(monkeypatch, groups)
    cam = FakeCamera(configured=True)
    p = VideoFormatPanel(virtual_camera=cam)
    qtbot.addWidget(p)
    p._on_start()
    assert cam.started_flip == "none"


def test_orientation_change_persisted_to_settings(qtbot, monkeypatch):
    groups = [FormatGroup("MJPG", "", [VideoMode("MJPG", 1280, 720, 60.0)])]
    _install_modes(monkeypatch, groups)
    settings = _FakeSettings()
    p = VideoFormatPanel(virtual_camera=FakeCamera(configured=True),
                         settings=settings)
    qtbot.addWidget(p)

    i = p.orientation_combo.findData("rotate-180")
    p.orientation_combo.setCurrentIndex(i)
    assert settings.store[VideoFormatPanel.ORIENTATION_KEY] == "rotate-180"


def test_orientation_restored_from_settings(qtbot, monkeypatch):
    groups = [FormatGroup("MJPG", "", [VideoMode("MJPG", 1280, 720, 60.0)])]
    _install_modes(monkeypatch, groups)
    settings = _FakeSettings()
    settings.store[VideoFormatPanel.ORIENTATION_KEY] = "vertical"
    p = VideoFormatPanel(virtual_camera=FakeCamera(configured=True),
                         settings=settings)
    qtbot.addWidget(p)
    assert p._selected_flip() == "vertical"


def test_changing_orientation_while_running_restarts_with_new_flip(
        qtbot, monkeypatch):
    groups = [FormatGroup("MJPG", "", [VideoMode("MJPG", 1280, 720, 60.0)])]
    _install_modes(monkeypatch, groups)
    cam = FakeCamera(configured=True)
    p = VideoFormatPanel(virtual_camera=cam)
    qtbot.addWidget(p)
    p._on_start()
    assert cam.is_running is True

    i = p.orientation_combo.findData("horizontal")
    p.orientation_combo.setCurrentIndex(i)

    # The live change should have restarted the pipeline with the new flip.
    assert cam.started_flip == "horizontal"


def test_changing_orientation_while_stopped_does_not_start(qtbot, monkeypatch):
    groups = [FormatGroup("MJPG", "", [VideoMode("MJPG", 1280, 720, 60.0)])]
    _install_modes(monkeypatch, groups)
    cam = FakeCamera(configured=True)
    p = VideoFormatPanel(virtual_camera=cam)
    qtbot.addWidget(p)

    i = p.orientation_combo.findData("horizontal")
    p.orientation_combo.setCurrentIndex(i)

    # Not streaming, so no start should have happened from the change.
    assert cam.started_with is None


def test_start_saves_mode_to_settings(qtbot, monkeypatch):
    groups = [FormatGroup("MJPG", "", [VideoMode("MJPG", 1280, 720, 60.0)])]
    _install_modes(monkeypatch, groups)
    settings = _FakeSettings()
    p = VideoFormatPanel(virtual_camera=FakeCamera(configured=True),
                         settings=settings)
    qtbot.addWidget(p)

    p._on_start()

    assert settings.store[VideoFormatPanel.WIDTH_KEY] == 1280
    assert settings.store[VideoFormatPanel.HEIGHT_KEY] == 720
    assert settings.store[VideoFormatPanel.FPS_KEY] == 60.0
    assert settings.store[VideoFormatPanel.FOURCC_KEY] == "MJPG"


def test_autostart_vcam_toggle_enables_entry_and_saves_mode(qtbot, monkeypatch):
    import app.widgets.video_format_panel as mod
    calls = []
    monkeypatch.setattr(mod.autostart, "is_vcam_enabled", lambda: False)
    monkeypatch.setattr(
        mod.autostart, "set_vcam_enabled", lambda v: calls.append(v))

    groups = [FormatGroup("MJPG", "", [VideoMode("MJPG", 1280, 720, 60.0)])]
    _install_modes(monkeypatch, groups)
    settings = _FakeSettings()
    p = VideoFormatPanel(virtual_camera=FakeCamera(configured=True),
                         settings=settings)
    qtbot.addWidget(p)

    p.autostart_vcam_check.setChecked(True)

    assert calls == [True]
    # Toggling on should have persisted the current mode for the login
    # service to reuse.
    assert settings.store[VideoFormatPanel.WIDTH_KEY] == 1280
    assert settings.store[VideoFormatPanel.FOURCC_KEY] == "MJPG"


def test_autostart_vcam_checkbox_reflects_disk_state(qtbot, monkeypatch):
    import app.widgets.video_format_panel as mod
    monkeypatch.setattr(mod.autostart, "is_vcam_enabled", lambda: True)
    _install_modes(monkeypatch, [])
    p = VideoFormatPanel(virtual_camera=FakeCamera(configured=True))
    qtbot.addWidget(p)
    assert p.autostart_vcam_check.isChecked() is True


def test_panel_reflects_already_running_pipeline_on_open(qtbot, monkeypatch):
    groups = [FormatGroup("MJPG", "", [VideoMode("MJPG", 1280, 720, 60.0)])]
    _install_modes(monkeypatch, groups)
    cam = FakeCamera(configured=True)
    # Simulate a pipeline already running in another process at open time.
    cam._running = True
    p = VideoFormatPanel(virtual_camera=cam)
    qtbot.addWidget(p)

    # The panel must show streaming state, not the default "Detenida".
    assert "Transmitiendo" in p.status_label.text()
    assert p.start_button.isEnabled() is False
    assert p.stop_button.isEnabled() is True


def test_panel_shows_stopped_when_nothing_running(qtbot, monkeypatch):
    groups = [FormatGroup("MJPG", "", [VideoMode("MJPG", 1280, 720, 60.0)])]
    _install_modes(monkeypatch, groups)
    cam = FakeCamera(configured=True)  # not running
    p = VideoFormatPanel(virtual_camera=cam)
    qtbot.addWidget(p)
    assert p.status_label.text() == "Detenida"
    assert p.start_button.isEnabled() is True
    assert p.stop_button.isEnabled() is False
