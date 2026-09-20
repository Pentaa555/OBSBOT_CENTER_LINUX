from app.video_formats import FormatGroup, VideoMode
from app import virtualcam_service as svc


class _FakeSettings:
    def __init__(self, store=None):
        self.store = store or {}

    def value(self, key, default=None, type=None):
        return self.store.get(key, default)


def test_load_saved_mode_reconstructs_when_all_present():
    settings = _FakeSettings({
        svc._WIDTH_KEY: 1280,
        svc._HEIGHT_KEY: 720,
        svc._FPS_KEY: 60.0,
        svc._FOURCC_KEY: "MJPG",
    })
    mode = svc._load_saved_mode(settings)
    assert mode == VideoMode("MJPG", 1280, 720, 60.0)


def test_load_saved_mode_returns_none_when_incomplete():
    settings = _FakeSettings({svc._WIDTH_KEY: 1280})  # missing the rest
    assert svc._load_saved_mode(settings) is None


def test_fallback_best_mode_prefers_highest_fps_compressed(monkeypatch):
    groups = [
        FormatGroup("MJPG", "", [
            VideoMode("MJPG", 1280, 720, 60.0),
            VideoMode("MJPG", 1920, 1080, 30.0),
        ]),
        FormatGroup("YUYV", "", [VideoMode("YUYV", 1280, 720, 60.0)]),
    ]
    monkeypatch.setattr(svc, "enumerate_modes", lambda: groups)
    mode = svc._fallback_best_mode()
    assert mode.fourcc != "YUYV"
    assert mode.fps == 60.0


def test_fallback_best_mode_none_when_enumeration_fails(monkeypatch):
    def boom():
        raise RuntimeError("no camera")
    monkeypatch.setattr(svc, "enumerate_modes", boom)
    assert svc._fallback_best_mode() is None
