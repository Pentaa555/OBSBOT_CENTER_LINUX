"""Headless entry point that starts only the virtual-camera pipeline.

Launched at login by the XDG autostart entry created from the "Iniciar
cámara virtual al encender" option. Running the pipeline independently of
the GUI is deliberately more stable for OBS: the pipeline comes up once at
boot and stays up, instead of being torn down and recreated every time the
control app is opened or closed (which makes OBS drop/re-detect the source).

It reads the last-used resolution/fps/flip from the same QSettings the GUI
writes, starts the pipeline, and stays alive so the child GStreamer process
keeps running. It exits cleanly on SIGTERM/SIGINT.
"""
from __future__ import annotations

import signal
import sys
import time

from PySide6.QtCore import QSettings

from app.video_formats import VideoMode, enumerate_modes
from app.virtual_camera import VirtualCamera, VirtualCameraConfig

# QSettings keys shared with the GUI (see VideoFormatPanel).
_WIDTH_KEY = "video/width"
_HEIGHT_KEY = "video/height"
_FPS_KEY = "video/fps"
_FOURCC_KEY = "video/fourcc"
_FLIP_KEY = "video/flip"


def _load_saved_mode(settings: QSettings) -> VideoMode | None:
    """Reconstruct the last-used mode from settings, if fully present."""
    width = settings.value(_WIDTH_KEY, 0, type=int)
    height = settings.value(_HEIGHT_KEY, 0, type=int)
    fps = settings.value(_FPS_KEY, 0.0, type=float)
    fourcc = settings.value(_FOURCC_KEY, "", type=str)
    if width and height and fps and fourcc:
        return VideoMode(fourcc, width, height, fps)
    return None


def _fallback_best_mode() -> VideoMode | None:
    """If nothing was saved, pick the highest-fps compressed mode available."""
    try:
        groups = enumerate_modes()
    except Exception:
        return None
    modes = [m for g in groups for m in g.modes if m.fourcc != "YUYV"]
    if not modes:
        return None
    modes.sort(key=lambda m: (-m.fps, -(m.width * m.height)))
    return modes[0]


def main() -> int:
    settings = QSettings("OBSBOT", "OBSBOT Control")
    mode = _load_saved_mode(settings) or _fallback_best_mode()
    if mode is None:
        print("virtualcam_service: no hay modo disponible; saliendo.",
              file=sys.stderr)
        return 1
    flip = settings.value(_FLIP_KEY, "none", type=str)

    camera = VirtualCamera(VirtualCameraConfig())
    try:
        camera.check_dependencies()
        camera.ensure_loopback()
        camera.start(mode, flip=flip)
    except Exception as e:
        print(f"virtualcam_service: no se pudo iniciar: {e}", file=sys.stderr)
        return 1

    print(f"virtualcam_service: transmitiendo {mode} (flip={flip})")

    stopping = {"flag": False}

    def _handle(signum, _frame):
        stopping["flag"] = True

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)

    # Keep the process alive while the pipeline runs; if the pipeline dies
    # on its own (e.g. camera unplugged), exit so the service isn't a
    # lingering no-op.
    while not stopping["flag"]:
        if not camera.is_running:
            break
        time.sleep(1.0)

    camera.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
