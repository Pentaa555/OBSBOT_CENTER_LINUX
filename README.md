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
