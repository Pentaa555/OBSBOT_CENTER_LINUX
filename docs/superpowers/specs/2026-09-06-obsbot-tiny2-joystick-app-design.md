# OBSBOT Tiny2 Joystick Control App — Design

Date: 2026-09-06
Status: Approved (pending spec self-review)

## 1. Goal

Build a Linux desktop app to control an OBSBOT Tiny2-family camera
(Tiny2 / Tiny2 Lite / Tiny SE) using the vendored `libdev_v1.0.2` SDK,
replacing OBSBOT Center's arrow-button pan/tilt pad with a true analog
on-screen joystick: drag direction and distance from center map
continuously to gimbal speed, and releasing stops the gimbal
immediately.

## 2. Scope

**In scope (v1):**
- Device discovery/connect/disconnect for a single Tiny2-family camera.
- On-screen virtual joystick for continuous pan/tilt speed control.
- Zoom control (slider), synced with live device status.
- AI tracking mode selection (cabezal/headroom, estándar/standard,
  movimiento/motion) and AI on/off.
- Gimbal presets: add (capture current position + zoom), go to,
  delete, rename.

**Out of scope (v1, future iterations):**
- Exposure, white balance, image adjustments (contrast/sharpness/etc).
- Sleep mode, gesture control, audio settings, firmware info/export.
- Physical USB gamepad/joystick input.
- Multi-device switching (app targets the first Tiny2-family device
  it sees; others are ignored, not an error).

## 3. Architecture

Two packages:

- **`bridge/`** — C++ pybind11 extension module (`obsbot_bridge`),
  built via CMake, linking directly against the vendored `libdev.so`.
  Purely mechanical: wraps the ~10 SDK calls we use, converts the raw
  `Device::CameraStatus` union into a plain Python dict, and
  translates SDK error codes into a lightweight `ObsbotError` Python
  exception. No UI or business logic lives here.
- **`app/`** — Python (PySide6). Device management, joystick widget,
  gimbal controller (rate limiting + AI hand-off), status/zoom/AI
  panel, presets panel, main window.

```
obsbot/
  libdev_v1.0.2/            (vendored SDK, already present)
  bridge/
    CMakeLists.txt
    obsbot_bridge.cpp
  app/
    main.py
    device_manager.py
    gimbal_controller.py
    widgets/
      joystick.py
      status_panel.py
      presets_panel.py
  requirements.txt
  README.md                 (build + run instructions)
```

## 4. SDK surface used

From `include/dev/dev.hpp` / `include/dev/devs.hpp` (Tiny2 series):

| Purpose | Function |
|---|---|
| Device discovery | `Devices::get()`, `setDevChangedCallback`, `getDevList()`, `getDevBySn()` |
| Live status push | `Device::setDevStatusCallbackFunc`, `enableDevStatusCallback(true)`, `cameraStatus()` (`.tiny` variant: `zoom_ratio`, `ai_mode`, `dev_status`, ...) |
| Gimbal continuous speed (joystick) | `aiSetGimbalSpeedCtrlR(pitch, pan)` — pitch −90..90, pan −180..180 |
| Gimbal stop | `aiSetGimbalStop()` |
| AI enable/disable (required around manual speed control) | `aiSetEnabledR(bool)` |
| AI tracking mode | `aiSetTrackingModeR(AiVerticalTrackType)` — `AiVTrackStandard` / `AiVTrackHeadroom` / `AiVTrackMotion` |
| Zoom | `cameraSetZoomAbsoluteR(float)` (1.0–2.0), `cameraGetZoomAbsoluteR(float&)` |
| Current gimbal angle (for capturing a preset) | `aiGetGimbalStateR(AiGimbalStateInfo*)` |
| Presets | `aiAddGimbalPresetR`, `aiDelGimbalPresetR`, `aiUpdGimbalPresetR`, `aiTrgGimbalPresetR`, `aiGetGimbalPresetListR`, `aiGetGimbalPresetInfoWithIdR`, `aiSetGimbalPresetNameWithIdR` |

## 5. Components

1. **`obsbot_bridge` (C++/pybind11)** — exposes `list_devices()` and a
   `Device` wrapper class with: `set_gimbal_speed(pitch, pan)`,
   `stop_gimbal()`, `set_ai_enabled(bool)`, `set_tracking_mode(mode)`,
   `set_zoom(float)` / `get_zoom()`, `add_preset(...)` /
   `delete_preset(id)` / `goto_preset(id)` / `list_presets()`, and
   `set_status_callback(fn)`. Converts `CameraStatus` to a plain dict
   before invoking the Python callback. Wraps every Python callback
   invocation in a try/catch on the C++ side so a bug in UI code can
   never crash the SDK's internal callback thread.

2. **`DeviceManager` (Python, `QObject`)** — owns the single connected
   `Device` (v1: single camera). Registers the bridge's device-changed
   callback and calls `list_devices()` once at startup to catch a
   camera that was already plugged in before the app launched.
   Exposes Qt signals: `device_connected(sn, name)`,
   `device_disconnected(sn)`, `status_changed(dict)`. Bridges callbacks
   arriving on the SDK's internal thread into these signals, which Qt
   safely queues onto the main thread.

