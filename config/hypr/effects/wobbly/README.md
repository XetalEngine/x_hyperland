# Compiz Wobbly Windows

Open **Fusion Settings → Theme → Window effects → Wobbly Windows**. Enable the
effect and apply, then drag or resize a floating window. **Try Wobbly** opens a
sample window with editable text and a live clock. Hold Shift during a drag to
enable magnetic edge resistance, or choose another snapping modifier.

This is a port of the original `compiz-core/plugins/wobbly.c` from XetalCompiz.
`native/compiz.hpp` retains its 4 × 4 spring lattice, 24 springs, 15 ms integration,
bicubic Bézier surface, shiver impulse and magnetic edge resistance. The Hyprland
adapter supplies window geometry and renders the live window through that mesh.
It does not substitute a rigid window animation or a static screenshot. Original
attribution and license are in `NOTICE`; adapter licensing is in `COPYING`.

Rendering follows the monitor's presentation frames. The original 15 ms physics
steps are interpolated for smooth motion on high-refresh displays, while the
grabbed point follows the pointer immediately. Mesh weights and triangle storage
are cached; the color image and blur matte reuse the same uploaded geometry.
Only the window's old and new deformed bounds are damaged, including portions on
neighboring monitors. Once the effect settles it requests no further frames.
The complete decorated window is captured before deformation, so fast dragging
near a display edge cannot cut away pixels that the springs bend back onscreen.
Capture buffers are reused separately for each display scale; rotated outputs
use the same window coordinates for content, corners, borders and blur.
Monitor visibility and transformed-pass blur bounds include the interpolated
mesh. During a monitor crossing, the trailing edge therefore remains drawable
after the undeformed window rectangle has left the old output. This extends only
the compositor's geometric visibility test; its workspace, fullscreen, stacking
and Minimize filters still decide whether the window may be shown. Source capture
coordinates, input geometry and the original spring physics are unchanged.
If a maximized or fullscreen window is behind a crossing float, its remaining
mesh joins the existing foreground window pass on the old output. The compositor
normally restricts that pass to the background window's workspace, so changing
workspace at the seam would otherwise put the tail underneath the background.
Crossing windows keep their order relative to the other foreground windows, are
painted once, and do not change workspace, input geometry or stacking state.
The same ordering applies to a settled float straddling the seam, so releasing
the drag does not make its visible half disappear when the springs stop.
Before each output's render checks, a visible lattice also prevents the
single-fullscreen-window shortcut for that frame. The compositor normally checks
only floats on that fullscreen window's workspace; a crossing window already
belongs to the neighbor's workspace. Without this guard, the shortcut can skip
the trailing mesh even though its bounds are correct. Normal visibility rules
still apply, and the optimization resumes when no visible lattice needs it.

All 14 options from `compiz-core/metadata/wobbly.xml.in` are present. The original
metadata is included as `compiz-options.xml` and checked against the controls:

| Control | Original default |
| --- | --- |
| Snap windows | Shift |
| Invert snapping | Off |
| Shiver on application bell | Off |
| Friction | 3.0 (0.1–10) |
| Spring K | 8.0 (0.1–10) |
| Grid resolution | 8 (1–64) |
| Minimum grid size | 8 (4–128 logical pixels) |
| Map effect | None; Shiver available |
| Focus effect | None; Shiver available |
| Map windows | Splash, DropdownMenu, PopupMenu, Tooltip, Notification, Combo, Dnd, Unknown |
| Focus windows | Empty |
| Grab windows | Empty; matching windows get an extra impulse when grabbed |
| Move windows | Toolbar, Menu, Utility, Dialog, Normal, Unknown |
| Maximize effect | On |

Window matches accept the original type names, `Any`, parentheses, `!`, `&` and
`|`. App-specific matches include `class=kitty`, `title=*Settings*`, `role=...`,
`floating=1`, `xwayland=1`, `state=maximized`, `rgba=1`, `override_redirect=1` and
`xid=0x1234`. Class, title and role use shell wildcards, not regular expressions.
Wayland exposes popups as children of a toplevel rather than independent X11
windows; they do not receive their own spring lattice. XWayland window types are
read from their EWMH atoms. Fullscreen windows, hidden workspaces, session locks
and disabled compositor animations suspend deformation.

