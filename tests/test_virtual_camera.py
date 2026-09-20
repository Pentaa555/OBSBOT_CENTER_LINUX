import subprocess

import pytest

from app.video_formats import VideoMode
from app.virtual_camera import (
    VirtualCamera, VirtualCameraConfig, build_gst_pipeline,
    build_modprobe_command, build_rmmod_command, build_setup_command,
)


def test_is_running_anywhere_detects_external_pipeline(monkeypatch):
    import app.virtual_camera as vc
    cam = VirtualCamera(VirtualCameraConfig(virtual_nr=10))
    # No local process, but an external pipeline is found.
    monkeypatch.setattr(vc, "find_external_pipeline_pid", lambda dev: 4242)
    assert cam.is_running is False
    assert cam.is_running_anywhere() is True


def test_is_running_anywhere_false_when_nothing_running(monkeypatch):
    import app.virtual_camera as vc
    cam = VirtualCamera(VirtualCameraConfig(virtual_nr=10))
    monkeypatch.setattr(vc, "find_external_pipeline_pid", lambda dev: None)
    assert cam.is_running_anywhere() is False


def test_stop_kills_external_pipeline_when_no_local_proc(monkeypatch):
    import app.virtual_camera as vc
    cam = VirtualCamera(VirtualCameraConfig(virtual_nr=10))
    monkeypatch.setattr(vc, "find_external_pipeline_pid", lambda dev: 4242)
    killed = []
    monkeypatch.setattr(vc.os, "kill", lambda pid, sig: killed.append(pid))
    cam.stop()
    assert killed == [4242]


def test_modprobe_command_uses_exclusive_caps():
    cfg = VirtualCameraConfig(virtual_nr=10, card_label="OBSBOT Virtual")
    cmd = build_modprobe_command(cfg)
    assert "video_nr=10" in cmd
    assert "card_label=OBSBOT Virtual" in cmd
    # OBS/Chrome need exclusive_caps=1 to list the loopback as a webcam.
    assert "exclusive_caps=1" in cmd
    # Runs through a graphical privilege helper (pkexec) or non-interactive
    # sudo, never bare `sudo` (which needs a tty a GUI app doesn't have).
    assert cmd[0] in ("pkexec", "sudo")
    assert "modprobe" in cmd


def test_rmmod_command_uses_privilege_prefix():
    cmd = build_rmmod_command()
    assert cmd[0] in ("pkexec", "sudo")
    assert cmd[-3:] == ["modprobe", "-r", "v4l2loopback"]


def test_virtual_device_path_from_nr():
    assert VirtualCameraConfig(virtual_nr=7).virtual_device == "/dev/video7"


def test_gst_pipeline_mjpg_inserts_jpegdec():
    cfg = VirtualCameraConfig(real_device="/dev/video0", virtual_nr=10)
    mode = VideoMode("MJPG", 1280, 720, 60.0)
    cmd = build_gst_pipeline(cfg, mode)
    # Each token must be its own argv entry (regression guard: passing
    # "v4l2src device=..." as one token makes GStreamer report a syntax
    # error). shlex-style tokenisation keeps element and property separate.
    assert "v4l2src" in cmd
    assert "device=/dev/video0" in cmd
    assert "device=/dev/video10" in cmd
    assert "!" in cmd  # pipeline links present as standalone tokens
    joined = " ".join(cmd)
    assert "image/jpeg,width=1280,height=720,framerate=60/1" in joined
    assert "jpegdec" in cmd
    assert "v4l2sink" in cmd


def test_gst_pipeline_yuyv_has_no_decoder():
    cfg = VirtualCameraConfig()
    mode = VideoMode("YUYV", 640, 480, 30.0)
    cmd = build_gst_pipeline(cfg, mode)
    joined = " ".join(cmd)
    assert "video/x-raw" in joined
    assert "jpegdec" not in joined


def test_gst_pipeline_fractional_fps():
    cfg = VirtualCameraConfig()
    mode = VideoMode("MJPG", 1280, 720, 59.94)
    cmd = build_gst_pipeline(cfg, mode)
    assert "framerate=59940/1000" in " ".join(cmd)


