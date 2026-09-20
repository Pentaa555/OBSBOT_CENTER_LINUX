"""Read-only enumeration of the camera's real V4L2 capture modes.

This does NOT open the video stream, it only asks the driver which modes
it advertises (VIDIOC_ENUM_FMT / ENUM_FRAMESIZES / ENUM_FRAMEINTERVALS via
`v4l2-ctl --list-formats-ext`). That means it is safe to call even while
OBS (or anything else) currently holds the camera open: enumeration does
not require exclusive access the way streaming does.

The virtual-camera pipeline (see `virtual_camera.py`) is what actually
opens the stream and re-exposes a chosen mode to OBS; this module just
tells the UI which modes are worth offering.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field


@dataclass(frozen=True)
class VideoMode:
    """A single (format, resolution, fps) capture mode the camera supports.

    `fourcc` is the V4L2 pixel format string as reported by the driver,
    e.g. "MJPG", "YUYV", "H264".
    """

    fourcc: str
    width: int
    height: int
    fps: float

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"

    def __str__(self) -> str:
        return f"{self.resolution} @ {self.fps:g}fps ({self.fourcc})"


@dataclass
class FormatGroup:
    """All discrete (resolution, fps) modes for one pixel format."""

    fourcc: str
    description: str
    modes: list[VideoMode] = field(default_factory=list)


class V4l2NotAvailable(RuntimeError):
    """Raised when the `v4l2-ctl` tool is not installed on the system."""


# Lines look like:
#   [0]: 'MJPG' (Motion-JPEG, compressed)
#   Size: Discrete 1280x720
#   Interval: Discrete 0.017s (60.000 fps)
_FORMAT_RE = re.compile(r"\[\d+\]:\s*'(?P<fourcc>[^']+)'\s*\((?P<desc>.*)\)")
_SIZE_RE = re.compile(r"Size:\s*Discrete\s*(?P<w>\d+)x(?P<h>\d+)")
_INTERVAL_RE = re.compile(r"Interval:\s*Discrete\s*[\d.]+s\s*\((?P<fps>[\d.]+)\s*fps\)")


def _run_v4l2_ctl(device: str) -> str:
    if shutil.which("v4l2-ctl") is None:
        raise V4l2NotAvailable(
            "v4l2-ctl not found. Install it with: sudo apt install v4l-utils"
        )
    result = subprocess.run(
        ["v4l2-ctl", "-d", device, "--list-formats-ext"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"v4l2-ctl failed for {device}: {result.stderr.strip()}"
        )
    return result.stdout


def parse_formats(output: str) -> list[FormatGroup]:
    """Parse `v4l2-ctl --list-formats-ext` output into FormatGroups.

    Split out from the subprocess call so it can be unit-tested against
    captured fixture text without a camera attached.
    """
    groups: list[FormatGroup] = []
    current_group: FormatGroup | None = None
    current_size: tuple[int, int] | None = None

    for line in output.splitlines():
        fmt_match = _FORMAT_RE.search(line)
        if fmt_match:
            current_group = FormatGroup(
                fourcc=fmt_match.group("fourcc"),
                description=fmt_match.group("desc"),
            )
            groups.append(current_group)
            current_size = None
            continue

        size_match = _SIZE_RE.search(line)
        if size_match:
            current_size = (int(size_match.group("w")), int(size_match.group("h")))
            continue

        interval_match = _INTERVAL_RE.search(line)
        if interval_match and current_group is not None and current_size is not None:
            current_group.modes.append(
                VideoMode(
                    fourcc=current_group.fourcc,
                    width=current_size[0],
                    height=current_size[1],
                    fps=float(interval_match.group("fps")),
                )
            )

    return groups


def enumerate_modes(device: str = "/dev/video0") -> list[FormatGroup]:
    """Return the capture modes the camera at `device` advertises.

    Raises V4l2NotAvailable if the tool is missing, or RuntimeError if the
    device can't be queried.
    """
    return parse_formats(_run_v4l2_ctl(device))


def best_fps_for_resolution(
    groups: list[FormatGroup], width: int, height: int
) -> float:
    """Highest fps available at a resolution across all formats (0 if none)."""
    best = 0.0
    for group in groups:
        for mode in group.modes:
            if mode.width == width and mode.height == height:
                best = max(best, mode.fps)
    return best
