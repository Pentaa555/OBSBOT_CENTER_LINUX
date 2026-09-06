# OBSBOT Tiny2 Joystick Control App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Linux desktop app (Python/PySide6 + a thin C++ pybind11 bridge) that controls an OBSBOT Tiny2-family camera's gimbal via a true analog on-screen joystick, plus zoom, AI tracking mode, and gimbal presets.

**Architecture:** A C++ pybind11 extension module (`bridge/obsbot_bridge.cpp`) wraps the ~10 `libdev` SDK calls we need and converts the raw `CameraStatus` union to plain Python dicts. A Python/PySide6 app (`app/`) does all device management, throttling, and UI on top of that thin bridge — no business logic lives in C++.

**Tech Stack:** C++14, CMake, pybind11, Python 3, PySide6, pytest, pytest-qt.

**Spec:** `docs/superpowers/specs/2026-09-06-obsbot-tiny2-joystick-app-design.md`

## Global Constraints

- Target platform: Debian/Ubuntu Linux (apt-based). All shell commands in this
  plan assume `apt`, `bash`, and a Debian/Ubuntu-family filesystem layout.
- **This plan was authored on a Windows machine with no WSL distro
  installed.** Tasks 2–8 and 13 involve compiling against the vendored
  Linux-only `libdev.so` and/or exercising it against a physical camera —
  they **cannot be executed or verified from a Windows authoring session**
  and must be run on an actual Debian/Ubuntu machine (or WSL with a
  Debian/Ubuntu distro) with the OBSBOT Tiny2 plugged in. Tasks 9–12 are
  pure Python/Qt logic with no SDK dependency and can be developed and
  tested on any OS, including Windows.
- Gimbal joystick speed caps (from the design spec): max pitch speed 40
  (SDK range is −90..90), max pan speed 60 (SDK range is −180..180). These
  are deliberately conservative starting values — see spec §9.
- Joystick send rate: 20 Hz (50 ms timer tick).
- Zoom absolute range from the SDK is 1.0–2.0; the live status field
  `zoom_ratio` reports 0–100. These are two different scales and must not be
  conflated (see Task 6 and Task 11).
- Single-camera app: the first Tiny2-family device seen is the only one
  controlled; others are ignored, not an error (spec §2/§7).
- The vendored SDK travels with the repo as `libdev_v1.0.2.tar.gz` (tracked
  in git); the extracted `libdev_v1.0.2/` directory is gitignored and must
  be (re-)extracted locally with `tar -xzf libdev_v1.0.2.tar.gz` before
  building the bridge (Task 2 onward) — extracting on Windows turns the
  SDK's `.so` symlinks into full copies, so always extract on the actual
  Debian/Ubuntu build machine, not by copying a Windows-extracted copy.

---

## Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `app/__init__.py`
- Create: `app/widgets/__init__.py`
- Create: `README.md`

**Interfaces:**
- Produces: the directory layout every later task writes into.

- [ ] **Step 1: Create `requirements.txt`**

```
PySide6>=6.6
pybind11>=2.11
pytest>=7.4
pytest-qt>=4.2
```

- [ ] **Step 2: Create `.gitignore`**

```
__pycache__/
*.pyc
.venv/
bridge/build/
*.so
.pytest_cache/
```

- [ ] **Step 3: Create empty package markers**

`app/__init__.py`:
```python
```

`app/widgets/__init__.py`:
```python
```

- [ ] **Step 4: Create a README stub (filled in fully in Task 14)**

`README.md`:
```markdown
# OBSBOT Tiny2 Joystick Control

See `docs/superpowers/specs/2026-09-06-obsbot-tiny2-joystick-app-design.md`
for the design. Build/run instructions are added in a later step of this
project (Task 14).
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .gitignore app/__init__.py app/widgets/__init__.py README.md
git commit -m "chore: scaffold project layout"
```

---

## Task 2: Bridge scaffolding — CMake project + device discovery

**Files:**
- Create: `bridge/CMakeLists.txt`
- Create: `bridge/obsbot_bridge.cpp`
- Create: `bridge/smoke_test.py`

**Interfaces:**
- Consumes: `libdev_v1.0.2/include/dev/devs.hpp`, `libdev_v1.0.2/include/dev/dev.hpp`, `libdev_v1.0.2/linux/{x86_64,arm64}-release/libdev.so`.
- Produces: Python-importable module `obsbot_bridge` with `obsbot_bridge.list_devices() -> list[dict]` (each dict has `sn: str`, `name: str`, `product_type: int`).

> **Environment note:** every "Run" step below must be executed on a
> Debian/Ubuntu Linux machine with `build-essential`, `cmake`, `python3-dev`,
> and the `pybind11`/`pytest` packages from `requirements.txt` installed
> (see Task 14 for the full one-time setup). It cannot be run from this
> Windows authoring session.

- [ ] **Step 1: Write the CMake project**

`bridge/CMakeLists.txt`:
```cmake
cmake_minimum_required(VERSION 3.15)
project(obsbot_bridge)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT DEFINED SDK_ROOT)
    set(SDK_ROOT ${CMAKE_SOURCE_DIR}/../libdev_v1.0.2)
endif()

if(CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|AMD64")
    set(SDK_LINK_PATH ${SDK_ROOT}/linux/x86_64-release)
elseif(CMAKE_SYSTEM_PROCESSOR MATCHES "arm64|aarch64")
    set(SDK_LINK_PATH ${SDK_ROOT}/linux/arm64-release)
else()
    message(FATAL_ERROR "Unsupported architecture: ${CMAKE_SYSTEM_PROCESSOR}")
endif()

find_package(pybind11 REQUIRED)

pybind11_add_module(obsbot_bridge obsbot_bridge.cpp)

target_include_directories(obsbot_bridge PRIVATE ${SDK_ROOT}/include)
target_link_directories(obsbot_bridge PRIVATE ${SDK_LINK_PATH})
target_link_libraries(obsbot_bridge PRIVATE dev)

set_target_properties(obsbot_bridge PROPERTIES
    BUILD_RPATH "${SDK_LINK_PATH}"
    INSTALL_RPATH "${SDK_LINK_PATH}"
)
```

- [ ] **Step 2: Write the bridge module with only device discovery**

`bridge/obsbot_bridge.cpp`:
```cpp
#include <pybind11/pybind11.h>
#include <pybind11/functional.h>
#include <pybind11/stl.h>

#include <dev/devs.hpp>
#include <dev/dev.hpp>

namespace py = pybind11;

PYBIND11_MODULE(obsbot_bridge, m)
{
	m.doc() = "Thin pybind11 bridge over the OBSBOT libdev SDK";

	py::enum_<ObsbotProductType>(m, "ProductType")
		.value("Tiny", ObsbotProdTiny)
		.value("Tiny4k", ObsbotProdTiny4k)
		.value("Tiny2", ObsbotProdTiny2)
		.value("Tiny2Lite", ObsbotProdTiny2Lite)
		.value("TinySE", ObsbotProdTinySE)
		.export_values();

	m.def("list_devices", []() {
		py::list out;
		for (auto &dev : Devices::get().getDevList()) {
			py::dict item;
			item["sn"] = dev->devSn();
			item["name"] = dev->devName();
			item["product_type"] = dev->productType();
			out.append(item);
		}
		return out;
	});
}
```

