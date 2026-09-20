from __future__ import annotations

import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow

_LOGO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "obsbot_logo.png",
)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("OBSBOT Control")
    app.setApplicationDisplayName("OBSBOT Control")
    app.setOrganizationName("OBSBOT")
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
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