3. **`GimbalController` (Python)** — takes normalized joystick `(x, y)`
   in `[-1, 1]`, maps to `(pitch, pan)` speeds using a configurable,
   conservative max (below the SDK's full ±90/±180 range so motion
   isn't violent), throttles outgoing `set_gimbal_speed` calls to a
   fixed tick (default 20 Hz) via `QTimer`. On first press: remembers
   whether AI tracking was active, calls `set_ai_enabled(False)`. On
   release: calls `stop_gimbal()` immediately (not throttled) and
   restores AI enabled state if it was on before. Each tick checks the
   device is still connected before calling the SDK.

4. **`JoystickWidget` (PySide6 `QWidget`)** — circular pad drawn with
   `QPainter`, draggable handle constrained to the pad radius, small
   deadzone near center, snaps back to center on release. Only updates
   a pending value on mouse-move (does not call the SDK directly at
   mouse-move frequency).

5. **`StatusPanel`** — connection state, live zoom slider (calls
   `set_zoom`, and reflects `status_changed` updates unless the user is
   actively dragging it), three buttons for
   cabezal/estándar/movimiento (`AiVerticalTrackType`), and an AI
   on/off toggle. Selecting a tracking mode also enables AI if it was
   off, since choosing a mode implies wanting AI active.

6. **`PresetsPanel`** — list populated via `list_presets()` on connect.
   "Agregar" captures current angle (`aiGetGimbalStateR`) + zoom
   (`get_zoom`), prompts for a name, calls `add_preset`. "Ir" calls
   `goto_preset`. "Borrar" confirms then calls `delete_preset`. All
   three refresh the list afterward.

7. **`MainWindow`** — lays out the above to mirror the "Consola" tab
   layout from OBSBOT Center (joystick where the arrow pad was, zoom +
   AI tracking above it, presets below).

## 6. Data flow

**Startup:** `DeviceManager` registers the device-changed callback,
then calls `list_devices()` once to pick up an already-connected
camera.

**Connect/disconnect:** SDK callback → `DeviceManager` sets/clears the
current `Device`, emits a Qt signal → `MainWindow` enables/disables all
controls; `PresetsPanel` reloads via `list_presets()`.

**Live status (~every 2–3s):** SDK internal thread invokes the C++
callback → bridge converts relevant `CameraStatus.tiny` fields to a
dict → calls the Python callback, which only does
`self.status_changed.emit(dict)` → Qt queues delivery to the main
thread → UI updates the zoom slider position and highlights the active
AI mode, unless the user is currently dragging that control.

**Joystick drag:**
- Press: remember prior AI state, `set_ai_enabled(False)`, start a
  20 Hz `QTimer`.
- Move: widget stores the latest normalized `(x, y)` as a pending
  value only (mouse-move can fire far faster than 20 Hz).
- Timer tick: if the pending value changed, map to `(pitch, pan)` and
  call `set_gimbal_speed`.
- Release: snap handle to center, call `stop_gimbal()` immediately,
  restore prior AI state.

**Zoom slider:** throttled similarly (less time-critical than the
joystick); reflects live status updates except while the user is
dragging it.

**Tracking mode buttons:** click calls `set_tracking_mode` directly
(no throttle needed for a click), and enables AI if it was off.

**Presets:** "Agregar" reads current angle + zoom, prompts for a name,
calls `add_preset`; "Ir" calls `goto_preset`; "Borrar" confirms then
calls `delete_preset`; all refresh the list afterward.

## 7. Error handling

- No device connected (startup or after disconnect): clear
  "sin dispositivo conectado" banner, all controls disabled/greyed —
  never a crash from a null `Device`.
- SDK calls returning `RM_RET_ERR`: bridge raises `ObsbotError`; UI
  catches it and shows non-blocking status text (not a modal dialog
  that would interrupt continuous joystick use).
- Disconnect mid-drag: the controller's timer tick checks the device
  is still connected before calling the SDK; if gone, it stops the
  timer and resets UI state gracefully.
- Exceptions inside the C++-invoked status callback are caught on the
  C++ side and logged to stderr — they must never propagate back into
  the SDK's internal thread and crash it.
- Shutdown: `Devices::close()` must be called on Qt's `aboutToQuit`
  before the Python interpreter starts tearing down, so SDK-internal
  threads stop cleanly and can't call back into a destroyed
  interpreter.
- Multiple cameras connected: out of scope for v1; `DeviceManager`
  takes the first Tiny2-family device it sees and ignores the rest
  (explicit scope decision, not a bug).

## 8. Testing

- **Bridge smoke test**: small script that calls `list_devices()` with
  the camera plugged in, run after each build to confirm the
  compile/link succeeded and discovery works, before touching the GUI.
- **`GimbalController` unit tests (pytest)** against a fake/mock
  `Device` (no real SDK needed): speed-mapping formula for known
  `(x, y)` inputs, throttle only sends on tick, `stop_gimbal` + AI
  restore called on release, AI enable/disable sequencing.
- **`JoystickWidget` tests (pytest-qt)**: simulated mouse
  press/move/release verifying emitted normalized values and deadzone
  behavior, without touching the SDK.
- **Manual hardware checklist** (run by the user against the real
  Tiny2, since this cannot be exercised without physical hardware):
  - Joystick pans/tilts smoothly without jitter or lag.
  - Releasing stops the gimbal immediately.
  - AI tracking correctly re-enables after a drag if it was on before.
  - Zoom slider matches the physical zoom.
  - The three tracking mode buttons switch correctly.
  - Add/go-to/delete preset round-trips correctly.
  - Unplugging/replugging the camera mid-session doesn't crash the app.

## 9. Open assumptions / risks to verify on hardware

- `aiTrgGimbalPresetR` (go-to-preset) is assumed to manage its own
  interaction with AI tracking internally, unlike
  `aiSetGimbalSpeedCtrlR` which explicitly requires disabling AI
  first per the SDK docs. This should be confirmed on real hardware —
  if going to a preset while AI tracking is active doesn't move the
  gimbal, we'll need to also disable AI around `goto_preset`.
- Conservative default max joystick speed (below the SDK's full
  ±90 pitch / ±180 pan range) is a starting guess; the actual value
  should be tuned by feel against the real camera.