- [ ] **Step 3: Write the smoke test script**

`bridge/smoke_test.py`:
```python
import sys

sys.path.insert(0, "build")
import obsbot_bridge as bridge  # noqa: E402

print("Devices found:")
for info in bridge.list_devices():
    print(info)
```

- [ ] **Step 4: Build the module (run on Debian/Ubuntu Linux)**

```bash
cmake -S bridge -B bridge/build -Dpybind11_DIR="$(python3 -m pybind11 --cmakedir)"
cmake --build bridge/build -j"$(nproc)"
```

Expected: `bridge/build/obsbot_bridge*.so` is produced with no compile errors.

- [ ] **Step 5: Run the smoke test (run on Debian/Ubuntu Linux, camera plugged in)**

```bash
cd bridge && python3 smoke_test.py
```

Expected: prints `Devices found:` followed by one dict per connected camera
(or an empty list if none is plugged in — that's fine, it means discovery
ran without crashing).

- [ ] **Step 6: Commit**

```bash
git add bridge/CMakeLists.txt bridge/obsbot_bridge.cpp bridge/smoke_test.py
git commit -m "feat(bridge): add device discovery via pybind11"
```

---

## Task 3: Bridge — connect/disconnect callback, get-by-sn, Device identity

**Files:**
- Modify: `bridge/obsbot_bridge.cpp`
- Modify: `bridge/smoke_test.py`

**Interfaces:**
- Consumes: `list_devices()` from Task 2.
- Produces: `obsbot_bridge.Device` class with read-only properties `sn: str`,
  `name: str`, `product_type: ProductType`; module functions
  `get_device_by_sn(sn: str) -> Device | None`,
  `set_device_changed_callback(fn: Callable[[str, bool], None]) -> None`,
  `close() -> None`.

- [ ] **Step 1: Add the `Device` class and connection callback**

Add to `bridge/obsbot_bridge.cpp`, inside `PYBIND11_MODULE`, before the
existing `list_devices` binding:

```cpp
	py::class_<Device, std::shared_ptr<Device>>(m, "Device")
		.def_property_readonly("sn", &Device::devSn)
		.def_property_readonly("name", [](Device &d) { return d.devName(); })
		.def_property_readonly("product_type", &Device::productType);

	m.def("get_device_by_sn", [](const std::string &sn) {
		return Devices::get().getDevBySn(sn);
	});

	m.def("set_device_changed_callback", [](py::function callback) {
		static py::function stored_callback;
		stored_callback = std::move(callback);
		Devices::get().setDevChangedCallback(
			[](std::string sn, bool connected, void *) {
				py::gil_scoped_acquire acquire;
				try {
					stored_callback(sn, connected);
				} catch (const std::exception &e) {
					std::cerr << "device changed callback error: "
						  << e.what() << std::endl;
				}
			},
			nullptr);
	});

	m.def("close", []() { Devices::get().close(); });
```

Add `#include <iostream>` to the top of the file (needed for `std::cerr`).

- [ ] **Step 2: Extend the smoke test to exercise the new bindings**

Replace the body of `bridge/smoke_test.py`:
```python
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
bridge.close()
```

- [ ] **Step 3: Rebuild and run (run on Debian/Ubuntu Linux)**

```bash
cmake --build bridge/build -j"$(nproc)"
cd bridge && python3 smoke_test.py
```

Expected: prints device info as before, plus resolves each device via
`get_device_by_sn` and prints its `sn`/`name`/`product_type`. If you unplug
and replug the camera during the 10s wait, a `device changed:` line prints
for each event.

- [ ] **Step 4: Commit**

```bash
git add bridge/obsbot_bridge.cpp bridge/smoke_test.py
git commit -m "feat(bridge): add device identity, get-by-sn, connect callback, close"
```

---

## Task 4: Bridge — live status callback

**Files:**
- Modify: `bridge/obsbot_bridge.cpp`
- Modify: `bridge/smoke_test.py`

**Interfaces:**
- Consumes: `Device` class from Task 3.
- Produces: `Device.set_status_callback(fn: Callable[[dict], None]) -> None`.
  The dict passed to `fn` has keys `zoom_ratio: int` (0-100),
  `ai_mode: int`, `dev_status: int`, `vertical: int`, `hdr: int`.
  Also produces the `ObsbotError` Python exception type, raised by every
  mutating SDK call added from this task onward when the SDK returns a
  non-`RM_RET_OK` code.

- [ ] **Step 1: Add the error helper and status conversion**

Add near the top of `bridge/obsbot_bridge.cpp`, after the includes and
`namespace py = pybind11;` line:

```cpp
#include <stdexcept>
#include <string>

struct ObsbotError : public std::runtime_error {
	using std::runtime_error::runtime_error;
};

static void check_ok(int32_t ret, const char *what)
{
	if (ret != RM_RET_OK) {
		throw ObsbotError(std::string(what) + " failed with code " +
				   std::to_string(ret));
	}
}

static py::dict status_to_dict(const Device::CameraStatus &status)
{
	py::dict d;
	d["zoom_ratio"] = status.tiny.zoom_ratio;
	d["ai_mode"] = status.tiny.ai_mode;
	d["dev_status"] = status.tiny.dev_status;
	d["vertical"] = status.tiny.vertical;
	d["hdr"] = status.tiny.hdr;
	return d;
}
```

- [ ] **Step 2: Register the exception type and the status callback method**

Add right after `py::class_<Device, ...>` is opened in `PYBIND11_MODULE`
(before its closing `;`), i.e. chain another `.def(...)` onto the existing
`py::class_<Device, std::shared_ptr<Device>>(m, "Device")` declaration:

```cpp
		.def("set_status_callback", [](Device &d, py::function callback) {
			auto shared_cb = std::make_shared<py::function>(std::move(callback));
			d.setDevStatusCallbackFunc(
				[shared_cb](void *, const void *data) {
					const auto *status =
						static_cast<const Device::CameraStatus *>(data);
					py::gil_scoped_acquire acquire;
					try {
						(*shared_cb)(status_to_dict(*status));
					} catch (const std::exception &e) {
						std::cerr << "status callback error: "
							  << e.what() << std::endl;
					}
				},
				nullptr);
			d.enableDevStatusCallback(true);
		});
```

And, at the very start of `PYBIND11_MODULE` body (before the `ProductType`
enum), register the exception:

```cpp
	py::register_exception<ObsbotError>(m, "ObsbotError");
```

