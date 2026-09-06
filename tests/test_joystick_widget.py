from PySide6.QtCore import QPoint, Qt

from app.widgets.joystick import JoystickWidget


def _center(widget):
    return widget.rect().center()


def test_press_at_center_emits_zero(qtbot):
    widget = JoystickWidget()
    qtbot.addWidget(widget)
    widget.resize(200, 200)
    received = []
    widget.moved.connect(lambda x, y: received.append((x, y)))

    qtbot.mousePress(widget, Qt.LeftButton, pos=_center(widget))

    assert received[-1] == (0.0, 0.0)


def test_drag_right_emits_positive_x_near_zero_y(qtbot):
    widget = JoystickWidget()
    qtbot.addWidget(widget)
    widget.resize(200, 200)
    received = []
    widget.moved.connect(lambda x, y: received.append((x, y)))
    center = _center(widget)
    edge = QPoint(center.x() + 80, center.y())

    qtbot.mousePress(widget, Qt.LeftButton, pos=center)
    qtbot.mouseMove(widget, pos=edge)

    x, y = received[-1]
    assert x > 0.9
    assert abs(y) < 0.05


def test_release_resets_to_center_and_emits_zero(qtbot):
    widget = JoystickWidget()
    qtbot.addWidget(widget)
    widget.resize(200, 200)
    received = []
    widget.moved.connect(lambda x, y: received.append((x, y)))
    released = []
    widget.released.connect(lambda: released.append(True))
    center = _center(widget)
    edge = QPoint(center.x() + 80, center.y())

    qtbot.mousePress(widget, Qt.LeftButton, pos=center)
    qtbot.mouseMove(widget, pos=edge)
    qtbot.mouseRelease(widget, Qt.LeftButton, pos=edge)

    assert received[-1] == (0.0, 0.0)
    assert released == [True]


def test_release_without_press_does_nothing(qtbot):
    widget = JoystickWidget()
    qtbot.addWidget(widget)
    widget.resize(200, 200)
    received = []
    widget.moved.connect(lambda x, y: received.append((x, y)))
    released = []
    widget.released.connect(lambda: released.append(True))

    qtbot.mouseRelease(widget, Qt.LeftButton, pos=_center(widget))

    assert received == []
    assert released == []


def test_small_movement_inside_deadzone_emits_zero(qtbot):
    widget = JoystickWidget()
    qtbot.addWidget(widget)
    widget.resize(200, 200)
    received = []
    widget.moved.connect(lambda x, y: received.append((x, y)))
    center = _center(widget)
    tiny_offset = QPoint(center.x() + 2, center.y())

    qtbot.mousePress(widget, Qt.LeftButton, pos=center)
    qtbot.mouseMove(widget, pos=tiny_offset)

    assert received[-1] == (0.0, 0.0)
