import app.widgets.video_format_panel as panel_mod
from app.video_formats import FormatGroup, VideoMode
from app.widgets.video_format_panel import VideoFormatPanel


class FakeCamera:
    """Stand-in for VirtualCamera that records calls instead of touching
    the kernel module or spawning GStreamer."""

    def __init__(self, configured=False):
        self.started_with = None
        self.stopped = False
        self.loopback_ensured = False
        self.deps_checked = False
        self.setup_called = False
        self._configured = configured
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

    def start(self, mode):
        self.started_with = mode

    def stop(self):
        self.stopped = True


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

    def boom(mode):
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