- [ ] **Step 3: Exercise it from the smoke test**

Add before `bridge.close()` in `bridge/smoke_test.py`:
```python
for info in bridge.list_devices():
    device = bridge.get_device_by_sn(info["sn"])
    device.set_status_callback(lambda data: print("status:", data))
```

- [ ] **Step 4: Rebuild and run (run on Debian/Ubuntu Linux, camera plugged in)**

```bash
cmake --build bridge/build -j"$(nproc)"
cd bridge && python3 smoke_test.py
```

Expected: within a few seconds, `status: {...}` lines print with the five
keys above.

- [ ] **Step 5: Commit**

```bash
git add bridge/obsbot_bridge.cpp bridge/smoke_test.py
git commit -m "feat(bridge): add ObsbotError and live status callback"
```

---

## Task 5: Bridge — gimbal control

**Files:**
- Modify: `bridge/obsbot_bridge.cpp`

**Interfaces:**
- Consumes: `check_ok` helper from Task 4.
- Produces on `Device`: `set_gimbal_speed(pitch: float, pan: float) -> None`,
  `stop_gimbal() -> None`, `set_ai_enabled(enabled: bool) -> None`,
  `set_tracking_mode(mode: TrackMode) -> None`,
  `get_gimbal_angle() -> dict` (keys `pitch`, `yaw`, `roll`, all `float`).
  Also produces the `TrackMode` enum (`TrackMode.Standard`,
  `TrackMode.Headroom`, `TrackMode.Motion`).

- [ ] **Step 1: Add the `TrackMode` enum**

Add next to the existing `ProductType` enum in `PYBIND11_MODULE`:
```cpp
	py::enum_<Device::AiVerticalTrackType>(m, "TrackMode")
		.value("Standard", Device::AiVTrackStandard)
		.value("Headroom", Device::AiVTrackHeadroom)
		.value("Motion", Device::AiVTrackMotion)
		.export_values();
```

- [ ] **Step 2: Add the gimbal control methods**

Chain onto the `Device` class definition (after `set_status_callback`):
```cpp
		.def("set_gimbal_speed", [](Device &d, double pitch, double pan) {
			check_ok(d.aiSetGimbalSpeedCtrlR(pitch, pan),
				 "set_gimbal_speed");
		})
		.def("stop_gimbal", [](Device &d) {
			check_ok(d.aiSetGimbalStop(), "stop_gimbal");
		})
		.def("set_ai_enabled", [](Device &d, bool enabled) {
			check_ok(d.aiSetEnabledR(enabled), "set_ai_enabled");
		})
		.def("set_tracking_mode", [](Device &d,
					      Device::AiVerticalTrackType mode) {
			check_ok(d.aiSetTrackingModeR(mode), "set_tracking_mode");
		})
		.def("get_gimbal_angle", [](Device &d) {
			Device::AiGimbalStateInfo info{};
			check_ok(d.aiGetGimbalStateR(&info), "get_gimbal_angle");
			py::dict out;
			out["pitch"] = info.pitch_euler;
			out["yaw"] = info.yaw_euler;
			out["roll"] = info.roll_euler;
			return out;
		});
```

- [ ] **Step 3: Rebuild (run on Debian/Ubuntu Linux)**

```bash
cmake --build bridge/build -j"$(nproc)"
```

Expected: no compile errors.

- [ ] **Step 4: Manually exercise from a Python shell (run on Debian/Ubuntu Linux, camera plugged in)**

```bash
cd bridge
PYTHONPATH=build python3 -c "
import obsbot_bridge as bridge
devs = bridge.list_devices()
assert devs, 'no camera found'
d = bridge.get_device_by_sn(devs[0]['sn'])
d.set_ai_enabled(False)
d.set_gimbal_speed(0, 30)
import time; time.sleep(1)
d.stop_gimbal()
d.set_ai_enabled(True)
print('gimbal angle:', d.get_gimbal_angle())
"
```

Expected: the camera pans for ~1 second then stops; `gimbal angle:` prints
a dict with `pitch`/`yaw`/`roll` floats.

- [ ] **Step 5: Commit**

```bash
git add bridge/obsbot_bridge.cpp
git commit -m "feat(bridge): add gimbal speed control, AI enable, tracking mode"
```

---

## Task 6: Bridge — zoom control

**Files:**
- Modify: `bridge/obsbot_bridge.cpp`

**Interfaces:**
- Consumes: `check_ok` helper from Task 4.
- Produces on `Device`: `set_zoom(zoom: float) -> None` (accepts the SDK's
  native 1.0–2.0 absolute range), `get_zoom() -> float` (same range).

> Reminder (Global Constraints): this 1.0–2.0 scale is **not** the same as
> the `zoom_ratio` field (0–100) delivered by the status callback added in
> Task 4. Task 11's `StatusPanel` is responsible for converting between the
> two; this bridge layer stays a 1:1 mirror of the SDK's own units.

- [ ] **Step 1: Add the zoom methods**

Chain onto the `Device` class definition:
```cpp
		.def("set_zoom", [](Device &d, float zoom) {
			check_ok(d.cameraSetZoomAbsoluteR(zoom), "set_zoom");
		})
		.def("get_zoom", [](Device &d) {
			float zoom = 0.f;
			check_ok(d.cameraGetZoomAbsoluteR(zoom), "get_zoom");
			return zoom;
		});
```

- [ ] **Step 2: Rebuild (run on Debian/Ubuntu Linux)**

```bash
cmake --build bridge/build -j"$(nproc)"
```

Expected: no compile errors.

- [ ] **Step 3: Manually exercise (run on Debian/Ubuntu Linux, camera plugged in)**

```bash
cd bridge
PYTHONPATH=build python3 -c "
import obsbot_bridge as bridge
d = bridge.get_device_by_sn(bridge.list_devices()[0]['sn'])
d.set_zoom(1.5)
print('zoom:', d.get_zoom())
"
```

Expected: the camera visibly zooms in; `zoom:` prints a value close to
`1.5`.

- [ ] **Step 4: Commit**

```bash
git add bridge/obsbot_bridge.cpp
git commit -m "feat(bridge): add zoom get/set"
```

---

## Task 7: Bridge — gimbal presets

**Files:**
- Modify: `bridge/obsbot_bridge.cpp`

**Interfaces:**
- Consumes: `check_ok` helper from Task 4, `Device::PresetPosInfo` /
  `Device::DevDataArray` structs from the SDK.
- Produces on `Device`: `list_presets() -> list[dict]` (each dict has `id:
  int`, `name: str`, `pitch: float`, `yaw: float`, `roll: float`, `zoom:
  float`), `add_preset(name: str, pitch: float, yaw: float, roll: float,
  zoom: float) -> int` (returns the new preset's id), `delete_preset(id:
  int) -> None`, `goto_preset(id: int) -> None`,
  `rename_preset(id: int, name: str) -> None`.

- [ ] **Step 1: Add `#include <cstring>`**

