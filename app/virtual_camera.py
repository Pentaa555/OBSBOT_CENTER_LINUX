"""Manage a v4l2loopback virtual camera fed from the real OBSBOT camera.

Why this exists: on Linux a UVC device like /dev/video0 is opened
exclusively by whoever consumes its video (OBS, browser, etc.), and that
consumer picks the capture resolution/fps when it opens the device. There
is no supported way to make the OBSBOT control SDK change the format of the
stream another app is receiving.

So to let the *app* choose resolution/fps (like the Windows OBSBOT Center
effectively does through its own pipeline), we insert ourselves as the
owner of the real stream and re-expose it on a virtual device that OBS
consumes instead:

    /dev/video0 (real)  --GStreamer(chosen mode)-->  /dev/videoN (virtual)  -->  OBS

Two OS-level actions are involved, both of which require privileges and are
reversible:
  1. Loading the v4l2loopback kernel module (creates /dev/videoN).
  2. Running a GStreamer pipeline that opens the real camera.

This module only *builds the commands and manages the subprocess*; it
intentionally does not run anything on import, so it is safe to unit-test.
"""
from __future__ import annotations

import shlex
import shutil
import subprocess
import os
from dataclasses import dataclass

from app.video_formats import VideoMode

# GStreamer decoder element per pixel format. YUYV is raw so it needs no
# decoder; MJPG/H264 are compressed and must be decoded before hitting the
# loopback sink (OBS expects a plain video stream on the virtual device).
_DECODER_FOR_FOURCC = {
    "MJPG": "jpegdec",
    "MJPEG": "jpegdec",
    "H264": "h264parse ! avdec_h264",
    "YUYV": None,  # raw, passthrough
}

# The v4l2src caps 'format' string GStreamer expects for the compressed
# formats, keyed by the driver's fourcc.
_GST_ENCODING = {
    "MJPG": "image/jpeg",
    "MJPEG": "image/jpeg",
    "H264": "video/x-h264",
    "YUYV": "video/x-raw",
}

# User-facing flip options mapped to GstVideoFlipMethod values. "Inverted"
# most commonly means either a horizontal mirror or an upside-down (180°)
# image, so both are offered plus a plain vertical flip.
FLIP_METHODS = {
    "none": "none",
    "horizontal": "horizontal-flip",  # left-right mirror
    "vertical": "vertical-flip",      # top-bottom
    "rotate-180": "rotate-180",       # upside down
}

# Human labels for the flip options (Spanish UI).
FLIP_LABELS = {
    "none": "Normal (sin voltear)",
    "horizontal": "Espejo horizontal",
    "vertical": "Voltear vertical",
    "rotate-180": "Girar 180° (boca abajo)",
}


class DependencyMissing(RuntimeError):
    """A required system tool (modprobe, gst-launch-1.0) is unavailable."""


@dataclass(frozen=True)
class VirtualCameraConfig:
    real_device: str = "/dev/video0"
    virtual_nr: int = 10
    card_label: str = "OBSBOT Virtual"

    @property
    def virtual_device(self) -> str:
        return f"/dev/video{self.virtual_nr}"


def _privilege_prefix() -> list[str]:
    """Choose how to run a privileged command from a GUI app.

    Prefer pkexec: it pops up a graphical password dialog via PolicyKit, so
    it works when the app was launched without a controlling terminal (from
    the desktop icon / autostart). `sudo` is only usable here if it has been
    configured for passwordless use, because a GUI app has no tty to type a
    password into — that is exactly why the first attempt failed.
    """
    if shutil.which("pkexec"):
        return ["pkexec"]
    # Fall back to non-interactive sudo; only works if a sudoers rule allows
    # this command without a password. Otherwise ensure_loopback() surfaces
    # a clear error telling the user how to set things up.
    return ["sudo", "-n"]


def is_loopback_loaded() -> bool:
    """True if the v4l2loopback kernel module is currently loaded.

    When it is, no privilege escalation is needed at all — we skip modprobe
    entirely and just run the (unprivileged) GStreamer pipeline.
    """
    try:
        with open("/proc/modules", "r") as f:
            return any(line.startswith("v4l2loopback ") for line in f)
    except OSError:
        return False


def find_external_pipeline_pid(virtual_device: str) -> int | None:
    """Return the PID of a GStreamer pipeline already feeding `virtual_device`.

    The pipeline may have been started by the headless login service or by a
    previous app session; because it runs in another process, the panel's
    own VirtualCamera object doesn't know about it. We scan /proc for a
    process whose command line writes to this virtual device, so the UI can
    reflect the true "streaming" state instead of always showing "stopped".
    """
    needle = f"device={virtual_device}"
    try:
        pids = [name for name in os.listdir("/proc") if name.isdigit()]
    except OSError:
        return None
    for pid in pids:
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmdline = f.read().replace(b"\x00", b" ").decode(
                    "utf-8", "replace")
        except OSError:
            continue  # process vanished or not readable
        if "gst-launch" in cmdline and needle in cmdline:
            return int(pid)
    return None


