from app.single_instance import SingleInstance


def test_first_instance_not_already_running(qtbot):
    guard = SingleInstance(name="obsbot-test-single-1")
    try:
        assert guard.already_running() is False
    finally:
        pass


def test_second_instance_detects_running_and_activates(qtbot):
    from PySide6.QtWidgets import QApplication

    primary = SingleInstance(name="obsbot-test-single-2")
    activated = []
    primary.start_server(on_activate=lambda: activated.append(True))

    second = SingleInstance(name="obsbot-test-single-2")
    assert second.already_running() is True

    # Signalling should reach the primary's on_activate callback. Pump the
    # event loop so the server processes the incoming connection. Note that
    # already_running() also opens a connection, so one or more activations
    # may be recorded; we only assert that activation happened.
    assert second.signal_existing() is True
    for _ in range(50):
        QApplication.processEvents()
        if activated:
            break
    assert len(activated) >= 1


def test_signal_existing_false_when_no_server(qtbot):
    guard = SingleInstance(name="obsbot-test-single-3-nonexistent")
    assert guard.signal_existing() is False
