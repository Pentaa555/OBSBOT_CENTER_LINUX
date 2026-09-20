from __future__ import annotations

import os
import sys

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow
from app.single_instance import SingleInstance
from app.widgets.system_panel import SystemPanel
from app import resources

_LOGO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "obsbot_logo.png",
)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("OBSBOT Control")
    app.setApplicationDisplayName("OBSBOT Control")
    app.setOrganizationName("OBSBOT")

    # App-wide dark theme (OBSBOT Center look).
    stylesheet = resources.load_stylesheet("dark")
    if stylesheet:
        app.setStyleSheet(stylesheet)

    # Register bundled fonts. Inter is the app's UI typeface:
    #   - Inter (Regular) as the base font for secondary/body text.
    #   - Inter Medium / SemiBold for buttons and titles (applied via QSS).
    families = resources.load_fonts()
    base_family = "Inter" if "Inter" in families else next(iter(families), None)
    if base_family:
        base_font = QFont(base_family)
        base_font.setPointSize(10)
        app.setFont(base_font)

    # Single-instance guard: if the app is already running (e.g. hidden in
    # the tray), just tell that instance to show itself and exit, instead of
    # stacking another background process. Stacked instances were silently
    # overwriting each other's saved settings.
    guard = SingleInstance()
    if guard.already_running():
        guard.signal_existing()
        return 0

    # With the system-tray feature the window can be "closed" (hidden) while
    # the app keeps running in the background, so Qt must not quit just
    # because no window is visible. Real quit goes through the tray's
    # "Salir" action or a SIGTERM.
    app.setQuitOnLastWindowClosed(False)
    # Debe coincidir con StartupWMClass en obsbot-control.desktop para que
    # el escritorio asocie la ventana con el lanzador (y muestre su icono).
    app.setDesktopFileName("obsbot-control")
    if os.path.exists(_LOGO_PATH):
        app.setWindowIcon(QIcon(_LOGO_PATH))
    window = MainWindow()
    app.aboutToQuit.connect(window.shutdown)

    # Now that we're the primary instance, listen for future launches asking
    # us to surface the window.
    guard.start_server(on_activate=window.show_from_tray)

    # When launched at login (--tray) and the user wants tray behaviour,
    # start hidden in the tray instead of popping a window in their face.
    started_by_autostart = "--tray" in sys.argv[1:]
    settings = QSettings("OBSBOT", "OBSBOT Control")
    wants_tray = settings.value(
        SystemPanel.MINIMIZE_TO_TRAY_KEY, True, type=bool)
    if started_by_autostart and wants_tray and window.tray_icon is not None:
        # Stay in the tray; the icon is already shown by MainWindow.
        pass
    else:
        window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