# System files that make v4l2loopback load automatically at every boot with
# the parameters OBS needs. Writing these once is what lets the app run the
# virtual camera afterwards without ever asking for a password again.
MODULES_LOAD_FILE = "/etc/modules-load.d/obsbot-v4l2loopback.conf"
MODPROBE_OPTIONS_FILE = "/etc/modprobe.d/obsbot-v4l2loopback.conf"


def is_boot_configured() -> bool:
    """True if the boot-time autoload files are already in place."""
    import os
    return os.path.exists(MODULES_LOAD_FILE) and os.path.exists(
        MODPROBE_OPTIONS_FILE)


def build_setup_command(config: VirtualCameraConfig) -> list[str]:
    """One privileged command (via pkexec) that writes both autoload files
    and loads the module immediately, so no reboot is needed.

    Everything runs inside a single `sh -c` so the user is prompted for
    authentication exactly once. The options string is embedded with fixed,
    non-user-controlled values (integers and a constant label), so there is
    no shell-injection surface here.
    """
    options = (
        f'options v4l2loopback video_nr={int(config.virtual_nr)} '
        f'card_label="{config.card_label}" exclusive_caps=1'
    )
    script = (
        f"set -e\n"
        f"echo v4l2loopback > {MODULES_LOAD_FILE}\n"
        f"echo '{options}' > {MODPROBE_OPTIONS_FILE}\n"
        # Load now too (ignore failure if already loaded with other params).
        f"modprobe v4l2loopback video_nr={int(config.virtual_nr)} "
        f'card_label="{config.card_label}" exclusive_caps=1 || true\n'
    )
    return _privilege_prefix() + ["sh", "-c", script]


def build_modprobe_command(config: VirtualCameraConfig) -> list[str]:
    """Command to create the virtual device.

    exclusive_caps=1 makes the loopback advertise itself as a pure capture
    device, which OBS and Chrome require to list it as a webcam.
    """
    return _privilege_prefix() + [
        "modprobe", "v4l2loopback",
        f"video_nr={config.virtual_nr}",
        f"card_label={config.card_label}",
        "exclusive_caps=1",
        "max_buffers=2",
    ]


def build_rmmod_command() -> list[str]:
    return _privilege_prefix() + ["modprobe", "-r", "v4l2loopback"]


def build_gst_pipeline(
    config: VirtualCameraConfig,
    mode: VideoMode,
    flip: str = "none",
) -> list[str]:
    """Build the GStreamer command that pumps `mode` into the virtual device.

    `flip` inserts a videoflip element to correct an inverted/mirrored image
    (the OBSBOT feed can come out flipped depending on mounting/firmware).
    Accepted values are the keys of FLIP_METHODS.

    Raises ValueError for a pixel format we don't know how to handle, or an
    unknown flip method.

    gst-launch-1.0 expects each pipeline token as its own argv entry (the
    element name, each property, and the `!` links are all separate tokens).
    We build the human-readable pipeline string and tokenise it with
    shlex.split so e.g. `v4l2src device=/dev/video0` becomes two argv
    entries rather than one — passing it as a single string is exactly what
    triggered the "error de sintaxis" from GStreamer.
    """
    encoding = _GST_ENCODING.get(mode.fourcc)
    if encoding is None:
        raise ValueError(f"Unsupported pixel format: {mode.fourcc}")
    if flip not in FLIP_METHODS:
        raise ValueError(f"Unknown flip method: {flip}")

    # Represent fps as an integer fraction where possible (GStreamer wants
    # framerate as a fraction, e.g. 60/1). 59.94-style values become n/1000.
    if float(mode.fps).is_integer():
        framerate = f"{int(mode.fps)}/1"
    else:
        framerate = f"{int(round(mode.fps * 1000))}/1000"

    caps = (
        f"{encoding},width={mode.width},height={mode.height},"
        f"framerate={framerate}"
    )

    stages = [f"v4l2src device={config.real_device}", caps]

    decoder = _DECODER_FOR_FOURCC.get(mode.fourcc)
    if decoder:
        stages.append(decoder)

    # videoconvert guarantees a pixel layout the loopback/consumer accepts.
    stages.append("videoconvert")

    # Insert the flip right before the sink, after decode/convert, so it
    # operates on raw frames. "none" adds nothing to keep the pipeline lean.
    gst_method = FLIP_METHODS[flip]
    if gst_method != "none":
        stages.append(f"videoflip method={gst_method}")

    stages.append(f"v4l2sink device={config.virtual_device} sync=false")

    pipeline_str = " ! ".join(stages)
    return ["gst-launch-1.0", "-e"] + shlex.split(pipeline_str)


