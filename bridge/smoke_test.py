import sys

sys.path.insert(0, "build")
import obsbot_bridge as bridge  # noqa: E402

print("Devices found:")
for info in bridge.list_devices():
    print(info)
