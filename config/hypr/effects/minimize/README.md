# Minimize: animated docks and Fireball stacks

Press **Super+Z** or use an application's minimize button to send its window
into a burning slot on that monitor. Click its Fireball to restore the window.
The animated dock grows and shrinks with its windows, magnifies hovered icons,
and slides out of view after an adjustable delay. It appears when the pointer
approaches its edge. By default, it sits opposite that monitor's Waybar.
Apps keep running, and grouped windows travel together. The taskbar groups minimized
apps under **M3**, for example, followed by their app icons: “M” means minimized,
and “3” is their original workspace. Cube uses its local 1–4 face number.
Clicking an app icon restores that specific app, focuses it and raises it above
the other windows using the same ordering operation as Super+F.

The center of a Fireball shows the application's icon when one is
available. Apps without an identifiable icon retain the small window preview.
The shrinking/restoring window blends into/out of the icon during travel.
`icons.py` resolves desktop IDs, executable names and StartupWMClass through
the installed app/icon inventory outside the compositor. The session controller
owns this helper; its bounded PNG cache lives inside the current Hyprland
instance's `xetal-minimize-icons/` runtime directory. It follows new windows,
installed apps and the light/dark icon theme. No personal icon cache is shipped.

**Super+Ctrl+Z** hides or shows all minimized effects for this session. Apps
stay minimized and running; their taskbar icons can still restore them. Hidden
effects do not draw or intercept clicks or scrolling. This works for the dock
and classic stack, including windows minimized while the effects are hidden.

**Fusion Settings → Theme → Window effects → Minimize** offers:

- **Animated dock** or **Classic edge stack**. The classic stack keeps its
  Left/Right edge and Bottom to top/Top to bottom order.
- Dock position: **Opposite Waybar**, Bottom, Top, Left or Right. Each output
  has its own dock. Side proximity works across shared monitor boundaries;
  the pointer must be inside that output to reveal or interact with its dock.
- **Dock design**: Follow desktop theme, or choose any theme's design independently.
- **Automatically hide after use**, **Hide after** (200–10,000 ms),
  **Transition and resize time** (100–1,000 ms), **Edge proximity** (2–64 logical pixels)
  and **Hover zoom** (100–150%). Disabling auto-hide keeps a populated dock visible.
- **Hide animation**: **Slide away** (the default) or **Burn away**. Burning
  consumes the dock toward its chosen edge. Its optional **Fire indicator**
  keeps a low strip of embers as wide as the dock while windows remain minimized.
  The indicator disappears when empty, respects all four edges and becomes
  static when compositor animations are disabled. **Preview hiding** lets you
  try both modes in the settings page.
- Window travel time, effect size, flame animation speed and color.

New windows open slots as their previews shrink into the Fireballs. Closing or
restoring a window collapses its slot. Slots reduce in size as space runs out;
scroll over a slot to page when the dock fills up. Empty docks disappear.
An empty dock starts collapsing immediately after the last window is restored
or closed, even with auto-hide turned off or the pointer over its old slot.
Position changes move existing effects and respect reserved panel space.
**Follow the active theme accent**
is on by default, or you can choose a custom color. The effect starts enabled. Turning it off or
choosing **Restore all windows** returns minimized apps to their workspaces.
Closing a window still uses the separate Burn effect.

- **Fireball** uses the original Compiz particle sprite and motion, adapted to
  continuously emit soft rising flames while the window is minimized.
- **Splat is parked**: its selector and renderer are commented out. Old Splat
  preferences use Fireball while preserving their shape/material settings.
- Theme changes recolor existing minimized windows immediately, including
  colors-only presets. Custom colors and effect settings stay intact. Custom
  theme presets can also save the Minimize settings.

Dock designs have distinct silhouettes and details: Raw's circuit rail,
Modern's glass capsule, BreakPoint's reactor console, Binary Knife's cut crystal,
Tidal Glass's waves, Porcelain Ink's ink tray, Obsidian Forge's metal and rivets,
Candy Cloud's pearl pillows, Shadow Edge's smoked steel, Hollow Grove's vines,
The Gilded Hollow's brass caps, traveling gleam and lantern-cut diamond,
and HyperFusion Blue's Blue Vault: silver end caps, sapphire edge lights and
individual glass chambers around each minimized window.
Their materials use the profile's palette, including light themes. No shared
KDE/Qt color files are changed.

The same **Dock design** selector is also in **Theme → Mix & match**, beside
Waybar style. Its **Open dock settings** button opens Minimize for timing,
position and size. Theme presets have a separate **Dock design** component,
so you can take one theme's dock without changing your desktop or other effects.
Both pages read and update the same saved preference, including conflict checks
and rollback if the live renderer rejects a change.

