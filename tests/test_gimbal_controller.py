from app.gimbal_controller import GimbalController, MAX_PITCH_SPEED, MAX_PAN_SPEED
from tests.fake_bridge import FakeDevice, ObsbotError


class FakeDeviceManager:
    def __init__(self, device):
        self.device = device
        self.last_status = {}


def test_start_disables_ai_and_starts_timer(qtbot):
    device = FakeDevice("SN1", "Tiny2")
    manager = FakeDeviceManager(device)
    manager.last_status = {"ai_mode": 1}
    controller = GimbalController(manager)

    controller.start()

    assert ("set_ai_enabled", False) in device.calls
    assert controller._timer.isActive()


def test_tick_sends_mapped_speed_only_when_changed():
    device = FakeDevice("SN1", "Tiny2")
    manager = FakeDeviceManager(device)
    controller = GimbalController(manager)

    controller.start()
    device.calls.clear()

    controller.update(1.0, -1.0)
    controller._on_tick()
    controller._on_tick()  # same value again, should not resend

    speed_calls = [c for c in device.calls if c[0] == "set_gimbal_speed"]
    assert speed_calls == [("set_gimbal_speed", MAX_PITCH_SPEED, MAX_PAN_SPEED)]


def test_stop_sends_stop_and_restores_ai_if_it_was_on():
    device = FakeDevice("SN1", "Tiny2")
    manager = FakeDeviceManager(device)
    manager.last_status = {"ai_mode": 1}
    controller = GimbalController(manager)

    controller.start()
    device.calls.clear()
    controller.stop()

    assert not controller._timer.isActive()
    assert device.calls == [("stop_gimbal",), ("set_ai_enabled", True)]


def test_stop_does_not_restore_ai_if_it_was_off():
    device = FakeDevice("SN1", "Tiny2")
    manager = FakeDeviceManager(device)
    manager.last_status = {"ai_mode": 0}
    controller = GimbalController(manager)

    controller.start()
    device.calls.clear()
    controller.stop()

    assert device.calls == [("stop_gimbal",)]


def test_tick_stops_itself_if_device_disconnects():
    device = FakeDevice("SN1", "Tiny2")
    manager = FakeDeviceManager(device)
    controller = GimbalController(manager)

    controller.start()
    manager.device = None
    controller._on_tick()

    assert not controller._timer.isActive()


def test_error_occurred_signal_emitted_on_device_error(qtbot):
    device = FakeDevice("SN1", "Tiny2")
    manager = FakeDeviceManager(device)
    controller = GimbalController(manager)

    # Monkeypatch set_gimbal_speed to raise ObsbotError
    def raise_error(*args, **kwargs):
        raise ObsbotError("Device communication failed")
    device.set_gimbal_speed = raise_error

    # Capture emitted signals
    emitted_errors = []
    controller.error_occurred.connect(lambda msg: emitted_errors.append(msg))

    controller.start()
    controller.update(1.0, -1.0)
    controller._on_tick()

    # Verify the signal was emitted with the error message
    assert emitted_errors == ["Device communication failed"]


def test_inversion_and_speed_scaling():
    device = FakeDevice("SN1", "Tiny2")
    manager = FakeDeviceManager(device)
    controller = GimbalController(manager)

    controller.start()
    device.calls.clear()

    # Normal tick: x=1.0, y=1.0 -> pitch = -40, pan = 60
    controller.update(1.0, 1.0)
    controller._on_tick()
    speed_calls = [c for c in device.calls if c[0] == "set_gimbal_speed"]
    assert speed_calls[-1] == ("set_gimbal_speed", -MAX_PITCH_SPEED, MAX_PAN_SPEED)

    # Invert pan and tilt
    controller.set_invert_pan(True)
    controller.set_invert_tilt(True)
    controller._last_sent = None
    controller._on_tick()
    speed_calls = [c for c in device.calls if c[0] == "set_gimbal_speed"]
    assert speed_calls[-1] == ("set_gimbal_speed", MAX_PITCH_SPEED, -MAX_PAN_SPEED)

    # Speed scale 50%
    controller.set_speed_scale(0.5)
    controller._last_sent = None
    controller._on_tick()
    speed_calls = [c for c in device.calls if c[0] == "set_gimbal_speed"]
    assert speed_calls[-1] == ("set_gimbal_speed", MAX_PITCH_SPEED * 0.5, -MAX_PAN_SPEED * 0.5)

    # Precision mode 25% factor
    controller.set_precision_mode(True)
    controller._last_sent = None
    controller._on_tick()
    speed_calls = [c for c in device.calls if c[0] == "set_gimbal_speed"]
    assert speed_calls[-1] == ("set_gimbal_speed", MAX_PITCH_SPEED * 0.5 * 0.25, -MAX_PAN_SPEED * 0.5 * 0.25)
