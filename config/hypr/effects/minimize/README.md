# Fireball Minimize

Use an application's minimize button to send its window to a burning fireball
on the left edge of that monitor. Click the fireball to restore the window.
Windows form one column; scroll over it when the column fills up. Apps keep
running, and grouped windows travel together.

**Fusion Settings → Theme → Window effects → Minimize** controls the effect,
travel time and fireball size. The effect starts enabled. Turning it off or
choosing **Restore all windows** returns minimized apps to their workspaces.
Closing a window still uses the separate Burn effect.

The same native handler fixes **Super+F / Super+B** ordering for floating windows
above a maximized/fullscreen window and remembers the order across workspace
switches. That part remains active when the minimize effect is disabled.

## Compatibility and recovery

- Hyprland **0.56.2**, commit `efb50993780079460b0cbed1363e2166a2de1d9f`,
  x86-64 and OpenGL. Other compositor ABIs are rejected before loading.
- Build dependencies: C++23, matching Hyprland headers, `pkg-config`,
  `libeis-1.0` development headers and GLESv2. Setup builds the adapter; the
  session owns its loader. No shared desktop services are changed.
- Handles Wayland xdg-shell, XWayland and foreign-toplevel minimize requests.
  Apps without a minimize button can use a custom hotkey calling
  `xetalminimize:minimize`.
- Restore preserves workspace, floating geometry, maximized/fullscreen and
  pinned state. Plugin unload and monitor disconnect restore apps first.
- Effects do not render or receive input over the session lock or while input
  is captured. With compositor animations disabled, travel is immediate.

For recovery from a terminal in the same session:

```sh
hyprctl dispatch xetalminimize:restoreall
```

`hyprctl xetal-minimize` reports active records and their IDs. Previews are
bounded to 1024 pixels on their longest side. Settled fireballs update at 30 FPS
and damage only their small screen region; there is no frame timer when idle.

## Development checks

```sh
python3 config/hypr/effects/minimize/build.py
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s config/hypr/effects/minimize -v
python3 tests/check-minimize.py /absolute/path/to/xetal-minimize.so /tmp/new-minimize-test
```

The integration check uses a disposable nested compositor and test apps,
including a maximized viewer stand-in. It never starts or alters a VM.
Code is licensed under GPL-2.0-or-later; see `COPYING`.