def test_gst_pipeline_rejects_unknown_format():
    cfg = VirtualCameraConfig()
    with pytest.raises(ValueError):
        build_gst_pipeline(cfg, VideoMode("XVID", 1280, 720, 30.0))


def test_gst_pipeline_no_flip_by_default():
    cfg = VirtualCameraConfig()
    cmd = build_gst_pipeline(cfg, VideoMode("MJPG", 1280, 720, 60.0))
    assert "videoflip" not in " ".join(cmd)


def test_gst_pipeline_horizontal_flip():
    cfg = VirtualCameraConfig()
    cmd = build_gst_pipeline(
        cfg, VideoMode("MJPG", 1280, 720, 60.0), flip="horizontal")
    assert "videoflip" in cmd
    assert "method=horizontal-flip" in cmd


def test_gst_pipeline_rotate_180_flip():
    cfg = VirtualCameraConfig()
    cmd = build_gst_pipeline(
        cfg, VideoMode("MJPG", 1280, 720, 60.0), flip="rotate-180")
    assert "method=rotate-180" in cmd


def test_gst_pipeline_rejects_unknown_flip():
    cfg = VirtualCameraConfig()
    with pytest.raises(ValueError):
        build_gst_pipeline(
            cfg, VideoMode("MJPG", 1280, 720, 60.0), flip="sideways")


def test_start_stop_lifecycle_with_injected_spawner():
    cam = VirtualCamera(VirtualCameraConfig())

    class FakeProc:
        """A pipeline that stays alive: communicate() times out, which is how
        start() concludes streaming began successfully."""

        def __init__(self):
            self._alive = True

        def communicate(self, timeout=None):
            raise subprocess.TimeoutExpired(cmd="gst", timeout=timeout)

        def poll(self):
            return None if self._alive else 0

        def terminate(self):
            self._alive = False

        def wait(self, timeout=None):
            return 0

        def kill(self):
            self._alive = False

    spawned = []

    def fake_spawn(cmd, **kwargs):
        spawned.append(cmd)
        return FakeProc()

    cam._spawner = fake_spawn

    assert cam.is_running is False
    cam.start(VideoMode("MJPG", 1280, 720, 60.0))
    assert cam.is_running is True
    assert len(spawned) == 1

    cam.stop()
    assert cam.is_running is False


def test_start_raises_when_pipeline_dies_from_format_conflict():
    from app.virtual_camera import DependencyMissing
    cam = VirtualCamera(VirtualCameraConfig())

    class DyingProc:
        """Simulates the real failure: pipeline exits immediately with a
        not-negotiated error because OBS holds the camera in another format."""

        def communicate(self, timeout=None):
            return ("", "streaming stopped, reason not-negotiated (-4)")

        def poll(self):
            return 1

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 1

        def kill(self):
            pass

    cam._spawner = lambda cmd, **kwargs: DyingProc()
    with pytest.raises(DependencyMissing) as exc:
        cam.start(VideoMode("MJPG", 1280, 720, 60.0))
    assert "OBS" in str(exc.value)
    assert cam.is_running is False


def test_start_replaces_existing_process():
    cam = VirtualCamera(VirtualCameraConfig())
    procs = []

    class FakeProc:
        def __init__(self):
            self.alive = True

        def communicate(self, timeout=None):
            raise subprocess.TimeoutExpired(cmd="gst", timeout=timeout)

        def poll(self):
            return None if self.alive else 0

        def terminate(self):
            self.alive = False

        def wait(self, timeout=None):
            return 0

        def kill(self):
            self.alive = False

    def fake_spawn(cmd, **kwargs):
        p = FakeProc()
        procs.append(p)
        return p

    cam._spawner = fake_spawn
    cam.start(VideoMode("MJPG", 1280, 720, 60.0))
    cam.start(VideoMode("MJPG", 1920, 1080, 30.0))
    # First process was terminated when the second started.
    assert procs[0].alive is False
    assert procs[1].alive is True