Older settings files retain **Classic edge stack** when upgraded. Existing size,
timing, color and enabled preferences are preserved. Fresh installations default
to the animated dock. Select Animated dock and Apply to opt in on an older profile.

The same native handler fixes **Super+F / Super+B** ordering for floating windows
above a maximized/fullscreen window and remembers the order across workspace
switches. That part remains active when the minimize effect is disabled.

It also keeps native maximize/restore requests and reported window state in
sync for Wayland and XWayland. Chrome's title-bar double-click and native middle
button can repeatedly maximize and restore without minimizing to reset them.
Explicit maximize/unmaximize requests are idempotent. On this pinned compositor,
the adapter also crops client decoration padding to the xdg window geometry so
restored native buttons remain fully visible. Pointer hit testing and held-button
motion use the same geometry origin; Chrome's tab X no longer requires clicking
below the visible button. Client popups and XWayland retain their existing paths.
These corrections remain active when the minimize animation is disabled.

## Compatibility and recovery

Minimizing is enabled on fresh installations. Native plugins wait for a ready
compositor and monitor at login. Cold-start builds and loads run one at a time;
a failed attempt is retried with increasing delays instead of staying inactive
for the entire login. Retries stop with the compositor and preserve all settings.

The dock icon helper uses a verified Python executable, including a system
fallback if the login environment leaves `sys.executable` empty. The native
minimizer starts first; a failed icon helper is reported without disabling it.

Run **`fusion-check`** in any terminal in the Fusion session to check every native
plugin. Green checks mean loaded/responding or intentionally disabled; red crosses
identify missing plugins, failed status requests, or a mismatch with saved settings.
The report includes the startup error and log path when available. It is read-only;
`fusion-check --json` produces the same results for scripts. Foreground installation
also installs the command in `/usr/local/bin`, so Bash, Zsh and Fish can all use it.

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
- An adapter upgrade unloads the old, recorded build before loading a distinct
  content-addressed binary. Existing minimized windows are restored once during
  this upgrade. A failed Apply restores the saved configuration and prior build.
  Internal symbols stay private to each build so an earlier library cannot
  supply stale settings or dock designs after a live upgrade.
- Effects do not render or receive input over the session lock or while input
  is captured. With compositor animations disabled, travel and dock transitions are immediate.

For recovery from a terminal in the same session:

```sh
hyprctl dispatch xetalminimize:restoreall
```

`hyprctl xetal-minimize` reports active records and their IDs. Previews are
also identified by an `icon` flag in each window record. Window snapshots are
bounded to 1024 pixels on their longest side. Visible effects update at up to 60 FPS and damage only their small screen
region. Fire uses a fixed 30 ms physics step and a bounded 384-particle pool
per window; offscreen effects skip simulation and rendering. There is no frame
timer after an empty/hidden dock finishes its transition (except an enabled
fire indicator, limited to 30 FPS), or when all effects
are hidden and travel has finished. Edge motion wakes a hidden dock without
creating an input-blocking surface. `hyprctl dispatch xetalminimize:togglevisibility` also toggles
visibility, and `hyprctl xetal-minimize` reports the session's `hidden` state.

## Development checks

```sh
python3 config/hypr/effects/minimize/build.py
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s config/hypr/effects/minimize -v
python3 tests/check-minimize.py /absolute/path/to/xetal-minimize.so /tmp/new-minimize-test
```

The integration check uses a disposable nested compositor and test apps,
including a maximized viewer stand-in. It never starts or alters a VM.
Add `--upgrade-from /absolute/path/to/previous.so` to verify window recovery and
new dock designs after replacing an older build in the same compositor session.
Add `--dock-only` for the dock scenarios. They produce a gallery of all designs and check live
palette changes, custom colors, rejected reloads, growth/collapse, hover zoom,
auto-hide, burn-away, indicator cleanup, all four edges, real top/bottom Waybars,
multiple outputs, overflow, reduced motion and rendering sleep.

## Attribution

Code is licensed under GPL-2.0-or-later; see `COPYING`. Fire reuses
[`../burn/native/engine.hpp`](../burn/native/engine.hpp), ported from Compiz
animationaddon by Erkin Bahceci and Dennis Kasprzyk (2006), and Dennis Kasprzyk's
original [`fire_texture.hpp`](../burn/native/fire_texture.hpp) particle sprite.
The persistent emitter, dock materials, parked Splat shader and Hyprland integration are by XetalEngine.