At the top of `bridge/obsbot_bridge.cpp`, alongside the other includes
(needed for `memcpy` in `add_preset`).

- [ ] **Step 2: Add the preset methods**

Chain onto the `Device` class definition:
```cpp
		.def("list_presets", [](Device &d) {
			Device::DevDataArray ids{};
			check_ok(d.aiGetGimbalPresetListR(&ids), "list_presets");
			py::list out;
			for (int32_t i = 0; i < ids.len; ++i) {
				int32_t id = ids.data_int32[i];
				Device::PresetPosInfo info{};
				check_ok(d.aiGetGimbalPresetInfoWithIdR(&info, id),
					 "get_preset_info");
				py::dict item;
				item["id"] = id;
				item["name"] = std::string(info.name,
							    static_cast<size_t>(info.name_len));
				item["pitch"] = info.pitch;
				item["yaw"] = info.yaw;
				item["roll"] = info.roll;
				item["zoom"] = info.zoom;
				out.append(item);
			}
			return out;
		})
		.def("add_preset", [](Device &d, const std::string &name,
				       float pitch, float yaw, float roll,
				       float zoom) {
			Device::PresetPosInfo info{};
			info.id = 0;
			info.pitch = pitch;
			info.yaw = yaw;
			info.roll = roll;
			info.zoom = zoom;
			std::string truncated = name.substr(0, 63);
			memcpy(info.name, truncated.c_str(), truncated.size());
			info.name_len = static_cast<int32_t>(truncated.size());
			check_ok(d.aiAddGimbalPresetR(&info), "add_preset");
			return info.id;
		})
		.def("delete_preset", [](Device &d, int32_t id) {
			check_ok(d.aiDelGimbalPresetR(id), "delete_preset");
		})
		.def("goto_preset", [](Device &d, int32_t id) {
			check_ok(d.aiTrgGimbalPresetR(id), "goto_preset");
		})
		.def("rename_preset", [](Device &d, int32_t id,
					  const std::string &name) {
			check_ok(d.aiSetGimbalPresetNameWithIdR(name, id),
				 "rename_preset");
		});
```

- [ ] **Step 3: Rebuild (run on Debian/Ubuntu Linux)**

```bash
cmake --build bridge/build -j"$(nproc)"
```

Expected: no compile errors.

- [ ] **Step 4: Manually exercise (run on Debian/Ubuntu Linux, camera plugged in)**

```bash
cd bridge
PYTHONPATH=build python3 -c "
import obsbot_bridge as bridge
d = bridge.get_device_by_sn(bridge.list_devices()[0]['sn'])
angle = d.get_gimbal_angle()
new_id = d.add_preset('test-preset', angle['pitch'], angle['yaw'], 0.0, d.get_zoom())
print('presets:', d.list_presets())
d.rename_preset(new_id, 'renamed-preset')
print('presets after rename:', d.list_presets())
d.goto_preset(new_id)
d.delete_preset(new_id)
print('presets after delete:', d.list_presets())
"
```

Expected: `presets:` includes an entry named `test-preset`; after
`rename_preset`, `presets after rename:` shows the same id with name
`renamed-preset`; after `delete_preset`, the final
`presets after delete:` list no longer contains it.

- [ ] **Step 5: Commit**

```bash
git add bridge/obsbot_bridge.cpp
git commit -m "feat(bridge): add gimbal preset list/add/delete/goto"
```

---

## Task 8: Python — DeviceManager

**Files:**
- Create: `app/device_manager.py`
- Test: `tests/test_device_manager.py`
- Create: `tests/conftest.py`
- Create: `tests/fake_bridge.py`

**Interfaces:**
- Consumes: `obsbot_bridge` module surface from Tasks 2–7 (`list_devices`,
  `get_device_by_sn`, `set_device_changed_callback`, `close`,
  `Device.set_status_callback`).
- Produces: `DeviceManager(QObject)` with signals
  `device_connected(str, str)`, `device_disconnected(str)`,
  `status_changed(dict)`; attribute `device: Device | None`; attribute
  `last_status: dict`; methods `start() -> None` and `shutdown() -> None`.
  `start()` must be called once, after every consumer has connected to its
  signals, to pick up a camera that was already plugged in before the app
  launched — the constructor itself only registers the SDK callback, it
  does not scan (see Task 13, where `MainWindow` calls it last).

This task's tests run on any OS (including this Windows machine) because
they substitute a fake `obsbot_bridge` module — they never touch the real
compiled extension or a physical camera.

- [ ] **Step 1: Write the fake bridge module used by all app-level tests**

`tests/fake_bridge.py`:
```python
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
```

- [ ] **Step 2: Write `tests/conftest.py` to install the fake module once,
  before any app import, and reset its state between tests**

```python
import sys

import pytest

from tests.fake_bridge import FakeBridgeModule


def pytest_configure(config):
    # Installed once, before any `app.*` module is imported, so every
    # `import obsbot_bridge as bridge` inside the app package binds to this
    # exact instance for the whole test session.
    sys.modules["obsbot_bridge"] = FakeBridgeModule()


@pytest.fixture(autouse=True)
def reset_fake_bridge():
    # Reset the SAME instance's state before each test (not replace it —
    # see the docstring on FakeBridgeModule.reset for why replacing it
    # would silently not work).
    sys.modules["obsbot_bridge"].reset()
    yield
```

- [ ] **Step 3: Write the failing test**

`tests/test_device_manager.py`:
```python
import sys

from app.device_manager import DeviceManager


def test_start_picks_up_already_connected_device(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    bridge.add_device("SN1", "Tiny2")  # present before the manager exists
    manager = DeviceManager()

    with qtbot.waitSignal(manager.device_connected, timeout=1000) as blocker:
        manager.start()

    assert blocker.args == ["SN1", "Tiny2"]


def test_connect_emits_signal_and_exposes_device(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    bridge.add_device("SN123", "Tiny2")

    with qtbot.waitSignal(manager.device_connected, timeout=1000) as blocker:
        bridge.connect_device("SN123")

    assert blocker.args == ["SN123", "Tiny2"]
    assert manager.device is not None
    assert manager.device.sn == "SN123"


def test_disconnect_clears_device(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    bridge.add_device("SN123", "Tiny2")
    bridge.connect_device("SN123")

    with qtbot.waitSignal(manager.device_disconnected, timeout=1000):
        bridge.remove_device("SN123")

    assert manager.device is None


def test_status_update_populates_last_status_and_emits(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    device = bridge.add_device("SN123", "Tiny2")
    bridge.connect_device("SN123")

    with qtbot.waitSignal(manager.status_changed, timeout=1000) as blocker:
        device.push_status({"zoom_ratio": 42})

    assert blocker.args == [{"zoom_ratio": 42}]
    assert manager.last_status == {"zoom_ratio": 42}


def test_shutdown_closes_bridge():
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    manager.shutdown()
    assert bridge.closed is True
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `pytest tests/test_device_manager.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.device_manager'`.

