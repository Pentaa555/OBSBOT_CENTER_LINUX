"""Single-instance guard using a Qt local socket.

Without this, closing the window (which only hides it to the tray, since
quitOnLastWindowClosed is False) and relaunching would spawn a *second*
background process. Repeated over a session that produced many stacked
instances, each with its own QSettings, silently overwriting each other's
saved options on exit — the root cause of "my settings don't stick".

Usage:
    guard = SingleInstance()
    if guard.already_running():
        guard.signal_existing()   # ask the running one to show itself
        return 0                  # and exit this redundant process
    guard.start_server(on_activate=window.show_from_tray)
    ...keep guard alive for the process lifetime...

The socket name is per-user (includes the uid) so two different users on
the same machine don't collide.
"""
from __future__ import annotations

import os

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket

_ACTIVATE_MSG = b"activate"


def _socket_name() -> str:
    return f"obsbot-control-{os.getuid()}"


class SingleInstance(QObject):
    def __init__(self, name: str | None = None, parent=None):
        super().__init__(parent)
        self._name = name or _socket_name()
        self._server: QLocalServer | None = None
        self._on_activate = None

    def already_running(self) -> bool:
        """True if another instance owns the socket.

        Tries to connect as a client; a successful connection means a
        primary instance is already listening.
        """
        socket = QLocalSocket()
        socket.connectToServer(self._name)
        connected = socket.waitForConnected(200)
        if connected:
            socket.disconnectFromServer()
        return connected

    def signal_existing(self) -> bool:
        """Tell the already-running instance to surface its window."""
        socket = QLocalSocket()
        socket.connectToServer(self._name)
        if not socket.waitForConnected(200):
            return False
        socket.write(_ACTIVATE_MSG)
        socket.flush()
        socket.waitForBytesWritten(200)
        socket.disconnectFromServer()
        return True

    def start_server(self, on_activate=None) -> None:
        """Become the primary instance: listen for activation requests.

        `on_activate` is called (no args) whenever another launch asks this
        instance to show itself.
        """
        self._on_activate = on_activate
        # Remove any stale socket left by a crashed previous instance.
        QLocalServer.removeServer(self._name)
        self._server = QLocalServer(self)
        self._server.listen(self._name)
        self._server.newConnection.connect(self._handle_connection)

    def _handle_connection(self) -> None:
        conn = self._server.nextPendingConnection()
        if conn is None:
            return
        # Any incoming connection means "please activate"; we don't need the
        # payload. Activating right away avoids blocking the event loop on a
        # synchronous read, which delayed or missed the callback.
        if self._on_activate is not None:
            self._on_activate()
        conn.disconnectFromServer()
