"""Manage launch-on-login via freedesktop XDG autostart entries.

The XDG Autostart spec is honoured by GNOME, KDE, XFCE, Cinnamon, etc.: any
`.desktop` file placed in ~/.config/autostart/ is executed when the user
logs in.

Two independent entries are managed:
  - the app itself (so the control window/tray comes up at login), and
  - the virtual camera pipeline (so "OBSBOT Virtual" is available to OBS at
    login without opening the app, which is more stable for OBS than
    restarting the pipeline every time the app launches).

This module only reads/writes those files under ~/.config/autostart/; it
does not touch anything system-wide and requires no privileges. All paths
are overridable so it can be unit-tested against a temp directory.
"""
from __future__ import annotations

import os
from pathlib import Path

_ENTRY_NAME = "obsbot-control-autostart.desktop"
_VCAM_ENTRY_NAME = "obsbot-virtualcam-autostart.desktop"


def _project_root() -> Path:
    # app/autostart.py -> project root is two levels up.
    return Path(__file__).resolve().parent.parent


def default_autostart_dir() -> Path:
    """~/.config/autostart, honouring $XDG_CONFIG_HOME if set."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "autostart"


def _entry_path(autostart_dir: Path | None) -> Path:
    return (autostart_dir or default_autostart_dir()) / _ENTRY_NAME


def _vcam_entry_path(autostart_dir: Path | None) -> Path:
    return (autostart_dir or default_autostart_dir()) / _VCAM_ENTRY_NAME


def _run_command() -> str:
    """The Exec= line: the run.sh wrapper if present, else python -m app.main.

    Passes --tray so the app knows it was started at login and can honour
    the minimise-to-tray preference (start hidden in the tray) instead of
    popping a window on every boot.
    """
    run_sh = _project_root() / "run.sh"
    if run_sh.exists():
        return f"{run_sh} --tray"
    return f"{os.sys.executable} -m app.main --tray"


def _vcam_run_command() -> str:
    """Exec= line that starts only the virtual-camera pipeline (no GUI).

    Prefers the run-vcam.sh wrapper (venv + PYTHONPATH) if present, so the
    autostart environment matches how the pipeline runs from the app.
    """
    wrapper = _project_root() / "run-vcam.sh"
    if wrapper.exists():
        return str(wrapper)
    return f"{os.sys.executable} -m app.virtualcam_service"


def build_entry_text(exec_command: str, icon_path: str,
                     name: str = "OBSBOT Control") -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        f"Name={name}\n"
        "Comment=Control de cámara OBSBOT Tiny para Linux\n"
        f"Exec={exec_command}\n"
        f"Icon={icon_path}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


# --- App autostart -------------------------------------------------------

def is_enabled(autostart_dir: Path | None = None) -> bool:
    return _entry_path(autostart_dir).exists()


def enable(autostart_dir: Path | None = None) -> Path:
    """Create the app autostart entry. Returns the path written."""
    path = _entry_path(autostart_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    icon = str(_project_root() / "obsbot_logo.png")
    path.write_text(build_entry_text(_run_command(), icon))
    path.chmod(0o755)
    return path


def disable(autostart_dir: Path | None = None) -> None:
    """Remove the app autostart entry if present (no error if already gone)."""
    _entry_path(autostart_dir).unlink(missing_ok=True)


def set_enabled(enabled: bool, autostart_dir: Path | None = None) -> None:
    if enabled:
        enable(autostart_dir)
    else:
        disable(autostart_dir)


# --- Virtual-camera autostart -------------------------------------------

def is_vcam_enabled(autostart_dir: Path | None = None) -> bool:
    return _vcam_entry_path(autostart_dir).exists()


def enable_vcam(autostart_dir: Path | None = None) -> Path:
    """Create the virtual-camera autostart entry. Returns the path written."""
    path = _vcam_entry_path(autostart_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    icon = str(_project_root() / "obsbot_logo.png")
    path.write_text(build_entry_text(
        _vcam_run_command(), icon, name="OBSBOT Cámara Virtual"))
    path.chmod(0o755)
    return path


def disable_vcam(autostart_dir: Path | None = None) -> None:
    _vcam_entry_path(autostart_dir).unlink(missing_ok=True)


def set_vcam_enabled(enabled: bool, autostart_dir: Path | None = None) -> None:
    if enabled:
        enable_vcam(autostart_dir)
    else:
        disable_vcam(autostart_dir)