- [ ] **Step 5: Write the implementation**

`app/device_manager.py`:
```python
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

import obsbot_bridge as bridge


class DeviceManager(QObject):
    device_connected = Signal(str, str)
    device_disconnected = Signal(str)
    status_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.device = None
        self.last_status: dict = {}
        self._sn: str | None = None
        bridge.set_device_changed_callback(self._on_device_changed)

    def start(self) -> None:
        """Pick up a camera that was already plugged in before the app
        launched. Call this once, after every consumer (widgets) has
        connected to device_connected/device_disconnected/status_changed —
        otherwise an already-connected device's signal fires before anyone
        is listening."""
        for info in bridge.list_devices():
            self._on_device_changed(info["sn"], True)

    def _on_device_changed(self, sn: str, connected: bool) -> None:
        if connected:
            if self.device is not None:
                return
            device = bridge.get_device_by_sn(sn)
            if device is None:
                return
            self.device = device
            self._sn = sn
            device.set_status_callback(self._on_status)
            self.device_connected.emit(sn, device.name)
        else:
            if sn != self._sn:
                return
            self.device = None
            self._sn = None
            self.device_disconnected.emit(sn)

    def _on_status(self, data: dict) -> None:
        self.last_status = data
        self.status_changed.emit(data)

    def shutdown(self) -> None:
        bridge.close()
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `pytest tests/test_device_manager.py -v`
Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add app/device_manager.py tests/test_device_manager.py tests/conftest.py tests/fake_bridge.py
git commit -m "feat(app): add DeviceManager wrapping the bridge"
```

---

## Task 9: Python — GimbalController

**Files:**
- Create: `app/gimbal_controller.py`
- Test: `tests/test_gimbal_controller.py`

**Interfaces:**
- Consumes: `DeviceManager` shape from Task 8 (`.device`, `.last_status`);
  `obsbot_bridge.ObsbotError`.
- Produces: `GimbalController(device_manager, parent=None)` (QObject) with
  methods `start() -> None`, `update(x: float, y: float) -> None`,
  `stop() -> None`, and constants `MAX_PITCH_SPEED = 40.0`,
  `MAX_PAN_SPEED = 60.0`, `TICK_INTERVAL_MS = 50`.

- [ ] **Step 1: Write the failing tests**

`tests/test_gimbal_controller.py`:
```python
from app.gimbal_controller import GimbalController, MAX_PITCH_SPEED, MAX_PAN_SPEED
from tests.fake_bridge import FakeDevice


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_gimbal_controller.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.gimbal_controller'`.

- [ ] **Step 3: Write the implementation**

`app/gimbal_controller.py`:
```python
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer

import obsbot_bridge as bridge

MAX_PITCH_SPEED = 40.0
MAX_PAN_SPEED = 60.0
TICK_INTERVAL_MS = 50  # 20 Hz


class GimbalController(QObject):
    def __init__(self, device_manager, parent=None):
        super().__init__(parent)
        self._device_manager = device_manager
        self._pending = (0.0, 0.0)
        self._last_sent = None
        self._ai_was_enabled = False
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_INTERVAL_MS)
        self._timer.timeout.connect(self._on_tick)

    def start(self) -> None:
        device = self._device_manager.device
        if device is None:
            return
        self._ai_was_enabled = self._device_manager.last_status.get(
            "ai_mode", 0) != 0
        self._pending = (0.0, 0.0)
        self._last_sent = None
        try:
            device.set_ai_enabled(False)
        except bridge.ObsbotError:
            pass
        self._timer.start()

    def update(self, x: float, y: float) -> None:
        self._pending = (x, y)

    def stop(self) -> None:
        self._timer.stop()
        device = self._device_manager.device
        if device is None:
            return
        try:
            device.stop_gimbal()
        except bridge.ObsbotError:
            pass
        if self._ai_was_enabled:
            try:
                device.set_ai_enabled(True)
            except bridge.ObsbotError:
                pass

    def _on_tick(self) -> None:
        device = self._device_manager.device
        if device is None:
            self._timer.stop()
            return
        if self._pending == self._last_sent:
            return
        x, y = self._pending
        pitch = -y * MAX_PITCH_SPEED
        pan = x * MAX_PAN_SPEED
        try:
            device.set_gimbal_speed(pitch, pan)
        except bridge.ObsbotError:
            pass
        self._last_sent = self._pending
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_gimbal_controller.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add app/gimbal_controller.py tests/test_gimbal_controller.py
git commit -m "feat(app): add GimbalController with throttling and AI hand-off"
```

---

## Task 10: Python — JoystickWidget

**Files:**
- Create: `app/widgets/joystick.py`
- Test: `tests/test_joystick_widget.py`

**Interfaces:**
- Produces: `JoystickWidget(QWidget)` with signals `moved(float, float)`
  (normalized `x, y` in `[-1, 1]`), `pressed()`, `released()`.

- [ ] **Step 1: Write the failing tests**

`tests/test_joystick_widget.py`:
```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_joystick_widget.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.widgets.joystick'`.

- [ ] **Step 3: Write the implementation**

`app/widgets/joystick.py`:
```python
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
        return QPointF(self.width() / 2, self.height() / 2)

    def mousePressEvent(self, event):
        self._dragging = True
        self._update_from_pos(event.position())
        self.pressed.emit()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._update_from_pos(event.position())

    def mouseReleaseEvent(self, event):
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_joystick_widget.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/widgets/joystick.py tests/test_joystick_widget.py
git commit -m "feat(app): add analog JoystickWidget"
```

---

## Task 11: Python — StatusPanel (zoom + AI tracking mode)

**Files:**
- Create: `app/widgets/status_panel.py`
- Test: `tests/test_status_panel.py`

**Interfaces:**
- Consumes: `DeviceManager` signals from Task 8; `obsbot_bridge.TrackMode`,
  `obsbot_bridge.ObsbotError`.
