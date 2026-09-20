"""Static application resources (icons, themes) and helpers to load them.

Icons under ``images/`` are reused from OBSBOT Center (LGPL-3.0). See
``THIRD_PARTY_LICENSES.md`` at the repo root for attribution.
"""
from __future__ import annotations

import os

from PySide6.QtGui import QIcon, QPixmap

_RESOURCES_DIR = os.path.dirname(os.path.abspath(__file__))
_IMAGES_DIR = os.path.join(_RESOURCES_DIR, "images")
_THEMES_DIR = os.path.join(_RESOURCES_DIR, "themes")
_FONTS_DIR = os.path.join(_RESOURCES_DIR, "fonts")


def load_fonts() -> list[str]:
    """Register the bundled fonts with Qt's font database.

    Returns the list of font family names that were successfully loaded.
    Safe to call once at startup after a QApplication exists.
    """
    from PySide6.QtGui import QFontDatabase

    families: list[str] = []
    if not os.path.isdir(_FONTS_DIR):
        return families
    for name in sorted(os.listdir(_FONTS_DIR)):
        if not name.lower().endswith((".ttf", ".otf")):
            continue
        font_id = QFontDatabase.addApplicationFont(
            os.path.join(_FONTS_DIR, name))
        if font_id != -1:
            families.extend(QFontDatabase.applicationFontFamilies(font_id))
    return families


def load_stylesheet(name: str = "dark") -> str:
    """Return the contents of a QSS theme under ``themes/`` (empty if missing).

    ``name`` may be given with or without the ``.qss`` extension.
    """
    if not os.path.splitext(name)[1]:
        name = f"{name}.qss"
    path = os.path.join(_THEMES_DIR, name)
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def image_path(name: str) -> str:
    """Return the absolute path to an image resource.

    ``name`` may be given with or without the ``.png`` extension, e.g.
    ``image_path("gimbal_ball")`` or ``image_path("gimbal_ball.png")``.
    """
    if not os.path.splitext(name)[1]:
        name = f"{name}.png"
    return os.path.join(_IMAGES_DIR, name)


def icon(name: str) -> QIcon:
    """Load an image resource as a :class:`QIcon` (empty if it's missing)."""
    path = image_path(name)
    return QIcon(path) if os.path.exists(path) else QIcon()


def pixmap(name: str) -> QPixmap:
    """Load an image resource as a :class:`QPixmap` (null if it's missing)."""
    path = image_path(name)
    return QPixmap(path) if os.path.exists(path) else QPixmap()