New installations enable Wobbly, with friction 3, spring K 3, grid resolution 3,
minimum grid size 8, focus effect Shiver, and both drag modes on. The empty Focus
windows match is preserved, so focus shivering requires selecting windows first.
**System defaults** restores these choices; **Compiz defaults** restores the
original table above while keeping the enable switch. Both require Apply.
The **Help** button documents every supported window type and predicate.

Hotkey drags and normal drags have independent switches. The hotkey label follows
the Hotkeys configuration. Native application title bars and the text-safe
floating-window top grip use the compositor's native movement path, so neither
is limited to the grip helper's polling cadence. The close affordance remains
hidden during either drag. Each visible monitor samples the lattice on its own
presentation callbacks using one shared elapsed-time clock. A window spanning
different refresh rates neither locks to the slower display nor runs its physics
twice as fast. A monitor transfer retains the clock and spring state instead of
ending the wobble. Physics preferences
are personal settings: applying a built-in skin preserves them, while custom
theme snapshots can save and restore them. Disabling detaches the mesh at once.
The helper belongs to the Hyprland session and does not install a service or alter
KDE/Plasma. System-bell shivering uses Hyprland's event socket for Wayland and an
XKB bell subscription for XWayland; it does not alter audio settings.

## Build and diagnostics

The adapter is pinned to the repository's x86-64 Hyprland 0.56.2 build
(`efb50993780079460b0cbed1363e2166a2de1d9f`). A different compositor ABI requires
an adapter update. Dependencies include g++, pkg-config, matching Hyprland
headers, json-c, libei, GLESv2 and xcb-xkb development files. Setup builds this
adapter alongside Cube, Burn and Minimize. Each native build has a unique path
so a loaded library is never overwritten.

```sh
python3 ~/.config/hypr/effects/wobbly/build.py
hyprctl xetal-wobbly
hyprctl dispatch xetalwobbly:shiver
```

The status command reports active lattices, render/physics counters, mesh builds,
requested damage area as a fraction of the affected outputs, current source and
deformed render bounds, per-output `crossing_frames` (foreground pass repairs)
and `composited_frames` (fullscreen shortcuts avoided for a visible crossing or
lattice), and bell
subscriptions. There is no independent animation timer. Reload,
disable, close, workspace changes and unload detach owned transformers. Snapping
modifiers are allowed during a drag without Hyprland ending that drag; other
keyboard and pointer bindings retain normal behavior.

## Verification

```sh
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s config/hypr/effects/wobbly -v
python3 tests/check-wobbly.py /absolute/path/to/xetal-wobbly.so /tmp/new-test-directory
```

Unit checks cover original option defaults/ranges, actual spring forces,
refresh-independent integration, interpolated rendering, cached mesh accuracy,
snapping, extreme settings, matching, save
rollback and unsaved-edit guards. The integration check starts a disposable
nested compositor and exercises real window/input/rendering behavior. It never
loads a test binary into the parent session. Pixel checks cover fast drags at
all four edges and a window spanning a rotated, fractionally scaled display.
Native regressions also cover the final trailing strip after the source rectangle
has completely departed all four output edges, including translated and negative
monitor origins, and verify that rendering stops when the mesh has left. The
nested check captures that last strip during transfers in both directions.
The pass-order unit test reproduces the old background occlusion and verifies
both maximized and fullscreen backgrounds, foreground stack order, single draws,
hidden/minimized exclusions and cleanup. The nested check also repeats both
seams of a three-monitor layout (1920×1080, 2560×1440, 2560×1440), with ordinary,
maximized and fullscreen backgrounds. A solid red background fixture makes
missing blue window pixels detectable. It checks that solitary rendering resumes
after the mesh leaves.