- Produces: `StatusPanel(device_manager, parent=None)` (QWidget) with
  widgets `connection_label`, `zoom_slider` (range 0–100, mirrors the
  status callback's `zoom_ratio` units directly), `ai_enabled_checkbox`,
  `mode_headroom_btn`, `mode_standard_btn`, `mode_motion_btn`. Also
  produces two module-level
  pure functions used for the zoom scale conversion:
  `zoom_ratio_to_slider_value(zoom_ratio: int) -> int` and
  `slider_value_to_absolute_zoom(value: int) -> float`.

- [ ] **Step 1: Write the failing tests**

`tests/test_status_panel.py`:
```python
import sys

from app.widgets.status_panel import (
    StatusPanel,
    slider_value_to_absolute_zoom,
    zoom_ratio_to_slider_value,
)
from app.device_manager import DeviceManager


def test_zoom_conversion_round_trip():
    assert zoom_ratio_to_slider_value(0) == 0
    assert zoom_ratio_to_slider_value(100) == 100
    assert slider_value_to_absolute_zoom(0) == 1.0
    assert slider_value_to_absolute_zoom(100) == 2.0
    assert slider_value_to_absolute_zoom(50) == 1.5


def test_connect_enables_controls(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    panel = StatusPanel(manager)
    qtbot.addWidget(panel)

    bridge.add_device("SN1", "Tiny2")
    bridge.connect_device("SN1")

    assert panel.zoom_slider.isEnabled()
    assert panel.mode_standard_btn.isEnabled()
    assert panel.ai_enabled_checkbox.isEnabled()


def test_ai_checkbox_reflects_status_and_toggles_device(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    panel = StatusPanel(manager)
    qtbot.addWidget(panel)
    device = bridge.add_device("SN1", "Tiny2")
    bridge.connect_device("SN1")

    device.push_status({"ai_mode": 1})
    assert panel.ai_enabled_checkbox.isChecked()

    panel.ai_enabled_checkbox.setChecked(False)
    assert ("set_ai_enabled", False) in device.calls


def test_status_update_moves_zoom_slider_when_not_dragging(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    panel = StatusPanel(manager)
    qtbot.addWidget(panel)
    device = bridge.add_device("SN1", "Tiny2")
    bridge.connect_device("SN1")

    device.push_status({"zoom_ratio": 73})

    assert panel.zoom_slider.value() == 73


def test_clicking_mode_button_calls_set_tracking_mode_and_enables_ai(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    panel = StatusPanel(manager)
    qtbot.addWidget(panel)
    device = bridge.add_device("SN1", "Tiny2")
    bridge.connect_device("SN1")

    panel.mode_motion_btn.click()

    assert ("set_tracking_mode", bridge.TrackMode.Motion) in device.calls
    assert ("set_ai_enabled", True) in device.calls
    assert panel.mode_motion_btn.isChecked()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_status_panel.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.widgets.status_panel'`.

- [ ] **Step 3: Write the implementation**

`app/widgets/status_panel.py`:
```python
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout,
    QWidget,
)

import obsbot_bridge as bridge


def zoom_ratio_to_slider_value(zoom_ratio: int) -> int:
    return max(0, min(100, int(zoom_ratio)))


def slider_value_to_absolute_zoom(value: int) -> float:
    return 1.0 + (value / 100.0)


class StatusPanel(QWidget):
    def __init__(self, device_manager, parent=None):
        super().__init__(parent)
        self._device_manager = device_manager
        self._user_dragging_zoom = False

        self.connection_label = QLabel("Sin dispositivo conectado")

        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(0, 100)
        self.zoom_slider.setEnabled(False)

        self.ai_enabled_checkbox = QCheckBox("AI activo")
        self.ai_enabled_checkbox.setEnabled(False)

        self.mode_headroom_btn = QPushButton("cabezal")
        self.mode_standard_btn = QPushButton("estandar")
        self.mode_motion_btn = QPushButton("movimiento")
        self._mode_buttons = {
            bridge.TrackMode.Headroom: self.mode_headroom_btn,
            bridge.TrackMode.Standard: self.mode_standard_btn,
            bridge.TrackMode.Motion: self.mode_motion_btn,
        }
        for btn in self._mode_buttons.values():
            btn.setCheckable(True)
            btn.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.connection_label)
        layout.addWidget(self.zoom_slider)
        layout.addWidget(self.ai_enabled_checkbox)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.mode_headroom_btn)
        mode_row.addWidget(self.mode_standard_btn)
        mode_row.addWidget(self.mode_motion_btn)
        layout.addLayout(mode_row)

        self.zoom_slider.sliderPressed.connect(self._on_zoom_pressed)
        self.zoom_slider.sliderReleased.connect(self._on_zoom_released)
        self.zoom_slider.valueChanged.connect(self._on_zoom_changed)
        self.ai_enabled_checkbox.toggled.connect(self._on_ai_toggled)
        for mode, btn in self._mode_buttons.items():
            btn.clicked.connect(lambda _checked=False, m=mode: self._set_mode(m))

        device_manager.device_connected.connect(self._on_connected)
        device_manager.device_disconnected.connect(self._on_disconnected)
        device_manager.status_changed.connect(self._on_status_changed)

    def _on_connected(self, sn: str, name: str) -> None:
        self.connection_label.setText(f"Conectado: {name}")
        self.zoom_slider.setEnabled(True)
        self.ai_enabled_checkbox.setEnabled(True)
        for btn in self._mode_buttons.values():
            btn.setEnabled(True)

    def _on_disconnected(self, sn: str) -> None:
        self.connection_label.setText("Sin dispositivo conectado")
        self.zoom_slider.setEnabled(False)
        self.ai_enabled_checkbox.blockSignals(True)
        self.ai_enabled_checkbox.setChecked(False)
        self.ai_enabled_checkbox.blockSignals(False)
        self.ai_enabled_checkbox.setEnabled(False)
        for btn in self._mode_buttons.values():
            btn.setEnabled(False)
            btn.setChecked(False)

    def _on_status_changed(self, data: dict) -> None:
        if not self._user_dragging_zoom and "zoom_ratio" in data:
            self.zoom_slider.blockSignals(True)
            self.zoom_slider.setValue(
                zoom_ratio_to_slider_value(data["zoom_ratio"]))
            self.zoom_slider.blockSignals(False)
        if "ai_mode" in data:
            self.ai_enabled_checkbox.blockSignals(True)
            self.ai_enabled_checkbox.setChecked(bool(data["ai_mode"]))
            self.ai_enabled_checkbox.blockSignals(False)

    def _on_zoom_pressed(self) -> None:
        self._user_dragging_zoom = True

    def _on_zoom_released(self) -> None:
        self._user_dragging_zoom = False

    def _on_zoom_changed(self, value: int) -> None:
        device = self._device_manager.device
        if device is None:
            return
        try:
            device.set_zoom(slider_value_to_absolute_zoom(value))
        except bridge.ObsbotError:
            pass

    def _set_mode(self, mode) -> None:
        device = self._device_manager.device
        if device is None:
            return
        try:
            device.set_tracking_mode(mode)
            device.set_ai_enabled(True)
        except bridge.ObsbotError:
            pass
        for m, btn in self._mode_buttons.items():
            btn.setChecked(m == mode)
        self.ai_enabled_checkbox.blockSignals(True)
        self.ai_enabled_checkbox.setChecked(True)
        self.ai_enabled_checkbox.blockSignals(False)

    def _on_ai_toggled(self, checked: bool) -> None:
        device = self._device_manager.device
        if device is None:
            return
        try:
            device.set_ai_enabled(checked)
        except bridge.ObsbotError:
            pass
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_status_panel.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add app/widgets/status_panel.py tests/test_status_panel.py
git commit -m "feat(app): add StatusPanel with zoom slider and AI tracking modes"
```

---

## Task 12: Python — PresetsPanel

**Files:**
- Create: `app/widgets/presets_panel.py`
- Test: `tests/test_presets_panel.py`

**Interfaces:**
- Consumes: `DeviceManager` signals from Task 8; `Device.list_presets` /
  `add_preset` / `delete_preset` / `goto_preset` / `rename_preset` /
  `get_gimbal_angle` / `get_zoom` from Tasks 6–7; `obsbot_bridge.ObsbotError`.
- Produces: `PresetsPanel(device_manager, parent=None)` (QWidget) with
  `list_widget`, `add_btn`, `goto_btn`, `delete_btn`, `rename_btn`. Preset id
  is stored on each `QListWidgetItem` under Qt role `PRESET_ID_ROLE` (module
  constant).

- [ ] **Step 1: Write the failing tests**

`tests/test_presets_panel.py`:
```python
import sys

from app.device_manager import DeviceManager
from app.widgets.presets_panel import PRESET_ID_ROLE, PresetsPanel


def test_connect_populates_existing_presets(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    device = bridge.add_device("SN1", "Tiny2")
    device.add_preset("home", 0.0, 0.0, 0.0, 1.0)
    panel = PresetsPanel(manager)
    qtbot.addWidget(panel)

    bridge.connect_device("SN1")

    assert panel.list_widget.count() == 1
    assert panel.list_widget.item(0).text() == "home"


def test_goto_calls_goto_preset_with_selected_id(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    device = bridge.add_device("SN1", "Tiny2")
    preset_id = device.add_preset("home", 0.0, 0.0, 0.0, 1.0)
    panel = PresetsPanel(manager)
    qtbot.addWidget(panel)
    bridge.connect_device("SN1")

    panel.list_widget.setCurrentRow(0)
    panel.goto_btn.click()

    assert ("goto_preset", preset_id) in device.calls


def test_delete_removes_from_device_and_refreshes(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    device = bridge.add_device("SN1", "Tiny2")
    device.add_preset("home", 0.0, 0.0, 0.0, 1.0)
    panel = PresetsPanel(manager)
    qtbot.addWidget(panel)
    bridge.connect_device("SN1")

    panel.list_widget.setCurrentRow(0)
    panel._on_delete(confirm=True)

    assert panel.list_widget.count() == 0
    assert device.list_presets() == []


def test_rename_calls_rename_preset_and_refreshes_label(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    device = bridge.add_device("SN1", "Tiny2")
    preset_id = device.add_preset("home", 0.0, 0.0, 0.0, 1.0)
    panel = PresetsPanel(manager)
    qtbot.addWidget(panel)
    bridge.connect_device("SN1")

    panel.list_widget.setCurrentRow(0)
    panel._on_rename(new_name="office")

    assert ("rename_preset", preset_id, "office") in device.calls
    assert panel.list_widget.item(0).text() == "office"


def test_disconnect_clears_list_and_disables_buttons(qtbot):
    bridge = sys.modules["obsbot_bridge"]
    manager = DeviceManager()
    device = bridge.add_device("SN1", "Tiny2")
    device.add_preset("home", 0.0, 0.0, 0.0, 1.0)
    panel = PresetsPanel(manager)
    qtbot.addWidget(panel)
    bridge.connect_device("SN1")

    bridge.remove_device("SN1")

    assert panel.list_widget.count() == 0
    assert not panel.add_btn.isEnabled()
    assert not panel.rename_btn.isEnabled()
```

Note: `test_delete_...` calls `panel._on_delete(confirm=True)` directly
(bypassing the confirmation dialog), and `test_rename_...` calls
`panel._on_rename(new_name="office")` directly (bypassing the name input
dialog) — both are the same pattern used by `_on_add`'s dialog-free test
path. Every test creates the device and (where relevant) its presets via
`bridge.add_device`/`device.add_preset` *before* calling
`bridge.connect_device`, so `PresetsPanel`'s `_on_connected` handler sees
the full state on its very first `_refresh()`, exactly like a real preset
that already existed on the camera before the app was launched.
`PRESET_ID_ROLE` is imported to keep the test file future-proof if the role
value changes, even though these tests don't use it directly.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_presets_panel.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.widgets.presets_panel'`.

- [ ] **Step 3: Write the implementation**

`app/widgets/presets_panel.py`:
```python
from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout, QInputDialog, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)

