# Desktop Cube & 3D Windows

Open **Control desk → Theme → Window effects → Desktop Cube + 3D**.
Hold **Ctrl + Alt + left mouse** and drag to rotate the cube on that monitor.
Release the button to select the nearest face. **Escape** or a right click
cancels. The pointer stays where the drag started.

Each monitor has its own workspaces and wallpaper. Other monitors' workspaces
are never borrowed. There are at least four faces; empty faces create a workspace
only when selected. More than four workspaces form a prism with additional faces,
as in Compiz. Named workspaces are included; special/scratch workspaces are not.

## Controls

Changes are drafts until **Apply Cube**. **Discard** returns to saved settings.
**Defaults** resets appearance while preserving the enable switch. **Preview
Cube** opens a tilted preview; Escape or a click closes it without switching.

| Control | Purpose |
| --- | --- |
| Enable Desktop Cube | On/off, saved for future logins |
| Wall opacity | 0–100%; windows stay readable above transparent walls |
| Cube size | Zoom out to leave room for rotation and raised windows |
| Mouse sensitivity | Rotation per unit of pointer movement |
| Transition | Opening/settling duration; the global Animations switch also applies |
| Cube edge color | RGBA picker for the thin outlines |
| Ceiling / floor pictures | Independent artwork for the two caps |
| Ceiling / floor color | RGBA fallback; alpha also controls cap artwork opacity |
| Background | Gradient, fitted picture, or panoramic sky |
| Move sky with cube rotation | Pan a picture or rotate a panorama as you turn the cube |
| Sky drift | Independent, gentle picture panning or continuous panorama rotation; zero stops drift |
| Gradient top / bottom | Background colors when no picture is selected |
| Raise windows above the cube | Enable/disable 3D window layers |
| Minimum cube size | Compiz's lower limit on shrinking walls for window layers |
| Window separation | Compiz's spacing between successive window layers |
| Window thickness / side color | Depth and RGBA color of extruded window edges |

A 2:1 equirectangular panorama works best for the sky. Choose **Background
picture** to fit an ordinary image without wrapping it. Motion adds a small zoom
and pans within the picture so no empty or stretched edges appear. Turn off
**Move sky with cube rotation** and set **Sky drift** to zero for a completely
static picture or panorama. Motion controls are inactive for a plain gradient.
Pictures are copied into
`images/`; originals remain untouched. GIF imports use the first frame; moving
sky means picture panning or panorama rotation. Images are decoded outside the compositor, limited
to 4096×2048, and cached as bounded RGBA data. The cache is rebuilt locally and
excluded from the repository and installer payload.

The gesture appears in **Hotkeys → Workspaces** and reset defaults. The plugin
reads the actual enabled binding on each press. Modifiers and mouse button can
be changed there; disabling/removing the binding disables the gesture. Only this
Ctrl+Alt mouse gesture gets an exception to keyboard shortcut protection.

## Integration and compatibility

This native Hyprland adaptation uses Compiz cube geometry and 3D window spacing.
Actual application buffers are drawn on separate layers with perspective and
depth testing. Other monitors render normally. Snapshots refresh during rotation,
with a bounded texture budget and one window refreshed per tick; large window
counts reduce each preview's refresh rate. Textures stay in GPU memory and are
released when the gesture ends. Capturing never switches a workspace for preview.

Monitor removal, output mode/scale/position changes, an outside workspace change,
session locking, disabling the effect, and plugin unload cancel the scene.
Pointer constraints, input capture, and an active special workspace prevent a
gesture. Rendering/input hooks are removed on unload. Burn remains independent.

The adapter is tested with **Hyprland 0.56.2**, commit
`efb50993780079460b0cbed1363e2166a2de1d9f`, on x86-64 with its OpenGL renderer.
Build requirements: C++23, matching Hyprland development headers, pkg-config,
GLESv2, json-c and libei development files (`hyprland`, `json-c`,
`libeis-1.0` pkg-config modules). On Arch, these are provided by Hyprland,
json-c, libei and libglvnd packages. Other distributions can require separate
development packages. The installer attempts the build; the session loader can
build on first use. Complete sources and controls are included; binaries are not.

The tested-commit and runtime ABI checks must both pass. A different compositor
version leaves ordinary workspace switching available and reports the optional
effect's error in the session's `cube.log`. No replacement plugin is downloaded.
Settings apply atomically, with external-edit checks and rollback. No shared
KDE/Plasma settings, global environment or persistent services change.

The native settings/status reader uses json-c so replacing or unloading a Cube
build cannot leave GLib JSON type registrations pointing into an unloaded library.

`hyprctl xetal-cube` reports enable state, scene state, workspace IDs, the selected
face and lifecycle counters. Run automated checks from the repository:

```sh
QT_QPA_PLATFORM=offscreen python3 -B -m unittest discover -s config/hypr/effects/cube -v
```

Native changes must also be checked in a disposable nested Hyprland, including
real press/motion/release input, repeated gestures, multiple monitors, custom
images, scaled/rotated outputs, and replacement with a different plugin build,
before loading on a working desktop. The pixel/replacement probe is
`tests/check-cube-sky.py` at the repository root; its optional third argument is
the previous plugin binary for checking an upgrade.

## Source and license

The native adaptation and tests are **GPL-2.0-or-later**; see [COPYING](COPYING).
Python controls/build helpers retain the repository's MIT license. Cube geometry:
**David Reveman / Novell**; Compiz sky support: **Mirco Müller**. 3D window equations:
**Roi Cohen**, modified by **Dennis Kasprzyk, Danny Baumann, Robert Carr, Diogo
Ferreira and Kevin Lange**. Original notices are in [NOTICE](NOTICE). Hyprland
integration, input, shaders and controls: XetalEngine, 2026.

Reference SHA-256 hashes from the supplied `XetalCompiz_old` tree:

```
eb15d7e18e97d13b544266a4ea0254c0d7e80899cd4a3521fcd79080f7873c26  compiz-core/plugins/cube.c
753d221a813c56688505b2be53911268adc476598e014b408c92ab6a056e4488  compiz-plugins-extra/src/3d/3d.c
```
