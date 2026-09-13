from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

DEADZONE = 0.08
HANDLE_RADIUS = 14
EDGE_MARGIN = 12


class JoystickWidget(QWidget):
    moved = Signal(float, float)
    pressed = Signal()
    released = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(160, 160)
        self._handle = QPointF(0.0, 0.0)
        self._dragging = False

    def _radius(self) -> float:
        return min(self.width(), self.height()) / 2 - EDGE_MARGIN

    def _center(self) -> QPointF:
        center = self.rect().center()
        return QPointF(center.x(), center.y())

    def _is_inside_circle(self, pos: QPointF) -> bool:
        center = self._center()
        dx = pos.x() - center.x()
        dy = pos.y() - center.y()
        return math.hypot(dx, dy) <= self._radius()

    def mousePressEvent(self, event):
        if not self._is_inside_circle(event.position()):
            event.ignore()
            return
        self._dragging = True
        self._update_from_pos(event.position())
        self.pressed.emit()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._update_from_pos(event.position())

    def mouseReleaseEvent(self, event):
        # Qt can deliver a release to a widget that never got the matching
        # press; ignore those so they don't re-trigger the stop/AI-restore
        # path from stale state.
        if not self._dragging:
            return
        self._dragging = False
        self._handle = QPointF(0.0, 0.0)
        self.update()
        self.released.emit()
        self.moved.emit(0.0, 0.0)

    def _update_from_pos(self, pos: QPointF) -> None:
        center = self._center()
        radius = self._radius()
        dx = pos.x() - center.x()
        dy = pos.y() - center.y()
        dist = math.hypot(dx, dy)
        if dist > radius:
            dx = dx * radius / dist
            dy = dy * radius / dist
        nx = dx / radius
        ny = dy / radius
        if math.hypot(nx, ny) < DEADZONE:
            nx, ny = 0.0, 0.0
        self._handle = QPointF(nx, ny)
        self.update()
        self.moved.emit(nx, ny)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        center = self._center()
        radius = self._radius()
        painter.setPen(QPen(QColor(80, 80, 80), 2))
        painter.setBrush(QBrush(QColor(30, 30, 30)))
        painter.drawEllipse(center, radius, radius)
        handle_pos = QPointF(center.x() + self._handle.x() * radius,
                              center.y() + self._handle.y() * radius)
        painter.setPen(QPen(QColor(200, 30, 30), 2))
        painter.setBrush(QBrush(QColor(220, 40, 40)))
        painter.drawEllipse(handle_pos, HANDLE_RADIUS, HANDLE_RADIUS)