import obsbot_bridge as bridge

PRESET_ID_ROLE = 1000


class PresetsPanel(QWidget):
    def __init__(self, device_manager, parent=None):
        super().__init__(parent)
        self._device_manager = device_manager

        self.list_widget = QListWidget()
        self.add_btn = QPushButton("Agregar")
        self.goto_btn = QPushButton("Ir")
        self.rename_btn = QPushButton("Renombrar")
        self.delete_btn = QPushButton("Borrar")
        self._buttons = (self.add_btn, self.goto_btn, self.rename_btn,
                          self.delete_btn)
        for btn in self._buttons:
            btn.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.list_widget)
        btn_row = QHBoxLayout()
        for btn in self._buttons:
            btn_row.addWidget(btn)
        layout.addLayout(btn_row)

        self.add_btn.clicked.connect(self._on_add)
        self.goto_btn.clicked.connect(self._on_goto)
        self.rename_btn.clicked.connect(self._on_rename)
        self.delete_btn.clicked.connect(self._on_delete)

        device_manager.device_connected.connect(self._on_connected)
        device_manager.device_disconnected.connect(self._on_disconnected)

    def _on_connected(self, sn: str, name: str) -> None:
        for btn in self._buttons:
            btn.setEnabled(True)
        self._refresh()

    def _on_disconnected(self, sn: str) -> None:
        for btn in self._buttons:
            btn.setEnabled(False)
        self.list_widget.clear()

    def _refresh(self) -> None:
        device = self._device_manager.device
        self.list_widget.clear()
        if device is None:
            return
        try:
            presets = device.list_presets()
        except bridge.ObsbotError:
            presets = []
        for preset in presets:
            item = QListWidgetItem(preset["name"] or f"Preset {preset['id']}")
            item.setData(PRESET_ID_ROLE, preset["id"])
            self.list_widget.addItem(item)

    def _on_add(self) -> None:
        device = self._device_manager.device
        if device is None:
            return
        name, ok = QInputDialog.getText(self, "Nuevo preset", "Nombre:")
        if not ok or not name:
            return
        try:
            angle = device.get_gimbal_angle()
            zoom = device.get_zoom()
            device.add_preset(name, angle["pitch"], angle["yaw"], 0.0, zoom)
        except bridge.ObsbotError:
            QMessageBox.warning(self, "Error", "No se pudo guardar el preset")
        self._refresh()

    def _on_goto(self) -> None:
        device = self._device_manager.device
        item = self.list_widget.currentItem()
        if device is None or item is None:
            return
        preset_id = item.data(PRESET_ID_ROLE)
        try:
            device.goto_preset(preset_id)
        except bridge.ObsbotError:
            QMessageBox.warning(self, "Error", "No se pudo mover al preset")

    def _on_rename(self, new_name: str | None = None) -> None:
        device = self._device_manager.device
        item = self.list_widget.currentItem()
        if device is None or item is None:
            return
        if new_name is None:
            new_name, ok = QInputDialog.getText(
                self, "Renombrar preset", "Nuevo nombre:")
            if not ok or not new_name:
                return
        preset_id = item.data(PRESET_ID_ROLE)
        try:
            device.rename_preset(preset_id, new_name)
        except bridge.ObsbotError:
            QMessageBox.warning(self, "Error", "No se pudo renombrar el preset")
            return
        item.setText(new_name)

    def _on_delete(self, confirm: bool | None = None) -> None:
        device = self._device_manager.device
        item = self.list_widget.currentItem()
        if device is None or item is None:
            return
        if confirm is None:
            confirm = QMessageBox.question(
                self, "Borrar preset", "¿Confirmar borrado?"
            ) == QMessageBox.Yes
        if not confirm:
            return
        preset_id = item.data(PRESET_ID_ROLE)
        try:
            device.delete_preset(preset_id)
        except bridge.ObsbotError:
            QMessageBox.warning(self, "Error", "No se pudo borrar el preset")
        self._refresh()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_presets_panel.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add app/widgets/presets_panel.py tests/test_presets_panel.py
