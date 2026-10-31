# Minimize: Fireball & Splat

Press **Super+Z** or use an application's minimize button to send its window
to the bottom-left of that monitor, filling upward by default. Click its effect to restore the window.
Windows form one column; scroll over it when the column fills up. Apps keep
running, and grouped windows travel together. The taskbar groups minimized
apps under **M3**, for example, followed by their app icons: “M” means minimized,
and “3” is their original workspace. Cube uses its local 1–4 face number.
Clicking an app icon restores that specific app.

**Fusion Settings → Theme → Window effects → Minimize** controls the effect,
screen edge (Left/Right), stack direction (Bottom to top/Top to bottom),
travel time, size, animation speed and color. Placement changes move existing
effects immediately and respect the monitor’s reserved panel space. **Follow the active theme accent**
is on by default, or you can choose a custom color. The effect starts enabled. Turning it off or
choosing **Restore all windows** returns minimized apps to their workspaces.
Closing a window still uses the separate Burn effect.

- **Fireball** uses the original Compiz particle sprite and motion, adapted to
  continuously emit soft rising flames while the window is minimized.
- **Splat** has a glossy, moving surface with swelling bubbles, bursts and
  ripples. Choose Bloom, Starburst, Spill, Tendrils, Wide splash, Coral, Webbed
  splash or Heavy droplets, or
  choose **Random per window**. Fixed silhouettes are consistent across windows;
  random shapes stay with each window until it is restored. Boiling intensity
  controls the bubbles independently of animation speed.
- Splat has three surfaces: **Living slime**, **Alien membrane** (dark pockets,
  bright veins and wet ridges), and **Glossy paint** (smooth liquid color and
  broad highlights). All three can follow the theme or use a custom color.
- Theme changes recolor existing minimized windows immediately, including
  colors-only presets. Custom colors and effect settings stay intact. Custom
  theme presets can also save the Minimize settings.

The original four-field settings file is upgraded when you next save. Existing
size, timing and enabled preferences are preserved.

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
  Apps without a minimize button can use **Super+Z**. A custom hotkey can run
  `hyprctl dispatch xetalminimize:minimize` with the `exec` dispatcher.
- Restore preserves workspace, floating geometry, maximized/fullscreen and
  pinned state. Plugin unload and monitor disconnect restore apps first.
- Effects do not render or receive input over the session lock or while input
  is captured. With compositor animations disabled, travel is immediate.

For recovery from a terminal in the same session:

```sh
hyprctl dispatch xetalminimize:restoreall
```

`hyprctl xetal-minimize` reports active records and their IDs. Previews are
bounded to 1024 pixels on their longest side. Visible effects update at up to 60 FPS and damage only their small screen
region. Fire uses a fixed 30 ms physics step and a bounded 384-particle pool
per window; offscreen effects skip simulation and rendering. There is no frame
timer when no windows are minimized.

## Development checks

```sh
python3 config/hypr/effects/minimize/build.py
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s config/hypr/effects/minimize -v
python3 tests/check-minimize.py /absolute/path/to/xetal-minimize.so /tmp/new-minimize-test
```

The integration check uses a disposable nested compositor and test apps,
including a maximized viewer stand-in. It never starts or alters a VM.
The integration check also produces a color/shape gallery and checks live
palette changes, custom colors and rejected settings reloads.

## Attribution

Code is licensed under GPL-2.0-or-later; see `COPYING`. Fire reuses
[`../burn/native/engine.hpp`](../burn/native/engine.hpp), ported from Compiz
animationaddon by Erkin Bahceci and Dennis Kasprzyk (2006), and Dennis Kasprzyk's
original [`fire_texture.hpp`](../burn/native/fire_texture.hpp) particle sprite.
The persistent emitter, Splat shader and Hyprland integration are by XetalEngine.
