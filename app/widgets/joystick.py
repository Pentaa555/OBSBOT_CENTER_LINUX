from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

DEADZONE = 0.08
HANDLE_RADIUS = 15
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

        # Outer ring (dark disc with a subtle rim), matching OBSBOT Center.
        painter.setPen(QPen(QColor(58, 58, 58), 1))
        painter.setBrush(QBrush(QColor(38, 38, 38)))
        painter.drawEllipse(center, radius, radius)

        # Inner disc to give the ring some depth. A high ratio keeps the
        # ring/border thin.
        inner_radius = radius * 0.78
        painter.setPen(QPen(QColor(70, 70, 70), 1))
        painter.setBrush(QBrush(QColor(46, 46, 46)))
        painter.drawEllipse(center, inner_radius, inner_radius)

        # Four directional arrows in the ring band.
        self._draw_arrows(painter, center, radius, inner_radius)

        # Handle (white ball), offset by the current normalized position.
        handle_pos = QPointF(center.x() + self._handle.x() * radius,
                             center.y() + self._handle.y() * radius)
        painter.setPen(QPen(QColor(210, 210, 210), 1))
        painter.setBrush(QBrush(QColor(245, 245, 245)))
        painter.drawEllipse(handle_pos, HANDLE_RADIUS, HANDLE_RADIUS)

    def _draw_arrows(self, painter, center, radius, inner_radius) -> None:
        band = (radius + inner_radius) / 2
        size = max(4.0, radius * 0.05)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(150, 150, 150)))
        cx, cy = center.x(), center.y()
        # (tip, then two base corners) for up/down/left/right.
        arrows = [
            [QPointF(cx, cy - band - size), QPointF(cx - size, cy - band + size),
             QPointF(cx + size, cy - band + size)],  # up
            [QPointF(cx, cy + band + size), QPointF(cx - size, cy + band - size),
             QPointF(cx + size, cy + band - size)],  # down
            [QPointF(cx - band - size, cy), QPointF(cx - band + size, cy - size),
             QPointF(cx - band + size, cy + size)],  # left
            [QPointF(cx + band + size, cy), QPointF(cx + band - size, cy - size),
             QPointF(cx + band - size, cy + size)],  # right
        ]
        for pts in arrows:
            painter.drawPolygon(QPolygonF(pts))
