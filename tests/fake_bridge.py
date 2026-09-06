"""A fake stand-in for the compiled obsbot_bridge extension, used so the
Python app layer's tests can run without the real SDK or hardware."""
from __future__ import annotations


class ObsbotError(Exception):
    pass


class ProductType:
    Tiny2 = 2


class TrackMode:
    Standard = 0
    Headroom = 1
    Motion = 2


class FakeDevice:
    def __init__(self, sn: str, name: str):
        self.sn = sn
        self.name = name
        self.product_type = ProductType.Tiny2
        self.calls: list[tuple] = []
        self._status_callback = None
        self._zoom = 1.0
        self._presets: dict[int, dict] = {}
        self._next_preset_id = 1

    def set_status_callback(self, fn):
        self._status_callback = fn

    def push_status(self, data: dict) -> None:
        if self._status_callback is not None:
            self._status_callback(data)

    def set_gimbal_speed(self, pitch: float, pan: float) -> None:
        self.calls.append(("set_gimbal_speed", pitch, pan))

    def stop_gimbal(self) -> None:
        self.calls.append(("stop_gimbal",))

    def set_ai_enabled(self, enabled: bool) -> None:
        self.calls.append(("set_ai_enabled", enabled))

    def set_tracking_mode(self, mode) -> None:
        self.calls.append(("set_tracking_mode", mode))

    def get_gimbal_angle(self) -> dict:
        return {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}

    def set_zoom(self, zoom: float) -> None:
        self._zoom = zoom
        self.calls.append(("set_zoom", zoom))

    def get_zoom(self) -> float:
        return self._zoom

    def list_presets(self) -> list:
        return list(self._presets.values())

    def add_preset(self, name, pitch, yaw, roll, zoom) -> int:
        preset_id = self._next_preset_id
        self._next_preset_id += 1
        self._presets[preset_id] = {
            "id": preset_id, "name": name, "pitch": pitch,
            "yaw": yaw, "roll": roll, "zoom": zoom,
        }
        return preset_id

    def delete_preset(self, preset_id: int) -> None:
        self._presets.pop(preset_id, None)

    def goto_preset(self, preset_id: int) -> None:
        self.calls.append(("goto_preset", preset_id))

    def rename_preset(self, preset_id: int, name: str) -> None:
        if preset_id in self._presets:
            self._presets[preset_id]["name"] = name
        self.calls.append(("rename_preset", preset_id, name))


class FakeBridgeModule:
    """Mimics the module-level surface of obsbot_bridge."""

    def __init__(self):
        self.ObsbotError = ObsbotError
        self.ProductType = ProductType
        self.TrackMode = TrackMode
        self._devices: dict[str, FakeDevice] = {}
        self._changed_callback = None
        self.closed = False

    def add_device(self, sn: str, name: str) -> FakeDevice:
        """Create the device, but do NOT fire the connected signal yet —
        call connect_device() separately once any listeners (e.g. a widget
        constructed after this call) are ready. Splitting these two steps
        lets tests pre-populate a device (e.g. with presets) before the
        connected signal is observed."""
        device = FakeDevice(sn, name)
        self._devices[sn] = device
        return device

    def connect_device(self, sn: str) -> None:
        if self._changed_callback is not None:
            self._changed_callback(sn, True)

    def remove_device(self, sn: str) -> None:
        self._devices.pop(sn, None)
        if self._changed_callback is not None:
            self._changed_callback(sn, False)

    def list_devices(self):
        return [{"sn": d.sn, "name": d.name, "product_type": d.product_type}
                for d in self._devices.values()]

    def get_device_by_sn(self, sn: str):
        return self._devices.get(sn)

    def set_device_changed_callback(self, fn) -> None:
        self._changed_callback = fn

    def close(self) -> None:
        self.closed = True

    def reset(self) -> None:
        """Called by the per-test fixture (tests/conftest.py) to clear state
        between tests. This clears the SAME instance rather than replacing
        it in sys.modules, because app modules do `import obsbot_bridge as
        bridge` at module import time — swapping sys.modules['obsbot_bridge']
        after that first import would not change what their `bridge` name
        points to."""
        self._devices.clear()
        self._changed_callback = None
        self.closed = False