def test_ensure_loopback_skips_modprobe_when_already_loaded(monkeypatch):
    import app.virtual_camera as vc
    monkeypatch.setattr(vc, "is_loopback_loaded", lambda: True)
    cam = VirtualCamera(VirtualCameraConfig(virtual_nr=10))
    calls = []
    cam._runner = lambda *a, **k: calls.append((a, k))
    cam.ensure_loopback()
    # Module already present -> no privileged command run at all.
    assert calls == []


def test_ensure_loopback_runs_modprobe_when_not_loaded(monkeypatch):
    import app.virtual_camera as vc
    monkeypatch.setattr(vc, "is_loopback_loaded", lambda: False)
    cam = VirtualCamera(VirtualCameraConfig(virtual_nr=10))

    class OkResult:
        returncode = 0
        stderr = ""

    calls = []

    def runner(cmd, **kwargs):
        calls.append(cmd)
        return OkResult()

    cam._runner = runner
    cam.ensure_loopback()
    assert calls[0] == build_modprobe_command(cam.config)


def test_ensure_loopback_raises_clear_error_on_failure(monkeypatch):
    import app.virtual_camera as vc
    from app.virtual_camera import DependencyMissing
    monkeypatch.setattr(vc, "is_loopback_loaded", lambda: False)
    cam = VirtualCamera(VirtualCameraConfig(virtual_nr=10))

    class FailResult:
        returncode = 1
        stderr = "Not authorized"

    cam._runner = lambda cmd, **kwargs: FailResult()
    with pytest.raises(DependencyMissing) as exc:
        cam.ensure_loopback()
    # The message must guide the user toward the boot-load setup.
    assert "v4l2loopback" in str(exc.value)
    assert "modules-load.d" in str(exc.value)


def test_setup_command_writes_both_boot_files():
    cfg = VirtualCameraConfig(virtual_nr=10, card_label="OBSBOT Virtual")
    cmd = build_setup_command(cfg)
    assert cmd[0] in ("pkexec", "sudo")
    # A single sh -c so the user authenticates once.
    assert "sh" in cmd and "-c" in cmd
    script = cmd[-1]
    assert "/etc/modules-load.d/obsbot-v4l2loopback.conf" in script
    assert "/etc/modprobe.d/obsbot-v4l2loopback.conf" in script
    assert "video_nr=10" in script
    assert 'card_label="OBSBOT Virtual"' in script
    assert "exclusive_caps=1" in script


def test_is_configured_true_when_boot_files_present(monkeypatch):
    import app.virtual_camera as vc
    monkeypatch.setattr(vc, "is_boot_configured", lambda: True)
    monkeypatch.setattr(vc, "is_loopback_loaded", lambda: False)
    cam = VirtualCamera(VirtualCameraConfig())
    assert cam.is_configured() is True


def test_is_configured_true_when_module_loaded(monkeypatch):
    import app.virtual_camera as vc
    monkeypatch.setattr(vc, "is_boot_configured", lambda: False)
    monkeypatch.setattr(vc, "is_loopback_loaded", lambda: True)
    cam = VirtualCamera(VirtualCameraConfig())
    assert cam.is_configured() is True


def test_is_configured_false_when_neither(monkeypatch):
    import app.virtual_camera as vc
    monkeypatch.setattr(vc, "is_boot_configured", lambda: False)
    monkeypatch.setattr(vc, "is_loopback_loaded", lambda: False)
    cam = VirtualCamera(VirtualCameraConfig())
    assert cam.is_configured() is False


def test_setup_persistent_reports_failure(monkeypatch):
    from app.virtual_camera import DependencyMissing
    cam = VirtualCamera(VirtualCameraConfig())

    class FailResult:
        returncode = 126
        stderr = "Request dismissed"

    cam._runner = lambda cmd, **kwargs: FailResult()
    with pytest.raises(DependencyMissing):
        cam.setup_persistent()


def test_setup_persistent_success(monkeypatch):
    cam = VirtualCamera(VirtualCameraConfig())

    class OkResult:
        returncode = 0
        stderr = ""

    calls = []
    cam._runner = lambda cmd, **kwargs: (calls.append(cmd), OkResult())[1]
    cam.setup_persistent()
    assert calls and "sh" in calls[0]
