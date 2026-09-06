import sys
import time

sys.path.insert(0, "build")
import obsbot_bridge as bridge  # noqa: E402


def on_changed(sn: str, connected: bool) -> None:
    print(f"device changed: sn={sn} connected={connected}")


bridge.set_device_changed_callback(on_changed)

print("Devices found at startup:")
for info in bridge.list_devices():
    print(info)
    device = bridge.get_device_by_sn(info["sn"])
    print("  ->", device.sn, device.name, device.product_type)

print("Waiting 10s for plug/unplug events (Ctrl+C to stop)...")
time.sleep(10)

for info in bridge.list_devices():
    device = bridge.get_device_by_sn(info["sn"])
    device.set_status_callback(lambda data: print("status:", data))

bridge.close()
