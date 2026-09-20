"""Manage launch-on-login via a freedesktop XDG autostart entry.

The XDG Autostart spec is honoured by GNOME, KDE, XFCE, Cinnamon, etc.: any
`.desktop` file placed in ~/.config/autostart/ is executed when the user
logs in. We reuse the same run.sh the app is normally launched from, so the
autostart entry stays in sync with how the app actually runs (venv,
PYTHONPATH, bridge build).

This module only reads/writes that one file; it does not touch anything
system-wide and requires no privileges. All paths are overridable so it can
be unit-tested against a temp directory.
"""
from __future__ import annotations

import os
from pathlib import Path

_ENTRY_NAME = "obsbot-control-autostart.desktop"


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


def _run_command() -> str:
    """The Exec= line: the run.sh wrapper if present, else python -m app.main."""
    run_sh = _project_root() / "run.sh"
    if run_sh.exists():
        return str(run_sh)
    return f"{os.sys.executable} -m app.main"


def build_entry_text(exec_command: str, icon_path: str) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        "Name=OBSBOT Control\n"
        "Comment=Control de cámara OBSBOT Tiny para Linux\n"
        f"Exec={exec_command}\n"
        f"Icon={icon_path}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def is_enabled(autostart_dir: Path | None = None) -> bool:
    return _entry_path(autostart_dir).exists()


def enable(autostart_dir: Path | None = None) -> Path:
    """Create the autostart entry. Returns the path written."""
    path = _entry_path(autostart_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    icon = str(_project_root() / "obsbot_logo.png")
    path.write_text(build_entry_text(_run_command(), icon))
    path.chmod(0o755)
    return path


def disable(autostart_dir: Path | None = None) -> None:
    """Remove the autostart entry if present (no error if already gone)."""
    _entry_path(autostart_dir).unlink(missing_ok=True)


def set_enabled(enabled: bool, autostart_dir: Path | None = None) -> None:
    if enabled:
        enable(autostart_dir)
    else:
        disable(autostart_dir)