class VirtualCamera:
    """Lifecycle wrapper around the loopback device + GStreamer process."""

    def __init__(self, config: VirtualCameraConfig | None = None):
        self.config = config or VirtualCameraConfig()
        self._proc: subprocess.Popen | None = None
        self._runner = subprocess.run  # injectable for tests
        self._spawner = subprocess.Popen  # injectable for tests

    @staticmethod
    def check_dependencies() -> None:
        for tool in ("modprobe", "gst-launch-1.0"):
            if shutil.which(tool) is None:
                raise DependencyMissing(
                    f"Required tool '{tool}' not found on PATH."
                )

    def is_configured(self) -> bool:
        """True once the one-time setup has been done (boot files present or
        module already loaded), meaning starting won't prompt for a password."""
        return is_boot_configured() or is_loopback_loaded()

    def setup_persistent(self) -> None:
        """Run the one-time setup: write autoload files and load the module.

        Prompts for authentication exactly once via pkexec. Raises
        DependencyMissing with an actionable message if it fails or the user
        cancels the dialog.
        """
        result = self._runner(
            build_setup_command(self.config),
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise DependencyMissing(
                "No se pudo completar la configuración de la cámara virtual.\n"
                f"Detalle: {stderr or 'autenticación cancelada'}"
            )

    def ensure_loopback(self) -> None:
        """Create the virtual device if the module isn't already loaded.

        If v4l2loopback is already loaded (e.g. loaded at boot via
        /etc/modules-load.d, the recommended setup), this does nothing and
        no privilege escalation happens. Otherwise it runs modprobe through
        pkexec/sudo; a failure there (typically: no graphical auth agent, or
        the user cancelled the password dialog) is turned into a clear,
        actionable error instead of a raw non-zero exit.
        """
        if is_loopback_loaded():
            return
        result = self._runner(
            build_modprobe_command(self.config),
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise DependencyMissing(
                "No se pudo cargar el módulo v4l2loopback (se necesitan "
                "permisos de administrador).\n"
                f"Detalle: {stderr or 'comando de elevación cancelado o no disponible'}\n\n"
                "Solución recomendada: cargar el módulo al arranque una sola vez:\n"
                "  echo v4l2loopback | sudo tee /etc/modules-load.d/v4l2loopback.conf\n"
                "  echo 'options v4l2loopback video_nr=10 card_label=\"OBSBOT Virtual\" "
                "exclusive_caps=1' | sudo tee /etc/modprobe.d/obsbot-v4l2loopback.conf\n"
                "Luego reinicia. Después la cámara virtual arranca sin pedir contraseña."
            )

    def remove_loopback(self) -> None:
        self._runner(build_rmmod_command(), check=False)

    def start(self, mode: VideoMode, flip: str = "none") -> None:
        """Start streaming `mode` from the real camera to the virtual one.

        `flip` corrects an inverted/mirrored image (see FLIP_METHODS).

        The pipeline can die immediately for a very common reason: another
        app (usually OBS) already has the real camera open in a *different*
        format, and Linux UVC only serves one format at a time, so GStreamer
        fails to negotiate. We detect that early death, read the pipeline's
        stderr, and raise a DependencyMissing with an actionable message
        instead of leaving the UI claiming it is streaming (and leaving a
        zombie process behind).
        """
        if self.is_running:
            self.stop()
        cmd = build_gst_pipeline(self.config, mode, flip=flip)
        self._proc = self._spawner(
            cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True
        )
        # Give it a moment to either start streaming or fail negotiation.
        try:
            _out, err = self._proc.communicate(timeout=1.5)
        except subprocess.TimeoutExpired:
            # Still alive after the grace period -> streaming successfully.
            return
        # It exited within the grace period: something went wrong.
        err = err or ""
        self._proc = None
        if "not-negotiated" in err or "cannot capture" in err.lower() \
                or "returned format" in err:
            raise DependencyMissing(
                "No se pudo iniciar: la cámara ya está en uso por otra "
                "aplicación (probablemente OBS) con un formato distinto.\n"
                "Quita o desactiva la fuente de la cámara real en OBS, inicia "
                "aquí la cámara virtual, y luego en OBS selecciona la fuente "
                "«{}».".format(self.config.card_label)
            )
        raise DependencyMissing(
            "El pipeline de la cámara virtual terminó inesperadamente.\n"
            f"Detalle: {err.strip()[-400:] or 'sin salida de error'}"
        )

    def stop(self) -> None:
        # Stop our own child if we started one.
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=2)
            finally:
                self._proc = None
            return
        # Otherwise, stop an external pipeline (login service / previous
        # session) feeding our virtual device, so "Detener" works regardless
        # of which process started it.
        pid = find_external_pipeline_pid(self.config.virtual_device)
        if pid is not None:
            import signal
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass

    @property
    def is_running(self) -> bool:
        """True if THIS object started a pipeline that is still alive."""
        return self._proc is not None and self._proc.poll() is None

    def is_running_anywhere(self) -> bool:
        """True if any process (this one, the login service, or a previous
        session) is currently feeding the virtual device."""
        if self.is_running:
            return True
        return find_external_pipeline_pid(self.config.virtual_device) is not None
