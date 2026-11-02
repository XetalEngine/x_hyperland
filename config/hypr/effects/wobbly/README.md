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

The enable switch is initially off for new installations. Physics preferences
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

The status command reports active lattices, render/physics counters and bell
subscriptions. Once windows settle there is no animation timer running. Reload,
disable, close, workspace changes and unload detach owned transformers. Snapping
modifiers are allowed during a drag without Hyprland ending that drag; other
keyboard and pointer bindings retain normal behavior.

## Verification

```sh
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s config/hypr/effects/wobbly -v
python3 tests/check-wobbly.py /absolute/path/to/xetal-wobbly.so /tmp/new-test-directory
```

Unit checks cover original option defaults/ranges, actual spring forces,
refresh-independent integration, snapping, extreme settings, matching, save
rollback and unsaved-edit guards. The integration check starts a disposable
nested compositor and exercises real window/input/rendering behavior. It never
loads a test binary into the parent session.