git commit -m "feat(app): add PresetsPanel"
```

---

## Task 13: Python — MainWindow and entry point

**Files:**
- Create: `app/main_window.py`
- Create: `app/main.py`

**Interfaces:**
- Consumes: `DeviceManager` (Task 8), `GimbalController` (Task 9),
  `JoystickWidget` (Task 10), `StatusPanel` (Task 11), `PresetsPanel`
  (Task 12).
- Produces: `MainWindow(QMainWindow)` with `shutdown() -> None`; `main.py`
  with a `main() -> int` entry point.

> This task's own behavior can't be exercised without the real bridge and
> a physical camera — run the manual steps below on the Debian/Ubuntu
> machine (see Task 14 for the one-time environment setup).

- [ ] **Step 1: Write `app/main_window.py`**

```python
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QVBoxLayout, QWidget

from app.device_manager import DeviceManager
from app.gimbal_controller import GimbalController
from app.widgets.joystick import JoystickWidget
from app.widgets.presets_panel import PresetsPanel
from app.widgets.status_panel import StatusPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OBSBOT Tiny2 Control")

        self.device_manager = DeviceManager(self)
        self.gimbal_controller = GimbalController(self.device_manager, self)

        self.joystick = JoystickWidget()
        self.status_panel = StatusPanel(self.device_manager)
        self.presets_panel = PresetsPanel(self.device_manager)

        self.joystick.pressed.connect(self.gimbal_controller.start)
        self.joystick.moved.connect(self.gimbal_controller.update)
        self.joystick.released.connect(self.gimbal_controller.stop)

        central = QWidget()
        root = QHBoxLayout(central)
        left = QVBoxLayout()
        left.addWidget(self.joystick)
        left.addWidget(self.status_panel)
        root.addLayout(left)
        root.addWidget(self.presets_panel)
        self.setCentralWidget(central)

        # Must run last: DeviceManager's constructor only registers the SDK
        # callback, it does not scan for an already-connected camera (see
        # Task 8) — start() does that scan, and by now every widget above
        # has already connected to device_connected/status_changed, so none
        # of them miss the initial event if a camera is already plugged in.
        self.device_manager.start()

    def shutdown(self) -> None:
        self.device_manager.shutdown()
```

- [ ] **Step 2: Write `app/main.py`**

```python
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    app.aboutToQuit.connect(window.shutdown)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run the full app (run on Debian/Ubuntu Linux, camera plugged in)**

```bash
export PYTHONPATH="$PYTHONPATH:$(pwd)/bridge/build"
python3 -m app.main
```

Expected: a window opens showing the joystick pad, zoom slider, the three
AI tracking mode buttons, and the presets list. Dragging the joystick pans
the physical camera and releasing stops it immediately; the zoom slider
and AI mode buttons reflect the design's data flow (spec §6). Work through
the full manual hardware checklist in Task 14 at this point.

- [ ] **Step 4: Commit**

```bash
git add app/main_window.py app/main.py
git commit -m "feat(app): wire MainWindow and entry point"
```

---

## Task 14: README with build/run instructions and manual hardware checklist

**Files:**
- Modify: `README.md`

**Interfaces:**
- None (documentation only).

- [ ] **Step 1: Replace `README.md` with full instructions**

```markdown
# OBSBOT Tiny2 Joystick Control

Analog on-screen joystick control for an OBSBOT Tiny2-family camera
(Tiny2 / Tiny2 Lite / Tiny SE), using the vendored `libdev_v1.0.2` SDK.

Design: `docs/superpowers/specs/2026-09-06-obsbot-tiny2-joystick-app-design.md`

## One-time environment setup (Debian/Ubuntu)

```bash
sudo apt update
sudo apt install -y build-essential cmake python3 python3-dev python3-pip python3-venv pkg-config

tar -xzf libdev_v1.0.2.tar.gz

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Build the C++ bridge

```bash
cmake -S bridge -B bridge/build -Dpybind11_DIR="$(python3 -m pybind11 --cmakedir)"
cmake --build bridge/build -j"$(nproc)"
```

## Run the app

```bash
export PYTHONPATH="$PYTHONPATH:$(pwd)/bridge/build"
python3 -m app.main
```

## Run the tests

Pure Python/Qt tests (no camera or bridge required, run from the repo root):

```bash
pytest tests/ -v
```

## Manual hardware checklist

Run these against the real camera after building, and any time you touch
the bridge or `GimbalController`:

- [ ] Joystick pans/tilts smoothly with no jitter or lag.
- [ ] Releasing the joystick stops the gimbal immediately.
- [ ] AI tracking re-enables correctly after a drag if it was on before
      you grabbed the joystick.
- [ ] Zoom slider position matches the physical zoom, both ways (dragging
      the slider zooms the camera; zooming another way, e.g. via the
      physical button if present, updates the slider).
- [ ] The three tracking mode buttons (cabezal/estandar/movimiento)
      switch correctly and highlight the active one.
- [ ] Add / go-to / rename / delete preset round-trips correctly.
- [ ] Unplugging and replugging the camera mid-session doesn't crash the
      app.
- [ ] Going to a preset while AI tracking is active actually moves the
      gimbal (spec §9 open assumption — if not, `goto_preset` needs to
      also disable AI around the call, same as `set_gimbal_speed` does).
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add build/run instructions and manual hardware checklist"
```
